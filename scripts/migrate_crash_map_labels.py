"""Prepare a new Streets Watch crash snapshot with readable base-field values."""
import argparse
from copy import deepcopy
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile

from danger_zones.common_structure import CONTRACT
from danger_zones.crash_labels import export_display_fields
import danger_zones.crash_labels as crash_labels
from danger_zones.field_inventory import CATALOG


def encoded(value):
    return json.dumps(value, separators=(',', ':'), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def migrate(source, output):
    if output.exists():
        raise ValueError('Output must be a new directory')
    map_raw = (source / 'map.json').read_bytes()
    details_raw = gzip.decompress((source / 'details.json.gz').read_bytes())
    layer, details = json.loads(map_raw), json.loads(details_raw)
    previous = layer['dataset']
    if len(previous) != 64 or any(c not in '0123456789abcdef' for c in previous):
        raise ValueError('Invalid source dataset pin')
    archived = json.loads(gzip.decompress((source / 'versions' / (previous + '.json.gz')).read_bytes()))
    if archived != {'map': layer, 'details': details}:
        raise ValueError('Current snapshot differs from its retained version')
    original = deepcopy(details)
    unresolved = set()
    for detail in details.values():
        for record in detail['records']:
            if record['source'] not in {'UDOT', 'Utah Crash Data Portal'}:
                continue
            for section in record['sections']:
                title = section['title']
                table = 'udot.arcgis' if record['source'] == 'UDOT' else (
                    'portal.persons' if title.startswith('Person ') else
                    'portal.vehicles' if title.startswith('Vehicle ') else
                    'portal.rollups' if title == 'Recorded involvement and factors' else 'portal.crashes')
                section['fields'] = export_display_fields(table, section['fields'])
                unresolved.update(table + ':' + f['label'] for f in section['fields']
                                  if str(f['value']).startswith('Unmapped code: '))
    changed = sum(details[k] != original[k] for k in details)
    layer.pop('dataset')
    dataset = digest(encoded(layer) + encoded(details))
    layer['dataset'] = dataset
    files = {'map.json': encoded(layer), 'details.json.gz': gzip.compress(encoded(details), mtime=0),
             'versions/' + dataset + '.json.gz': gzip.compress(encoded({'map': layer, 'details': details}), mtime=0)}
    report = {'previousDataset': previous, 'dataset': dataset, 'records': len(details),
              'changedDetails': changed, 'unmappedFields': sorted(unresolved),
              'inputs': {'map.json': digest(map_raw), 'details.json': digest(details_raw)},
              'definitions': {p.name: digest(p.read_bytes()) for p in [CATALOG, CONTRACT, CONTRACT.with_name('export-codes.json')]},
              'tools': {p.name: digest(p.read_bytes()) for p in [Path(__file__), Path(crash_labels.__file__)]},
              'outputs': {name: digest(raw) for name, raw in files.items()},
              'verification': 'Only record section fields changed. Map geometry, membership, IDs, filters and associations preserved. Old versions must be retained on adoption.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        stage = Path(temporary) / 'snapshot'
        (stage / 'versions').mkdir(parents=True)
        for name, raw in files.items():
            (stage / name).write_bytes(raw)
        (stage / 'migration.json').write_text(json.dumps(report, indent=2) + '\n')
        stage.rename(output)
    return report


def apply(source, candidate):
    """Publish the immutable local version before switching the current map pointer."""
    report = json.loads((candidate / 'migration.json').read_text())
    dataset = report['dataset']
    if len(dataset) != 64 or any(c not in '0123456789abcdef' for c in dataset):
        raise ValueError('Invalid candidate dataset pin')
    version = 'versions/' + dataset + '.json.gz'
    if set(report['outputs']) != {'map.json', 'details.json.gz', version}:
        raise ValueError('Unexpected candidate paths')
    payloads = {name: (candidate / name).read_bytes() for name in report['outputs']}
    if any(digest(raw) != report['outputs'][name] for name, raw in payloads.items()):
        raise ValueError('Candidate checksum mismatch')
    current = (source / 'map.json').read_bytes()
    if digest(current) == report['outputs']['map.json']:
        if any((source / name).read_bytes() != raw for name, raw in payloads.items()):
            raise ValueError('Applied snapshot is incomplete')
        return
    current_details = (source / 'details.json.gz').read_bytes()
    if digest(current) != report['inputs']['map.json'] or (digest(gzip.decompress(current_details)) != report['inputs']['details.json'] and current_details != payloads['details.json.gz']):
        raise ValueError('Source changed since migration')
    target = source / version
    try:
        with target.open('xb') as handle:
            handle.write(payloads[version])
    except FileExistsError:
        if target.read_bytes() != payloads[version]:
            raise ValueError('Refusing to replace an immutable version')
    for name in ['details.json.gz', 'map.json']:
        with tempfile.NamedTemporaryFile(dir=source, delete=False) as handle:
            handle.write(payloads[name])
        os.replace(handle.name, source / name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Existing data/crash-stress directory, including versions')
    parser.add_argument('output', type=Path, help='New private candidate directory')
    parser.add_argument('--apply', action='store_true', help='Verify and adopt the candidate, preserving old versions; safe to repeat')
    args = parser.parse_args()
    report = json.loads((args.output / 'migration.json').read_text()) if args.apply and args.output.exists() else migrate(args.source, args.output)
    if args.apply:
        apply(args.source, args.output)
    print(json.dumps(report, indent=2))
