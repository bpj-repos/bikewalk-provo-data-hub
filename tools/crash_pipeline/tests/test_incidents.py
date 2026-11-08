import copy
import unittest
from danger_zones.incidents import combine_observations


def observations():
    return [
        {"id": "udot-crashes:1", "sourceKey": "udot-crashes", "sourceRecordId": "1", "observedAt": "2025-03-04T16:30:00Z", "coordinates": [-111.66, 40.23], "modes": ["bicycle"], "metadata": {"severity": "minor"}},
        {"id": "provo-police-incidents:P1", "sourceKey": "provo-police-incidents", "sourceRecordId": "P1", "observedAt": "2025-03-04T16:31:00Z", "coordinates": [-111.6601, 40.23], "mode": "bicycle", "metadata": {"severity": None}},
    ]


class IncidentTests(unittest.TestCase):
    def test_nearby_observations_remain_distinct_until_reviewed(self):
        inputs = observations()
        original = copy.deepcopy(inputs)
        result = combine_observations(inputs, [])
        self.assertEqual(result["counts"]["records"], 2)
        self.assertEqual(result["counts"]["possibleMatches"], 1)
        self.assertEqual(inputs, original)
        self.assertEqual(result["possibleMatches"][0]["status"], "unreviewed")

    def test_reviewed_link_retains_both_source_values(self):
        link = {"policeId": "provo-police-incidents:P1", "udotId": "udot-crashes:1", "reviewer": "owner", "reviewedAt": "2026-11-02T20:00:00Z", "reason": "Verified source identity", "evidenceType": "agency-crosswalk", "evidence": "private crosswalk delivery"}
        with self.assertRaises(ValueError):
            combine_observations(observations(), [{**link, "evidenceType": "nearby-same-day"}])
        result = combine_observations(observations(), [link])
        self.assertEqual(result["counts"]["records"], 1)
        self.assertEqual(len(result["records"][0]["observations"]), 2)
        self.assertEqual(result["possibleMatches"], [])
        with self.assertRaises(ValueError):
            combine_observations(observations(), [link, link])
        with self.assertRaises(ValueError):
            combine_observations(observations(), [{**link, "udotId": "udot-crashes:missing"}])

    def test_merged_geography_follows_state_and_leaves_source_points_intact(self):
        from danger_zones.query_incidents import select
        obs = observations()
        link = dict(policeId=obs[1]["id"], udotId=obs[0]["id"], evidenceType="agency-crosswalk",
                    evidence="crosswalk", reviewer="owner", reason="verified", reviewedAt="2026-11-02T20:00:00Z")
        # A corroborated portal point supersedes both the UDOT layer and the local address.
        portal = {**obs[0], "sourceKey":"utah-crash-portal", "id":"utah-crash-portal:1",
                  "coordinates":[-111.67,40.24], "metadata":{"crash":{}}}
        obs[0]["statePortal"] = portal
        local = obs[1]["coordinates"][:]
        obs[1]["metadata"]["location"] = {"geocoding":{"status":"matched"}}
        def near(pt):
            return {"near":{"longitude":pt[0],"latitude":pt[1],"metres":1}}
        group, = combine_observations(obs,[link])["records"]
        self.assertEqual(group["resolvedCrash"]["coordinateSource"],portal["id"])
        self.assertEqual(group["resolvedCrash"]["coordinates"],portal["coordinates"])
        self.assertEqual(select([group],near(local))[0],[])
        self.assertEqual(select([group],near(portal["coordinates"]))[0],[group])
        self.assertEqual(obs[1]["coordinates"],local)
        del obs[0]["statePortal"]
        group, = combine_observations(obs,[link])["records"]
        self.assertEqual(group["resolvedCrash"]["coordinateSource"],obs[0]["id"])
        obs[0]["coordinates"] = None
        group, = combine_observations(obs,[link])["records"]
        self.assertIsNone(group["resolvedCrash"]["coordinates"])
        self.assertEqual(select([group],near(local))[1]["unknown"],1)

    def test_owner_authorized_circumstantial_link_is_explicit_and_reversible(self):
        link={'policeId':'provo-police-incidents:P1','udotId':'udot-crashes:1','reviewer':'owner-directed review',
              'reviewedAt':'2026-11-03T20:00:00Z','reason':'Strict rule reviewed', 'evidenceType':'owner-authorized-circumstantial',
              'evidence':'checksummed report','rule':'exact-clock-address','reviewReportSha256':'abc','authorization':'Owner requested reconciliation'}
        self.assertEqual(combine_observations(observations(),[link])['counts']['records'],1)
        with self.assertRaises(ValueError):combine_observations(observations(),[{**link,'authorization':''}])
        self.assertEqual(combine_observations(observations(),[])['counts']['records'],2)

    def test_dates_modes_and_locations_do_not_force_a_match(self):
        for changes in [{"observedAt": "2025-04-04T16:30:00Z"}, {"coordinates": None}, {"coordinates": [-111.7, 40.3]}]:
            inputs = observations()
            inputs[1].update(changes)
            self.assertEqual(combine_observations(inputs, [])["possibleMatches"], [])
        inputs = observations()
        inputs[0]["modes"] = ["pedestrian"]
        self.assertEqual(combine_observations(inputs, [])["possibleMatches"], [])

    def test_duplicate_ids_and_invalid_coordinates_rejected(self):
        inputs = observations()
        with self.assertRaises(ValueError):
            combine_observations(inputs + [inputs[0]], [])
        inputs[0]["coordinates"] = [999, 40]
        with self.assertRaises(ValueError):
            combine_observations(inputs, [])
