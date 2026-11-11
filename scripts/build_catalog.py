"""Restore approved releases into a new private staging directory."""
import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

from scripts import build_counts_releases as counts
from scripts.build_demo_counts import encoded

ROOT = Path(__file__).resolve().parents[1]


def checked_package(directory, entry):
    raw=(directory/'datapackage.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=entry['sha256']:
        raise ValueError('Manifest pin mismatch')
    m=json.loads(raw)
    if (m['name'],m['version']) != (entry['dataset'],entry['version']):
        raise ValueError('Package identity mismatch')
    files={'datapackage.json':raw}
    for r in m['resources']:
        name=r['path']
        if Path(name).name!=name or name in files:
            raise ValueError('Bad resource path')
        b=(directory/name).read_bytes()
        if len(b)!=r['bytes'] or 'sha256:'+hashlib.sha256(b).hexdigest()!=r['hash']:
            raise ValueError('Bad resource: '+name)
        files[name]=b
    return files


def download_zip(tree, release):
    prefix=release['manifest'].lstrip('/').rsplit('/',1)[0]+'/'
    raw=tree[prefix+'datapackage.json']
    manifest=json.loads(raw)
    for part in (manifest['name'],manifest['version']):
        if Path(part).name!=part or part in ('','.','..') or '\\' in part or ':' in part:
            raise ValueError('Invalid download identity')
    files={'datapackage.json':raw}
    for resource in manifest['resources']:
        name=resource['path']
        if Path(name).name!=name or name in ('','.','..') or name in files or '\\' in name or ':' in name:
            raise ValueError('Bad download resource path')
        data=tree[prefix+name]
        if len(data)!=resource['bytes'] or 'sha256:'+hashlib.sha256(data).hexdigest()!=resource['hash']:
            raise ValueError('Bad download resource: '+name)
        files[name]=data
    folder=f"{manifest['name']}-{manifest['version']}"
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo(folder+'/'+name,date_time=(1980,1,1,0,0,0))
            info.create_system=3
            info.external_attr=0o100644 << 16
            archive.writestr(info,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    return output.getvalue()


def build(repo, output, approvals=None):
    tree,_=counts.bundle(repo,counts.load('coverage.json'),corrected=True)
    catalog=json.loads(tree['catalog.json'])
    ledger=json.loads((ROOT/'releases/release-ledger.json').read_bytes()) if approvals is None else approvals
    by_id={d['id']:d for d in catalog['datasets']}
    public_cities = {(r['dataset'], r['version']) for r in ledger.get('publicCityReleases', [])}
    def included(dataset, version):
        return not dataset.endswith('-annual-at-crash-aggregates') or (dataset, version) in public_cities

    for entry in ledger['approved']:
        dataset,version=entry['dataset'],entry['version']
        for part in (dataset,version):
            if Path(part).name!=part or part in ('','.','..'):
                raise ValueError('Invalid package identity')
        if not included(dataset, version):
            continue
        path=f'datasets/{dataset}/{version}/'
        d=by_id.setdefault(dataset,dict(id=dataset,releases=[]))
        if any(r['version']==version for r in d['releases']):
            raise ValueError('Cannot replace a pin')
        files=checked_package(ROOT/'releases/datasets'/dataset/version,entry)
        if json.loads(files['datapackage.json']).get('synthetic'):
            raise ValueError('Cannot promote a drill fixture')
        tree.update({path+k:v for k,v in files.items()})
        d['releases'].append(dict(version=version,manifest='/'+path+'datapackage.json',sha256=entry['sha256']))
        d['current']=version
    for w in ledger['withdrawn']:
        if not included(w['dataset'], w['version']):
            continue
        d=by_id[w['dataset']]
        r=next(r for r in d['releases'] if r['version']==w['version'])
        prefix=r['manifest'].lstrip('/').rsplit('/',1)[0]+'/'
        tree={k:b for k,b in tree.items() if not k.startswith(prefix)}
        r.update(status='withdrawn',notice=w['notice'],withdrawnAt=w['date'])
        if d['current']==w['version']:
            d['current']=next((p['version'] for p in reversed(d['releases']) if p.get('status')!='withdrawn'),None)
    catalog['datasets']=[d for dataset,d in by_id.items() if dataset not in ledger.get('retired', [])]
    for dataset in catalog['datasets']:
        for release in dataset['releases']:
            if release.get('status')=='withdrawn':
                continue
            path=f"downloads/{dataset['id']}/{release['version']}/{dataset['id']}-{release['version']}.zip"
            data=download_zip(tree,release)
            tree[path]=data
            release['download']=dict(path='/'+path,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    tree['catalog.json']=encoded(catalog)
    output.mkdir(parents=True,exist_ok=False)
    for path,b in tree.items():
        dest=output/'public'/path
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(b)
    (output/'vercel.json').write_bytes((ROOT/'config/vercel.json').read_bytes())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('repo',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args()
    build(a.repo,a.output)

