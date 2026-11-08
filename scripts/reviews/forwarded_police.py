"""Review forwarded PRPD email tables against a pinned private collection, offline."""
import argparse
from collections import Counter
import csv
from datetime import datetime
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from danger_zones.police_forward import read_forward_rows
from danger_zones.incident_updates import candidate_rows, local_rows
from danger_zones.match_review import review, POLICY
from danger_zones.normalize import normalize_police_mode
from danger_zones.police_datastore import StreetIntersectionGeocoder, normalize_police_location
from danger_zones.util import sha256_file


def read_forward(path):
    result=[]
    for row in read_forward_rows(path):
        when=row['observed_at']
        timed=isinstance(when,datetime)
        result.append(dict(id=row['incident_id'],date=(when.date() if timed else when).isoformat(),
                           time=when.time().isoformat() if timed else None,address=row['location_raw'],modeRaw=row['mode_raw']))
    return result


def write_cases(path, records):
    with path.open('x',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['police_case','report_date','reported_time','status','top_tier','state_candidates',
                         'competing_police_cases','conflicts','source_message'])
        for key,record in sorted(records.items(),key=lambda item:(item[1]['row']['date'],item[0])):
            r=record['review']
            rows=r['candidates']
            best=[c for c in rows if c['rank']==rows[0]['rank']]
            writer.writerow([key,record['row']['date'],record['row']['time'],r['status'],
                             best[0]['tier'] if best else '', ' '.join(c['stateId'] for c in best),
                             ' '.join(sorted({v for c in best for v in c['competingPoliceIds']})),
                             ' '.join(sorted({v for c in best for v in c['conflicts']})),record['source']])


def run(manifest,pin,street,street_sha,sources,output):
    if sha256_file(manifest)!=pin or sha256_file(street)!=street_sha:
        raise ValueError('Pinned input differs')
    m=json.loads(manifest.read_bytes())
    state_path=manifest.parent/'input-state.json.gz'
    links_path=manifest.parent/'reviewed-links.json'
    for f in (state_path,links_path):
        if sha256_file(f)!=m['files'][f.name]:
            raise ValueError('Invalid managed release member')
    with gzip.open(state_path,'rt') as stream:
        state=json.load(stream)
    linked={r['policeId'].split(':',1)[1]:r['udotId'] for r in json.loads(links_path.read_bytes())}
    geocoder=StreetIntersectionGeocoder(street)
    existing={r['id']:r for r in local_rows(state['observations'].values())}
    locals_=dict(existing)
    records={}
    inputs={}
    for f in sources:
        inputs[f.name]=sha256_file(f)
        for raw in read_forward(f):
            key=raw['id']
            if key in records:
                raise ValueError('Repeated police ID across deliveries')
            loc=normalize_police_location(raw['address'])
            geo=geocoder.geocode(loc['addressPartRaw']) or {'status':'unresolved'}
            point=geo.get('coordinates')
            mode=normalize_police_mode({'Electric Bike':'Electric Bicycle','E-Scooter':'Electric Scooter'}.get(raw['modeRaw'],raw['modeRaw']))
            local=dict(id=key,date=raw['date'],time=raw['time'],address=loc['addressPartRaw'],notes=loc['noteRaw'],
                       mode=mode,coordinates=[point['lng'],point['lat']] if point else None,geocoding=geo)
            records[key]=dict(source=f.name,row=raw,inCollection=key in existing,existingLink=linked.get(key))
            if key in existing:
                records[key]['priorRow']=existing[key]
            locals_[key]=local
    crashes=candidate_rows(state)
    reviewed=review(list(locals_.values()),crashes,json.loads(POLICY.read_bytes()))
    for r in reviewed:
        key=r['police']['id']
        if key in records:
            records[key]['review']=r
    if output.exists() or not output.resolve().is_relative_to(Path(__file__).resolve().parents[2]/'private'):
        raise ValueError('Use a new private hub output directory')
    output.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as tmp:
        dest=Path(tmp)/'review'
        dest.mkdir(mode=0o700)
        (dest/'review.json').write_text(json.dumps(dict(manifestSHA256=pin,streetSHA256=street_sha,
            policySHA256=sha256_file(POLICY),sourceHashes=inputs,
            latestCandidateDate=max(c['date'] for c in crashes),records=records),indent=2)+'\n')
        write_cases(dest/'cases.csv', records)
        dest.rename(output)
    print(len(records),'cases',dict(Counter(r['review']['status'] for r in records.values())))
    print('Existing police IDs:',sum(r['inCollection'] for r in records.values()),'previous links:',sum(bool(r['existingLink']) for r in records.values()))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ['manifest','pin','street','street_sha','output']:
        p.add_argument(k,type=str if k in ('pin','street_sha') else Path)
    p.add_argument('sources',nargs='+',type=Path)
    a=p.parse_args()
    run(a.manifest,a.pin,a.street,a.street_sha,a.sources,a.output)
