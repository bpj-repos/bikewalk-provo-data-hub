import json
import unittest

from scripts.prepare_crash_streets import DATASET, ROOT, match


class StreetMembershipTests(unittest.TestCase):
    def test_grid_and_names(self):
        names = {n: n for n in ('200 NORTH', '200 SOUTH', 'UNIVERSITY AVENUE', 'UNIVERSITY PARKWAY')}
        for raw, expected in [('500 W 200 NORTH ST', '200 NORTH'), ('200 S ST', '200 SOUTH'),
                              ('100 N UNIVERSITY AVE', 'UNIVERSITY AVENUE'),
                              ('N UNIVERSITY PKWY', 'UNIVERSITY PARKWAY'), ('300 S UNIVERSITY', None)]:
            self.assertEqual(match(raw, names)[0], expected)

    def test_released_membership(self):
        folder = ROOT/'releases/datasets'/DATASET/'1.0.0'
        rows = json.loads((folder/'membership.json').read_bytes())
        directory = json.loads((folder/'streets.json').read_bytes())
        coverage = json.loads((folder/'coverage.json').read_bytes())
        self.assertEqual(coverage['explicitUniversityAvenue'], 231)
        self.assertEqual(coverage['explicitOnly'], [])
        self.assertEqual(len(rows), 1358)
        self.assertTrue(any({'provo:university-avenue', 'provo:university-parkway'} <= set(row['streetIds'])
                            for row in rows.values()))
        for row in rows.values():
            self.assertEqual(row['streetIds'], sorted({e['streetId'] for e in row['evidence']}))
            self.assertTrue(all(i in directory for i in row['streetIds']))
