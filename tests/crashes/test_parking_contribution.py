from pathlib import Path
import tempfile
import unittest

from danger_zones.parking_contribution import FIELD, RULE, apply_reviews, screen
from scripts.bike_lane_parking import project


class ParkingTests(unittest.TestCase):
    def test_private_screen_is_a_lead_only(self):
        examples = [
            ('A car parked in the bike lane. The rider hit it.', 'possible'),
            ('A truck was unloading. The rider swerved around it and fell.', 'possible'),
            ('A vehicle blocked the cycle track. The rider merged and was struck.', 'possible'),
            ('A van stopped at a red light. A cyclist hit it.', 'unknown'),
            ('The van was parked after the crash.', 'unknown'),
            ('No vehicle was parked in the bike lane. A witness denied an obstruction.', 'unknown'),
            ('The door opened from a parking bay.', 'unknown'),
            ('Accounts conflict about a van parked in the bicycle lane.', 'unknown'),
            ('Amazon van eastbound.', 'unknown'),
            ('', 'unknown'),
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'report.txt'
            for sentence, expected in examples:
                with self.subTest(sentence=sentence):
                    path.write_text('Cover page\f' + sentence)
                    result = screen(path)
                    self.assertEqual(result['proposal'], expected)
                    self.assertTrue(all(p['page'] == 2 for p in result['passages']))

    def test_review_requires_current_unique_case_link(self):
        group = {'id': 'g', 'observations': [{'sourceKey': 'udot-crashes', 'sourceRecordId': '1'}], 'enrichment': {}}
        review = {'case': 'state:1', 'links': ['state:1'], 'receipt': 'example', 'rule': RULE, 'value': 'documented'}
        apply_reviews([group], {'g': review})
        layer = {'features': [{'properties': {'details': {'UDOT: CRASH_ID': 1}}}]}
        self.assertEqual(project(layer, [group])['reviewedGroups'], 1)
        layer['features'] *= 2
        self.assertEqual(project(layer, [group])['categories']['unknown'], 2)
        group['observations'].append({'sourceKey': 'provo-police-incidents', 'sourceRecordId': 'X'})
        apply_reviews([group], {'g': review})
        self.assertEqual(group['enrichment'][FIELD], 'unknown')
        self.assertEqual(project({'features': layer['features'][:1]}, [group])['reviewedGroups'], 0)

    def test_original_and_review_survive_replay_and_changed_bytes_are_rejected(self):
        from danger_zones.parking_contribution import import_reviews
        from danger_zones.update_incidents import retain_input
        from danger_zones.util import read_json, write_json
        from scripts.bike_lane_parking import screen_case
        group = {'id': 'g', 'observations': [{'sourceKey': 'utah-crash-portal', 'sourceRecordId': '1'}], 'enrichment': {}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / 'original.txt'
            report.write_text('A truck parked in the bike lane. The rider swerved to avoid it and fell.')
            packet = screen_case([group], 'state:1', [report])
            packet.update(value='documented', reviewer='fixture', rationale='Page 1 establishes position and avoidance.')
            path = root / 'review.json'
            write_json(path, packet)
            state = {'inputs': []}
            for _ in range(2):
                import_reviews(path, state, root, {'records': [group]}, retain_input, read_json)
            self.assertEqual(len(state['inputs']), 2)
            apply_reviews([group], state['parkingReviews'])
            self.assertEqual(group['enrichment'][FIELD], 'documented')
            report.write_text('Corrected report')
            with self.assertRaisesRegex(ValueError, 'changed'):
                import_reviews(path, state, root, {'records': [group]}, retain_input, read_json)
