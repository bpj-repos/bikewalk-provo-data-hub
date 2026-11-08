import json
from copy import deepcopy
from pathlib import Path
import tempfile
import shutil
from datetime import datetime
from email.message import EmailMessage
from openpyxl import Workbook
from danger_zones.field_inventory import read_catalog
import unittest
from unittest.mock import patch
from danger_zones.incident_updates import flatten, fingerprint, make_collection, changes_between
from danger_zones.update_incidents import RestorePaths, run_update, write_gzip, update_lock, rollback
from danger_zones.util import write_json, read_json, sha256_file
from danger_zones.match_review import POLICY


def state_record(id='1',road='200 N UNIVERSITY AVE',time='2025-03-04T16:30:00Z'):
    return {'id':'udot-crashes:'+id,'sourceKey':'udot-crashes','sourceRecordId':id,'sourceSnapshotId':'raw-1',
            'observedAt':time,'dateMeaning':'crash date/time','coordinates':[-111.66,40.23],
            'modes':['bicycle'],'metadata':{'MAIN_ROAD_NAME':road,'CRASH_DATETIME':123,'CURRENT_AS_OF_DATE':1}}


def portal_record(id='1',road='200 N UNIVERSITY AVE',city='Provo'):
    crash={'Crash_ID':id,'crashDateandTime':'2025-03-04 09:30:00','roadName':road,'City_Geo':city,
           'longitude':'-111.66','latitude':'40.23','crashSeverity_label':'Possible injury','officer_department':'PROVO POLICE',
           'cyclist_involved':'Y','pedestrian_involved':'N'}
    return {'id':'utah-crash-portal:'+id,'sourceKey':'utah-crash-portal','sourceRecordId':id,'sourceSnapshotId':'raw-p',
            'observedAt':'2025-03-04T09:30:00-07:00','timePrecision':'second','dateMeaning':'state crash date/time in America/Denver',
            'coordinates':[-111.66,40.23],'modes':['bicycle'],
            'metadata':{'crash':crash,'persons':[{'Crash_ID':id,'personType':'4','personType_label':'Pedalcyclist','ageCalculated':'30','injuryLevel_label':'Possible injury'}],
                        'vehicles':[],'rollups':[{'Crash_ID':id,'crash_id':id,'cyclist_involved':'Y'}]}}


def police_record(id='P1'):
    return {'id':'provo-police-incidents:'+id,'sourceKey':'provo-police-incidents','sourceRecordId':id,
            'sourceSnapshotId':'raw-local','observedAt':'2025-03-04T16:30:00Z','dateMeaning':'police workbook Date of Report',
            'coordinates':[-111.66,40.23],'mode':'bicycle',
            'metadata':{'location':{'addressPartRaw':'200 N UNIVERSITY AVE','noteRaw':None,'geocoding':{'status':'matched'}},
                        'observedAt':{'localDate':'2025-03-04','localTime':'09:30:00'},'sourceVersions':[]}}


def collection(observations):
    return {'schemaVersion':1,'storageClass':'private-owner-only','snapshotId':'original','sources':[],
            'records':[{'id':o['id'],'observations':[deepcopy(o)]} for o in observations], 'counts':{},'possibleMatches':[]}


def inputs(old,portals=()):
    return {'observations':flatten(old),'portal':{p['id']:p for p in portals},'inputs':[],
            'policeStore':{'schemaVersion':1,'records':[],'ingestions':[]},'sources':[]}


def portal_workbook(path,records,city='Provo',reverse=False):
    wb=Workbook();wb.remove(wb.active);catalog=read_catalog()
    for title,key in [('Crashes','crash'),('Persons','persons'),('Vehicles','vehicles'),('Rollups','rollups')]:
        sheet=wb.create_sheet(title);headers=list(catalog['tables']['portal.'+title.lower()]['fields']);sheet.append(headers)
        for o in list(records)[::-1] if reverse else records:
            rows=[o['metadata'][key]] if key=='crash' else o['metadata'][key]
            for row in rows:sheet.append([row.get(h) for h in headers])
    sheet=wb.create_sheet('Filters');sheet.append(['Filter','Value'])
    for k,v in {'City':city,'Counties':'Utah' if city=='All' else 'All','Crash Severity':'1, 2, 3, 4, 5','Months':'All Months','Vehicle Types':'All'}.items():sheet.append([k,v])
    wb.save(path)
    return path


class TransformationTests(unittest.TestCase):
    def setUp(self): self.policy=read_json(POLICY)
    def build(self,old,state):return make_collection(old,state,self.policy,'2026-11-03T20:00:00Z',Path('/tmp/evidence.json'),'abc')
    def test_new_police_evidence_is_not_new_incident(self):
        old=collection([state_record()]);s=inputs(old,[portal_record()]);s['observations']['provo-police-incidents:P1']=police_record()
        new,rows,errors=self.build(old,s);self.assertFalse(errors)
        changes=changes_between(old,new,rows)
        self.assertEqual(len(new['records']),1);self.assertEqual(len(changes['newLinks']),1)
        self.assertEqual(changes['newIncidentGroups'],[])
        self.assertIn('provo-police-incidents:P1',changes['addedSourceRecords'])
    def test_new_state_crash_is_new_incident(self):
        old=collection([state_record()]);s=inputs(old);s['observations']['udot-crashes:2']=state_record('2')
        new,rows,errors=self.build(old,s)
        self.assertEqual(changes_between(old,new,rows)['newIncidentGroups'],['udot-crashes:2'])
    def test_correction_is_changed_not_added(self):
        old=collection([state_record()]);s=inputs(old);s['observations']['udot-crashes:1']['metadata']['WEATHER']='Rain'
        new,rows,errors=self.build(old,s);changes=changes_between(old,new,rows)
        self.assertFalse(changes['addedSourceRecords']);self.assertIn('metadata.WEATHER',changes['changedSourceRecords'][0]['changedFields'])
        self.assertNotIn('WEATHER',old['records'][0]['observations'][0]['metadata'])
    def test_bookkeeping_does_not_change_fingerprint(self):
        a=state_record();b=deepcopy(a);b['sourceSnapshotId']='new';b['metadata']['CURRENT_AS_OF_DATE']=99
        self.assertEqual(fingerprint(a),fingerprint(b))
        a=portal_record();b=deepcopy(a);b['metadata']['persons'].append(deepcopy(b['metadata']['persons'][0]));a=deepcopy(b)
        b['metadata']['persons'].reverse();self.assertEqual(fingerprint(a),fingerprint(b))
    def test_timestamp_presentation_does_not_change_content(self):
        a=portal_record();b=deepcopy(a);b['metadata']['crash']['crashDateandTime']='3/4/2025 9:30:00 AM'
        b['metadata']['crash']['longitude']=-111.66
        self.assertEqual(fingerprint(a),fingerprint(b))
    def test_county_reference_not_bulk_added_but_strict_match_can_include_it(self):
        old=collection([state_record('9',time='2024-01-01T16:30:00Z')]);s=inputs(old,[portal_record(city='Outside city limits')])
        new,rows,errors=self.build(old,s);self.assertNotIn('utah-crash-portal:1',flatten(new))
        s['observations']['provo-police-incidents:P1']=police_record()
        new,rows,errors=self.build(old,s);self.assertIn('utah-crash-portal:1',flatten(new))
    def test_state_group_id_stable_when_udot_arrives(self):
        old=collection([portal_record()]);s=inputs(old,[portal_record()]);s['observations']['udot-crashes:1']=state_record()
        new,rows,errors=self.build(old,s);self.assertEqual(new['records'][0]['id'],'utah-crash-portal:1')
    def test_absorbed_police_group_is_reported(self):
        old=collection([state_record(),police_record()]);s=inputs(old,[portal_record()])
        new,rows,errors=self.build(old,s)
        self.assertEqual(changes_between(old,new,rows)['absorbedGroups'],[{'previousId':'provo-police-incidents:P1','destinationId':'udot-crashes:1'}])
    def test_existing_link_conflict_blocks_candidate(self):
        old=collection([state_record(),police_record()]);s=inputs(old,[portal_record()]);new,rows,errors=self.build(old,s)
        new['snapshotId']='accepted';s=inputs(new,[portal_record()]);s['portal']['utah-crash-portal:1']['metadata']['crash']['crashDateandTime']='2025-03-05 09:30:00'
        new2,rows,errors=self.build(new,s);self.assertIsNone(new2);self.assertTrue(errors)
    def test_ambiguous_matches_remain_separate(self):
        old=collection([police_record()]);s=inputs(old,[portal_record('1'),portal_record('2')])
        new,rows,errors=self.build(old,s);self.assertEqual(rows[0]['status'],'ambiguous');self.assertFalse(new['counts']['reviewedLinks'])
    def test_geocode_error_does_not_get_repaired(self):
        p=police_record();p['metadata']['location']['geocoding']['providerCandidates']=[{'properties':{'kind':'street'}}]
        old=collection([p]);s=inputs(old)
        new,rows,errors=self.build(old,s);self.assertTrue(rows[0]['manualConfirmationRequired']);self.assertEqual(flatten(new)[p['id']]['coordinates'],p['coordinates'])


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.old=collection([state_record()]);self.old_path=self.root/'old.json';write_json(self.old_path,self.old)
        self.pointer=self.root/'datastores/combined-incidents.json'
        write_json(self.pointer,{'path':str(self.old_path),'sha256':sha256_file(self.old_path),'snapshotId':'original'})
        self.bootstrap=patch('danger_zones.update_incidents.bootstrap',side_effect=lambda *_:inputs(self.old))
        self.bootstrap.start()
    def tearDown(self):self.bootstrap.stop();self.temp.cleanup()
    def run_update(self,**kwargs):return run_update(self.root,offline=kwargs.pop('offline',True),**kwargs)
    def test_forward_preserves_report_date_without_inventing_midnight(self):
        msg=EmailMessage()
        msg.set_content("forward")
        msg.add_alternative("<table><tr><td>number</td><td>dtrepor</td><td>agency</td><td>street</td><td>desc</td></tr>"
                            "<tr><td>26PRW1234</td><td>3/4/2025</td><td>PRPD</td><td>200 N UNIVERSITY AVE</td>"
                            "<td>Electric Bike</td></tr></table>",subtype="html")
        source=self.root/'delivery.eml'
        source.write_bytes(msg.as_bytes())
        result=self.run_update(police_workbooks=[source],data_root=self.root)
        bundle=Path(result['bundle'])
        record=flatten(read_json(bundle/'collection.json'))['provo-police-incidents:26PRW1234']
        self.assertEqual(record['observedAt'],'2025-03-04')
        self.assertIsNone(record['metadata']['observedAt']['localTime'])
        self.assertIsNone(record['metadata']['observedAt']['utc'])
        self.assertEqual(record['mode'],'electric-bicycle')
        version=record['metadata']['sourceVersions'][-1]
        self.assertEqual((version['sourceRow'],version['workbookSha256']),(2,sha256_file(source)))
        self.assertEqual(read_json(bundle/'reviewed-links.json'),[])
        original=self.pointer.read_bytes()
        self.assertEqual(self.run_update(police_workbooks=[source],data_root=self.root)['status'],'unchanged')
        self.assertEqual(self.pointer.read_bytes(),original)

    def test_reviewed_match_receipt_is_pinned_repeatable_and_reversible(self):
        local = police_record()
        local['observedAt'] = '2025-03-05'
        local['metadata']['observedAt'] = {'localDate':'2025-03-05','localTime':None,'utc':None}
        self.old['records'].append({'id':local['id'], 'observations':[local]})
        write_json(self.old_path, self.old)
        write_json(self.pointer, {'path':str(self.old_path),'sha256':sha256_file(self.old_path),'snapshotId':'original'})
        county = portal_workbook(self.root/'county.xlsx', [portal_record('7')], city='All')
        first = self.run_update(portal_workbooks=[county])
        prior_pointer = self.pointer.read_bytes()
        receipt = self.root/'review.json'
        decision = {'policeCase':'P1','stateId':'7','confidence':'probable',
                    'reason':'Next-day report with the same numbered address','evidence':'private case comparison'}
        packet = {'collectionSHA256':read_json(self.pointer)['sha256'], 'reviewer':'reviewer',
                  'reviewedAt':'2026-11-07T19:00:00-07:00','authorization':'owner decision','matches':[decision]}
        for invalid in ({**packet,'matches':[decision, decision]}, {**packet,'collectionSHA256':'stale'}):
            write_json(receipt, invalid)
            with self.assertRaises(ValueError):
                self.run_update(reviewed_matches=receipt)
            self.assertEqual(self.pointer.read_bytes(), prior_pointer)
        write_json(receipt, packet)
        result = self.run_update(reviewed_matches=receipt)
        bundle = Path(result['bundle'])
        link, = read_json(bundle/'reviewed-links.json')
        self.assertEqual((link['udotId'],link['confidence'],link['decisionReceiptSha256']),
                         ('utah-crash-portal:7','probable',sha256_file(receipt)))
        self.assertFalse(link['documentaryIdentityConfirmed'])
        self.assertFalse(read_json(bundle/'changes.json')['unresolvedCandidates'])
        published = self.pointer.read_bytes()
        self.assertEqual(self.run_update(reviewed_matches=receipt)['status'],'unchanged')
        self.assertEqual(self.pointer.read_bytes(),published)
        self.assertEqual(rollback(self.root)['releaseId'],first['releaseId'])
        self.assertEqual(self.pointer.read_bytes(),prior_pointer)

    def test_accept_repeat_checksum_and_rollback(self):
        before=self.pointer.read_bytes();r=self.run_update();self.assertEqual(r['status'],'accepted')
        pointer=self.pointer.read_bytes();manifest=read_json(Path(read_json(self.pointer)['releaseManifest']['path']))
        bundle=Path(r['bundle'])
        for name,digest in manifest['files'].items():self.assertEqual(sha256_file(bundle/name),digest)
        self.assertEqual(self.run_update()['status'],'unchanged');self.assertEqual(self.pointer.read_bytes(),pointer)
        # Isolated fixture rollback verifies the prior collection checksum and restores the exact pointer.
        prior=manifest['predecessor']['pointer'];self.assertEqual(sha256_file(Path(prior['path'])),prior['sha256'])
        self.assertEqual(rollback(self.root)['status'],'rolled-back')
        self.assertEqual(self.pointer.read_bytes(),before);self.assertEqual(read_json(Path(read_json(self.pointer)['path'])),self.old)
    def test_restore_uses_only_local_receipts_and_rebases_rollback(self):
        workbook = portal_workbook(self.root/'new.xlsx', [portal_record('2')])
        release = self.run_update(portal_workbooks=[workbook])
        original_pointer = self.pointer.read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder).resolve()/'restored'
            shutil.copytree(self.root, dest)
            mappings = [(p, dest) for p in {self.root, self.root.resolve()}]
            restore = RestorePaths(mappings)
            local_pointer = dest/'datastores/combined-incidents.json'
            receipt = next((dest/'incident-inputs').rglob('records.xlsx'))
            data = receipt.read_bytes()
            receipt.write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                run_update(dest, dest/'data', offline=True, restore=restore)
            self.assertEqual(local_pointer.read_bytes(), original_pointer)
            receipt.write_bytes(data)
            result = run_update(dest, dest/'data', offline=True, restore=restore)
            self.assertEqual(result['status'], 'unchanged')
            self.assertEqual(read_json(local_pointer)['snapshotId'], release['releaseId'])
            for ref in (read_json(local_pointer), read_json(local_pointer)['releaseManifest'],
                        read_json(local_pointer)['reviewedLinksSource']):
                self.assertTrue(Path(ref['path']).is_relative_to(dest))
            before_rollback = local_pointer.read_bytes()
            (dest/'old.json').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                rollback(dest, restore=restore)
            self.assertEqual(local_pointer.read_bytes(), before_rollback)
            shutil.copyfile(self.old_path, dest/'old.json')
            self.assertEqual(rollback(dest, restore=restore)['releaseId'], 'original')
            self.assertEqual(Path(read_json(local_pointer)['path']), dest/'old.json')
            self.assertEqual(self.pointer.read_bytes(), original_pointer)

    def test_restore_rejects_path_outside_the_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder).resolve()
            restore = RestorePaths([(self.root, dest)])
            link = dest/'escape'
            link.symlink_to(self.old_path)
            with self.assertRaisesRegex(ValueError, 'escapes'):
                restore.local(self.root/'escape')
            with self.assertRaisesRegex(ValueError, 'Unmapped'):
                restore.local(Path('/unmapped/source.json'))

    def test_download_failure_preserves_pointer(self):
        before=self.pointer.read_bytes()
        with self.assertRaisesRegex(RuntimeError,'download failed'):
            self.run_update(offline=False,refresh=lambda _:(_ for _ in ()).throw(RuntimeError('download failed')))
        self.assertEqual(self.pointer.read_bytes(),before)
    def test_interruption_before_promotion_preserves_pointer(self):
        before=self.pointer.read_bytes()
        from danger_zones import update_incidents as mod
        original=mod.write_json
        def interrupt(path,value):
            if path.name=='candidate-pointer.json':raise RuntimeError('interrupted')
            original(path,value)
        with patch.object(mod,'write_json',side_effect=interrupt),self.assertRaisesRegex(RuntimeError,'interrupted'):self.run_update()
        self.assertEqual(self.pointer.read_bytes(),before)
    def test_corrupt_bundle_rejected(self):
        r=self.run_update();(Path(r['bundle'])/'collection.json').write_text('{}')
        before=self.pointer.read_bytes()
        with self.assertRaises(ValueError):self.run_update()
        self.assertEqual(self.pointer.read_bytes(),before)
    def test_partial_overlapping_exports_and_row_order_noop(self):
        p2,p3=portal_record('2'),portal_record('3')
        a=portal_workbook(self.root/'a.xlsx',[p2])
        b=portal_workbook(self.root/'b.xlsx',[p2,p3])
        result=self.run_update(portal_workbooks=[a,b]);pointer=read_json(self.pointer);records=flatten(read_json(Path(pointer['path'])))
        self.assertIn('udot-crashes:1',records);self.assertIn('utah-crash-portal:2',records);self.assertIn('utah-crash-portal:3',records)
        c=portal_workbook(self.root/'c.xlsx',[p2,p3],reverse=True)
        self.assertEqual(self.run_update(portal_workbooks=[c])['status'],'unchanged')
    def test_conflicting_fresh_exports_preserve_pointer(self):
        a=portal_record('2');b=deepcopy(a);b['metadata']['crash']['weatherCondition']='2'
        paths=[portal_workbook(self.root/'a.xlsx',[a]),portal_workbook(self.root/'b.xlsx',[b])]
        before=self.pointer.read_bytes()
        with self.assertRaisesRegex(ValueError,'exports conflict'):self.run_update(portal_workbooks=paths)
        self.assertEqual(self.pointer.read_bytes(),before)
    def test_updated_export_reports_source_correction(self):
        a=portal_record('2');path=portal_workbook(self.root/'a.xlsx',[a]);first=self.run_update(portal_workbooks=[path])
        a['metadata']['crash']['weatherCondition']='2';path=portal_workbook(self.root/'b.xlsx',[a])
        second=self.run_update(portal_workbooks=[path]);changes=read_json(Path(second['bundle'])/'changes.json')
        self.assertEqual(len(changes['changedSourceRecords']),1);self.assertFalse(changes['addedSourceRecords'])
        self.assertTrue((Path(first['bundle'])/'collection.json').exists())
    def test_person_code_without_label_still_includes_active_transport(self):
        o=portal_record('2');o['metadata']['crash']['cyclist_involved']='N'
        o['metadata']['rollups'][0]['cyclist_involved']='N';o['metadata']['persons'][0]['personType_label']=None
        path=portal_workbook(self.root/'coded.xlsx',[o]);result=self.run_update(portal_workbooks=[path])
        record=flatten(read_json(Path(read_json(self.pointer)['path'])))['utah-crash-portal:2']
        self.assertEqual(record['modes'],['bicycle'])
    def test_minute_only_clock_does_not_auto_link(self):
        o=portal_record();o['metadata']['crash']['crashDateandTime']='2025-03-04 09:30'
        old=collection([police_record()]);s=inputs(old,[o])
        new,rows,errors=make_collection(old,s,read_json(POLICY),'2026-11-03T20:00:00Z',Path('/tmp/review'),'abc')
        self.assertFalse(new['counts']['reviewedLinks'])
    def test_invalid_workbook_does_not_promote(self):
        p=self.root/'bad.xlsx';wb=Workbook();wb.save(p);before=self.pointer.read_bytes()
        with self.assertRaises((KeyError,ValueError)):self.run_update(portal_workbooks=[p])
        self.assertEqual(self.pointer.read_bytes(),before)
    def test_new_police_workbook_links_without_provider(self):
        p=self.root/'police.xlsx';wb=Workbook();sheet=wb.active
        sheet.append(['Case Number:','Date of Report:','Address:','Type:'])
        sheet.append(['P2',datetime(2025,3,4,9,30,0),'200 N UNIVERSITY AVE','Bicycle']);wb.save(p)
        with patch('danger_zones.update_incidents.bootstrap',side_effect=lambda *_:inputs(self.old,[portal_record()])),patch('danger_zones.police.latest_artifact',side_effect=FileNotFoundError):
            result=self.run_update(police_workbooks=[p])
        self.assertEqual(result['counts']['records'],1);self.assertEqual(result['counts']['reviewedLinks'],1)
        before=self.pointer.read_bytes();self.assertEqual(self.run_update(police_workbooks=[p])['status'],'unchanged')
        self.assertEqual(self.pointer.read_bytes(),before)
    def test_failed_promotion_can_be_retried(self):
        from danger_zones import update_incidents as mod
        original=mod.write_json
        def interrupt(path,value):
            if path.name=='candidate-pointer.json':raise RuntimeError('interrupted')
            original(path,value)
        with patch.object(mod,'write_json',side_effect=interrupt),self.assertRaises(RuntimeError):self.run_update()
        self.assertEqual(self.run_update()['status'],'accepted')
    def test_legacy_rebuild_cannot_replace_managed_release(self):
        self.run_update();before=self.pointer.read_bytes()
        from danger_zones.incidents import build_snapshot
        with self.assertRaisesRegex(ValueError,'Managed incident release'):build_snapshot(self.root/'data',self.root)
        self.assertEqual(self.pointer.read_bytes(),before)
    def test_code_change_during_run_blocks_acceptance(self):
        before=self.pointer.read_bytes()
        with patch('danger_zones.update_incidents.tool_hash',side_effect=['before','after']),self.assertRaisesRegex(ValueError,'Tool or policy changed'):
            self.run_update()
        self.assertEqual(self.pointer.read_bytes(),before)
    def test_lock_rejects_concurrent_updates(self):
        with update_lock(self.root),self.assertRaisesRegex(ValueError,'Another incident update'):self.run_update()

    def test_enrichment_rule_reprocessing_and_failure_preserves_pointer(self):
        first=self.run_update();bundle=Path(first['bundle'])
        current=read_json(bundle/'collection.json')
        self.assertTrue(all('enrichment' in g for g in current['records']))
        self.assertEqual(flatten(current),flatten(self.old))
        self.assertEqual(read_json(bundle/'changes.json')['enrichmentChangedGroups'],[self.old['records'][0]['id']])
        with patch('danger_zones.update_incidents.tool_hash',return_value='new-rules'):
            changed=self.run_update();self.assertNotEqual(changed['releaseId'],first['releaseId'])
            self.assertEqual(read_json(Path(changed['bundle'])/'changes.json')['changedSourceRecords'],[])
            self.assertEqual(self.run_update()['status'],'unchanged')
        before=self.pointer.read_bytes()
        with patch('danger_zones.crash_enrichment.enrich_collection',side_effect=ValueError('bad-code')):
            with self.assertRaisesRegex(ValueError,'bad-code'):self.run_update()
        self.assertEqual(self.pointer.read_bytes(),before)


if __name__=='__main__':unittest.main()


