import unittest
from copy import deepcopy
from danger_zones.match_review import POLICY, review, validate_policy, state_signature, address_agrees, previous_year
from danger_zones.util import read_json

class MatchReviewTests(unittest.TestCase):
    def setUp(self):
        self.rules = read_json(POLICY)
        self.p = dict(id='local',date='2025-06-01',time='12:13:14',address='200 N UNIVERSITY AVE',notes=None,
                      mode='bicycle',coordinates=[-111.66,40.23],geocoding={'status':'matched'})
        self.c = dict(id='state',date='2025-06-01',time='12:13:14',road='200 N UNIVERSITY AVE',
                      modes=['bicycle'],coordinates=[-111.66,40.23],sourceConflict=False)
    def run_one(self,p=None,c=None):
        return review([p or self.p],[c or self.c],self.rules)[0]
    def test_clock_address_recovers_far_point_without_confirming_identity(self):
        r=self.run_one(c=dict(self.c,coordinates=[-111.66,40.28]))
        self.assertEqual(r['status'],'distinctive-circumstantial-lead')
        self.assertFalse(r['documentaryIdentityConfirmed'])
        self.assertGreater(r['candidates'][0]['distanceMetres'],5000)
    def test_street_result_is_manual_error_and_not_spatial_evidence(self):
        p=deepcopy(self.p);p['geocoding']['providerCandidates']=[{'properties':{'kind':'street'}}]
        r=self.run_one(p,dict(self.c,time='14:00:00',road='900 W CENTER ST'))
        self.assertTrue(r['manualConfirmationRequired']);self.assertEqual(r['candidates'],[])
        self.assertIn('street-only-geocode-possible-input-or-validation-error',r['validationFlags'])
    def test_missing_address_and_coordinates_preserve_exact_clock_lead(self):
        r=self.run_one(dict(self.p,address=None,coordinates=None))
        self.assertEqual(r['candidates'][0]['tier'],'exact-clock')
        self.assertEqual(r['status'],'distinctive-circumstantial-lead')
    def test_exact_address_and_clock_preserve_police_mode_despite_absent_state_flag(self):
        r=self.run_one(c=dict(self.c,modes=[]))
        self.assertEqual(r['status'],'distinctive-circumstantial-lead')
        self.assertIn('no-active-transportation-evidence',r['candidates'][0]['conflicts'])
    def test_both_competing_police_records_remain_ambiguous(self):
        r=review([self.p,dict(self.p,id='other')],[self.c],self.rules)
        self.assertEqual([x['status'] for x in r],['ambiguous','ambiguous'])
    def test_multiple_state_records_at_top_remain_ambiguous(self):
        r=review([self.p],[self.c,dict(self.c,id='other')],self.rules)[0]
        self.assertEqual(r['status'],'ambiguous')
    def test_order_is_deterministic(self):
        a=[self.p,dict(self.p,id='other')];b=[self.c,dict(self.c,id='other')]
        self.assertEqual(review(a,b,self.rules),review(a[::-1],b[::-1],self.rules))
    def test_delayed_window_is_address_only(self):
        p=dict(self.p,notes='DELAYED')
        self.assertEqual(self.run_one(p,dict(self.c,date='2024-06-01'))['candidates'][0]['tier'],'window-address-at')
        self.assertEqual(self.run_one(p,dict(self.c,date='2024-05-31'))['candidates'],[])
        self.assertEqual(self.run_one(p,dict(self.c,date='2024-06-01',road='900 W CENTER ST'))['candidates'],[])
    def test_source_conflict_blocks_distinctive_status(self):
        self.assertEqual(self.run_one(c=dict(self.c,sourceConflict=True))['status'],'candidate-only')
    def test_mode_conflict_is_not_silently_confirmed(self):
        self.assertEqual(self.run_one(c=dict(self.c,modes=['pedestrian']))['status'],'distinctive-circumstantial-lead')
    def test_bad_policy_and_duplicate_ids_fail(self):
        with self.assertRaises(ValueError):validate_policy(dict(self.rules,wideMetres=float('nan')))
        with self.assertRaises(ValueError):review([self.p,self.p],[self.c],self.rules)
    def test_row_order_does_not_create_export_conflicts(self):
        a=dict(self.c,people=[{'age':22},{'age':33}],scopes=['city'],sourceRow=2)
        b=dict(a,people=a['people'][::-1],scopes=['county'],sourceRow=200)
        self.assertEqual(state_signature(a),state_signature(b))
        self.assertNotEqual(state_signature(a),state_signature(dict(b,road='OTHER ROAD')))
    def test_address_grid_roles_are_not_interchangeable(self):
        self.assertTrue(address_agrees('200 NORTH 300 WEST ST','300 WEST ST & 200 N',3))
        self.assertFalse(address_agrees('200 N 300 W','300 N 200 W',3))
        self.assertFalse(address_agrees('900 E','900 E BIRCH LN',3))
    def test_named_intersections_match_both_streets_even_when_order_reverses(self):
        self.assertTrue(address_agrees('E COUGAR BLVD & N UNIVERSITY AVE','N UNIVERSITY AVENUE  E COUGAR BOULEVARD',3))
        self.assertFalse(address_agrees('E COUGAR BLVD & N UNIVERSITY AVE','S UNIVERSITY AVE  E COUGAR BLVD',3))
        self.assertEqual(self.run_one(c=dict(self.c,road='500 W CENTER ST'))['status'],'candidate-only')
    def test_control_year_and_leap_day(self):
        self.assertEqual(previous_year('2024-02-29'),'2023-02-28')
        self.assertEqual(previous_year('2025-06-01'),'2024-06-01')
    def test_date_and_spatial_windows(self):
        self.assertEqual(self.run_one(c=dict(self.c,date='2025-07-02'))['candidates'],[])
        self.assertEqual(self.run_one(c=dict(self.c,date='2025-05-31',road='OTHER RD'))['candidates'][0]['tier'],'near-day-tight-at')

if __name__ == '__main__': unittest.main()
