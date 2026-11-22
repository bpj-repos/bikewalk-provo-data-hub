from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from danger_zones.update_incidents import SUMMARY_FIELDS, apply_summaries, summary_basis, summary_groups
from danger_zones.util import read_json, write_json
from scripts.crash_summaries import prepare, collect, resolve, pending_work
from tests.crashes.test_update_incidents import police_record, portal_record


class SummaryWorkTests(unittest.TestCase):
    def test_ambiguous_state_id_gets_separate_group_summaries(self):
        from tests.crashes.test_update_incidents import state_record
        a = {'id': 'udot-crashes:123', 'observations': [state_record('123')], 'enrichment': {}}
        b = {'id': 'utah-crash-portal:123', 'observations': [portal_record('123')], 'enrichment': {}}
        collection = {'records': [a, b]}
        groups = summary_groups(collection, {'123', 'group:' + a['id'], 'group:' + b['id']})
        self.assertIsNone(groups['123'])
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            resolve('123', groups)
        key = 'group:' + b['id']
        self.assertEqual(resolve(key, groups), key)
        summary = dict.fromkeys(SUMMARY_FIELDS, '')
        summary['brief'] = 'Car hit bicyclist.'
        self.assertEqual(apply_summaries(collection, {key: {'basis': summary_basis(b), 'summary': summary}}), [])
        self.assertNotIn('reviewedSummary', a['enrichment'])
        self.assertEqual(b['enrichment']['reviewedSummary'], summary)

    def test_batch_resume_stale_draft_and_police_lookup(self):
        pd = police_record('24PR12345')
        state = portal_record('123')
        group = {'observations':[pd,state], 'enrichment':{}}
        groups = summary_groups({'records':[group]}, {'123'})
        self.assertEqual(resolve('24PR12345',groups),'123')
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)/'batch'
            prepare(work, groups, ['123'], 'first-pin')
            packet = read_json(work/'123.input.json')
            self.assertNotIn('notes',str(packet))
            person = next(o for o in packet['observations'] if 'portal.persons' in o)['portal.persons'][0]
            self.assertEqual(person['ageGroup'],'18–64')
            self.assertNotIn('ageCalculated', person)
            summary = dict.fromkeys(SUMMARY_FIELDS, '')
            summary['brief'] = 'Bicycle involved.'
            write_json(work/'123.summary.json',summary)
            self.assertEqual(collect(work,groups,'next-pin'),{'collectionSHA256':'next-pin','summaries':{'123':summary}})
            group['enrichment']['reviewedSummary'] = summary
            self.assertFalse(collect(work,groups,'next-pin')['summaries'])
            group['enrichment']['reviewedSummary'] = {**summary,'brief':'Different reviewed wording.'}
            with self.assertRaisesRegex(ValueError,'Concurrent summary'):
                collect(work,groups,'next-pin')
            state['metadata']['crash']['roadName'] = 'Corrected'
            with self.assertRaisesRegex(ValueError,'Reporting changed'):
                collect(work,groups,'next-pin')
        lone = {'observations':[pd], 'enrichment':{}}
        key = pd['id']
        groups = summary_groups({'records':[lone]}, {key})
        self.assertEqual(resolve('24PR12345', groups),key)
        self.assertEqual(apply_summaries({'records':[lone]}, {key:{'basis':summary_basis(lone),'summary':summary}}),[])
        self.assertEqual(lone['enrichment']['reviewedSummary'],summary)

    def test_update_summary_queue_resumes_and_reports_readiness(self):
        group = {'observations': [portal_record('123')], 'enrichment': {}}
        groups = {'123': group, '456': None}
        pointer = {'snapshotId': 'incidents-test', 'sha256': 'test-pin'}
        with tempfile.TemporaryDirectory() as tmp, \
                patch('scripts.crash_summaries.DEFAULT_PRIVATE_DATA_ROOT', Path(tmp)), \
                patch('scripts.crash_summaries.snapshot', return_value=(pointer, groups)):
            first = pending_work()
            self.assertEqual(first['status'], 'needs-summary-review')
            self.assertEqual(first['ambiguousIds'], ['456'])
            work = Path(first['work'])
            (work / '123.summary.json').write_text('preserve draft')
            self.assertEqual(pending_work(), first)
            self.assertEqual((work / '123.summary.json').read_text(), 'preserve draft')
            group['enrichment']['reviewedSummary'] = dict.fromkeys(SUMMARY_FIELDS, '')
            ready = pending_work()
            self.assertEqual(ready['status'], 'ready')
            self.assertEqual(ready['pending'], [])
            self.assertNotIn('nextCommand', ready)

    def test_update_wrapper_emits_one_result_and_reports_partial_failure(self):
        import io, json
        from contextlib import redirect_stdout
        from scripts.update_crashes import run
        from argparse import Namespace
        parsed = (Namespace(rollback=False, offline=True), Path('/tmp/test'), None, None)
        with patch('scripts.update_crashes.main', return_value={'status':'accepted', 'releaseId':'new'}), \
                patch('scripts.update_crashes.parse_args', return_value=parsed), \
                patch('scripts.update_crashes.producer_preflight'), \
                patch('scripts.update_crashes.read_json', return_value={'snapshotId':'new'}), \
                patch('scripts.crash_summaries.pending_work', return_value={'pending':['123'], 'nextCommand':'review'}), \
                patch('sys.argv', ['update_crashes.py', '--offline', '--json']):
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(run(), 2)
            self.assertEqual(json.loads(out.getvalue())['status'], 'needs-summary-review')
            with patch('scripts.crash_summaries.pending_work', return_value={'pending':[]}), \
                    patch('scripts.crash_road_segments.refresh', side_effect=ValueError('missing capture')):
                out = io.StringIO()
                with redirect_stdout(out):
                    self.assertEqual(run(), 1)
                result = json.loads(out.getvalue())
                self.assertEqual(result['status'], 'partially-complete')
                self.assertEqual(result['releaseId'], 'new')
                self.assertEqual(result['blockedStage'], 'roadSegments')

    def test_receipt_review_includes_all_consumer_changes(self):
        from scripts.review_crash_receipt import semantic_changes
        a = {'crashes': {'1': {'releaseId':'old', 'reviewedSummary':{'brief':'Old'}}, '2':{}, '4':{'releaseId':'old'}}}
        b = {'crashes': {'1': {'releaseId':'new', 'reviewedSummary':{'brief':'New'}, 'recordedRoadName':'Main'}, '3':{}, '4':{'releaseId':'new'}}}
        diff = semantic_changes(a,b)
        self.assertEqual(diff['added'], ['3'])
        self.assertEqual(diff['removed'], ['2'])
        self.assertEqual(set(diff['changed']['1']), {'reviewedSummary', 'recordedRoadName'})
        self.assertNotIn('4', diff['changed'])

    def test_preflight_rejects_checkout_before_active_producer(self):
        from scripts.update_crashes import producer_preflight
        from types import SimpleNamespace
        with patch('scripts.update_crashes.read_json', side_effect=[{'path':'/tmp/collection', 'sha256':'pin'}, {'producerCommit':'newer'}]), \
                patch('scripts.update_crashes.sha256_file', return_value='pin'), \
                patch('scripts.update_crashes.subprocess.run', return_value=SimpleNamespace(returncode=1)):
            with self.assertRaisesRegex(ValueError, 'predates or diverges'):
                producer_preflight(Path('/tmp'))
