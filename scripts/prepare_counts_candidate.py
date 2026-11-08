"""Prepare a private revision using reviewed, complete annual slices and pinned evidence."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from scripts import build_counts_releases as counts
from scripts.build_demo_counts import check_version, encoded


def digest(b):
    return hashlib.sha256(b).hexdigest()


def resource(root, item):
    path = root / item['path']
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Receipt path escapes the delivery')
    data = path.read_bytes()
    if digest(data) != item['sha256']:
        raise ValueError('Receipt checksum mismatch: ' + item['path'])
    return data


def parse(data):
    reader = csv.DictReader(io.StringIO(data.decode('utf-8')))
    if reader.fieldnames != list(counts.FIELDS):
        raise ValueError('Unexpected annual schema')
    rows = {}
    for r in reader:
        key = (r['year'], r['station_id'], r['source_field'])
        if not all(key) or key in rows or r['status'] not in {'observed','unresolved','missing','unavailable'}:
            raise ValueError('Invalid row identity or status')
        if r['unit'] != 'observations' or r['slot'] not in {'combined','session_1','session_2'}:
            raise ValueError('Unreviewed unit or session')
        valid = r['value'].isascii() and r['value'].isdigit() if r['status']=='observed' else r['value']==''
        if not valid:
            raise ValueError('Invalid observation')
        rows[key] = r
    return rows


def candidate(repo, receipt, output):
    spec = json.loads(receipt.read_bytes())
    year = str(spec['year'])
    version = spec['version']
    from scripts.build_catalog import ROOT, checked_package
    ledger=json.loads((ROOT/'releases/release-ledger.json').read_bytes())
    withdrawn={(r['dataset'],r['version']) for r in ledger['withdrawn']}
    versions=[counts.PATCH_VERSION]+[r['version'] for r in ledger['approved'] if r['dataset']==counts.DATASET]
    previous=next(v for v in reversed(versions) if (counts.DATASET,v) not in withdrawn)
    check_version(previous, version, spec['change'])
    if version in versions:
        raise ValueError('A cited version cannot be reused')
    if spec['change'] == 'breaking':
        raise ValueError('Implement and review a new schema adapter for breaking changes')
    tree, _ = counts.bundle(repo, counts.load('coverage.json'), corrected=True)
    prefix = f'datasets/{counts.DATASET}/{counts.PATCH_VERSION}/'
    files = {p[len(prefix):]:b for p,b in tree.items() if p.startswith(prefix)}
    if previous != counts.PATCH_VERSION:
        entry=next(r for r in ledger['approved'] if r['dataset']==counts.DATASET and r['version']==previous)
        files=checked_package(ROOT/'releases/datasets'/counts.DATASET/previous,entry)
    manifest = json.loads(files.pop('datapackage.json'))
    source = spec['source']
    if not all(source.get(k) for k in ('origin','received','sha256','path')) or not spec['note'].strip():
        raise ValueError('Source provenance and change note required')
    resource(receipt.parent,source)
    updated = parse(resource(receipt.parent,spec['slice']))
    old = parse(files['series.csv'])
    before = {k:r for k,r in old.items() if k[0]==year}
    if bool(before) != (spec['change']=='correction'):
        raise ValueError('Use correction for an existing year and compatible for a new year')
    if not updated or any(k[0]!=year for k in updated):
        raise ValueError('Expected a complete single-year slice')
    if before and set(before)!=set(updated):
        raise ValueError('A value correction cannot change row membership')
    mapping=json.loads(files['mapping.json'])
    mapped = spec['mapping']
    if not all(k[2] in mapped and all(mapped[k[2]].get(f)==r[f] for f in ('slot','mode','breakdown')) for k,r in updated.items()):
        raise ValueError('Slice disagrees with reviewed source mapping')
    if before and mapped!=mapping[year]:
        raise ValueError('A correction cannot replace the field mapping')
    mapping[year]=mapped
    diff=[{'identity':k,'previous':before.get(k),'proposed':r} for k,r in updated.items() if before.get(k)!=r]
    if not diff:
        raise ValueError('Candidate contains no changes')
    old.update(updated)
    rows=[old[k] for k in sorted(old,key=lambda k:(int(k[0]),k[1],k[2]))]
    years=sorted({int(r['year']) for r in rows})
    # Keep the exact row order of predecessor slices, including unaffected years.
    for y in years:
        if str(y)==year:
            annual=[r for r in rows if r['year']==year]
            files[f'{y}.csv']=counts.csv_data(annual,counts.FIELDS)
    files['series.csv']=counts.csv_data([r for y in years for r in parse(files[f'{y}.csv']).values()],counts.FIELDS)
    files['mapping.json']=encoded(mapping)
    files['changes.md']=(spec['note'].strip()+'\n').encode()
    manifest.update(version=version,coverage=years,synthetic=spec.get('fixture',False),citation=manifest['citation'].replace(previous,version))
    manifest['sources'].append({k:source[k] for k in ('origin','received','sha256')})
    manifest['resources']=[dict(name=Path(k).stem,path=k,bytes=len(b),hash='sha256:'+digest(b)) for k,b in sorted(files.items())]
    files['datapackage.json']=encoded(manifest)
    output.mkdir(parents=True,exist_ok=False)
    destination=output/'candidate'/counts.DATASET/version
    destination.mkdir(parents=True)
    for k,b in files.items():
        (destination/k).write_bytes(b)
    (output/'review.json').write_bytes(encoded(dict(version=version,sha256=digest(files['datapackage.json']),changes=diff)))
    return destination


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('source_repo','receipt','output'):
        p.add_argument(arg,type=Path)
    a=p.parse_args()
    print(candidate(a.source_repo,a.receipt,a.output))

