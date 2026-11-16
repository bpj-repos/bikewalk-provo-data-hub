import json
import os
import unittest
from collections import Counter
from pathlib import Path

from scripts.prepare_bike_parking import normalize, ROOT


class BikeParkingTest(unittest.TestCase):
    def test_unknown_parent_and_incomplete_inventory(self):
        point = {"attributes": {"OBJECTID": 1, "GlobalID": "{00000000-0000-4000-8000-000000000001}",
                 "FOLDERPATH": ROOT + "Future/Ideal Bike Racks", "NAME": None, "CAPTION": None},
                 "geometry": {"x": -111.65, "y": 40.23}}
        data = {"spatialReference": {"wkid": 4326}, "features": [point]}
        rows, flags = normalize(data, [1])
        self.assertEqual(rows[0]["properties"]["category"], "Unclassified")
        self.assertEqual(flags, [point["attributes"]["FOLDERPATH"]])
        with self.assertRaises(ValueError):
            normalize(data, [1, 2])

    @unittest.skipUnless(os.getenv("BWP_SOURCE_REPO"), "requires canonical research archive")
    def test_november_archive(self):
        base = Path(os.environ["BWP_SOURCE_REPO"]) / "docs/research/transportation-source-snapshots/bicycles-2026-11-08"
        data = json.loads((base / "provo-bike-parking.features.json").read_bytes())
        rows, flags = normalize(data, [row["attributes"]["OBJECTID"] for row in data["features"]])
        self.assertEqual(flags, [])
        counts = Counter(row["properties"]["category"] for row in rows)
        self.assertEqual(counts, {"Ideal Bike Racks": 108, "Racks that can be improved": 93,
            "Places where racks should be added": 44, "Lockers, Maintenance, Etc.": 10, "Unclassified": 248})
        self.assertEqual(len(rows), 503)
        self.assertEqual(counts["Ideal Bike Racks"] + counts["Racks that can be improved"], 201)
        self.assertEqual(sum(not row["properties"]["name"] for row in rows), 7)
        self.assertEqual(rows[0]["properties"]["name"], "Utah County Historic Courthouse")
        lon, lat = rows[0]["geometry"]["coordinates"]
        self.assertAlmostEqual(lon, -111.65760, places=4)
        self.assertAlmostEqual(lat, 40.23285, places=4)
