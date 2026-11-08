import unittest
from danger_zones.concern_details import reviewed_report


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
