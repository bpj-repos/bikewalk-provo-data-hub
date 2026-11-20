"""Add Hub-derived lighting and person flags to a minimized local crash-map candidate."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import tempfile

from danger_zones import crash_context, crash_labels, derived_incidents, incident_conversions
from scripts import migrate_crash_map_labels
from danger_zones.crash_labels import export_darkness, export_person_context
from danger_zones.derived_incidents import RULES
from danger_zones.common_structure import CONTRACT
from danger_zones.field_inventory import CATALOG
from scripts.migrate_crash_map_labels import apply, digest, encoded


def prepare(source, output):
    if output.exists():
        raise ValueError('Output must be a new directory')
    map_raw = (source / 'map.json').read_bytes()
    details_raw = gzip.decompress((source / 'details.json.gz').read_bytes())
    layer, details = json.loads(map_raw), json.loads(details_raw)
    previous = layer.get('dataset')
    if not isinstance(previous, str) or len(previous) != 64 or any(c not in '0123456789abcdef' for c in previous):
        raise ValueError('Invalid source dataset pin')
    archived = json.loads(gzip.decompress((source / 'versions' / (previous + '.json.gz')).read_bytes()))
    if archived != {'map': layer, 'details': details}:
        raise ValueError('Current snapshot differs from its retained version')
    categories, reasons = Counter(), Counter()
    person_counts = {'youngChild': Counter(), 'bikeLane': Counter()}
    for detail in details.values():
        darkness = export_darkness(detail['records'])
        detail['darknessCategory'] = darkness['category']
        categories[darkness['category']] += 1
        person_context = export_person_context(detail['records'])
        for field in person_counts:
            value = person_context[field]['value']
            detail[field] = value
            person_counts[field]['yes' if value is True else 'no' if value is False else 'unknown'] += 1
        if darkness['reason'] or darkness['lightingReason']:
            reasons[darkness['reason'] or darkness['lightingReason']] += 1
    ids = []
    for feature in layer['features']:
        properties = feature['properties']
        if properties.get('kind') == 'crash':
            identifier = properties['id']
            if identifier not in details:
                raise ValueError('Crash feature has no minimized detail')
            ids.append(identifier)
            properties['darknessCategory'] = details[identifier]['darknessCategory']
            for field in person_counts:
                properties[field] = details[identifier][field]
    if len(ids) != len(set(ids)) or set(ids) != set(details):
        raise ValueError('Map/detail crash membership differs or contains duplicates')
    layer.pop('dataset')
    dataset = digest(encoded(layer) + encoded(details))
    layer['dataset'] = dataset
    files = {'map.json': encoded(layer), 'details.json.gz': gzip.compress(encoded(details), mtime=0),
             'versions/' + dataset + '.json.gz': gzip.compress(encoded({'map': layer, 'details': details}), mtime=0)}
    report = {'previousDataset': previous, 'dataset': dataset, 'records': len(details),
              'fields': ['darknessCategory', 'youngChild', 'bikeLane'], 'categories': dict(categories),
              'personContext': {key: dict(counts) for key, counts in person_counts.items()}, 'unknownOrConflictReasons': dict(reasons),
              'inputs': {'map.json': digest(map_raw), 'details.json': digest(details_raw)},
              'definitions': {p.name: digest(p.read_bytes()) for p in [RULES, CONTRACT, CATALOG, CONTRACT.with_name('export-codes.json')]},
              'tools': {p.name: digest(p.read_bytes()) for p in [Path(__file__), Path(crash_context.__file__), Path(crash_labels.__file__),
                        Path(derived_incidents.__file__), Path(incident_conversions.__file__), Path(migrate_crash_map_labels.__file__)]},
              'outputs': {name: digest(raw) for name, raw in files.items()},
              'verification': 'Additive darknessCategory, youngChild and bikeLane only. Original crash membership, geometry, details and associations preserved.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        stage = Path(temporary) / 'snapshot'
        (stage / 'versions').mkdir(parents=True)
        for name, raw in files.items():
            (stage / name).write_bytes(raw)
        (stage / 'migration.json').write_text(json.dumps(report, indent=2) + '\n')
        stage.rename(output)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Existing minimized crash-stress snapshot')
    parser.add_argument('output', type=Path, help='New local candidate directory')
    parser.add_argument('--apply', action='store_true', help='Adopt a verified candidate in the specified local checkout')
    args = parser.parse_args()
    report = json.loads((args.output / 'migration.json').read_text()) if args.apply and args.output.exists() else prepare(args.source, args.output)
    if args.apply:
        apply(args.source, args.output)
    print(json.dumps(report, indent=2))
