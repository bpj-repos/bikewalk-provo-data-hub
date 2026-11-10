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
from danger_zones.research_reports import crash_report

AT = 'annual-at-crash-aggregates'
ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://highwaysafety.utah.gov/crash-data-and-statistics/'
REUSE = ('Credit the Utah Crash Data Portal and BikeWalk Provo when reusing these annual statistics. '
         'These terms apply to the published aggregates only.')


def encode(obj):
    return (json.dumps(obj, indent=2, ensure_ascii=False) + '\n').encode()


def prepare(manifest, digest, output, at_version, complete):
    output = output.resolve()
    if not output.is_relative_to(ROOT/'private') or output.exists():
        raise ValueError('Use a new directory inside private/')
    if not re.fullmatch(r'(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)', at_version):
        raise ValueError('Expected a numeric release version')
    managed = json.loads(verified(manifest, digest))
    snapshot = json.loads(verified(manifest.parent/'collection.json', managed['files']['collection.json']))
    report = crash_report(snapshot, complete)
    at_years = [r['year'] for r in report['annual']]
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
    if at_years and at_years[0] < 2018:
        lines = at_files['annual.csv'].splitlines(keepends=True)
        at_files['annual-from-2018.csv'] = lines[0] + b''.join(line for year, line in zip(at_years, lines[1:]) if year >= 2018)
        at_files['method.txt'] += b'annual.csv includes the 2010-2017 Provo archive. Use annual-from-2018.csv to exclude that archive.\n'
    dataset, title, version = AT, 'Provo active transportation crashes by year', at_version
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp)/'packages'
        directory = stage/dataset/version
        directory.mkdir(parents=True)
        package = dict(name=dataset,version=version,title=title,source=SOURCE,
                       attribution='Utah Crash Data Portal. Annual statistics prepared by BikeWalk Provo.',
                       reuse=REUSE,years=at_years,completeThrough=complete,latestEvent=report['coverageEnd'],
                       coverageNote='Latest event in this selection. Full calendar year describes the reporting period. Cases can still be amended. Treat the partial year as provisional and exclude it from full-year trend comparisons.',
                       dateGuidance='https://sites.google.com/utah.gov/udot-safety-standards/training-tools-and-resources/crash-analysis-date-range-faq',
                       sourceSelection=[x['filters']['Date Selection'] for x in managed['inputs']
                                        if x.get('scope')=='collection' and x.get('kind')=='portal'],
                       citation=f'BikeWalk Provo. {title}, {version}. https://bikewalk-provo-data-hub.vercel.app/datasets/{dataset}/{version}/datapackage.json',
                       resources=[])
        for name,b in sorted(at_files.items()):
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
    p.add_argument('output',type=Path)
    p.add_argument('--at-version',default='1.0.0')
    p.add_argument('--complete-through',type=int,required=True,help='Last full calendar year')
    a = p.parse_args()
    prepare(a.manifest,a.manifest_sha,a.output,a.at_version,a.complete_through)
