"""Screen private crash reports or build the historical AT map contribution candidate."""
import argparse
from collections import Counter
import json
from pathlib import Path
import tempfile

from danger_zones.parking_contribution import FIELD, RULE, VALUES, case_index, case_keys, screen
from danger_zones.util import sha256_file
from scripts.build_catalog import checked_package
from scripts.prepare_incident_map_release import NAME, encoded, sha

ROOT = Path(__file__).resolve().parents[1]
POINTER = ROOT / 'private/active/crashes/collection/datastores/combined-incidents.json'
BASE = ROOT / 'releases/datasets' / NAME / '1.0.0'
BASE_PIN = 'e9fdbe0101380792235c2ff1c43bccf0645c220730cf6d0ab12e8f403ea9df8e'
METHOD = """Bike-lane parking contribution, rule bike-lane-parking-v1.
Documented: an original report, diagram or supplement establishes both stationary motor-vehicle occupancy
of a designated bike lane for parking, standing or loading and its contribution to the crash sequence.
Contact with the vehicle is optional. Possible: case-specific evidence suggests the mechanism with a fact unresolved.
Ruled_out: reviewed evidence affirmatively excludes it. Unknown: missing, silent, ambiguous or unlinked evidence.
Ordinary traffic stops and doors opened from an adjacent bay alone do not qualify. This field does not assess legality.
Counts describe mapped groups, which can overlap in event identity. Only documented findings count as documented cases.
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


def feature_keys(feature):
    details = feature['properties']['details']
    fields = {'Police: Case number': 'police:', 'UDOT: CRASH_ID': 'state:', 'Portal: Crash_ID': 'state:'}
    return {prefix + str(details[k]) for k, prefix in fields.items() if details.get(k)}


def project(layer, records):
    index = case_index(records)
    keys = [feature_keys(f) for f in layer['features']]
    frequency = Counter(k for feature in keys for k in feature)
    reviewed = 0
    counts = dict.fromkeys(VALUES, 0)
    for feature, aliases in zip(layer['features'], keys):
        value = 'unknown'
        groups = {g['id']: g for k in aliases for g in index.get(k, [])}
        if len(groups) == 1:
            enrichment = next(iter(groups.values()))['enrichment']
            assessment = enrichment.get('parkingReview')
            if assessment and assessment['case'] in aliases and frequency[assessment['case']] == 1:
                value = enrichment[FIELD]
                reviewed += 1
        counts[value] += 1
        feature['properties'][FIELD] = value
    return {'mappedGroups': len(keys), 'reviewedGroups': reviewed, 'categories': counts}


def build(records, output):
    output = private_output(output)
    if any(r['enrichment'].get(FIELD) not in VALUES for r in records):
        raise ValueError('Run the private crash updater before building')
    files = checked_package(BASE, {'dataset': NAME, 'version': '1.0.0', 'sha256': BASE_PIN})
    package = json.loads(files.pop('datapackage.json'))
    layer = json.loads(files['incidents.geojson'])
    coverage = project(layer, records)
    files['incidents.geojson'] = (json.dumps(layer, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode()
    dictionary = json.loads(files['dictionary.json'])
    dictionary['fields'].append({'name': 'properties.' + FIELD, 'type': 'string', 'enum': VALUES,
                                 'description': 'Reviewed contribution to this crash from a motor vehicle parked or standing in a bike lane. See method.txt.'})
    files['dictionary.json'] = encoded(dictionary)
    files['method.txt'] += ('\n' + METHOD).encode()
    manifest = json.loads(files['map-manifest.json'])
    manifest.update(sha256=sha(files['incidents.geojson']), parkingCoverage=coverage,
                    approval='Historical map content derives from the pinned 1.0.0 package. The added category follows the published method.')
    files['map-manifest.json'] = encoded(manifest)
    package.update(version='1.1.0', parkingCoverage=coverage, baseManifestSha256=BASE_PIN,
                   preparation='Historical map with reviewed bike-lane parking contribution.')
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
