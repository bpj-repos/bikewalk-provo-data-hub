"""Screen private crash reports or build the historical AT map contribution candidate."""
import argparse
from collections import Counter
import json
from pathlib import Path
import tempfile

from danger_zones.parking_contribution import FIELD, RULE, LEVELS, structured_evidence, case_index, case_keys, screen
from danger_zones.util import sha256_file
from scripts.build_catalog import checked_package
from scripts.prepare_incident_map_release import NAME, encoded, sha

ROOT = Path(__file__).resolve().parents[1]
POINTER = ROOT / 'private/active/crashes/collection/datastores/combined-incidents.json'
BASE = ROOT / 'releases/datasets' / NAME / '1.0.0'
BASE_PIN = 'e9fdbe0101380792235c2ff1c43bccf0645c220730cf6d0ab12e8f403ea9df8e'
METHOD = """Structured bike-lane parking contribution assessment, version 1.
Stronger lead: the same crash records an AT participant in a designated bike lane plus improper
parking/stopping or a parked vehicle. Possible lead: a bike-lane participant plus a parking maneuver
or traffic-lane stop, or driver evasive action plus improper parking or a parked vehicle.
Weak lead: a parked vehicle, parking maneuver, or improper parking without the stronger combinations.
No specific signal: a portal record has an identified AT participant and a known vehicle maneuver,
without a qualifying combination. Insufficient data: the available fields cannot support that screen.
A UDOT parked-vehicle collision alone is a weak lead. Ordinary traffic stops, vehicle branding, or a
bike-lane location alone do not qualify. Code each source separately. Tier counts are groups, not
calibrated probabilities or established causes. The AT person's lane does not locate the motor vehicle.
"""


def private_output(path):
    path = path.resolve()
    if not path.is_relative_to(ROOT / 'private') or path.exists():
        raise ValueError('Choose a new path under private/')
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_records():
    pointer = json.loads(POINTER.read_bytes())
    raw = Path(pointer['path']).read_bytes()
    if sha(raw) != pointer['sha256']:
        raise ValueError('Active collection pin mismatch')
    return json.loads(raw)['records']


def screen_case(records, case, paths):
    groups = case_index(records).get(case, [])
    group = groups[0] if len(groups) == 1 else None
    reports = []
    for path in paths:
        digest = sha256_file(path)
        result = screen(path)
        if sha256_file(path) != digest:
            raise ValueError('Report changed during screening')
        reports.append({'path': str(path.resolve()), 'sha256': digest, **result})
    return {'rule': RULE, 'case': case, 'group': group['id'] if group else None,
            'links': case_keys(group) if group else [], 'reports': reports,
            'value': 'unknown', 'reviewer': '', 'rationale': ''}


def project(layer):
    """Read each historical feature's own frozen fields, independent of later matching."""
    counts = dict.fromkeys(LEVELS, 0)
    for feature in layer['features']:
        details = feature['properties']['details']
        portal = {'crash': {}, 'vehicles': [], 'persons': []}
        for key, value in details.items():
            if not key.startswith('Portal: '):
                continue
            name = key.removeprefix('Portal: ')
            kind, _, number = name.partition(' ')
            if kind in ('Person', 'Vehicle') and number.isdecimal():
                row = {}
                for cell in value.split(' · '):
                    field, sep, label = cell.partition(' = ')
                    if sep:
                        row[field.replace(' label', '_label')] = label
                portal['persons' if kind == 'Person' else 'vehicles'].append(row)
            else:
                portal['crash'][name] = value
        udot = {k.removeprefix('UDOT: '): v for k, v in details.items() if k.startswith('UDOT: ')}
        levels = [structured_evidence('utah-crash-portal', portal)[0], structured_evidence('udot-crashes', udot)[0]]
        level = min(levels, key=LEVELS.index)
        counts[level] += 1
        feature['properties'][FIELD] = level
    return {'mappedGroups': len(layer['features']), 'categories': counts}


def build(records, output):
    output = private_output(output)
    if any(r['enrichment'].get(FIELD) not in LEVELS for r in records):
        raise ValueError('Run the private crash updater before building')
    files = checked_package(BASE, {'dataset': NAME, 'version': '1.0.0', 'sha256': BASE_PIN})
    package = json.loads(files.pop('datapackage.json'))
    layer = json.loads(files['incidents.geojson'])
    coverage = project(layer)
    files['incidents.geojson'] = (json.dumps(layer, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode()
    dictionary = json.loads(files['dictionary.json'])
    dictionary['fields'].append({'name': 'properties.' + FIELD, 'type': 'string', 'enum': LEVELS,
                                 'description': 'Relative strength of structured crash evidence for bike-lane parking contribution. See method.txt.'})
    files['dictionary.json'] = encoded(dictionary)
    files['method.txt'] += ('\n' + METHOD).encode()
    manifest = json.loads(files['map-manifest.json'])
    manifest.update(sha256=sha(files['incidents.geojson']), parkingCoverage=coverage,
                    approval='Historical map content derives from the pinned 1.0.0 package. The added category follows the published method.')
    files['map-manifest.json'] = encoded(manifest)
    package.update(version='1.1.0', parkingCoverage=coverage, baseManifestSha256=BASE_PIN,
                   preparation='Historical map with structured bike-lane parking likelihood assessment.')
    package['citation'] = package['citation'].replace('1.0.0', '1.1.0')
    for resource in package['resources']:
        raw = files[resource['path']]
        resource.update(bytes=len(raw), hash='sha256:' + sha(raw))
    files['datapackage.json'] = encoded(package)
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp) / 'package'
        stage.mkdir()
        for name, raw in files.items():
            (stage / name).write_bytes(raw)
        stage.rename(output)
    return coverage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    review = commands.add_parser('screen')
    review.add_argument('case', help='state:CRASH_ID or police:CASE_NUMBER')
    review.add_argument('output', type=Path)
    review.add_argument('reports', type=Path, nargs='+')
    candidate = commands.add_parser('candidate')
    candidate.add_argument('output', type=Path)
    args = parser.parse_args()
    records = load_records()
    if args.command == 'screen':
        packet = screen_case(records, args.case, args.reports)
        with private_output(args.output).open('xb') as f:
            f.write(encoded(packet))
        print('Private review packet:', args.output)
    else:
        print(json.dumps(build(records, args.output)))


if __name__ == '__main__':
    main()
