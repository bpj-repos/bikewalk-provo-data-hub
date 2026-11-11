"""Enrich managed incidents and export the approved public concern details."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from .common_structure import read_contract
from .derived_incidents import derive, read_rules, result, RULES
from .field_inventory import read_catalog
from .incident_conversions import temporal
from .incident_updates import flatten
from .normalize_incidents import normalize_row
from .util import read_json, sha256_file, write_json

FIELDS = {
    'injuries': ('Injuries to people walking or biking', 'at_injury_summary'),
    'driverCircumstances': ('Recorded driver circumstances', 'reported_driver_circumstances'),
    'reportedFactors': ('Other reported crash factors', 'reported_behavior_flags'),
    'lighting': ('Lighting conditions', 'lighting_group'),
    'time': ('Time of day and weekday', 'time'),
    'conditions': ('Weather and road surface', None),
    'ageGroups': ('Age groups', 'at_age_groups'),
}
SOURCES = {'udot-crashes': 'UDOT crash data', 'utah-crash-portal': 'Utah Crash Portal',
           'provo-police-incidents': 'Provo Police'}
LABELS = {
    'failure-to-yield': 'Failure to yield', 'speeding': 'Speed-related',
    'too-fast-for-conditions': 'Too fast for conditions', 'dui': 'DUI classification',
    'disregarded-control': 'Disregarded traffic control', 'alcohol-confirmed': 'Alcohol confirmed',
    'alcohol-suspected': 'Alcohol suspected', 'drugs-confirmed': 'Drugs confirmed',
    'drugs-suspected': 'Drugs suspected', 'dark-lighted': 'Dark, roadway lighted',
    'dark-unlighted': 'Dark, roadway not lighted', 'dark-lighting-unknown': 'Dark, lighting unknown',
    'dawn-dusk': 'Dawn or dusk',
}


def normalized_rows(observation, catalog, contract):
    """Use exact related rows from this source version, never neighboring incidents."""
    source = observation['sourceKey']
    meta = observation['metadata']
    if source == 'utah-crash-portal':
        tables = [('portal.crashes', [meta['crash']]),
                  *[('portal.' + k, meta.get(k, [])) for k in ('persons', 'vehicles', 'rollups')]]
    elif source == 'udot-crashes':
        tables = [('udot.arcgis', [meta])]
    elif source == 'provo-police-incidents':
        # This delivery supplies report time and mode, not crash time or injuries.
        t = temporal(observation['observedAt'])
        return [{'observationId': observation['id'], 'source': source,
                 'snapshotId': observation.get('sourceSnapshotId', ''),
                 'sourceRecordId': observation['sourceRecordId'], 'table': 'police.xlsx',
                 'entity': 'police_report', 'modes': [observation['mode']] if observation.get('mode') else [],
                 'values': {'time.reported_at': {'value': t, 'state': 'reported', 'columns': ['Date of Report']}}}]
    else:
        raise ValueError('Unsupported enrichment source: ' + source)
    rows = []
    for table, originals in tables:
        for index, original in enumerate(originals):
            values, errors = normalize_row(table, original, catalog, contract)
            if errors:
                raise ValueError('Invalid enrichment input: ' + observation['id'] + ' ' +
                                 ', '.join(e['concept'] + ':' + e['error'] for e in errors))
            person = values.get('person.type', {}).get('value') or {}
            modes = list(observation.get('modes', [])) if table.endswith('crashes') or table == 'udot.arcgis' else []
            if person.get('code') in {'3', '4', '5'}:
                modes = [{'3': 'pedestrian', '4': 'bicycle', '5': 'other-conveyance'}[person['code']]]
            rows.append({'observationId': f"{observation['id']}:{table}:{index}", 'source': source,
                         'snapshotId': observation.get('sourceSnapshotId', observation['id']),
                         'sourceRecordId': observation['sourceRecordId'], 'table': table,
                         'entity': catalog['tables'][table]['entity'], 'values': values, 'modes': modes})
    return rows


def enrich_collection(collection):
    catalog = read_catalog()
    contract = read_contract(catalog=catalog)
    rules = read_rules()
    from .event_context import EventMatcher
    events = EventMatcher()
    counts = defaultdict(Counter)
    for group in collection['records']:
        enriched = []
        for observation in sorted(flatten({'records': [group]}).values(), key=lambda o: o['id']):
            rows = normalized_rows(observation, catalog, contract)
            output = derive(rows[0], rows, rules)
            if output['issues']:
                raise ValueError('Unreviewed enrichment mapping: ' + observation['id'] + ' ' + ', '.join(output['issues']))
            fields = {key: output['derived'][name] for key, (_, name) in FIELDS.items() if name}
            conditions = {key: output['derived'][key] for key in ['weather', 'road_surface']}
            known = sum(v['availability'] == 'complete' for v in conditions.values())
            fields.update(events.observation(observation, rows))
            fields['conditions'] = result(conditions, 'complete' if known == 2 else 'partial' if known else 'unavailable', [])
            t = output['derived']['time']['value']
            year = str(t['year']) if t else 'unknown'
            for key, field in fields.items():
                if 'availability' not in field:
                    continue
                counts[(observation['sourceKey'], year, key)][field['availability']] += 1
            enriched.append({'observationId': observation['id'], 'source': observation['sourceKey'],
                             'sourceRecordId': observation['sourceRecordId'], 'fields': fields})
        group['eventContext'] = events.group(enriched)
        group['enrichment'] = {'schemaVersion': 1, 'rulesVersion': rules['version'], 'rulesSha256': sha256_file(RULES), 'observations': enriched}
    return {'schemaVersion': 1, 'incidentGroups': len(collection['records']),
            'sourceObservations': len(flatten(collection)),
            'eventContextInputs': events.inputs,
            'eventContextCounts': {settings['field']: dict(Counter(g['eventContext']['fields'][settings['field']]['value'] for g in collection['records'])) for settings in events.series.values()},
            'coverage': [{'source': s, 'year': y, 'field': f, 'availability': dict(c)}
                         for (s, y, f), c in sorted(counts.items())]}


def label(value):
    return LABELS.get(value, value.replace('-', ' ').capitalize())


def public_text(key, cell, rules):
    value = cell['value']
    if cell['availability'] == 'unavailable' or value is None:
        return None
    if key == 'injuries':
        return '; '.join(mode + ': ' + ', '.join(f'{injury} ({count})' for injury, count in sorted(counts.items()))
                         for mode, counts in sorted(value['byMode'].items())) or None
    if key == 'ageGroups':
        return '; '.join(mode + ': ' + ', '.join(f"{rules['ageGroups'][band]} ({count})" for band, count in sorted(counts.items()))
                         for mode, counts in sorted(value.items())) or None
    if key in {'driverCircumstances', 'reportedFactors'}:
        return '; '.join(label(v) for v in value) if value else 'None reported' if cell['availability'] == 'complete' else None
    if key == 'lighting':
        return label(value)
    if key == 'time':
        if value['basis'] != 'occurrence':
            return None
        text = value['weekday']
        if value['hour'] is not None:
            # The normalized original preserves clock precision and timezone uncertainty.
            text += ', ' + datetime.strptime(value['clock'][:5], '%H:%M').strftime('%I:%M %p').lstrip('0')
            if value['timezoneStatus'] == 'unspecified-local-clock':
                text += ' (source time, time zone unspecified)'
            else:
                text += ' (Mountain Time)'
        else:
            text += ' (time not recorded)'
        return text
    if key == 'conditions':
        parts = []
        for name, title in [('weather', 'Weather'), ('road_surface', 'Road surface')]:
            v = value[name]
            category = v['value']
            parts.append(title + ': ' + (category['label'] if v['availability'] == 'complete' and category and category.get('label') else 'not recorded'))
        return '; '.join(parts)
    raise ValueError('Unknown public detail field')


def public_details(group, release_id):
    enrichment = group.get('enrichment')
    rules = read_rules()
    if not enrichment or enrichment['schemaVersion'] != 1 or enrichment['rulesVersion'] != rules['version'] or enrichment['rulesSha256'] != sha256_file(RULES):
        raise ValueError('Missing or unsupported enrichment')
    fields = []
    for key, (title, _) in FIELDS.items():
        values = {}
        statuses = []
        for observation in enrichment['observations']:
            cell = observation['fields'][key]
            text = public_text(key, cell, rules)
            if text is not None:
                values.setdefault(text, set()).add(SOURCES[observation['source']])
                statuses.append(cell['availability'])
        availability = 'conflicting' if len(values) > 1 or 'conflicting' in statuses else 'unavailable' if not values else 'partial' if 'partial' in statuses or 'conflicting' in statuses else 'complete'
        fields.append({'key': key, 'label': title, 'availability': availability,
                       'values': [{'text': text, 'sources': sorted(sources)} for text, sources in sorted(values.items())]})
    return {'schemaVersion': 1, 'releaseId': release_id, 'rulesVersion': rules['version'], 'fields': fields}


def export_release(directory, manifest_sha256):
    if sha256_file(directory / 'manifest.json') != manifest_sha256:
        raise ValueError('Manifest checksum mismatch')
    manifest = read_json(directory / 'manifest.json')
    path = directory / 'collection.json'
    if sha256_file(path) != manifest['files']['collection.json']:
        raise ValueError('Collection checksum mismatch')
    collection = read_json(path)
    if collection['snapshotId'] != manifest['releaseId']:
        raise ValueError('Release identity mismatch')
    crashes = {}; ambiguous = set()
    for group in collection['records']:
        ids = {o['sourceRecordId'] for o in flatten({'records': [group]}).values()
               if o['sourceKey'] in {'udot-crashes', 'utah-crash-portal'}}
        for identifier in ids:
            if not identifier.isascii() or not identifier.isdecimal():
                raise ValueError('Invalid state crash ID: ' + identifier)
            if identifier in crashes or identifier in ambiguous:
                crashes.pop(identifier, None); ambiguous.add(identifier); continue
            crashes[identifier] = public_details(group, collection['snapshotId'])
    return {'schemaVersion': 1, 'releaseId': collection['snapshotId'],
            'collectionSha256': manifest['files']['collection.json'], 'manifestSha256': manifest_sha256, 'ambiguousCrashIds': sorted(ambiguous), 'crashes': dict(sorted(crashes.items()))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, required=True, help='Pinned managed release directory')
    parser.add_argument('--manifest-sha256', required=True, help='Pinned manifest checksum from the active pointer')
    parser.add_argument('--output', type=Path, required=True, help='New public-details JSON file')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output must be a new file')
    data = export_release(args.release, args.manifest_sha256)
    write_json(args.output, data)
    print(f"Exported {len(data['crashes'])} state crash IDs from {data['releaseId']}")


if __name__ == '__main__':
    main()
