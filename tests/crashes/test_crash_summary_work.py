from pathlib import Path
import tempfile
import unittest

from danger_zones.update_incidents import SUMMARY_FIELDS, apply_summaries, summary_basis, summary_groups
from danger_zones.util import read_json, write_json
from scripts.crash_summaries import prepare, collect, resolve
from tests.crashes.test_update_incidents import police_record, portal_record


class SummaryWorkTests(unittest.TestCase):
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
