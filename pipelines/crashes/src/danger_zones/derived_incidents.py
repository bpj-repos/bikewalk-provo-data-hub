"""Audit and preview explicit derived fields over normalized, unmerged source observations."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .common_structure import CONTRACT
from .config import DEFAULT_PRIVATE_DATA_ROOT
from .util import read_json, sha256_file, write_json
from .validate_normalized import validate_snapshot

RULES=CONTRACT.with_name('derived.yml')
PRIMARY={'udot.arcgis','portal.crashes','police.numbers','police.xlsx'}
MISSING_STATES={'not-supplied','null','blank','unknown','not-provided','not-applicable','invalid-source-value'}


def read_rules(path=RULES):
    rules=yaml.safe_load(path.read_text())
    if set(rules)!={'version','scope','references','completeness','behaviorFlags','driverCircumstances','maneuvers','nonmotoristSettings','lighting','injuryLevels','ageGroups'} or rules['version']!=2:
        raise ValueError('Unsupported derivation rules')
    for name in ['behaviorFlags','driverCircumstances','maneuvers','nonmotoristSettings','lighting','injuryLevels','ageGroups']:
        if not isinstance(rules[name],dict) or any(not isinstance(k,str) or v is not None and not isinstance(v,str) for k,v in rules[name].items()):
            raise ValueError('Derivation mappings must use explicit text keys/categories')
    return rules


def cell(row,key):return row['values'].get(key,{'value':None,'state':'not-supplied','columns':[]})

def code(row,key):
    value=cell(row,key)['value']
    return value.get('code') if isinstance(value,dict) else None


def result(value,status,support):
    return {'value':value,'availability':status,'support':support}


def support(rows,keys):
    return [{'observationId':r['observationId'],'fields':[k for k in keys if k in r['values']]} for r in rows if any(k in r['values'] for k in keys)]


def mapped_list(rows,keys,mapping,issues):
    found=set();known=0;missing=0
    for row in rows:
        for key in keys:
            c=cell(row,key);value=code(row,key)
            if c['state'] in MISSING_STATES or value is None:
                missing+=1;continue
            if value not in mapping:
                issues.append(key+':unmapped-code');missing+=1;continue
            mapped=mapping[value]
            if mapped is not None:found.add(mapped);known+=1
            elif value=='0':known+=1
            else:missing+=1
    status='complete' if known and not missing else 'partial' if known else 'unavailable'
    return result(sorted(found),status,support(rows,keys))


def age_group(age):
    return None if age is None else 'under18' if age < 18 else '18to64' if age < 65 else '65plus'


def derive(primary, related, rules):
    issues=[];out={}
    crash_rows=[r for r in related if r['table'] in {'portal.crashes','portal.rollups','udot.arcgis','police.numbers','police.xlsx'}]
    people=[r for r in related if r['entity']=='person'];vehicles=[r for r in related if r['entity']=='vehicle']
    modes=sorted({m for r in related for m in r.get('modes',[])})
    conflict=False
    for key,mode in [('classification.bicycle_involved','bicycle'),('classification.pedestrian_involved','pedestrian')]:
        if mode in modes and any(cell(r,key)['value'] is False for r in crash_rows):conflict=True
    out['active_modes']=result(modes,'conflicting' if conflict else 'complete' if modes else 'unavailable',support(related,['classification.bicycle_involved','classification.pedestrian_involved','person.type','travel.police_mode']))
    at_people=[r for r in people if code(r,'person.type') in {'3','4','5'}]
    unclassified=sum(code(r,'person.type') not in {'1','2','3','4','5'} for r in people)
    injuries=Counter();unknown=0;by_mode=defaultdict(Counter);ages=defaultdict(Counter)
    for row in at_people:
        severity=code(row,'person.injury_severity')
        mode={'3':'Pedestrian','4':'Bicyclist','5':'Other conveyance user'}[code(row,'person.type')]
        by_mode[mode][rules['injuryLevels'].get(severity,'Unknown injury')]+=1
        ages[mode][age_group(cell(row,'person.age')['value']) or 'unknown']+=1
        if severity in rules['injuryLevels']:injuries[severity]+=1
        else:unknown+=1
    types={code(r,'person.type') for r in at_people}
    missing_flagged_people=('bicycle' in modes and '4' not in types) or ('pedestrian' in modes and not types.intersection({'3','5'}))
    complete=bool(at_people) and not unknown and not unclassified and not missing_flagged_people and not conflict
    injury_status='complete' if complete else 'partial' if at_people else 'unavailable'
    injury_value={'identifiedATPeople':len(at_people),'knownInjuries':{rules['injuryLevels'][k]:v for k,v in sorted(injuries.items())},
                  'highestKnown':rules['injuryLevels'][max(injuries,key=int)] if injuries else None,'unknownInjuries':unknown,'unclassifiedPeople':unclassified,'byMode':dict(sorted(by_mode.items()))} if people else None
    evidence=support(people,['person.type','person.injury_severity'])
    out['at_injury_summary']=result(injury_value,injury_status,evidence)
    age_status='unavailable' if not at_people else 'partial' if any(c.get('unknown') for c in ages.values()) or unclassified or missing_flagged_people or conflict else 'complete'
    out['at_age_groups']=result(dict(sorted(ages.items())) if at_people else None,age_status,support(at_people,['person.type','person.age']))
    for key in ['condition.weather','condition.road_surface']:
        c=cell(primary,key)
        out[key.split('.')[-1]]=result(c['value'],'complete' if c['state']=='reported' and c['value'] is not None else 'unavailable',support([primary],[key]))
    serious=bool(injuries.get('4') or injuries.get('5'))
    out['at_serious_or_fatal']=result(True if serious else False if complete else None,injury_status,evidence)
    flags=set();available=0;missing_flags=0;flag_conflict=False
    for key,label in rules['behaviorFlags'].items():
        values=[cell(r,key)['value'] for r in crash_rows]
        if any(v is True for v in values):flags.add(label)
        if True in values and False in values:flag_conflict=True
        if any(v is not None for v in values):available+=1
        else:missing_flags+=1
    out['reported_behavior_flags']=result(sorted(flags),'conflicting' if flag_conflict else 'complete' if available and not missing_flags else 'partial' if available else 'unavailable',support(crash_rows,list(rules['behaviorFlags'])))
    drivers=[r for r in people if code(r,'person.type')=='1']
    out['reported_driver_circumstances']=mapped_list(drivers,['person.driver_contributing_first','person.driver_contributing_second'],rules['driverCircumstances'],issues)
    out['vehicle_movements_present']=mapped_list(vehicles,['vehicle.maneuver'],rules['maneuvers'],issues)
    out['nonmotorist_setting']=mapped_list(at_people,['person.nonmotorist_location'],rules['nonmotoristSettings'],issues)
    light=cell(primary,'condition.light');v=light['value'];label=v.get('label') if v else None
    if label and label not in rules['lighting']:issues.append('condition.light:unmapped-label')
    lighting=rules['lighting'].get(label)
    out['lighting_group']=result(lighting,'complete' if lighting else 'unavailable',support([primary],['condition.light']))
    occurred=cell(primary,'time.occurred_at')['value'];reported=cell(primary,'time.reported_at')['value']
    t=occurred or reported;basis='occurrence' if occurred else 'report'
    time=None
    if t:
        local_date=t['date'];clock=t['time'];zone=t['zone'];offset=t['offset']
        if offset:
            instant=datetime.fromisoformat(t['date']+'T'+(clock or '00:00:00')+offset)
            local=instant.astimezone(ZoneInfo('America/Denver'))
            local_date=local.date().isoformat();clock=local.time().isoformat();zone='America/Denver'
        d=date.fromisoformat(local_date)
        time={'date':local_date,'year':d.year,'month':d.month,'weekday':d.strftime('%A'),'hour':int(clock[:2]) if clock else None,
              'clock':clock,'basis':basis,'precision':t['precision'],'timezoneStatus':'resolved' if offset else 'named-zone-no-offset' if zone else 'unspecified-local-clock','zone':zone}
    out['time']=result(time,'complete' if occurred and t['offset'] else 'partial' if t else 'unavailable',support([primary],['time.occurred_at','time.reported_at']))
    description=cell(primary,'location.police_description')['value'] or cell(primary,'location.description')['value']
    road=cell(primary,'location.road_name')['value'];city=cell(primary,'location.geographic_city')['value']
    label=description or (' · '.join(v for v in [road,city.get('label') if city else None] if v) if road else None)
    out['location_label']=result(label,'complete' if description else 'partial' if label else 'unavailable',support([primary],['location.police_description','location.description','location.road_name','location.geographic_city']))
    point=cell(primary,'location.point')['value']
    out['location_method']=result('provider-supplied-point' if point else None,'complete' if point else 'unavailable',support([primary],['location.point']))
    out['location_status']=result('usable-source-point' if point else 'not-in-source','complete',support([primary],['location.point']))
    return {'observationId':primary['observationId'],'source':primary['source'],'snapshotId':primary['snapshotId'],
            'sourceRecordId':primary['sourceRecordId'],'table':primary['table'],'derived':out,'issues':issues}


def preview(records,rules):
    grouped=defaultdict(list)
    for row in records:grouped[(row['source'],row['snapshotId'],row['sourceRecordId'])].append(row)
    output=[];counts=defaultdict(Counter);distributions=defaultdict(Counter);issues=Counter()
    for primary in records:
        if primary['table'] not in PRIMARY:continue
        related=grouped[(primary['source'],primary['snapshotId'],primary['sourceRecordId'])]
        row=derive(primary,related,rules);output.append(row)
        time=row['derived']['time']['value'];year=str(time['year']) if time else 'unknown'
        for key,value in row['derived'].items():
            counts[(primary['source'],year,key)][value['availability']]+=1
            sampled=value['value']
            if key=='location_label':sampled=sampled is not None
            if key=='time' and sampled:sampled={k:sampled[k] for k in ['basis','precision','timezoneStatus','hour']}
            encoded=json.dumps(sampled,sort_keys=True)
            distributions[(primary['source'],key)][encoded]+=1
        issues.update(primary['source']+':'+s for s in row['issues'])
    audit={'schemaVersion':1,'denominator':'source crash/report observations, not unique incidents or person counts','sourceObservations':len(output),'newCrossSourceLinks':0,
           'coverage':[{'source':s,'year':y,'field':f,'observations':sum(c.values()),'availability':dict(c)} for (s,y,f),c in sorted(counts.items())],
           'distributions':[{'source':s,'field':f,'values':[{'value':json.loads(v),'observations':n} for v,n in sorted(c.items())]} for (s,f),c in sorted(distributions.items())],
           'issues':dict(issues)}
    return output,audit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--normalized',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True,help='New private preview directory')
    parser.add_argument('--audit-only',action='store_true')
    args=parser.parse_args()
    if args.output.exists() or not args.output.resolve().is_relative_to(DEFAULT_PRIVATE_DATA_ROOT.resolve()):
        parser.error('Use a new directory under tools/.danger-zone-private/')
    validate_snapshot(args.normalized)
    records=[json.loads(s) for s in (args.normalized/'observations.jsonl').read_text().splitlines()]
    output,audit=preview(records,read_rules())
    args.output.mkdir(parents=True,exist_ok=False);write_json(args.output/'audit.json',audit)
    if not args.audit_only and not audit['issues']:
        with (args.output/'derived.jsonl').open('w') as handle:
            for row in output:handle.write(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n')
        write_json(args.output/'manifest.json',{'schemaVersion':1,'kind':'source-qualified-derived-incidents','rulesVersion':read_rules()['version'],
                   'normalizedManifestSha256':sha256_file(args.normalized/'manifest.json'),'rulesSha256':sha256_file(RULES),
                   'scriptSha256':sha256_file(Path(__file__)),'sha256':sha256_file(args.output/'derived.jsonl'),'observations':len(output),'newCrossSourceLinks':0})
    print(json.dumps({'sourceObservations':len(output),'issues':audit['issues'],'output':str(args.output)}))
    return 1 if audit['issues'] else 0


if __name__=='__main__':raise SystemExit(main())
