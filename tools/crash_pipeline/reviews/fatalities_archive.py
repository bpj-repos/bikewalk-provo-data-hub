"""Check the 1.1.0 extension independently against rows from the two city workbooks."""
from contextlib import closing
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import hashlib
import json
import sys
from openpyxl import load_workbook


def verify(package, prior, older, newer):
    raw_expected, identifiers, schemas, filters = {}, set(), [], []
    for path, first, last, checksum in [
        (older, 2010, 2017, '99eedb508fd52388f7c44dfaf7645e4b7816f53ceeb55a562be8458587c424c7'),
        (newer, 2018, 2026, '3405efb346c9b839a21a7812679b1a8dd6d504a8f24d775b985ef54c1b59ad14')
    ]:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == checksum
        with closing(load_workbook(path, read_only=True, data_only=True)) as wb:
            headers = {}
            def rows(name):
                sheet = wb[name]
                sheet.reset_dimensions()
                iterator = iter(sheet.values)
                headers[name] = next(iterator)
                return (dict(zip(headers[name], row)) for row in iterator)
            options = {r['Filter']:r['Value'] for r in rows('Filters')}
            filters.append({k:v for k,v in options.items() if k!='Date Selection'})
            deaths = defaultdict(list)
            for r in rows('Persons'):
                if str(r['injuryLevel']) == '5':
                    assert r['injuryLevel_label']=='Fatalities'
                    deaths[str(r['Crash_ID'])].append(r)
            rollups = {str(r['crash_id']):r for r in rows('Rollups')}
            vehicles = {str(r['Crash_ID']) for r in rows('Vehicles')}
            ids = set()
            for r in rows('Crashes'):
                key = str(r['Crash_ID'])
                assert key not in ids and key not in identifiers
                ids.add(key)
                if r['City_Geo']!='Provo' or not deaths[key]:
                    continue
                people = deaths[key]
                relevant = [p for p in people if str(p['personType']) in ('3','4','5')]
                if not relevant: continue
                assert len(people)==len(relevant) and key in vehicles
                assert str(r['crashSeverity'])=='5' and r['crashSeverity_label']=='Fatal'
                modes={str(p['personType']) for p in people}
                assert len(modes)==1
                mode={'3':'pedestrian','4':'bicycle','5':'other-conveyance'}[modes.pop()]
                for person in people:
                    assert person['personType_label'].startswith({'pedestrian':'Pedestrian','bicycle':'Pedalcyclist','other-conveyance':'Other Pedestrian'}[mode])
                if first==2010:
                    assert r['pedestrian_involved'] is None and r['cyclist_involved'] is None
                    assert rollups[key][{'pedestrian':'pedestrian_involved','bicycle':'cyclist_involved'}[mode]]=='Y'
                raw_date = r['crashDateandTime']
                if isinstance(raw_date, datetime):
                    stamp = raw_date
                elif '/' in raw_date:
                    stamp = datetime.strptime(raw_date,'%m/%d/%Y %I:%M:%S %p')
                else:
                    stamp = datetime.fromisoformat(raw_date)
                assert first<=stamp.year<=last
                raw_expected[key] = ([round(float(r['longitude']),4),round(float(r['latitude']),4)], stamp.strftime('%Y-%m'),mode,len(people))
            identifiers.update(ids)
            schemas.append(headers)
    assert schemas[0]==schemas[1] and filters[0]==filters[1]
    read=lambda p:json.loads((p/'fatal-crashes.geojson').read_bytes())['features']
    merged={r['id']:r for r in read(package)}
    old={r['id']:r for r in read(prior)}
    assert len(merged)==len(read(package))==25 and len(old)==17
    assert set(merged)==set(raw_expected)
    for key, (point,month,mode,deaths) in raw_expected.items():
        row=merged[key]
        assert row['geometry']=={'type':'Point','coordinates':point}
        assert row['properties']==dict(month=month,mode=mode,fatalities=deaths)
    assert all(merged[k]==f for k,f in old.items())
    added=[merged[k] for k in sorted(merged.keys()-old.keys())]
    print(json.dumps(dict(added=len(added),retained=len(old),nonoverlappingCityIDs=len(identifiers),
                          historicalByMode=Counter(r['properties']['mode'] for r in added),
                          deaths=sum(r['properties']['fatalities'] for r in merged.values())),indent=2))

if __name__=='__main__':
    verify(*map(Path,sys.argv[1:]))
