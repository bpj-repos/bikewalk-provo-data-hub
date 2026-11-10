"""Prepare a deterministic, checksummed citywide bicycle stress candidate from a source receipt."""
import argparse
import hashlib
import json
from pathlib import Path

from scripts.build_demo_counts import encoded
from scripts.route_stress import load
from pipelines.traffic_stress.network import build

ROOT = Path(__file__).resolve().parents[1]
DATASET = 'provo-bicycle-traffic-stress'


def prepare(receipt, output, version='1.0.0'):
    record = json.loads(receipt.read_bytes())
    inputs, sources = {}, {}
    for key, source in sorted(record['sources'].items()):
        path = receipt.parent / source['path']
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != source['sha256']:
            raise ValueError('Source pin mismatch: ' + key)
        inputs[key] = load(path)
        sources[key] = {k: v for k, v in source.items() if k != 'path'}
    segments, approaches, supplemental, coverage = build(inputs, sources, record.get('evidence', []))
    resources = {}
    for name, rows in [('segments', segments), ('approaches', approaches), ('supplemental-inventory', supplemental)]:
        if len({f['id'] for f in rows}) != len(rows):
            raise ValueError('Duplicate feature identity: ' + name)
        resources[name + '.geojson'] = json.dumps(dict(type='FeatureCollection', features=rows), separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
    resources['published-reference.geojson'] = (receipt.parent / record['sources']['published']['path']).read_bytes()
    resources['boundary.geojson'] = encoded(inputs['boundary'])
    resources['sources.json'] = encoded(dict(sources=sources, provenance=record.get('provenance', {}),
                                             tools={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT / 'pipelines/traffic_stress').glob('*.py'))},
                                             evidence=record.get('evidence', []),
                                             receiptSha256=hashlib.sha256(receipt.read_bytes()).hexdigest()))
    resources['coverage.json'] = encoded(coverage)
    from pipelines.traffic_stress.pilot import pilot
    resources['pilot.json'] = encoded(pilot(inputs, segments, approaches))
    contract = ROOT / 'data-definitions' / DATASET
    for name in ('method.md', 'dictionary.json'):
        resources[name] = (contract / name).read_bytes()
    manifest = dict(name=DATASET, version=version, title='Provo bicycle traffic stress',
        attribution='BikeWalk Provo; PeopleForBikes; © OpenStreetMap contributors; Utah Geospatial Resource Center / Utah Bikeways; Provo City; UDOT.',
        reuse='OSM-derived database: ODbL 1.0. Utah Bikeways and Utah Roads: CC BY 4.0 with attribution. Provo and UDOT inventories retain their source informational-use terms. See method.md.',
        citation=f'BikeWalk Provo. Provo bicycle traffic stress {version}. https://bikewalk-provo-data-hub.vercel.app/datasets/{DATASET}/{version}/datapackage.json',
        resources=[dict(name=Path(name).stem, path=name, bytes=len(raw), hash='sha256:' + hashlib.sha256(raw).hexdigest()) for name, raw in sorted(resources.items())])
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in resources.items():
        (output / name).write_bytes(raw)
    (output / 'datapackage.json').write_bytes(encoded(manifest))
    print(json.dumps(dict(manifestSha256=hashlib.sha256(encoded(manifest)).hexdigest(), coverage=coverage)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--version', default='1.0.0')
    prepare(**vars(parser.parse_args()))
