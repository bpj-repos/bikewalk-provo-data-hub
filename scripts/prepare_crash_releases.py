"""Build private, aggregate-only release packages for owner review."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from scripts.build_catalog import checked_package
from scripts.restore_crash_collections import verified
from danger_zones.motor_vehicle_candidate import DATASET, FIELDS, METHOD
from danger_zones.research_reports import crash_report

AT = 'annual-at-crash-aggregates'
ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://highwaysafety.utah.gov/crash-data-and-statistics/'
REUSE = ('Credit the Utah Crash Data Portal and BikeWalk Provo when reusing these annual statistics. '
         'These terms apply to the published aggregates only.')


def encode(obj):
    return (json.dumps(obj, indent=2, ensure_ascii=False) + '\n').encode()


def prepare(manifest, digest, motor, motor_digest, output, at_version, motor_version):
    output = output.resolve()
    if not output.is_relative_to(ROOT/'private') or output.exists():
        raise ValueError('Use a new directory inside private/')
    if not all(re.fullmatch(r'(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)', v) for v in (at_version, motor_version)):
        raise ValueError('Expected a numeric release version')
    managed = json.loads(verified(manifest, digest))
    snapshot = json.loads(verified(manifest.parent/'collection.json', managed['files']['collection.json']))
    candidate = json.loads(verified(motor/'datapackage.json', motor_digest))
    if (candidate['upstreamManifestSHA256'], candidate['name'], candidate['status']) != (digest, DATASET, 'private-candidate'):
        raise ValueError('Motor vehicle candidate must use the same private source release')
    allowed = {'annual.csv', 'method.txt', 'dictionary.json'}
    if sorted(r['path'] for r in candidate['resources']) != sorted(allowed):
        raise ValueError('Unexpected motor vehicle resources')
    motor_files = {}
    for r in candidate['resources']:
        b = (motor/r['path']).read_bytes()
        if len(b) != r['bytes'] or 'sha256:'+hashlib.sha256(b).hexdigest() != r['hash']:
            raise ValueError('Motor vehicle resource checksum mismatch')
        motor_files[r['path']] = b
    if json.loads(motor_files['dictionary.json']) != {'fields':FIELDS, 'primaryKey':'year'} or motor_files['method.txt'] != METHOD.encode():
        raise ValueError('Unreviewed motor vehicle schema or methodology')
    reader = csv.DictReader(io.StringIO(motor_files['annual.csv'].decode()))
    if reader.fieldnames != [f['name'] for f in FIELDS]:
        raise ValueError('Unexpected motor vehicle CSV fields')
    complete = candidate['completeThrough']
    years = []
    for row in reader:
        year = int(row['year'])
        if None in row or not row['crashes'].isascii() or not row['crashes'].isdecimal() or row['complete_year'] != str(year<=complete).lower():
            raise ValueError('Invalid motor vehicle annual row')
        years.append(year)
    if not years or years != sorted(set(years)) or years != candidate['years']:
        raise ValueError('Motor vehicle coverage mismatch')
    report = crash_report(snapshot, complete)
    if [r['year'] for r in report['annual']] != years:
        raise ValueError('Review year coverage before publishing these series')
    cols = ('year','total','bike','ped','other','complete_year')
    buf = io.StringIO(newline='')
    writer = csv.writer(buf)
    writer.writerow(cols)
    for row in report['annual']:
        modes = [row[k] for k in cols[2:5]]
        if not max(modes) <= row['total'] <= sum(modes):
            raise ValueError('Inconsistent mode totals')
        writer.writerow([row[k] for k in cols[:-1]]+[row['complete']])
    descriptions = ['Local calendar year.', 'Distinct qualifying Provo crashes.',
                    'Crashes involving a cyclist.', 'Crashes involving a pedestrian.',
                    'Crashes involving another nonmotorist conveyance.', 'Treated as a full calendar year.']
    at_files = {'annual.csv':buf.getvalue().encode(),
                'dictionary.json':encode({'primaryKey':'year','fields':[
                    dict(name=k,type='boolean' if k=='complete_year' else 'integer',description=v)
                    for k,v in zip(cols,descriptions)]}),
                'method.txt':(report['scope']+' '+report['modeMethod']+'\n').encode()}
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp)/'packages'
        for dataset,title,version,files,end in [
                (AT,'Provo active transportation crashes by year',at_version,at_files,report['coverageEnd']),
                (DATASET,'Provo motor vehicle crashes with no reported nonmotorist participants by year',motor_version,motor_files,candidate['latestCityEvent'])]:
            directory = stage/dataset/version
            directory.mkdir(parents=True)
            package = dict(name=dataset,version=version,title=title,source=SOURCE,
                           attribution='Utah Crash Data Portal. Annual statistics prepared by BikeWalk Provo.',
                           reuse=REUSE,years=years,completeThrough=complete,latestEvent=end,
                           coverageNote='Latest event in this selection. Full calendar year describes the reporting period. Cases can still be amended. Treat the partial year as provisional and exclude it from full-year trend comparisons.',
                           dateGuidance='https://sites.google.com/utah.gov/udot-safety-standards/training-tools-and-resources/crash-analysis-date-range-faq',
                           sourceSelection=[x['filters']['Date Selection'] for x in managed['inputs']
                                            if x.get('scope')=='collection' and x.get('kind')=='portal'],
                           citation=f'BikeWalk Provo. {title}, {version}. https://bikewalk-provo-data-hub.vercel.app/datasets/{dataset}/{version}/datapackage.json',
                           resources=[])
            for name,b in sorted(files.items()):
                (directory/name).write_bytes(b)
                package['resources'].append(dict(name=Path(name).stem,path=name,bytes=len(b),hash='sha256:'+hashlib.sha256(b).hexdigest()))
            raw = encode(package)
            (directory/'datapackage.json').write_bytes(raw)
            pin = hashlib.sha256(raw).hexdigest()
            checked_package(directory,dict(dataset=dataset,version=version,sha256=pin))
            print(dataset,version,pin)
        stage.rename(output)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest',type=Path)
    p.add_argument('manifest_sha')
    p.add_argument('motor_candidate',type=Path)
    p.add_argument('motor_sha')
    p.add_argument('output',type=Path)
    p.add_argument('--at-version',default='1.0.0')
    p.add_argument('--motor-version',default='1.0.0')
    a = p.parse_args()
    prepare(a.manifest,a.manifest_sha,a.motor_candidate,a.motor_sha,a.output,a.at_version,a.motor_version)
