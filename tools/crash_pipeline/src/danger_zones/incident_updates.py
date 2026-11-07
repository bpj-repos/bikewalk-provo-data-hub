"""Pure update transformations; no active pointers, downloads or publication."""
from copy import deepcopy
from collections import Counter
from .incidents import _date, combine_observations
from .crash_portal import enrich_state_records, state_join_evidence
from .match_review import review, load_portal
from .util import sha256_json


def flatten(snapshot):
    result = {}
    def add(o):
        if o['id'] in result: raise ValueError('Duplicate source observation: ' + o['id'])
        result[o['id']] = {k:deepcopy(v) for k,v in o.items() if k not in {'statePortal','stateJoinEvidence'}}
        if o.get('statePortal'): add(o['statePortal'])
    for g in snapshot['records']:
        for o in g['observations']: add(o)
    return result


def fingerprint(o):
    """Source values, excluding export positions and dataset/run bookkeeping."""
    m = deepcopy(o['metadata'])
    if o['sourceKey'] == 'provo-police-incidents':
        for key in ['sourceVersions','latestSourceVersionHash','hasSourceConflict','id','incidentId']: m.pop(key,None)
        # Source-value typing differs between compatible spreadsheet formats.
        m.get('observedAt',{}).pop('sourceValue',None)
    elif o['sourceKey'] == 'udot-crashes':
        for key in ['OBJECTID','CURRENT_AS_OF_DATE']: m.pop(key,None)
    else:
        m['crash']['crashDateandTime']=_date(o['observedAt']).isoformat()
        for key in ['longitude','latitude']:
            if m['crash'].get(key) is not None:m['crash'][key]=float(m['crash'][key])
        for key in ['persons','vehicles','rollups']:
            m[key] = sorted(m.get(key,[]),key=sha256_json)
    return sha256_json({'observedAt':_date(o['observedAt']).isoformat(),'coordinates':o['coordinates'],
                        'mode':o.get('mode'),'modes':sorted(o.get('modes',[])), 'metadata':m})


def upsert(target, records):
    for o in records:
        previous = target.get(o['id'])
        if previous is None or fingerprint(previous) != fingerprint(o): target[o['id']] = o


def police_observations(store):
    result=[]
    for row in store['records']:
        geo=row['location']['geocoding'];c=geo.get('coordinates')
        result.append({'id':'provo-police-incidents:'+row['incidentId'],'sourceKey':'provo-police-incidents',
                       'sourceRecordId':row['incidentId'],'sourceSnapshotId':row['sourceVersions'][-1]['snapshotId'],
                       'observedAt':row['observedAt']['utc'],'dateMeaning':'police workbook Date of Report',
                       'coordinates':[c['lng'],c['lat']] if c and geo['mapEligible'] else None,
                       'mode':row['mode']['category'],'metadata':row})
    return result


def local_rows(observations):
    result=[]
    for o in observations:
        if o['sourceKey']!='provo-police-incidents':continue
        m=o['metadata'];loc=m['location'];t=m['observedAt']
        result.append({'id':o['sourceRecordId'],'date':t['localDate'],'time':t['localTime'],
                       'address':loc['addressPartRaw'],'notes':loc.get('noteRaw'),'mode':o['mode'],
                       'coordinates':o['coordinates'],'geocoding':loc['geocoding']})
    return result


def candidate_rows(state):
    portal=list(state['portal'].values())
    tables={ 'portal.'+k:{'rows':[]} for k in ['crashes','persons','vehicles','rollups'] }
    for o in portal:
        tables['portal.crashes']['rows'].append(o['metadata']['crash'])
        for k in ['persons','vehicles','rollups']: tables['portal.'+k]['rows'].extend(o['metadata'][k])
    candidates={c['id']:c for c in load_portal(tables,'retained-portal-lookup')} if portal else {}
    udot={**state.get('udotLookup',{}),**{k:o for k,o in state['observations'].items() if o['sourceKey']=='udot-crashes'}}
    for o in udot.values():
        id=o['sourceRecordId'];when=_date(o['observedAt'])
        if id in candidates:
            p=state['portal']['utah-crash-portal:'+id]
            if not state_join_evidence(o,p):candidates[id]['sourceConflict']=True
        else:
            candidates[id]={'id':id,'date':when.date().isoformat(),'time':when.time().isoformat(),
                            'coordinates':o['coordinates'],'road':o['metadata'].get('MAIN_ROAD_NAME') or '',
                            'modes':o['modes'],'sourceConflict':False,'scopes':['udot'],'city':None}
    return list(candidates.values())


def make_collection(old, state, policy, now, evidence_path, report_hash):
    observations=deepcopy(state['observations'])
    locals=local_rows(observations.values())
    review_rows=review(locals,candidate_rows(state),policy)
    indexed={r['police']['id']:r for r in review_rows}
    old_links=[deepcopy(g['reviewedLink']) for g in old['records'] if g.get('reviewedLink')]
    problems=[]
    for link in old_links:
        row=indexed.get(link['policeId'].split(':',1)[1]);state_id=link['udotId'].split(':',1)[1]
        if row is None: problems.append({'link':link,'reason':'missing police record'});continue
        top=row['candidates'][0] if row['candidates'] else None
        if link['evidenceType']=='owner-authorized-circumstantial':
            if row['status']!='distinctive-circumstantial-lead' or top['stateId']!=state_id:
                problems.append({'link':link,'reason':'strict identity evidence changed or became contested'})
        elif top and top['stateId']!=state_id and row['status']=='distinctive-circumstantial-lead':
            problems.append({'link':link,'reason':'new competing documentary identity evidence'})
    if problems:return None,review_rows,problems
    selected={r['police']['id']:r['candidates'][0] for r in review_rows if r['status']=='distinctive-circumstantial-lead'}
    # A county record enters the collection only through a strict police match.
    for c in selected.values():
        key='utah-crash-portal:'+c['stateId']
        if key in state['portal'] and key not in observations:
            observations[key]=deepcopy(state['portal'][key])
    state_obs=[o for o in observations.values() if o['sourceKey']!='utah-crash-portal']
    portal=[o for o in observations.values() if o['sourceKey']=='utah-crash-portal']
    portal_summary=enrich_state_records(state_obs,portal)
    containers={o['id']:o['id'] for o in state_obs}
    for o in state_obs:
        if o.get('statePortal'):containers[o['statePortal']['id']]=o['id']
    links=[];approved={l['policeId']:l for l in old_links}
    for link in old_links:
        target=containers.get(link['udotId'])
        if target is None:return None,review_rows,[{'link':link,'reason':'missing state observation'}]
        if target!=link['udotId']:link['previousTargetId']=link['udotId'];link['udotId']=target
        links.append(link)
    for local_id,c in sorted(selected.items()):
        police_id='provo-police-incidents:'+local_id
        if police_id in approved:continue
        available=[containers[k] for k in ['udot-crashes:'+c['stateId'],'utah-crash-portal:'+c['stateId']] if k in containers]
        targets=set(available)
        if len(targets)!=1:raise ValueError('Strict match has ambiguous state observations')
        links.append({'policeId':police_id,'udotId':targets.pop(),'reviewer':'manually triggered update pipeline',
                      'reviewedAt':now,'reason':'Uncontested date and second with matching roads or an unavailable address',
                      'evidenceType':'owner-authorized-circumstantial','documentaryIdentityConfirmed':False,
                      'rule':c['tier'],'reviewReportSha256':report_hash,'evidence':str(evidence_path)+'#'+local_id,
                      'authorization':'Owner approved automatic strict-rule linking for manually triggered updates, November 7, 2026'})
    combined=combine_observations(state_obs,links)
    # Keep an existing state group ID when it gains another source representation.
    old_states={}
    for g in old['records']:
        for o in flatten({'records':[g]}).values():
            if o['sourceKey']!='provo-police-incidents':old_states[o['id']]=g['id']
    for g in combined['records']:
        previous={old_states[o['id']] for o in flatten({'records':[g]}).values() if o['id'] in old_states}
        if len(previous)>1:
            # Corroborated duplicate state groups collapse to the UDOT group.
            preferred=next((x for x in sorted(previous) if x.startswith('udot-crashes:')),min(previous))
        else:preferred=next(iter(previous),g['id'])
        g['id']=preferred
    if len({g['id'] for g in combined['records']})!=len(combined['records']):raise ValueError('Group ID collision')
    combined['records'].sort(key=lambda g:g['id'])
    expected=observations
    actual=flatten(combined)
    if set(actual)!=set(expected) or any(fingerprint(actual[k])!=fingerprint(v) for k,v in expected.items()):
        raise ValueError('Source preservation failed')
    return {**combined,'statePortalSummary':portal_summary},review_rows,[]


def changes_between(old,new,review_rows):
    a,b=flatten(old),flatten(new)
    membership={o:g['id'] for g in new['records'] for o in flatten({'records':[g]})}
    old_membership={o:g['id'] for g in old['records'] for o in flatten({'records':[g]})}
    old_groups={g['id'] for g in old['records']};new_groups={g['id'] for g in new['records']}
    absorbed=[{'previousId':id,'destinationId':dest[0]} for id in sorted(old_groups-new_groups)
              if (dest:=sorted({membership[o] for o,g in old_membership.items() if g==id and o in membership})) and len(dest)==1]
    prior_links={g['reviewedLink']['policeId'] for g in old['records'] if g.get('reviewedLink')}
    return {'addedSourceRecords':sorted(set(b)-set(a)),
            'changedSourceRecords':[{'id':k,'changedFields':changed_fields(a[k],b[k])} for k in sorted(set(a)&set(b)) if fingerprint(a[k])!=fingerprint(b[k])],
            'newIncidentGroups':sorted(new_groups-old_groups), 'absorbedGroups':absorbed,
            'newLinks':[g['reviewedLink'] for g in new['records'] if g.get('reviewedLink') and g['reviewedLink']['policeId'] not in prior_links],
            'unresolvedCandidates':[{'policeId':r['police']['id'],'status':r['status'],'candidateIds':[c['stateId'] for c in r['candidates']]} for r in review_rows if r['status']!='distinctive-circumstantial-lead'],
            'validationIssues':[{'policeId':r['police']['id'],'flags':r['validationFlags']} for r in review_rows if r['validationFlags']]}


def changed_fields(a,b,prefix=''):
    if isinstance(a,dict) and isinstance(b,dict):
        return [p for k in sorted(set(a)|set(b)) for p in changed_fields(a.get(k),b.get(k),prefix+'.'+k if prefix else k)]
    return [] if a==b else [prefix]
