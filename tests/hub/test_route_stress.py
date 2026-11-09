"""Regression checks on the pinned export; standard-library hub suite."""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "releases/datasets/safe-routes-to-school"


def rows(name):
    return json.loads((ROOT / "1.2.0" / (name + ".geojson")).read_text())["features"]


class StressRelease(unittest.TestCase):
    def test_all_base_geometry_preserved_and_lengths_reconciled(self):
        import math
        from collections import defaultdict

        sums = defaultdict(float)
        routes = rows("safe-school-routes")
        for key in (
            "safe-school-routes",
            "safe-route-plan-features",
            "safe-routes-schools",
        ):
            self.assertEqual(
                (ROOT / "1.1.0" / (key + ".geojson")).read_bytes(),
                (ROOT / "1.2.0" / (key + ".geojson")).read_bytes(),
            )
        lookup = {r["id"]: r["properties"]["schoolId"] for r in routes}
        for f in rows("safe-route-stress-segments"):
            p = f["properties"]
            self.assertEqual(lookup[p["routeId"]], p["schoolId"])
            sums[(p["routeId"], p["part"])] += p["lengthMeters"]
            self.assertGreater(p["lengthMeters"], 0)
        for f in routes:
            parts = f["geometry"]["coordinates"]
            if f["geometry"]["type"] == "LineString":
                parts = [parts]
            for index, line in enumerate(parts):
                meters = sum(
                    math.hypot(
                        (b[0] - a[0])
                        * 111320
                        * math.cos(math.radians((b[1] + a[1]) / 2)),
                        (b[1] - a[1]) * 111132,
                    )
                    for a, b in zip(line, line[1:])
                )
                self.assertAlmostEqual(
                    sums[(f["id"], index)], meters, delta=max(0.02, 0.005 * meters)
                )

    def test_quiet_approach_to_a_stressful_crossing(self):
        x = next(
            f
            for f in rows("safe-route-stress-crossings")
            if f["properties"].get("crossStreet") == "800 North"
            and f["properties"]["schoolName"] == "Timpanogos"
            and f["properties"]["stress"] == "higher"
        )
        p = x["properties"]
        approaches = [
            f["properties"]
            for f in rows("safe-route-stress-segments")
            if f["properties"]["routeId"] == p["routeId"]
            and f["properties"]["sourceId"] in {str(a) for a in p["approachIds"]}
        ]
        self.assertTrue(approaches)
        self.assertTrue(all(a["stress"] == "lower" for a in approaches))
        self.assertTrue(
            all(
                f["properties"]["stress"] == "unassessed"
                for f in rows("safe-route-stress-crossings")
                if f["properties"]["matchStatus"] == "plan-crosswalk"
            )
        )
