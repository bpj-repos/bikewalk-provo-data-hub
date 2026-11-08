import unittest
from copy import deepcopy

from danger_zones.address_points import apply_address_points, LAYER, WHERE
from danger_zones.police_datastore import normalize_police_location


class AddressTests(unittest.TestCase):
    def test_one_exact_point_or_blank_and_reapply_reference(self):
        labels = ["123 E 100 NORTH ST; private note", "125 E 100 N", "127 E 100 N", None]
        def record(label):
            return {"mode": {"category":"bicycle"}, "location": {**normalize_police_location(label),
                    "geocoding": {"status":"not-geocoded","mapEligible":False}}}
        store = {"records": list(map(record,labels))}
        rows = [[1,"123 E 100 N","a",-111.66,40.23],[2,"125 E 100 N","b",-111.67,40.23],
                [3,"125 E 100 N","c",-111.68,40.23]]
        ref = {"source":LAYER,"where":WHERE,"rows":rows}
        apply_address_points(store,ref,"hash")
        geo = [r["location"]["geocoding"] for r in store["records"]]
        self.assertEqual([g["status"] for g in geo],["matched","review-required","unmatched","not-geocoded"])
        self.assertEqual(geo[0]["coordinates"], {"lng":-111.66,"lat":40.23})
        self.assertIsNone(geo[1]["coordinates"])
        self.assertEqual(geo[0]["addressPointIDs"], ["a"])
        self.assertEqual(store["records"][0]["location"]["raw"],labels[0])
        repeated = deepcopy(store)
        apply_address_points(store,ref,"hash")
        self.assertEqual(store,repeated)
        apply_address_points(store,{**ref,"rows":rows[1:]},"new-hash")
        self.assertIsNone(store["records"][0]["location"]["geocoding"]["coordinates"])
