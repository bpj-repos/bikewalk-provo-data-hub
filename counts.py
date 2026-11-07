"""Prepare a counts release from checksummed Git blobs; never contacts a live service."""
import argparse
import csv
import hashlib
import io
import json
import subprocess
from pathlib import Path
from release import DATASET, VERSIONS, encoded, expected

HERE = Path(__file__).resolve().parent
META = HERE / 'counts'
VERSION = '1.0.0'
PREFIX = f'datasets/{DATASET}/{VERSION}/'
FIELDS = {
    'year': 'Source collection year', 'station_id': 'Source ID, scoped to year and layer',
    'station_name': 'Original station label', 'slot': 'session_1, session_2, or combined',
    'weekday': 'Verified or source-labeled session day; empty when unknown',
    'date': 'Workbook date for reconciled populated 2019 sessions, otherwise empty',
    'duration_minutes': 'Documented session window, not observer attendance; empty when unverified',
    'mode': 'all, bicycle, walking, scooter, or other', 'breakdown': 'total, F or M as recorded by source',
    'unit': 'observations', 'source_field': 'Original annual export field',
    'status': 'observed, missing, unavailable, or unresolved',
    'value': 'Count including numeric zero. Blank for other statuses.',
}


def csv_data(rows, fields):
    buf = io.StringIO(newline='')
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode()


def load(name):
    return json.loads((META / name).read_bytes())


def prepare(repo, years):
    inventory, cross = load('sources.json'), load('crosswalk.json')
    inputs = {}
    for item in inventory['inputs']:
        raw = subprocess.check_output(['git', '-C', str(repo), 'show',
                                       inventory['commit'] + ':' + item['path']])
        if hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('Source hash mismatch: ' + item['path'])
        inputs[item['path']] = raw
    audit = {(r['id'], r['slot']): r for r in load('workbook-review.json')}
    rows, issues = [], []
    for year in years:
        prefix = f'apps/maps/public/data/active-transportation-counts/{year}'
        strings = list(csv.DictReader(io.StringIO(inputs[prefix + '.csv'].decode())))
        records = json.loads(inputs[prefix + '.json'])
        mapping = cross[str(year)]
        if len(strings) != len(records) or len(records) != 14:
            raise ValueError(f'Incomplete annual roster for {year}')
        seen = set()
        for raw, rec in zip(strings, records):
            if set(raw) != set(mapping) or set(rec) != set(mapping):
                raise ValueError(f'Unmapped or missing fields in {year}')
            for k,v in rec.items():
                if raw[k] != ('' if v is None else str(v)):
                    raise ValueError(f'CSV/JSON mismatch {year} {k}')
            station = rec['FID' if year == 2026 else 'OBJECTID']
            if station in seen:
                raise ValueError('Duplicate station ID')
            seen.add(station)
            index = {(m['mode'],m['slot'],m['breakdown']):rec[k] for k,m in mapping.items()
                     if m['role']=='measure'}
            for field,m in mapping.items():
                if m['role'] != 'measure':
                    continue
                slot,mode,part = m['slot'],m['mode'],m['breakdown']
                value = rec[field]
                if value is not None and (type(value) != int or value < 0):
                    raise ValueError(f'Invalid count {year} {station} {field}')
                status = 'missing' if value is None else 'observed'
                day = {'session_1':'Tuesday','session_2':'Saturday','combined':''}[slot]
                date = duration = ''
                reasons = []
                if year == 2019 and slot != 'combined':
                    entry = audit.get((station,1 if slot == 'session_1' else 2))
                    day = ''
                    if entry and entry['has_count'] and not entry['differences']:
                        day,date = ('Thursday','2019-09-12') if slot=='session_1' else ('Saturday','2019-09-14')
                        duration = 120
                    if entry and field in entry['differences']:
                        reasons.append('Workbook/export disagreement')
                if year==2019 and station==10 and slot in ('session_1','combined') and mode=='all':
                    reasons.append('Total overlaps disputed Heritage Halls counts')
                if value is not None and slot!='combined' and index.get(('all',slot,'total')) is None:
                    reasons.append('Value stored without a session total')
                if part in ('F','M') and value is not None:
                    pair=[index.get((mode,slot,p)) for p in ('F','M')]
                    if None in pair or sum(pair)!=index.get((mode,slot,'total')):
                        reasons.append('Recorded breakdown does not reconcile')
                if reasons:
                    issues.append(dict(year=year,station=station,field=field,source_value=value,reason='; '.join(reasons)))
                    status,value='unresolved',None
                rows.append(dict(year=year,station_id=station,station_name=rec['StreetName'],
                                 slot=slot,weekday=day,date=date,duration_minutes=duration,
                                 mode=mode,breakdown=part,unit='observations',source_field=field,
                                 status=status,value=value))
    return rows, issues


PATCH_VERSION = '1.0.1'
PATCH_NOTE = ('For 2026, combined scooter observations are the sum of the two scooter session fields. '
              'At all 14 stations the original combined field equals Tuesday scooters plus Saturday Other. '
              'The corrected total is 283 (186 Tuesday and 97 Saturday); the original field sums to 236. '
              'Version 1.0.0 preserves the original values.')


def correct_scooters(rows):
    by_station = {}
    for row in rows:
        if row['year'] == 2026:
            by_station.setdefault(row['station_id'], {})[row['source_field']] = row
    for fields in by_station.values():
        sessions = [fields[key] for key in ('y26Scoot_T', 'y26Scoot_Sat')]
        combined = fields['y26Scoot']
        if all(r['status'] == 'observed' and type(r['value']) is int for r in sessions):
            combined.update(value=sum(r['value'] for r in sessions), status='observed')
        else:
            combined.update(value=None, status='unresolved')


def bundle(repo, years, *, corrected=False):
    rows, issues = prepare(repo,years)
    version = PATCH_VERSION if corrected else VERSION
    prefix = f'datasets/{DATASET}/{version}/'
    if corrected:
        correct_scooters(rows)
    files = {'series.csv':csv_data(rows,FIELDS)}
    for year in years:
        files[f'{year}.csv'] = csv_data([r for r in rows if r['year']==year],FIELDS)
    files['dictionary.json'] = encoded({'fields':[dict(name=k,description=v,type='integer' if k in
        ('year','duration_minutes','value') else 'string') for k,v in FIELDS.items()]})
    files['mapping.json'] = encoded({str(y):load('crosswalk.json')[str(y)] for y in years})
    files['protocol.md'] = (META/'protocol.md').read_bytes()
    files['changes.md'] = b'Initial release of verified annual station measures. See protocol and mapping for limitations.\n'
    if corrected:
        mapping=json.loads(files['mapping.json'])
        mapping['2026']['y26Scoot'].update(decision='derived sum of two observed session counts',
                                          inputs=['y26Scoot_T','y26Scoot_Sat'])
        files['mapping.json']=encoded(mapping)
        files['changes.md']=(PATCH_NOTE+'\n').encode()
        files['protocol.md']=files['protocol.md'].replace(
            b'Combined values are source-reported. The 2026 combined scooter column sums to 236; the session scooter columns sum to 283. Preserve both measures.',
            ('Combined values are source-reported except for 2026 scooters. '+PATCH_NOTE).encode())
    manifest = dict(name=DATASET,version=version,title='Provo annual active transportation counts',
        coverage=years, synthetic=False, sourceSnapshot=load('sources.json')['commit'],
        sources=[i for i in load('sources.json')['inputs'] if i['year'] in years or i['year'] is None],
        preparation='Annual station export values aligned to documented source fields; unresolved values withheld.',
        attribution='BikeWalk Provo and Provo City active transportation count contributors',
        licenses=[dict(name='CC0-1.0',path='https://creativecommons.org/publicdomain/zero/1.0/')],
        citation=f'BikeWalk Provo. Provo annual active transportation counts, {version}. https://bikewalk-provo-data-hub.vercel.app/{prefix}datapackage.json',
        resources=[dict(name=Path(k).stem,path=k,bytes=len(v),hash='sha256:'+hashlib.sha256(v).hexdigest())
                   for k,v in files.items()])
    files['datapackage.json']=encoded(manifest)
    tree=bundle(repo,years)[0] if corrected else expected(VERSIONS)
    catalog=json.loads(tree['catalog.json'])
    catalog['synthetic']=False
    dataset=catalog['datasets'][0]
    dataset['current']=version
    dataset['releases'].append(dict(version=version,manifest='/'+prefix+'datapackage.json',
                              sha256=hashlib.sha256(files['datapackage.json']).hexdigest()))
    if dataset['releases'][-1] != load('approved-pin-1.0.1.json' if corrected else 'approved-pin.json'):
        raise ValueError(f'Release differs from the approved {version} pin')
    tree['catalog.json']=encoded(catalog)
    tree.update({prefix+k:v for k,v in files.items()})
    return tree,issues


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source_repo',type=Path)
    p.add_argument('output',type=Path)
    args=p.parse_args()
    tree,issues=bundle(args.source_repo,load('coverage.json'),corrected=True)
    # Stage privately. A release owner separately approves publication of this exact tree.
    args.output.mkdir(parents=True,exist_ok=False)
    for name,data in tree.items():
        dest=args.output/'public'/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(data)
    (args.output/'review-issues.json').write_bytes(encoded(issues))
