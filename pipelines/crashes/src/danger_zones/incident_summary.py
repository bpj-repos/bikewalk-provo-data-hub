"""Prepare map summaries for existing published features without changing their source grouping."""
from __future__ import annotations

import argparse
import copy
import json
from collections import defaultdict
from pathlib import Path

from .config import DEFAULT_PRIVATE_DATA_ROOT
from .util import read_json, sha256_file, write_json
from .validate_normalized import validate_snapshot

SOURCE_LABELS={'udot.arcgis':'UDOT ArcGIS','portal.crashes':'Utah DPS portal','portal.rollups':'Utah DPS portal rollups',
               'portal.persons':'Utah DPS portal','portal.vehicles':'Utah DPS portal',
               'police.numbers':'Provo Police','police.xlsx':'Provo Police'}
GROUPS=['Identity','When','Location','Transportation','Outcomes','Circumstances']


def group(key):
    if key.startswith(('identity.','agency.')):return 'Identity'
    if key.startswith('time.'):return 'When'
    if key.startswith(('location.','road.')):return 'Location'
    if key.startswith('injury.') or key.startswith('count.') and key!='count.vehicles':return 'Outcomes'
    if key.startswith(('travel.','vehicle.')) or key in {'person.type','count.vehicles','classification.bicycle_involved','classification.pedestrian_involved'}:return 'Transportation'
    return 'Circumstances'


def display(cell):
    value=cell['value']
    if value is None:
        return {'invalid-source-value':'Invalid source value','incomplete-coordinate':'Incomplete coordinate'}.get(cell['state'])
    if isinstance(value,bool):return 'Yes' if value else 'No'
    if isinstance(value,dict) and set(value)=={'code','label'}:
        return value['label'] or ('Source code '+str(value['code']))
    if isinstance(value,dict) and 'precision' in value:
        s=value['date']
        if value['time']:
            clock=value['time'][:5] if value['precision']=='minute' else value['time']
            s+=' '+clock
            s+=(' '+value['offset']) if value['offset'] else ' (UTC offset not supplied)'
        if value['zone']:s+=' '+value['zone']
        return s
    return str(value)


def sections(rows):
    grouped={name:{} for name in GROUPS}
    for row in rows:
        for key,cell in row['values'].items():
            # Only the already approved approximate feature position is public. No full-precision normalized points.
            if key=='location.point':continue
            text=display(cell)
            if text is None:continue
            label=key.split('.',1)[-1].replace('_',' ').capitalize()
            entries=grouped[group(key)]
            entry=entries.setdefault(key,{'key':key,'label':label,'values':[]})
            source=SOURCE_LABELS[row['table']]
            existing=next((v for v in entry['values'] if v['text']==text),None)
            if existing:
                if source not in existing['sources']:existing['sources'].append(source)
            else:entry['values'].append({'text':text,'sources':[source]})
    if rows and all(r['source']=='provo-police-incidents' for r in rows):
        for name,key,label in [('When','time.occurred_at','Occurrence date/time'),('Outcomes','injury.crash_severity','Crash severity')]:
            grouped[name][key]={'key':key,'label':label,'values':[{'text':'Not supplied by this source','sources':['Provo Police']} ]}
    return [{'heading':name,'entries':list(entries.values())} for name,entries in grouped.items() if entries]


FACTOR_LABELS={'speeding':'Speed-related involvement','distraction':'Distraction','drowsiness':'Drowsiness','dui':'DUI classification','failure-to-yield':'Failure to yield','hit-and-run':'Hit-and-run',
               'aggressive-driving':'Aggressive driving','disregarded-control':'Disregarded traffic control','wrong-way':'Wrong-way driving','alcohol-confirmed':'Alcohol confirmed','alcohol-suspected':'Alcohol suspected','drugs-confirmed':'Drugs confirmed','drugs-suspected':'Drugs suspected'}


def prepare_fields(rows,people,vehicles,derived):
    primary=[r for r in rows if r['table']!='portal.rollups']
    observations=[]
    for row in primary:
        if row['observationId'] not in derived:raise ValueError('Missing derived source observation')
        observations.append(derived[row['observationId']]['derived'])
    modes=sorted({m for o in observations for m in o['active_modes']['value']})
    mode_groups=set()
    for mode in modes:
        mode_groups.add('walking' if mode=='pedestrian' else 'bicycle' if mode in {'bicycle','electric-bicycle'} else 'other')
    sources=sorted({r['source'] for r in primary})
    severity=set();severity_labels=[]
    for row in primary:
        c=row['values'].get('injury.crash_severity',{});v=c.get('value')
        label=v.get('label') if v else None
        if label in {'Fatal','Suspected Serious Injury','Suspected Minor Injury','Possible injury','No injury'}:
            severity.add('fatal' if label=='Fatal' else 'serious' if label=='Suspected Serious Injury' else 'other')
            if label not in severity_labels:severity_labels.append(label)
    if not severity:severity.add('unknown')
    at_values=[o['at_serious_or_fatal']['value'] for o in observations]
    at_severity='serious-fatal' if True in at_values else 'other' if False in at_values else 'unknown'
    factors={m for o in observations for m in o['reported_behavior_flags']['value']}
    circumstances={m for o in observations for m in o['reported_driver_circumstances']['value']}
    if 'failure-to-yield' in circumstances:factors.add('failure-to-yield')
    movements=sorted({m for o in observations for m in o['vehicle_movements_present']['value']})
    settings=sorted({m for o in observations for m in o['nonmotorist_setting']['value']})
    light={o['lighting_group']['value'] for o in observations if o['lighting_group']['value']}
    lighting=sorted({'dark' if x.startswith('dark-') else x for x in light}) or ['unknown']
    times=[o['time']['value'] for o in observations if o['time']['value']]
    labels=list(dict.fromkeys(o['location_label']['value'] for o in observations if o['location_label']['value']))
    dates=[]
    for o in observations:
        t=o['time']['value']
        if not t:continue
        label='Crash date' if t['basis']=='occurrence' else 'Police report date'
        text=t['date']
        existing=next((d for d in dates if d['label']==label and d['text']==text),None)
        if not existing:dates.append({'label':label,'text':text})
    injuries=[]
    for person in people:
        t=person['values'].get('person.type',{}).get('value')
        if t and t.get('code') in {'3','4','5'}:
            severity_cell=person['values'].get('person.injury_severity',{})
            severity_value=severity_cell.get('value')
            injury=severity_value.get('label') if severity_value else None
            injuries.append((t.get('label') or 'Active transportation user')+': '+(injury or 'Injury information unavailable'))
    reported=[FACTOR_LABELS.get(x,x.replace('-',' ').capitalize()) for x in sorted(factors)]
    reported += [m.replace('-',' ').capitalize()+' vehicle present' for m in movements]
    if light:reported += [x.replace('-',' ').capitalize() for x in sorted(light)]
    if settings:reported += [x.replace('-',' ').capitalize()+' (reported non-motorist position)' for x in settings]
    return {'version':1,'filters':{'years':sorted({str(t['year']) for t in times}),'modeGroups':sorted(mode_groups),'fineModes':modes,
             'crashSeverity':sorted(severity),'atSeverity':at_severity,'factors':sorted(factors),'lighting':lighting,'sources':sources},
            'overview':{'locationLabels':labels,'dates':dates,'atInjuries':injuries,'crashSeverity':severity_labels,
                        'circumstances':reported,'modeConflict':any(o['active_modes']['availability']=='conflicting' for o in observations),
                        'atInjuryAvailability':sorted({o['at_injury_summary']['availability'] for o in observations}),
                        'timeNotes':sorted({SOURCE_LABELS[row['table']]+': '+('Report date, not verified occurrence date' if o['time']['value']['basis']=='report' else 'Occurrence date')+(' · timezone unconfirmed' if o['time']['value']['timezoneStatus']=='unspecified-local-clock' else '') for row,o in zip(primary,observations,strict=True) if o['time']['value']})}}


def add_summaries(layer, records, derived=None):
    index=defaultdict(list)
    for row in records:index[(row['table'],row['sourceRecordId'])].append(row)
    output=copy.deepcopy(layer)
    for feature in output['features']:
        details=feature['properties'].get('details',{})
        rows=[];people=[];vehicles=[]
        for table,key in [('udot.arcgis','UDOT: CRASH_ID'),('portal.crashes','Portal: Crash_ID'),('police.numbers','Police: Case number'),('police.xlsx','Police: Case number')]:
            if key not in details:continue
            identifier=str(details[key]); found=index[(table,identifier)]
            if table.startswith('police.'):
                snapshots=(details.get('Police: Source snapshots') or '').split('; ')
                found=[r for r in found if r['snapshotId'] in snapshots]
            if not found and not table.startswith('police.'):
                raise ValueError('Published source observation absent from normalized candidate')
            if len(found)>1:raise ValueError('Ambiguous source observation in public summary')
            rows.extend(found)
            if table=='portal.crashes':
                rows.extend(index[('portal.rollups',identifier)])
                people.extend(index[('portal.persons',identifier)])
                vehicles.extend(index[('portal.vehicles',identifier)])
        if not rows:raise ValueError('Published feature lacks an exact retained source reference')
        if 'Police: Case number' in details and not any(r['source']=='provo-police-incidents' for r in rows):
            raise ValueError('Published police delivery does not match retained snapshot')
        summary=sections(rows)
        for n,person in enumerate(people,1):
            summary.append({'heading':f'Person {n}', 'entries':[e for s in sections([person]) for e in s['entries'] if e['key']!='identity.state_crash_id']})
        for n,vehicle in enumerate(vehicles,1):
            summary.append({'heading':f'Vehicle {n}', 'entries':[e for s in sections([vehicle]) for e in s['entries'] if e['key']!='identity.state_crash_id']})
        feature['properties']['summary']=summary
        if derived is not None:
            prepared=prepare_fields(rows,people,vehicles,derived)
            feature['properties']['prepared']=prepared
    for before,after in zip(layer['features'],output['features'],strict=True):
        copied=copy.deepcopy(after);copied['properties'].pop('summary');copied['properties'].pop('prepared',None)
        original=copy.deepcopy(before)
        original['properties'].pop('summary',None);original['properties'].pop('prepared',None)
        if copied!=original:raise AssertionError('Existing published feature changed')
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--normalized',type=Path,required=True)
    parser.add_argument('--derived',type=Path,required=True,help='Reviewed derived preview directory')
    parser.add_argument('--published',type=Path,required=True,help='Existing public release directory')
    parser.add_argument('--output',type=Path,required=True,help='New private review directory')
    args=parser.parse_args()
    if not args.output.resolve().is_relative_to(DEFAULT_PRIVATE_DATA_ROOT.resolve()) or args.output.exists():
        parser.error('Use a new directory under tools/.danger-zone-private/')
    validate_snapshot(args.normalized)
    manifest=read_json(args.published/'manifest.json');meta=read_json(args.normalized/'manifest.json')
    base=args.published/'incidents.json'
    if sha256_file(base)!=manifest['sha256']:raise ValueError('Published layer hash mismatch')
    for key,table in [('udot-crashes','udot.arcgis'),('utah-crash-portal','portal.crashes')]:
        coverage=next(s for s in manifest['sourceCoverage'] if s['sourceKey']==key)
        if coverage['snapshotId']!=meta['sources'][table]['snapshotId']:
            raise ValueError('Source snapshot changed; review a new data release separately')
    records=[json.loads(line) for line in (args.normalized/'observations.jsonl').read_text().splitlines()]
    from .derived_incidents import RULES
    derivation_meta=read_json(args.derived/'manifest.json')
    if derivation_meta.get('kind')!='source-qualified-derived-incidents' or derivation_meta['normalizedManifestSha256']!=sha256_file(args.normalized/'manifest.json') or derivation_meta['rulesSha256']!=sha256_file(RULES) or derivation_meta['sha256']!=sha256_file(args.derived/'derived.jsonl'):
        raise ValueError('Derived preview provenance/hash mismatch')
    derived_rows=[json.loads(line) for line in (args.derived/'derived.jsonl').read_text().splitlines()]
    derived={r['observationId']:r for r in derived_rows}
    if len(derived)!=len(derived_rows) or any(r['issues'] for r in derived_rows):raise ValueError('Ambiguous/unreviewed derived fields')
    output=add_summaries(read_json(base),records,derived)
    args.output.mkdir(parents=True,exist_ok=False)
    # Compact JSON avoids adding whitespace cost to the already large metadata extract.
    (args.output/'incidents.json').write_text(json.dumps(output,separators=(',',':'),ensure_ascii=False)+'\n')
    report={'schemaVersion':1,'baseReleaseId':manifest['releaseId'],'baseLayerSha256':manifest['sha256'],
            'normalizedManifestSha256':sha256_file(args.normalized/'manifest.json'),
            'derivedManifestSha256':sha256_file(args.derived/'manifest.json'), 'derivedRulesSha256':derivation_meta['rulesSha256'],
            'contractSha256':meta['rules']['contractSha256'], 'catalogSha256':meta['rules']['catalogSha256'],
            'features':len(output['features']),'coordinatesAndExistingPropertiesUnchanged':True,'newSourceLinks':0,
            'outputSha256':sha256_file(args.output/'incidents.json')}
    write_json(args.output/'review.json',report)
    print(json.dumps(report))


if __name__=='__main__':main()
