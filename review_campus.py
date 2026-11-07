"""Report changes to reviewed Treeside records and the provider's campus address."""
import argparse
import hashlib
import json
from pathlib import Path
from safe_routes import LAYERS,endpoint,query

ROOT=Path(__file__).resolve().parent


def inventory(receipt,address):
    rows={}
    for key in LAYERS:
        for f in json.loads((receipt/(key+'.json')).read_bytes()):
            if f['properties'].get('ID_SCHOOL')==773 and f['properties']['NAME_DISTRICT']=='CHARTER':
                payload=json.dumps(f,sort_keys=True,separators=(',',':')).encode()
                rows[key+':'+f['properties']['GlobalID']]=hashlib.sha256(payload).hexdigest()
    return dict(providerAddresses=sorted(address),features=rows)


def review(receipt):
    metadata=query(endpoint('safe-routes-schools')+'/query',dict(where="NAME_DISTRICT='CHARTER' AND ID_SCHOOL=773",outFields='ADDRESS_SCHOOL',returnGeometry='false',f='json'))
    current=inventory(receipt,[r['attributes']['ADDRESS_SCHOOL'] for r in metadata['features']])
    old=json.loads((ROOT/'treeside-baseline.json').read_bytes())
    return dict(addressBefore=old['providerAddresses'],addressNow=current['providerAddresses'],
                changedIDs=sorted(k for k in old['features'].keys()|current['features'].keys()
                                  if old['features'].get(k)!=current['features'].get(k)),
                requiresCampusVerification=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('receipt',type=Path)
    result=review(p.parse_args().receipt)
    print(json.dumps(result,indent=2))
    if result['addressNow']!=result['addressBefore'] or result['changedIDs']:
        raise SystemExit('Treeside campus evidence changed; review before releasing a new candidate')

