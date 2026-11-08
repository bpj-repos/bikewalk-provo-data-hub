"""Manually refresh, reconcile and release private incidents with one atomic promotion."""
import argparse
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
import csv
import fcntl
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import uuid

import pyarrow.parquet as pq
from shapely import from_wkb
from .config import DEFAULT_DATA_ROOT, DEFAULT_PRIVATE_DATA_ROOT, PACKAGE_ROOT
from .crash_portal import read_portal
from .incidents import _date
from .incident_updates import flatten, fingerprint, upsert, police_observations, local_rows, candidate_rows, make_collection, changes_between
from .match_review import POLICY, review, validate_policy, previous_year
from .pipeline import import_udot_crashes
from .police import import_police_workbook
from .util import read_json, write_json, sha256_file, sha256_json, isoformat, utc_now


@contextmanager
def update_lock(private_root):
    path=private_root/'datastores/update-incidents.lock';path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+') as f:
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Another incident update is running') from None
        try:yield
        finally:fcntl.flock(f,fcntl.LOCK_UN)


def write_gzip(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(value,sort_keys=True,default=str,separators=(',',':')).encode(),mtime=0))


def read_gzip(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def tool_hash():
    names=['update_incidents.py','incident_updates.py','match_review.py','incidents.py','crash_portal.py',
           'police.py','police_forward.py','police_datastore.py','police_portal_candidates.py','pipeline.py','normalize.py','arcgis.py',
           'incident_conversions.py','normalize_incidents.py','derived_incidents.py','crash_enrichment.py','common_structure.py','util.py','config.py','registry.py','geoparquet.py']
    return sha256_json({'modules':{n:sha256_file(Path(__file__).parent/n) for n in names},
                        'catalog':{name:sha256_file(PACKAGE_ROOT/'catalog/incident-metadata'/name) for name in ['fields.yml','common.yml','derived.yml']},
                        'dependencies':sha256_file(PACKAGE_ROOT/'pyproject.toml')})


class RestorePaths:
    """Read verified historical references inside the operator's restored repository."""
    def __init__(self, mappings):
        self.root = Path(mappings[0][1]).resolve(strict=True)
        self.origins = set()
        for old, new in mappings:
            old = Path(old)
            if not old.is_absolute() or ".." in old.parts or not Path(new).is_absolute() or Path(new).resolve() != self.root:
                raise ValueError("Restore mappings require absolute origins and one destination")
            original = old.resolve()
            if original.is_relative_to(self.root) or self.root.is_relative_to(original):
                raise ValueError("Original and restored roots must be disjoint")
            self.origins.add(old)

    def local(self, path):
        path = Path(path)
        if ".." in path.parts:
            raise ValueError("Invalid restore path")
        if not path.is_relative_to(self.root):
            origins = [origin for origin in self.origins if path.is_relative_to(origin)]
            if len(origins) != 1:
                raise ValueError("Unmapped or ambiguous historical path: " + str(path))
            path = self.root / path.relative_to(origins[0])
        path = path.resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Restore path escapes the destination")
        return path

    def ref(self, ref):
        path = self.local(ref['path'])
        if sha256_file(path) != ref['sha256']:
            raise ValueError("Restored file checksum mismatch: " + str(path))
        return {**ref, 'path': str(path)}

    def pointer(self, pointer):
        result = self.ref(pointer)
        for key in ('releaseManifest', 'reviewedLinksSource'):
            if key in pointer:
                result[key] = self.ref(pointer[key])
        return result


def retain_input(path,private_root,kind):
    digest=sha256_file(path)
    target=private_root/'incident-inputs'/digest/('records'+path.suffix.lower())
    if not target.exists():target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    if sha256_file(target)!=digest:raise ValueError('Retained input checksum mismatch')
    return {'kind':kind,'path':str(target.resolve()),'sha256':digest,'retrievedAt':isoformat(utc_now())}


def portal_input(path,private_root):
    desc=retain_input(path,private_root,'portal')
    parsed=Path(desc['path']).parent/'portal.json.gz';receipt=parsed.with_suffix('.receipt.json')
    if parsed.exists() and receipt.exists():
        if sha256_file(parsed)!=read_json(receipt)['sha256']:raise ValueError('Parsed portal checksum mismatch')
        payload=read_gzip(parsed)
    else:
        records,filters=read_portal(Path(desc['path']),include_all=True,allow_county=True,validate=True)
        for o in records:o['sourceSnapshotId']=desc['sha256']
        payload={'records':records,'filters':filters}
        write_gzip(parsed,payload);write_json(receipt,{'sha256':sha256_file(parsed)})
    desc.update(filters=payload['filters'],coverage=max((o['observedAt'] for o in payload['records']),default=None),
                scope='collection' if payload['filters']['City']=='Provo' else 'reference',checkedAt=isoformat(utc_now()))
    return payload['records'],desc


def bootstrap(old,private_root):
    observations=flatten(old)
    police_source=next(s for s in old['sources'] if s['sourceKey']=='provo-police-incidents')
    path=Path(police_source['path'])
    if sha256_file(path)!=police_source['sha256']:raise ValueError('Police datastore checksum mismatch')
    retained_store=retain_input(path,private_root,'police-store')
    sources=[{**s,'path':retained_store['path']} if s['sourceKey']=='provo-police-incidents' else deepcopy(s) for s in old['sources']]
    state={'observations':observations,'portal':{},'policeStore':read_json(path),'inputs':[],'sources':sources}
    udot_source=next(s for s in old['sources'] if s['sourceKey']=='udot-crashes')
    if sha256_file(Path(udot_source['path']))!=udot_source['sha256']:raise ValueError('UDOT source checksum mismatch')
    state['udotLookup']={o['id']:o for o in udot_observations(Path(udot_source['path']))}
    source=next((s for s in old['sources'] if s['sourceKey']=='utah-crash-portal'),None)
    if source:
        if sha256_file(Path(source['path']))!=source['sha256']:raise ValueError('Portal source checksum mismatch')
        rows,desc=portal_input(Path(source['path']),private_root);upsert(state['portal'],rows);state['inputs'].append(desc)
    # Discover only the previously retained county-reference namespace, not arbitrary exports.
    for path in sorted((private_root/'sources/portal-county-followup').glob('*/records.xlsx')):
        receipt=path.parent/'receipt.json'
        if not receipt.exists():continue
        if path.parent.name!=sha256_file(path):raise ValueError('County reference hash mismatch')
        rows,desc=portal_input(path,private_root)
        if desc['scope']!='reference':raise ValueError('Unexpected county-reference scope')
        for o in rows:
            state['portal'].setdefault(o['id'],o)
        state['inputs'].append(desc)
    return state


def udot_observations(path):
    result=[]
    for row in pq.read_table(path).to_pylist():
        point=from_wkb(row['geometry'])
        result.append({'id':'udot-crashes:'+row['crash_id'],'sourceKey':'udot-crashes','sourceRecordId':row['crash_id'],
                       'sourceSnapshotId':row['source_snapshot_id'],'observedAt':isoformat(row['observed_at']),
                       'dateMeaning':'crash date/time','coordinates':[point.x,point.y],
                       'modes':[m for m,f in [('bicycle','bicyclist_involved'),('pedestrian','pedestrian_involved')] if row[f]],
                       'metadata':json.loads(row['attributes'])})
    return result


def input_fingerprint(state):
    return sha256_json({'observations':{k:fingerprint(v) for k,v in sorted(state['observations'].items())},
                        'portal':{k:fingerprint(v) for k,v in sorted(state['portal'].items())},
                        'udotLookup':{k:fingerprint(v) for k,v in sorted(state.get('udotLookup',{}).items())}})


def load_state(pointer,old,private_root):
    if not pointer.get('releaseManifest'):return bootstrap(old,private_root),None
    ref=pointer['releaseManifest'];path=Path(ref['path'])
    if sha256_file(path)!=ref['sha256']:raise ValueError('Release manifest checksum mismatch')
    manifest=read_json(path)
    if 'input-state.json.gz' not in manifest['files']:
        raise ValueError("Missing checksummed cumulative input state")
    for name,digest in manifest['files'].items():
        if Path(name).name != name or (path.parent/name).is_symlink():
            raise ValueError("Invalid release file: " + name)
        if sha256_file(path.parent/name)!=digest:raise ValueError('Release file checksum mismatch: '+name)
    state=read_gzip(path.parent/'input-state.json.gz')
    # The immutable state must still describe the active collection's source records.
    expected=flatten(old)
    if any(k not in state['observations'] or fingerprint(v)!=fingerprint(state['observations'][k]) for k,v in expected.items()):
        raise ValueError('Release inputs differ from active collection')
    return state,manifest


def apply_inputs(state,private_root,data_root,run_dir,portal_workbooks,police_workbooks,offline,refresh):
    known={d['sha256'] for d in state['inputs']}
    if not offline:
        imported=refresh(run_dir/'udot')
        normalized=Path(imported['normalizedPath'])
        source={'sourceKey':'udot-crashes','snapshotId':normalized.parent.name,'path':str(normalized.resolve()),
                'sha256':sha256_file(normalized),'retrievedAt':imported['manifest']['retrievedAt'],
                'checkedAt':isoformat(utc_now()),'sourceCurrentThrough':imported['manifest']['sourceCurrentThrough']}
        if source['sha256']!=imported['report']['normalizedArtifacts'][0]['sha256']:raise ValueError('UDOT normalized checksum mismatch')
        rows=udot_observations(normalized)
        upsert(state.setdefault('udotLookup',{}),rows)
        present={o['id'] for o in rows}
        state['missingFromLatestUdotExport']=sorted(k for k,o in state['observations'].items() if o['sourceKey']=='udot-crashes' and k not in present)
        # Preserve historical records and records whose classifications were corrected.
        upsert(state['observations'],[o for o in rows if o['modes'] or o['id'] in state['observations']])
        state['sources']=[s for s in state['sources'] if s['sourceKey']!='udot-crashes']+[source]
    batch={}
    for path in portal_workbooks:
        if sha256_file(path) in known:continue
        rows,desc=portal_input(path,private_root)
        for o in rows:
            if o['id'] in batch and fingerprint(o)!=fingerprint(batch[o['id']]):
                raise ValueError('Supplied portal exports conflict: '+o['id'])
            batch[o['id']]=o
        upsert(state['portal'],rows)
        upsert(state['observations'],[o for o in rows if o['id'] in state['observations'] or desc['scope']=='collection' and o['modes']])
        state['inputs'].append(desc);known.add(desc['sha256'])
        source_key='utah-crash-portal' if desc['scope']=='collection' else 'utah-crash-portal-reference'
        source={**desc,'sourceKey':source_key,'snapshotId':desc['sha256'],
                'sourceCurrentThrough':desc['coverage'],'retainedInputHashes':[d['sha256'] for d in state['inputs'] if d['kind']=='portal']}
        state['sources']=[s for s in state['sources'] if s['sourceKey']!=source_key]+[source]
    store_path=run_dir/'police/datastores/provo-police-incidents.json'
    ingested={i['workbookSha256'] for i in state['policeStore'].get('ingestions',[])}
    for path in police_workbooks:
        digest=sha256_file(path)
        if digest in ingested:continue
        desc=retain_input(path,private_root,'police')
        write_json(store_path,state['policeStore'])
        import_police_workbook(Path(desc['path']),run_dir/'police',data_root=data_root,datastore_path=store_path,local_geocode=True,source_name=path.name)
        state['policeStore']=read_json(store_path)
        upsert(state['observations'],police_observations(state['policeStore']))
        state['inputs'].append(desc);ingested.add(digest)
        retained_store=retain_input(store_path,private_root,'police-store')
        source={'sourceKey':'provo-police-incidents','path':retained_store['path'],'sha256':sha256_file(store_path),
                'snapshotId':sha256_file(store_path),'sourceCurrentThrough':state['policeStore']['sourceCurrentThrough'],
                'retrievedAt':desc['retrievedAt'],'checkedAt':isoformat(utc_now())}
        state['sources']=[s for s in state['sources'] if s['sourceKey']!='provo-police-incidents']+[source]


def write_changes(path,changes):
    write_json(path/'changes.json',changes)
    with (path/'changes.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['changeType','id','details'])
        for kind,items in changes.items():
            for item in items:
                writer.writerow([kind,item if isinstance(item,str) else item.get('id',item.get('policeId',item.get('previousId',item.get('policeId','')))),'' if isinstance(item,str) else json.dumps(item,sort_keys=True)])


def run_update(private_root=DEFAULT_PRIVATE_DATA_ROOT,data_root=DEFAULT_DATA_ROOT,*,portal_workbooks=(),police_workbooks=(),offline=False,refresh=import_udot_crashes,restore=None):
    private_root=Path(private_root).resolve();data_root=Path(data_root).resolve()
    if restore and not private_root.is_relative_to(restore.root):
        raise ValueError("Private data root must be inside the restored repository")
    if restore and not data_root.is_relative_to(restore.root):
        raise ValueError("Data root must be inside the restored repository")
    with update_lock(private_root):
        pointer_path=private_root/'datastores/combined-incidents.json'
        original=read_json(pointer_path)
        before=restore.pointer(original) if restore else original
        if sha256_file(Path(before['path']))!=before['sha256']:raise ValueError('Active snapshot checksum mismatch')
        old=read_json(Path(before['path']))
        start_tools=tool_hash();start_policy=sha256_file(POLICY)
        now=isoformat(utc_now());run_id=now.replace(':','').replace('-','')+'-'+uuid.uuid4().hex[:8]
        run_dir=private_root/'incident-updates/runs'/run_id;run_dir.mkdir(parents=True)
        write_json(run_dir/'before-pointer.json',original)
        try:
            if restore and not before.get('releaseManifest'):
                old['sources'] = [restore.ref(source) for source in old['sources']]
            state,previous_manifest=load_state(before,old,private_root)
            if restore:
                for key in ('inputs', 'sources'):
                    state[key] = [restore.ref(ref) for ref in state[key]]
            for source in state['sources']+state['inputs']:
                if source.get('path') and source.get('sha256') and sha256_file(Path(source['path']))!=source['sha256']:
                    raise ValueError('Pinned source checksum mismatch: '+source['path'])
            old_lookup={k:fingerprint(v) for k,v in {**state.get('udotLookup',{}),**state['portal']}.items()}
            apply_inputs(state,private_root,data_root,run_dir,list(map(Path,portal_workbooks)),list(map(Path,police_workbooks)),offline,refresh)
            policy=read_json(POLICY);validate_policy(policy)
            content_fingerprint=input_fingerprint(state);tools=tool_hash();policy_hash=sha256_file(POLICY)
            if tools!=start_tools or policy_hash!=start_policy:raise ValueError('Tool or policy changed during update')
            if previous_manifest and content_fingerprint==previous_manifest['inputFingerprint'] and tools==previous_manifest['toolSha256'] and policy_hash==previous_manifest['policySha256']:
                report={'status':'unchanged','checkedAt':now,'releaseId':previous_manifest['releaseId'],
                        'checks':state['sources'],'inputs':state['inputs'],'offline':offline,
                        'missingFromLatestUdotExport':state.get('missingFromLatestUdotExport',[])}
                write_json(run_dir/'check.json',report);write_json(private_root/'incident-updates/latest-check.json',report)
                if before != original:
                    if read_json(pointer_path) != original:
                        raise ValueError("Concurrent pointer change")
                    write_json(pointer_path, before)
                return {'status':'unchanged','checkedAt':now,'releaseId':previous_manifest['releaseId'],'checkReport':str(run_dir/'check.json')}
            locals_=local_rows(state['observations'].values());candidates=candidate_rows(state)
            rows=review(locals_,candidates,policy)
            years={c['date'][:4] for c in candidates}
            controls=review([dict(p,date=previous_year(p['date'])) for p in locals_ if previous_year(p['date'])[:4] in years],candidates,policy)
            review_path=run_dir/'matching.json';write_json(review_path,{'policy':policy,'records':rows,'inputFingerprint':content_fingerprint,
                'negativeControl':{'method':'one calendar year earlier; leap day clamps to February 28',
                                   'records':len(controls),'statuses':dict(Counter(r['status'] for r in controls)),
                                   'limits':'Annual coverage differs; not a calibrated false-match probability.'}})
            combined,rows,problems=make_collection(old,state,policy,now,review_path,sha256_file(review_path))
            if problems:
                write_json(run_dir/'conflicts.json',problems)
                raise ValueError('Existing identity conflict; see '+str(run_dir/'conflicts.json'))
            all_sources=flatten(combined)
            # Persist newly matched reference records and current source versions in release inputs.
            upsert(state['observations'],all_sources.values())
            from .crash_enrichment import enrich_collection
            enrichment_audit=enrich_collection(combined)
            changes=changes_between(old,combined,rows)
            previous_enrichment={g['id']:g.get('enrichment') for g in old['records']}
            changes['enrichmentChangedGroups']=[g['id'] for g in combined['records'] if g['enrichment']!=previous_enrichment.get(g['id'])]
            changes['missingFromLatestUdotExport']=state.get('missingFromLatestUdotExport',[])
            new_lookup={k:fingerprint(v) for k,v in {**state.get('udotLookup',{}),**state['portal']}.items()}
            changes['addedLookupRecords']=sorted(set(new_lookup)-set(old_lookup))
            changes['changedLookupRecords']=sorted(k for k in set(old_lookup)&set(new_lookup) if old_lookup[k]!=new_lookup[k])
            release_id='incidents-'+sha256_json({'inputs':content_fingerprint,'tools':tools,'policy':policy_hash,
                                                'groups':[(g['id'],sorted(flatten({'records':[g]}))) for g in combined['records']]})[:20]
            destination=private_root/'incident-updates/releases'/release_id
            bundle=run_dir/'bundle'
            bundle.mkdir()
            collection={**old,**combined,'snapshotId':release_id,'createdAt':now,'toolSha256':tools,
                        'sources':state['sources'],'producerCommit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=PACKAGE_ROOT,text=True).strip()}
            write_json(bundle/'enrichment-audit.json',enrichment_audit)
            write_json(bundle/'collection.json',collection);write_gzip(bundle/'input-state.json.gz',state)
            shutil.copyfile(review_path,bundle/'matching.json')
            links=[g['reviewedLink'] for g in combined['records'] if g.get('reviewedLink')]
            write_json(bundle/'reviewed-links.json',links);write_changes(bundle,changes)
            summary='\n'.join(['# Incident collection update', '',f'Release: {release_id}',f'Predecessor: {old["snapshotId"]}',
                               f'Checked: {now}',f'Offline: {offline}', '',
                               *[f'- {k}: {len(v)}' for k,v in changes.items()],
                               f'- Incident groups: {len(combined["records"])}',f'- Preserved/raw source observations: {len(all_sources)}', '',
                               'Source freshness:',*[f'- {s["sourceKey"]}: '+str(s.get('sourceCurrentThrough','unknown')) for s in state['sources']],
                               '', 'County exports are lookup references. Existing uncertain geocodes require manual confirmation.',
                               'Local bundle only; no public map adoption or off-machine backup.'])+'\n'
            (bundle/'summary.md').write_text(summary)
            files={p.name:sha256_file(p) for p in bundle.iterdir() if p.is_file()}
            manifest={'schemaVersion':1,'releaseId':release_id,'predecessor':{'snapshotId':old['snapshotId'],'pointer':before},
                      'checkedAt':now,'offline':offline,'inputFingerprint':input_fingerprint(state),
                      'toolSha256':tools,'policySha256':policy_hash,'sources':state['sources'],'inputs':state['inputs'],
                      'files':files,'counts':combined['counts'],'changes':{k:len(v) for k,v in changes.items()},
                      'provenancePathsAreInformationalForConsumers':True}
            write_json(bundle/'manifest.json',manifest)
            for name,digest in files.items():
                if sha256_file(bundle/name)!=digest:raise ValueError('Bundle checksum mismatch')
            if read_json(pointer_path)!=original:raise ValueError('Active pointer changed during update')
            if tool_hash()!=tools or sha256_file(POLICY)!=policy_hash:raise ValueError('Tool or policy changed during update')
            destination.parent.mkdir(parents=True,exist_ok=True)
            if destination.exists():
                retained=read_json(destination/'manifest.json')
                prior = retained['predecessor']
                if restore:
                    prior = {**prior, 'pointer': restore.pointer(prior['pointer'])}
                if prior != manifest['predecessor'] or any(retained[k]!=manifest[k] for k in ['releaseId','inputFingerprint','toolSha256','policySha256']):
                    raise ValueError('Existing release identity mismatch')
                for name,digest in retained['files'].items():
                    if sha256_file(destination/name)!=digest:raise ValueError('Existing release checksum mismatch')
                manifest=retained;files=manifest['files']
            else:
                bundle.rename(destination)
            bundle=destination
            pointer={'snapshotId':release_id,'path':str((bundle/'collection.json').resolve()),'sha256':files['collection.json'],
                     'counts':combined['counts'],'reviewedLinksSource':{'path':str((bundle/'reviewed-links.json').resolve()),'sha256':files['reviewed-links.json']},
                     'releaseManifest':{'path':str((bundle/'manifest.json').resolve()),'sha256':sha256_file(bundle/'manifest.json')}}
            write_json(run_dir/'candidate-pointer.json',pointer)
            # This is the only mutation of the active data state.
            write_json(pointer_path,pointer)
            return {'status':'accepted','releaseId':release_id,'bundle':str(bundle),'counts':combined['counts'],'changes':manifest['changes']}
        except Exception as exc:
            write_json(run_dir/'failure.json',{'checkedAt':now,'error':str(exc),'activePointerUnchanged':read_json(pointer_path)==original})
            raise


def rollback(private_root=DEFAULT_PRIVATE_DATA_ROOT, *, restore=None):
    private_root=Path(private_root).resolve()
    if restore and not private_root.is_relative_to(restore.root):
        raise ValueError("Private data root must be inside the restored repository")
    with update_lock(private_root):
        pointer_path=private_root/'datastores/combined-incidents.json';original=read_json(pointer_path)
        current=restore.pointer(original) if restore else original
        if not current.get('releaseManifest'):raise ValueError('Current collection has no managed predecessor')
        ref=current['releaseManifest'];manifest_path=Path(ref['path'])
        if sha256_file(manifest_path)!=ref['sha256'] or sha256_file(Path(current['path']))!=current['sha256']:
            raise ValueError('Current release checksum mismatch')
        previous=read_json(manifest_path)['predecessor']['pointer']
        if restore:
            previous = restore.pointer(previous)
        if sha256_file(Path(previous['path']))!=previous['sha256']:raise ValueError('Previous collection checksum mismatch')
        flatten(read_json(Path(previous['path'])))
        if previous.get('releaseManifest'):
            state,_ = load_state(previous,read_json(Path(previous['path'])),private_root)
            if restore:
                for ref in state['inputs'] + state['sources']:
                    restore.ref(ref)
        audit=private_root/'incident-updates/rollbacks'/(uuid.uuid4().hex+'.json')
        write_json(audit,{'at':isoformat(utc_now()),'before':original,'restored':previous})
        if read_json(pointer_path)!=original:raise ValueError('Concurrent pointer change')
        write_json(pointer_path,previous)
        return {'status':'rolled-back','releaseId':previous['snapshotId'],'audit':str(audit)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--portal-workbook',type=Path,action='append',default=[])
    parser.add_argument('--police-input','--police-workbook',dest='police_workbook',help='Police .xlsx, .numbers or forwarded .eml (repeatable)',type=Path,action='append',default=[])
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--rollback',action='store_true',help='Restore the verified predecessor pointer; no downloads')
    parser.add_argument('--private-data-root',type=Path)
    parser.add_argument('--data-root',type=Path)
    parser.add_argument('--restore-path', nargs=2, type=Path, action='append', metavar=('ORIGINAL_ROOT','RESTORED_ROOT'),
                        help='Resolve historical paths under the restored repository; repeat for additional origins')
    args=parser.parse_args()
    restore = RestorePaths(args.restore_path) if args.restore_path else None
    private_root = args.private_data_root or (restore.root/'tools/.danger-zone-private' if restore else DEFAULT_PRIVATE_DATA_ROOT)
    data_root = args.data_root or (restore.root/'tools/.danger-zone-data' if restore else DEFAULT_DATA_ROOT)
    if args.rollback and (args.offline or args.portal_workbook or args.police_workbook):parser.error('--rollback cannot be combined with update inputs or --offline')
    result=rollback(private_root,restore=restore) if args.rollback else run_update(private_root,data_root,restore=restore,portal_workbooks=args.portal_workbook,police_workbooks=args.police_workbook,offline=args.offline)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
