"""Audit stored event context and compare the same rules with nearby non-event windows."""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path

from danger_zones.common_structure import read_contract
from danger_zones.crash_enrichment import normalized_rows
from danger_zones.event_context import EventMatcher, local_time
from danger_zones.field_inventory import read_catalog
from danger_zones.incident_updates import flatten
from danger_zones.util import sha256_file, write_json


def review(collection):
    matcher = EventMatcher()
    groups = collection['records']
    if any(g.get('eventContext', {}).get('inputs_sha256') != matcher.version for g in groups):
        raise ValueError('Stored fields are missing or stale; enrich through the updater first')
    counts = defaultdict(Counter)
    reasons = defaultdict(Counter)
    positives = []
    catalog = read_catalog(); contract = read_contract(catalog=catalog)
    prepared = []
    for g in groups:
        for o in flatten({'records':[g]}).values():
            rows = normalized_rows(o,catalog,contract)
            year = (rows[0]['values'].get('time.occurred_at',{}).get('value') or {}).get('date','unknown')[:4]
            fields = next(e['fields'] for e in g['enrichment']['observations'] if e['observationId']==o['id'])
            for settings in matcher.series.values():
                key = settings['field'];value=fields[key]
                counts[(key,year,o['sourceKey'])][value['value']]+=1
                reasons[key].update(value['reasons'])
            prepared.append((g['id'],o,rows))
        for key,cell in g['eventContext']['fields'].items():
            if cell['value']=='likely_match':
                positives.append({'group_id':g['id'],'field':key,'matches':cell['matches']})
    event_days = {e['event_date'] for events in matcher.events.values() for e in events if e['status']!='canceled'}
    baseline = {s:list(events) for s,events in matcher.events.items()}
    controls = []
    for offset in (-14,-7,7,14):
        shifted = {s:[] for s in baseline}
        windows=Counter()
        for series,events in baseline.items():
            for e in events:
                day = date.fromisoformat(e['event_date'])+timedelta(days=offset)
                if e['status']!='held' or day.isoformat() in event_days or not matcher.policy['from']<=day.isoformat()<=matcher.policy['through']:
                    continue
                clone = dict(e,event_date=day.isoformat())
                for key in ('start_local','end_local','arrival_start','arrival_end','departure_start','departure_end'):
                    if clone[key]:clone[key]=(local_time(clone[key])+timedelta(days=offset)).isoformat()
                shifted[series].append(clone)
                windows[series]+=sum(bool(e[phase+'_start']) for phase in ('arrival','departure'))
        matcher.events=shifted
        matched=defaultdict(set)
        for identifier,o,rows in prepared:
            result=matcher.observation(o,rows)
            for key,cell in result.items():
                if cell['value']=='likely_match':matched[key].add(identifier)
        controls.append({'days_shifted':offset,'known_windows':dict(windows),
                         'distinct_crashes':{s['field']:len(matched[s['field']]) for s in matcher.series.values()}})
    return {'schemaVersion':1,'release_id':collection['snapshotId'],'event_context_inputs':matcher.inputs,
            'incident_groups':len(groups),
            'group_counts':{s['field']:dict(Counter(g['eventContext']['fields'][s['field']]['value'] for g in groups)) for s in matcher.series.values()},
            'by_year_and_source':[{'field':k,'year':y,'source':s,'counts':dict(v)} for (k,y,s),v in sorted(counts.items())],
            'observation_reasons':{k:dict(v) for k,v in reasons.items()},'positive_review':positives,
            'controls':controls,'control_method':'Shift documented windows +/-7 and +/-14 days, same local weekday/clock, excluding dates with another registered held/unverified event.',
            'limits':'Descriptive comparison. Source capture completeness, historical location use, missing clocks and unresolved departure windows limit both samples. No exposure denominator or causal estimate.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args()
    if a.output.exists():p.error('Output must be a new file')
    data=json.loads(a.input.read_text())
    if 'records' not in data:
        path=Path(data['path'])
        if sha256_file(path)!=data['sha256']:raise ValueError('Collection checksum mismatch')
        data=json.loads(path.read_text())
    write_json(a.output,review(data));print(a.output)
