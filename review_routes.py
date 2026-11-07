"""Compare a complete Safe Routes candidate to the approved hub package by feature identity."""
import argparse
import json
from pathlib import Path

from safe_routes import DATASET, LAYERS

def compare(before,after):
    diff={}
    for layer in LAYERS:
        def index(folder):
            rows=json.loads((folder/(layer+'.geojson')).read_bytes())['features']
            result={r['id']:r for r in rows}
            if len(result)!=len(rows):
                raise ValueError('Duplicate ID in '+layer)
            return result
        old,new=index(before),index(after)
        changed=[]
        for key in sorted(old.keys() & new.keys()):
            a,b=old[key],new[key]
            def content(f):
                return (f['geometry'],{k:v for k,v in f['properties'].items() if k!='sourceRetrievedAt'})
            if content(a)!=content(b):
                changed.append(key)
        diff[layer]=dict(added=sorted(new.keys()-old.keys()),removed=sorted(old.keys()-new.keys()),changed=changed)
    return diff

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('candidate',type=Path)
    args=p.parse_args()
    from build_hub import ROOT
    ledger=json.loads((ROOT/'releases.json').read_bytes())
    retired={r['version'] for r in ledger['withdrawn'] if r['dataset']==DATASET}
    version=next(r['version'] for r in reversed(ledger['approved']) if r['dataset']==DATASET and r['version'] not in retired)
    print(json.dumps(compare(ROOT/'approved'/DATASET/version,args.candidate),indent=2))

