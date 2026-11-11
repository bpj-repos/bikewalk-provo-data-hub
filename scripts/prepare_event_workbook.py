"""Prepare the event workbook's source tables from the maintained register and geometry."""
import argparse
import csv
from io import StringIO
import json
from pathlib import Path

from danger_zones.event_context import ROOT


def prepare(root=ROOT):
    policy=json.loads((root/'policy.json').read_text())
    events=[r for name in policy['registers'] for r in csv.DictReader(StringIO((root/name).read_text()))]
    events.sort(key=lambda r:(r['event_date'],r['series']))
    columns=['event_date','series','name','venue','status','start_local','end_local','start_basis','arrival_start','arrival_end','departure_start','departure_end','end_basis','event_id','source_url','source_sha256','detail_url','notes']
    coverage=json.loads((root/'coverage.json').read_text())
    coverage_rows=[]
    for series,season in sorted({(r['series'],r['season']) for r in events}):
        rows=[r for r in events if r['series']==series and r['season']==season]
        source=next((c for c in coverage if c['series']==series and c['season']==season),None)
        coverage_rows.append([series,season,len(rows),sum(r['status']=='held' for r in rows),sum(bool(r['arrival_start']) for r in rows),sum(bool(r['departure_start']) for r in rows),
                              'Schedule captured through '+source['through'] if source else rows[0]['notes'],source['url'] if source else rows[0]['source_url']])
    features=json.loads((root/'locations.geojson').read_text())['features']
    locations=[[', '.join(f['properties'][k]) if isinstance(f['properties'][k],list) else f['properties'][k] for k in ['id','name','review_status','valid_from','valid_through','match_types','series','basis','sources']] for f in features]
    return {'tabs':[
        {'name':'Events','headers':['Date (Mountain Time)','Series','Game or event','Venue','Status','Start (Mountain Time)','End or release (Mountain Time)','Start basis','Arrival begins (MT)','Arrival ends (MT)','Departure begins (MT)','Departure ends (MT)','End basis','Event ID','Source URL','Source SHA-256','Game details URL','Notes'],'rows':[[r[c] for c in columns] for r in events],'dateColumns':[0,5,6,8,9,10,11],'widths':[16,26,32,28,16,25,25,24,25,25,25,25,30,44,65,65,65,95]},
        {'name':'Coverage','headers':['Series','Season or edition','Entries','Held','Known arrival windows','Known departure windows','Coverage notes','Source URL'],'rows':coverage_rows,'dateColumns':[],'widths':[27,20,14,12,24,24,100,65]},
        {'name':'Locations','headers':['Feature ID','Street, crossing or parking','Review status','Effective from','Effective through','Match types','Applicable series','Geometry and use basis','Sources'],'rows':locations,'dateColumns':[],'widths':[42,42,20,18,18,22,60,105,110]}]}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args()
    a.output.write_text(json.dumps(prepare()))
