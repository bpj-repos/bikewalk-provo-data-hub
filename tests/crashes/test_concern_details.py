import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from danger_zones.concern_details import export_concern_details, public_summary, reviewed_report
from danger_zones.crash_enrichment import enrich_collection
from danger_zones.update_incidents import SUMMARY_FIELDS
from danger_zones.util import sha256_file, write_json
from tests.crashes.test_crash_enrichment import fixture


class ReviewedPoliceReportTest(unittest.TestCase):
    def test_review_basis_and_source_binding(self):
        pd = {'id': 'provo-police-incidents:26PRW1234', 'sourceKey': 'provo-police-incidents', 'sourceRecordId': '26PRW1234'}
        state = {'id': 'utah-crash-portal:123', 'sourceKey': 'utah-crash-portal', 'sourceRecordId': '123'}
        group = {'observations': [pd, state]}
        self.assertIsNone(reviewed_report(group))
        group['reviewedLink'] = {'policeId': pd['id'], 'udotId': state['id'], 'evidenceType': 'manual-case-review',
                                 'confidence': 'probable', 'evidence': {'private': 'source material'}}
        self.assertEqual(reviewed_report(group), ('123', {'caseNumber': '26PRW1234', 'basis': 'probable'}))
        group['reviewedLink']['confidence'] = 'unreviewed'
        with self.assertRaisesRegex(ValueError, 'basis'):
            reviewed_report(group)

class ReviewedSummaryExportTest(unittest.TestCase):
    def test_unique_id_absent_and_withdrawn_summary(self):
        collection = fixture()
        enrich_collection(collection)
        group = collection['records'][0]
        summary = {k: '' for k in SUMMARY_FIELDS}
        summary['brief'] = 'A vehicle hit a person in a marked crossing.'
        with TemporaryDirectory() as folder:
            root = Path(folder)
            def export():
                write_json(root / 'collection.json', collection)
                write_json(root / 'manifest.json', {'releaseId': collection['snapshotId'],
                           'files': {'collection.json': sha256_file(root / 'collection.json')}})
                return export_concern_details(root, sha256_file(root / 'manifest.json'))
            group['enrichment']['reviewedSummary'] = summary
            result = export()
            self.assertEqual(result['schemaVersion'], 3)
            row = result['crashes']['123']
            self.assertEqual(row['schemaVersion'], 3)
            self.assertEqual(row['reviewedSummary'], summary)
            self.assertEqual(len(row['fields']), 7)
            collection['records'].append(deepcopy(group))
            self.assertEqual(export()['crashes'], {})
            collection['records'].pop()
            del group['enrichment']['reviewedSummary']
            self.assertNotIn('reviewedSummary', export()['crashes']['123'])

    def test_rejects_unreviewed_fields_and_invalid_text(self):
        summary = dict.fromkeys(SUMMARY_FIELDS, '')
        summary['brief'] = 'Person crossing the road.'
        for invalid in ({'privateNote': 'private'}, {'time': 'text\nmore'}, {'outcome': ' '},
                        {'brief': 'word ' * 13}, {'conditions': '🌧' * 1001}, {'otherFactors': None}):
            with self.subTest(keys=list(invalid)), self.assertRaisesRegex(ValueError, 'Invalid public'):
                public_summary({**summary, **invalid}, '123')
