"""Build Provo crash street membership from immutable map and street inputs."""
import argparse
from collections import Counter
from pathlib import Path
import gzip
import hashlib
import json
import re
import tempfile

from scripts.build_catalog import ROOT, checked_package

DATASET = 'provo-crash-street-membership'
BASE = '5d4eed90d3b2e5698746cee59e53b7fd49ff76ad1d6bf35e0ab628c174122061'
ROAD_PIN = 'fa704cf166a895cc4e829ec144f5e6701b9802ac523d0729a44e3c88c8b761f1'
DIR = {'N': 'NORTH', 'S': 'SOUTH', 'E': 'EAST', 'W': 'WEST'}
WORDS = {**DIR, 'AVE': 'AVENUE', 'ST': 'STREET', 'RD': 'ROAD', 'PKWY': 'PARKWAY',
         'BLVD': 'BOULEVARD', 'DR': 'DRIVE', 'LN': 'LANE', 'CIR': 'CIRCLE',
         'CT': 'COURT', 'HWY': 'HIGHWAY', 'PL': 'PLACE', 'TER': 'TERRACE'}
DIRECTION = r'(?:NORTH|SOUTH|EAST|WEST)'
GRID = rf'\d+ {DIRECTION}'
AVENUE = re.compile(r'\bUNIVERSITY\s+AVE(?:NUE)?\b', re.I)
FIELDS = {'Utah Crash Data Portal': 'Road name', 'UDOT': 'Main road name'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def compact(obj):
    return json.dumps(obj, separators=(',', ':'), allow_nan=False).encode()


def normalize(value):
    name = ' '.join(WORDS.get(w, w) for w in value.upper().replace('.', '').split())
    return re.sub(rf'^((?:{DIRECTION} )?{GRID}) STREET$', r'\1', name)


def identity(name):
    return 'provo:' + name.lower().replace(' ', '-')


def match(value, names):
    name = normalize(value)
    if name == 'UNIV AVENUE' and 'UNIVERSITY AVENUE' in names:
        return 'UNIVERSITY AVENUE', 'reviewed-abbreviation'
    if name in names:
        return names[name], 'recorded-name'
    addressed = re.sub(rf'^\d+ (?={DIRECTION} .)', '', name)
    addressed = normalize(addressed)
    for candidate in (addressed, re.sub(rf'^{DIRECTION} ', '', addressed)):
        if candidate in names:
            return names[candidate], 'address-or-direction-prefix'
    return None, None


def pinned_details(snapshot):
    bundle = json.loads(gzip.decompress(snapshot.read_bytes()))
    layer, details = bundle['map'], bundle['details']
    if layer.pop('dataset') != BASE or digest(compact(layer) + compact(details)) != BASE:
        raise ValueError('Wrong crash snapshot')
    ids = [f['properties']['id'] for f in layer['features'] if f['properties']['kind'] == 'crash']
    if len(set(ids)) != len(ids) or set(ids) != set(details):
        raise ValueError('Map and detail identities differ')
    return details


def build(snapshot, output):
    details = pinned_details(snapshot)
    road = 'provo-bicycle-traffic-stress'
    files = checked_package(ROOT/'releases/datasets'/road/'1.0.0',
                            dict(dataset=road, version='1.0.0', sha256=ROAD_PIN))
    inventory = {normalize(f['properties']['name']) for f in json.loads(files['segments.geojson'])['features']
                 if f['properties'].get('name')}
    names = {}
    for name in inventory:
        base = re.sub(rf'^{DIRECTION} ', '', name)
        names[name] = base if base in inventory or re.fullmatch(GRID, base) else name
    directory = {identity(n): n.title() for n in sorted(set(names.values()))}
    if len(directory) != len(set(names.values())):
        raise ValueError('Street identity collision')
    rows, counts, baseline, resolved = {}, Counter(), set(), set()
    for key, detail in sorted(details.items()):
        evidence, missing = set(), set()
        for record in detail['records']:
            label = FIELDS.get(record['source'])
            for section in record['sections']:
                for field in section['fields']:
                    if field['label'] != label:
                        continue
                    raw = field['value'].upper()
                    if AVENUE.search(raw):
                        baseline.add(key)
                    # Secondary semicolon clauses mix route aliases, businesses and dispatch notes.
                    primary = raw.split(';')[0].split(', PROVO')[0].strip(' ,')
                    parts = re.split(r'\s*(?:&|@|/|\bAND\b|\bAT\b)\s*', primary)
                    # Reviewed compound descriptions in this pinned source. The unmatched
                    # cross-street fragment keeps its own unresolved status.
                    reviewed = {'UNIVERSITY PKWY UNIVERSITY AVE': ['UNIVERSITY PKWY', 'UNIVERSITY AVE'],
                                'UNIVERSITY AVE CENTER STREET': ['UNIVERSITY AVE', 'CENTER STREET'],
                                'UNIVERSITY AVE PAUL REAMS': ['UNIVERSITY AVE', 'PAUL REAMS']}
                    parts = reviewed.get(primary, parts)
                    for part in parts:
                        part = re.sub(r'(?<=UNIVERSITY AVE) (?:SAMS CLUB|PROVO CITY LIBRARY)$', '', part)
                        pieces = re.split(r'\s{2,}', part.strip())
                        if len(pieces) != 2 or not all(match(p, names)[0] for p in pieces):
                            pieces = [part]
                        for piece in pieces:
                            street, rule = match(piece, names)
                            if street:
                                evidence.add((identity(street), record['source'], label, rule))
                            else:
                                missing.add('unrecognized-or-ambiguous-road')
        streets = sorted({e[0] for e in evidence})
        status = ('partial' if missing else 'matched') if streets else 'unresolved'
        if not streets and not missing:
            missing.add('no-recorded-road-field')
        rows[key] = dict(streetIds=streets, status=status, reasons=sorted(missing),
                         evidence=[dict(streetId=i, source=s, field=f, rule=r) for i,s,f,r in sorted(evidence)])
        counts[status] += 1
        if 'provo:university-avenue' in streets:
            resolved.add(key)
    coverage = dict(crashes=len(rows), statuses=dict(counts), explicitUniversityAvenue=len(baseline),
                    assignedUniversityAvenue=len(resolved), explicitOnly=sorted(baseline-resolved),
                    assignedOnly=sorted(resolved-baseline))
    manifest = dict(name=DATASET, version='1.0.0', title='Provo crash street membership',
                    crashDataset=BASE, streetInventoryManifest=ROAD_PIN,
                    attribution='BikeWalk Provo, Utah Crash Data Portal, UDOT and OpenStreetMap contributors.',
                    reuse='Street directory derived from OpenStreetMap under ODbL 1.0. Credit the named sources.',
                    resources=[])
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError('Use a fresh package directory')
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp)/'package'
        stage.mkdir()
        for name, obj in [('streets',directory), ('membership',rows), ('coverage',coverage)]:
            data = compact(obj) + b'\n'
            path = name+'.json'
            (stage/path).write_bytes(data)
            manifest['resources'].append(dict(name=name,path=path,bytes=len(data),hash='sha256:'+digest(data)))
        (stage/'datapackage.json').write_bytes(compact(manifest)+b'\n')
        stage.rename(output)
    return coverage


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.snapshot, args.output), indent=2))
