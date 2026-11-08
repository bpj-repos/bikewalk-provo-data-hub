"""Stage a verified Safe Routes pin for Projects or the Streets Watch legacy endpoint."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

from scripts.build_demo_counts import encoded
from scripts.safe_routes import DATASET, HOST, LAYERS


def adopt(previous,output,version,pin,producer):
    base=f'{HOST}/datasets/{DATASET}/{version}/'
    def download(name):
        with urlopen(base+name,timeout=45) as response:
            return response.read()
    raw=download('datapackage.json')
    if hashlib.sha256(raw).hexdigest()!=pin:
        raise ValueError('Unverified manifest')
    package=json.loads(raw)
    if (package['name'],package['version'])!=(DATASET,version):
        raise ValueError('Unexpected manifest')
    files={}
    for r in package['resources']:
        name=r['path']
        if Path(name).name!=name or name in files:
            raise ValueError('Invalid resource path')
        data=download(name)
        if len(data)!=r['bytes'] or 'sha256:'+hashlib.sha256(data).hexdigest()!=r['hash']:
            raise ValueError('Resource mismatch: '+name)
        files[name]=data
    compat=json.loads(previous.read_bytes())
    audit=json.loads(files['sources.json'])['review']
    for layer in compat['layerCatalog']:
        key=layer['key']
        data=files[key+'.geojson']
        layer.update(featureCount=len(json.loads(data)['features']),sha256=hashlib.sha256(data).hexdigest())
    if set(l['key'] for l in compat['layerCatalog'])!=set(LAYERS):
        raise ValueError('Unexpected legacy manifest')
    warnings=[package['notice']]
    for key,summary in audit.items():
        if summary['rejected'] or summary['missingSchoolId']:
            warnings.append(f"{key}: {len(summary['rejected'])} records without geometry; {summary['missingSchoolId']} features without provider school ID.")
    compat['generatedAt']=package['sourceRetrievedAt']
    if 'releaseId' in compat:
        compat['releaseId']=f'{DATASET}-{version}'
    compat['sourceFreshness'][0].update(currentThrough=package['providerApprovalDate'],lastImportedAt=package['sourceRetrievedAt'],snapshotId=f'{DATASET}-{version}',warnings=warnings)
    if 'approval' in compat:
        compat.update(approval='BikeWalk approved hub pin '+pin,producerCommit=producer)
    output.mkdir(parents=True,exist_ok=False)
    (output/'manifest.json').write_bytes(encoded(compat))
    (output/'datapackage.json').write_bytes(raw)
    for k in LAYERS:
        (output/(k+'.geojson')).write_bytes(files[k+'.geojson'])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('previous',type=Path)
    p.add_argument('output',type=Path)
    p.add_argument('version')
    p.add_argument('sha256')
    p.add_argument('producer')
    a=p.parse_args()
    adopt(a.previous,a.output,a.version,a.sha256,a.producer)

