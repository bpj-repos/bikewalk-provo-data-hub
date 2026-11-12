import unittest
from scripts.build_provo_intersections import read


class SignalReports(unittest.TestCase):
    def test_reported_splits_and_cycles(self):
        sites = read("sites.geojson")["features"]
        self.assertEqual(len({s["id"] for s in sites}), 123)
        site = next(s for s in sites if s["id"] == "udot-atspm-6444")
        splits = {p["phase"]: p["splitSeconds"] for p in site["properties"]["reportedPlans"] if p["plan"] == "7"}
        self.assertEqual(splits, {1:None, 2:53, 3:15, 4:37, 5:None, 6:53, 7:15, 8:37})
        cycles = read("cycles-6444.json")
        self.assertEqual(len(cycles), 7)
        for cycle in cycles:
            self.assertTrue(all(cycle["start"] <= e[0] < cycle["end"] for e in cycle["events"]))
