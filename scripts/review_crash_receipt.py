"""Compare a managed crash receipt with published annual series and the previous Streets Watch export."""
from contextlib import redirect_stdout
import sys
import argparse
import csv
import hashlib
import io
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.build_catalog import checked_package
from scripts.prepare_crash_releases import AT, prepare
from danger_zones.concern_details import export_concern_details
from danger_zones.config import DEFAULT_PRIVATE_DATA_ROOT

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = DEFAULT_PRIVATE_DATA_ROOT


def read(path):
    return json.loads(path.read_bytes())


def by_year(data):
    return {r['year']:r for r in csv.DictReader(io.StringIO(data.decode()))}


def semantic_changes(before, after):
    """Review all consumer fields without reporting release-only bookkeeping."""
    def content(value):
        if isinstance(value, dict):
            return {k: content(v) for k, v in value.items() if k != 'releaseId'}
        if isinstance(value, list):
            return [content(v) for v in value]
        return value
    old, new = before['crashes'], after['crashes']
    changed = {}
    for key in sorted(old.keys() & new.keys()):
        left, right = content(old[key]), content(new[key])
        fields = {k: {'before': left.get(k), 'after': right.get(k)}
                  for k in sorted(left.keys() | right.keys()) if left.get(k) != right.get(k)}
        if fields:
            changed[key] = fields
    return {'added': sorted(new.keys() - old.keys()), 'removed': sorted(old.keys() - new.keys()),
            'changed': changed,
            'ambiguousIds': {'before': before.get('ambiguousCrashIds', []), 'after': after.get('ambiguousCrashIds', [])}}


def package_version(dataset, version, crash_pin, ledger):
    if not version or not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", version):
        raise ValueError("Supply an explicit numeric version for " + dataset)
    if any(e['dataset'] == dataset and e['version'] == version for e in ledger['withdrawn']):
        raise ValueError("Withdrawn package version")
    existing = next((e for e in ledger['approved'] if e['dataset'] == dataset and e['version'] == version), None)
    if existing:
        files = checked_package(ROOT/'releases/datasets'/dataset/version, existing)
        if json.loads(files['datapackage.json'])['crashDataset'] != crash_pin:
            raise ValueError("Published version belongs to another snapshot; choose a new version")
    return existing


def review(output, previous_export, export_pin, follow_cases, map_snapshot=None, street_version=None, time_version=None):
    if not output.resolve().is_relative_to(ROOT/'private') or output.exists():
        raise ValueError('Use a new private output folder')
    previous_bytes = previous_export.read_bytes()
    if hashlib.sha256(previous_bytes).hexdigest() != export_pin:
        raise ValueError('Previous concern export checksum mismatch')
    prior = json.loads(previous_bytes)
    pointer = read(PRIVATE/'datastores/combined-incidents.json')
    mf = Path(pointer['releaseManifest']['path'])
    pin = pointer['releaseManifest']['sha256']
    ledger = read(ROOT/'releases/release-ledger.json')
    withdrawn = {w['version'] for w in ledger['withdrawn'] if w['dataset']==AT}
    entry = next(e for e in reversed(ledger['approved']) if e['dataset']==AT and e['version'] not in withdrawn)
    version = entry['version']
    old = checked_package(ROOT/'releases/datasets'/AT/version,entry)
    complete_through = json.loads(old['datapackage.json'])['completeThrough']
    output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with TemporaryDirectory(dir=output.parent) as temp:
        stage = Path(temp)/'review'
        stage.mkdir(mode=0o700)
        proposed = stage/'annual'
        with redirect_stdout(sys.stderr):
            prepare(mf,pin,proposed,version,complete_through)
        new = proposed/AT/version
        old_rows, new_rows = by_year(old['annual.csv']), by_year((new/'annual.csv').read_bytes())
        annual = {AT: {
            'comparedVersion':version,
            'changedYears':{y:[old_rows.get(y),new_rows.get(y)] for y in sorted(old_rows.keys()|new_rows.keys()) if old_rows.get(y)!=new_rows.get(y)},
            'changedFiles':sorted(k for k,v in old.items() if (new/k).read_bytes()!=v),
        }}
        details = export_concern_details(mf.parent,pin)
        (stage/'details.json').write_text(json.dumps(details,sort_keys=True,separators=(',',':'))+'\n')
        def links(export):
            return {k:v['policeReport'] for k,v in export['crashes'].items() if 'policeReport' in v}
        before,after = links(prior), links(details)
        changed = {k:[before.get(k),after.get(k)] for k in sorted(before.keys()|after.keys()) if before.get(k)!=after.get(k)}
        prepared = {}
        if map_snapshot:
            import gzip
            from scripts.prepare_crash_streets import build as streets
            from scripts.prepare_crash_time import build as occurrence
            snapshot = json.loads(gzip.decompress(map_snapshot.read_bytes()))['map']
            if snapshot['collectionHash'] != pointer['sha256'] or snapshot['release'] != pointer['snapshotId']:
                raise ValueError('Map snapshot belongs to another managed collection')
            map_pin = snapshot['dataset']
            for name, build, dataset, version in [('streets', streets, 'provo-crash-street-membership', street_version), ('time', occurrence, 'provo-crash-occurrence-time', time_version)]:
                existing = package_version(dataset, version, map_pin, ledger)
                destination = stage/name
                coverage = build(map_snapshot, destination, crash_pin=map_pin, version=version)
                if existing and hashlib.sha256((destination/'datapackage.json').read_bytes()).hexdigest() != existing['sha256']:
                    raise ValueError('Published version has different bytes; choose a new version')
                prepared[name] = {'path': str(output/name), 'coverage': coverage,
                                  'manifestSha256': hashlib.sha256((destination/'datapackage.json').read_bytes()).hexdigest()}
        collection = read(mf.parent/'collection.json')
        groups = {o['sourceRecordId']:g for g in collection['records'] for o in g['observations'] if o['sourceKey']=='provo-police-incidents'}
        tracked = {case:groups[case].get('reviewedLink',{}).get('udotId') for case in follow_cases}
        result = dict(release=details['releaseId'],manifestSHA256=pin,annual=annual,changedPoliceReferences=changed,trackedCases=tracked,consumerChanges=semantic_changes(prior, details),prepared=prepared,
                      exportSHA256=hashlib.sha256((stage/'details.json').read_bytes()).hexdigest())
        (stage/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
        stage.rename(output)
    return result


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path)
    p.add_argument('previous_export',type=Path)
    p.add_argument('export_sha256')
    p.add_argument('--case',action='append',default=[])
    p.add_argument('--map-snapshot',type=Path,help='Prepare street, occurrence and record-fact candidates for this verified map archive')
    p.add_argument('--street-version', help='Explicit street package version when preparing a map')
    p.add_argument('--time-version', help='Explicit occurrence package version when preparing a map')
    a=p.parse_args()
    print(json.dumps(review(a.output,a.previous_export,a.export_sha256,a.case,a.map_snapshot,a.street_version,a.time_version),indent=2))
