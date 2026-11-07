import unittest
from danger_zones.crash_portal import enrich_state_records, portal_time


def state(identifier="123", observed="2025-03-04T16:30:00Z", point=None):
    return {"sourceKey": "udot-crashes", "sourceRecordId": identifier,
            "observedAt": observed, "coordinates": point or [-111.66, 40.23]}


def portal(identifier="123", observed="2025-03-04T09:30:00-07:00", point=None):
    return {**state(identifier, observed, point), "sourceKey": "utah-crash-portal"}


class PortalTests(unittest.TestCase):
    def test_shared_state_id_requires_corroborating_time_and_location(self):
        observations = [state()]
        result = enrich_state_records(observations, [portal()])
        self.assertEqual(result["joined"], 1)
        self.assertEqual(len(observations), 1)
        self.assertIn("stateJoinEvidence", observations[0])
        for other in [portal(observed="2025-03-05T09:30:00-07:00"),
                      portal(point=[-111.68, 40.23]), portal(identifier="456"),
                      {**portal(), "timePrecision": "date-only"}]:
            observations = [state()]
            result = enrich_state_records(observations, [other])
            self.assertEqual(result["joined"], 0)
            self.assertEqual(len(observations), 2)
            self.assertNotIn("statePortal", observations[0])

    def test_shared_id_time_and_exact_road_corroborate_small_coordinate_difference(self):
        a=state(); a['metadata']={'MAIN_ROAD_NAME':'300 N 900 WEST ST'}
        b=portal(point=[-111.6605,40.23]);b['metadata']={'crash':{'roadName':'300 N 900 WEST ST'}}
        items=[a];self.assertEqual(enrich_state_records(items,[b])['joined'],1)
        self.assertTrue(items[0]['stateJoinEvidence']['coordinateDisagreement'])
        self.assertEqual(items[0]['statePortal']['coordinates'],b['coordinates'])
        self.assertEqual(items[0]['coordinates'],a['coordinates'])
        b['coordinates']=[-111.68,40.23]
        self.assertEqual(enrich_state_records([state()],[b])['joined'],0)

    def test_mixed_iso_date_and_twelve_hour_clock(self):
        self.assertEqual(portal_time('2020-01-17 07:30:00 PM'),portal_time('2020-01-17T19:30:00'))

    def test_portal_local_formats_share_the_same_timezone(self):
        self.assertEqual(portal_time("1/28/2019 6:50:12 AM"),
                         portal_time("2019-01-28 06:50:12"))
        self.assertEqual(portal_time("2025-03-04 09:30:00"), portal_time("2025-03-04T16:30:00Z"))
