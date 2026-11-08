"""Review police-to-portal candidates within one calendar month; never merge or publish."""
from __future__ import annotations

import argparse
import calendar
import csv
import json
import math
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

from pyproj import Geod

from .config import DEFAULT_DATA_ROOT, DEFAULT_PRIVATE_DATA_ROOT
from .field_inventory import REPO, read_catalog, source_tables
from .incident_conversions import temporal
from .normalize_incidents import selected_indices
from .util import read_json, sha256_file, write_json


def month_boundary(day, delta):
    month = day.year * 12 + day.month - 1 + delta
    year, month = divmod(month, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def road_tokens(value):
    aliases = {'NORTH': 'N', 'SOUTH': 'S', 'EAST': 'E', 'WEST': 'W'}
    ignored = {'ST', 'STREET', 'RD', 'ROAD', 'AVE', 'AV', 'AVENUE', 'BLVD', 'BOULEVARD',
               'DR', 'DRIVE', 'LN', 'LANE', 'PKWY', 'PARKWAY', 'AT', 'AND'}
    return {aliases.get(t, t) for t in re.findall(r'[A-Z]+|\d+', (value or '').upper()) if t not in ignored}


def point(value):
    if value is None:
        return None
    if len(value) != 2 or any(isinstance(v, bool) or not math.isfinite(float(v)) for v in value):
        raise ValueError('Invalid source coordinates')
    lng, lat = map(float, value)
    if not -180 <= lng <= 180 or not -90 <= lat <= 90:
        raise ValueError('Out-of-range source coordinates')
    return lng, lat


def portal_rows(tables):
    active = set(selected_indices(tables)['portal.crashes'])
    people, modes = defaultdict(list), defaultdict(set)
    for name in ('portal.crashes', 'portal.rollups'):
        for row in tables[name]['rows']:
            identifier = str(row['Crash_ID'])
            for field, mode in [('cyclist_involved', 'bicycle'), ('pedestrian_involved', 'pedestrian')]:
                if row.get(field) == 'Y':
                    modes[identifier].add(mode)
    for row in tables['portal.persons']['rows']:
        identifier = str(row['Crash_ID'])
        people[identifier].append({'type': row.get('personType'), 'typeLabel': row.get('personType_label'),
                                   'age': row.get('ageCalculated'), 'injury': row.get('injuryLevel_label')})
        kind = {'3': 'pedestrian', '4': 'bicycle', '5': 'other-conveyance'}.get(str(row.get('personType')))
        if kind:
            modes[identifier].add(kind)
    result, seen = [], set()
    for i, row in enumerate(tables['portal.crashes']['rows']):
        identifier = str(row['Crash_ID'])
        if not identifier.isdecimal() or identifier in seen:
            raise ValueError('Missing/duplicate portal crash ID')
        seen.add(identifier)
        coords = None if row['longitude'] is None or row['latitude'] is None else point([row['longitude'], row['latitude']])
        result.append({'id': identifier, 'date': temporal(row['crashDateandTime'])['date'],
                       'sourceRow': i + 2, 'road': row['roadName'], 'coordinates': coords,
                       'modes': sorted(modes[identifier]), 'activeTransportationSelected': i in active,
                       'severity': row['crashSeverity_label'], 'agency': row['officer_department'],
                       'people': people[identifier]})
    return result


def mode_relation(mode, modes):
    if mode in {'bicycle', 'electric-bicycle'}:
        return 'compatible' if 'bicycle' in modes else 'mode-mismatch-or-missing'
    if mode == 'pedestrian-and-scooter':
        return 'broadly-compatible' if 'pedestrian' in modes else 'mode-mismatch-or-missing'
    return 'broadly-compatible' if set(modes) & {'pedestrian', 'other-conveyance'} else 'mode-mismatch-or-missing'


def search(police, crashes, radius_metres):
    if not math.isfinite(radius_metres) or radius_metres <= 0:
        raise ValueError('Radius must be finite and positive')
    if len({r['id'] for r in police}) != len(police) or len({r['id'] for r in crashes}) != len(crashes):
        raise ValueError('Duplicate source identifiers')
    geod, results = Geod(ellps='WGS84'), []
    for local in police:
        report_day = date.fromisoformat(local['reportDate'])
        start, end = month_boundary(report_day, -1), month_boundary(report_day, 1)
        origin, tokens = point(local['coordinates']), road_tokens(local['address'])
        candidates, baseline = [], []
        for crash in crashes:
            crash_day = date.fromisoformat(crash['date'])
            if not start <= crash_day <= end:
                continue
            destination = point(crash['coordinates'])
            distance = geod.inv(*origin, *destination)[2] if origin and destination else None
            text_match = len(tokens) >= 2 and tokens <= road_tokens(crash['road'])
            if origin is not None:
                if distance is None or distance > radius_metres:
                    continue
                method = 'spatial'
            elif text_match:
                method = 'text-only-unverified-location'
            else:
                continue
            delta = (crash_day - report_day).days
            relation = mode_relation(local['mode'], crash['modes'])
            old_mode_ok = ('bicycle' in crash['modes'] if local['mode'] in {'bicycle', 'electric-bicycle'}
                           else 'pedestrian' in crash['modes'] if local['mode'] == 'pedestrian-and-scooter' else True)
            tight = method == 'spatial' and abs(delta) <= 1 and crash['activeTransportationSelected'] and old_mode_ok
            candidate = {**crash, 'distanceMetres': round(distance, 1) if distance is not None else None,
                         'crashDateMinusReportDays': delta, 'afterReportDate': delta > 0,
                         'modeRelationship': relation, 'locationMethod': method, 'roadTextContainsPoliceTokens': text_match,
                         'withinEarlierOneDayRule': tight, 'reviewStatus': 'unreviewed-not-an-identity-link'}
            candidates.append(candidate)
            if tight:
                baseline.append(crash['id'])
        candidates.sort(key=lambda c: (c['locationMethod'] != 'spatial',
                                       c['modeRelationship'] == 'mode-mismatch-or-missing',
                                       abs(c['crashDateMinusReportDays']), c['distanceMetres'] or 0, c['id']))
        results.append({**local, 'windowStart': start.isoformat(), 'windowEnd': end.isoformat(),
                        'baselinePortalCandidates': baseline, 'inFocusCohort': not baseline,
                        'status': 'candidates-for-review' if candidates else 'location-unresolved' if origin is None else 'no-candidate',
                        'candidates': candidates})
    tight_by_crash = defaultdict(list)
    for row in results:
        for identifier in row['baselinePortalCandidates']:
            tight_by_crash[identifier].append({k: row[k] for k in ('caseNumber', 'reportDate', 'mode')})
    for row in results:
        for candidate in row['candidates']:
            candidate['otherPoliceWithTightCandidate'] = [p for p in tight_by_crash[candidate['id']]
                                                          if p['caseNumber'] != row['caseNumber']]
    focused = [r for r in results if r['inFocusCohort']]
    return {'summary': {'policeRecords': len(results), 'portalCrashesSearched': len(crashes),
                        'withTightPortalCandidate': len(results) - len(focused), 'focusRecords': len(focused),
                        'focusWithCandidates': sum(bool(r['candidates']) for r in focused),
                        'focusWithSpatialCandidates': sum(any(c['locationMethod'] == 'spatial' for c in r['candidates']) for r in focused),
                        'focusWithBroadlyCompatibleCandidates': sum(any(c['modeRelationship'] != 'mode-mismatch-or-missing' for c in r['candidates']) for r in focused),
                        'focusWithUncontestedCompatibleSpatialDateExpansion': sum(any(c['modeRelationship'] != 'mode-mismatch-or-missing'
                            and c['locationMethod'] == 'spatial' and abs(c['crashDateMinusReportDays']) > 1
                            and not c['otherPoliceWithTightCandidate'] for c in r['candidates']) for r in focused),
                        'focusWithoutCandidates': sum(not r['candidates'] for r in focused),
                        'focusUnresolvedLocations': sum(r['coordinates'] is None for r in focused),
                        'focusCandidatePairs': sum(len(r['candidates']) for r in focused)}, 'records': results}


def markdown(report):
    lines = ['# Police-to-portal one-month candidate review', '',
             'Candidates are leads, not confirmed matches or merged records. Negative offsets mean the crash predates the report.', '',
             '## Counts', '', *[f'- {k}: {v}' for k, v in report['summary'].items()], '',
             '## Method and limits', '', *['- ' + item for item in report['limitations']], '']
    lines += ['## Active-transportation leads in the focus cohort', '',
              '| Police case | Report date | State crash ID | Crash date | Offset days | Distance m | Method | Other police tight candidate |',
              '| --- | --- | --- | --- | ---: | ---: | --- | --- |']
    for row in report['records']:
        if row['inFocusCohort']:
            for c in row['candidates']:
                if c['modeRelationship'] != 'mode-mismatch-or-missing':
                    cells = [row['caseNumber'], row['reportDate'], c['id'], c['date'], c['crashDateMinusReportDays'],
                             c['distanceMetres'], c['locationMethod'], ', '.join(p['caseNumber'] for p in c['otherPoliceWithTightCandidate']) or 'none']
                    lines.append('| ' + ' | '.join(str(x if x is not None else 'unavailable') for x in cells) + ' |')
    lines.append('')
    for row in report['records']:
        if not row['inFocusCohort']:
            continue
        lines += [f"## {row['caseNumber']} — {row['reportDate']} — {row['mode']}", '',
                  f"Police location: {row['address'] or 'not supplied'}. Notes: {row['notes'] or 'none supplied'}.", '',
                  f"Search window: {row['windowStart']} through {row['windowEnd']}. Status: {row['status']}.", '',
                  '| State crash ID | Crash date | Offset days | Distance m | Road | Modes | Severity | Mode relationship | Method | Other police tight candidate |',
                  '| --- | --- | ---: | ---: | --- | --- | --- | --- | --- | --- |']
        for c in row['candidates']:
            cells = [c['id'], c['date'], c['crashDateMinusReportDays'], c['distanceMetres'], c['road'],
                     ', '.join(c['modes']) or 'no AT evidence', c['severity'], c['modeRelationship'], c['locationMethod'],
                     ', '.join(p['caseNumber'] for p in c['otherPoliceWithTightCandidate']) or 'none']
            lines.append('| ' + ' | '.join(str(x if x is not None else 'unavailable').replace('|', '\\|').replace('\n', ' ') for x in cells) + ' |')
        lines.append('')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument('--private-root', type=Path, default=DEFAULT_PRIVATE_DATA_ROOT)
    parser.add_argument('--radius-metres', type=float, default=100, help='Keep the prior spatial radius; dates expand by +/- one calendar month')
    parser.add_argument('--output', type=Path, required=True, help='New review directory outside apps/maps')
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve().is_relative_to((REPO / 'apps/maps').resolve()):
        parser.error('Require a new review directory outside the public app')
    catalog = read_catalog()
    tables = source_tables(args.data_root, args.private_root, with_locators=True)
    for name, table in tables.items():
        for row in table['rows']:
            if set(row) != set(catalog['tables'][name]['fields']):
                raise ValueError('Source column drift: ' + name)
    pointer_path = args.private_root / 'datastores/combined-incidents.json'
    pointer = read_json(pointer_path)
    snapshot_path = Path(pointer['path'])
    if sha256_file(snapshot_path) != pointer['sha256']:
        raise ValueError('Combined snapshot checksum mismatch')
    snapshot = read_json(snapshot_path)
    police = []
    for group in snapshot['records']:
        for obs in group['observations']:
            if obs['sourceKey'] != 'provo-police-incidents':
                continue
            m = obs['metadata']
            versions = m['sourceVersions']
            if not any(v['snapshotId'] == t['snapshotId'] and v['workbookSha256'] == t['sha256']
                       for v in versions for name, t in tables.items() if name.startswith('police.')):
                raise ValueError('Police source provenance differs from retained inputs')
            police.append({'id': obs['id'], 'caseNumber': obs['sourceRecordId'], 'reportDate': m['observedAt']['localDate'],
                           'reportTime': m['observedAt']['localTime'], 'dateMeaning': obs['dateMeaning'],
                           'address': m['location']['addressPartRaw'], 'notes': m['location'].get('noteRaw'),
                           'mode': obs['mode'], 'modeRaw': m['mode']['raw'], 'coordinates': obs['coordinates'],
                           'geocodeStatus': m['location']['geocoding']['status'],
                           'sourceRows': [{'snapshotId': v['snapshotId'], 'sheet': v['sourceSheet'], 'row': v['sourceRow']} for v in versions],
                           'earlierAnyStateCandidate': any(c['policeId'] == obs['id'] for c in snapshot['possibleMatches'])})
    report = search(police, portal_rows(tables), args.radius_metres)
    report['provenance'] = {'combinedSnapshotSha256': pointer['sha256'],
                            'scriptSha256': sha256_file(Path(__file__)),
                            'sourceHashes': {name: t['sha256'] for name, t in tables.items()},
                            'portalFilters': tables['portal.filters']['rows']}
    report['selection'] = {'radiusMetres': args.radius_metres, 'monthsBeforeAndAfter': 1,
                            'baselineDaysBeforeAndAfter': 1, 'fullPortalExport': True}
    report['limitations'] = [
        'All retained portal crashes are searched, including records without active-transportation evidence. The export is filtered to Provo city.',
        'Focus means no portal candidate under the local-calendar-date +/-1 day, same-radius, AT-selection and previous mode rules; it does not mean confirmed absent.',
        'One calendar month on each side is inclusive, clamped at month ends. Positive offsets mean crash after report and need particular scrutiny.',
        'Police report dates use original local calendar dates, not the prior adapter UTC date. Portal timestamps have no confirmed timezone; dates are compared as supplied.',
        'The radius applies to geocoded police addresses, not surveyed collision positions. No radius increase is hidden in the date expansion.',
        'Without accepted police coordinates, exact significant address-token containment supplies separately labelled text-only hints; missing addresses cannot be evaluated spatially.',
        'Mode mismatches and no-AT records remain visible. Broad pedestrian/conveyance codes do not identify an exact device.',
        'Candidate ordering is a deterministic review aid, not a probability or identity decision. Multiple police records may point to the same state crash.',
        'No downloads, source changes, cross-source merges, datastore pointer changes or public deployment occur.',
    ]
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / 'report.json', report)
    (args.output / 'report.md').write_text(markdown(report))
    with (args.output / 'candidates.csv').open('w', newline='') as handle:
        columns = ['caseNumber', 'reportDate', 'policeMode', 'policeAddress', 'stateCrashId', 'crashDate',
                   'offsetDays', 'distanceMetres', 'road', 'portalModes', 'severity', 'modeRelationship', 'locationMethod', 'otherPoliceTightCandidates']
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for r in report['records']:
            if not r['inFocusCohort']:
                continue
            for c in r['candidates']:
                writer.writerow(dict(zip(columns, [r['caseNumber'], r['reportDate'], r['mode'], r['address'], c['id'],
                    c['date'], c['crashDateMinusReportDays'], c['distanceMetres'], c['road'], ', '.join(c['modes']),
                    c['severity'], c['modeRelationship'], c['locationMethod'],
                    ', '.join(p['caseNumber'] for p in c['otherPoliceWithTightCandidate'])])))
    print(json.dumps({'output': str(args.output), **report['summary']}))


if __name__ == '__main__':
    main()
