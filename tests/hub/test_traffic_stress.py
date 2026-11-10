import copy
import itertools
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

try:
    from shapely.geometry import LineString, Point, box, mapping
    from pipelines.traffic_stress.network import (PUBLISHED, UTAH, LOCAL, Ratings, band, build,
                                                 directions, eligibility, furth_crossing, select)
except ImportError:
    Ratings = None


def observation(source, score, **extra):
    return dict(source=source, score=score, applicable=True, recordId='1', **extra)


@unittest.skipIf(Ratings is None, 'Requires pinned GIS environment')
class TrafficStress(unittest.TestCase):
    def test_conflict_always_selects_same_source(self):
        rows = [observation(PUBLISHED, 3), observation(UTAH, 2), observation(LOCAL, 1)]
        for order in itertools.permutations(rows):
            result = select(order)
            self.assertEqual(result['source'], PUBLISHED)
            self.assertEqual(result['selectionReason'], 'published_directional_tiebreak')
            self.assertTrue(result['disagreement'])
        rows[1]['betterEvidence'] = {'reference': 'dated facility record'}
        self.assertEqual(select(rows)['source'], UTAH)
        rows[0]['betterEvidence'] = {'reference': 'other dated record'}
        self.assertEqual(select(rows)['source'], PUBLISHED)
        self.assertEqual(len(rows), 3)

    def test_missing_and_zero(self):
        self.assertIsNone(select([])['band'])
        self.assertEqual(select([observation(UTAH, 0)])['band'], 'lower')
        self.assertEqual(select([observation(LOCAL, 3)])['selectionReason'], 'published_method_gap_fill')
        row = observation(PUBLISHED, 1)
        row['applicable'] = False
        self.assertIsNone(select([row])['score'])
        with self.assertRaises(ValueError):
            band(5)

    def test_direction_and_access(self):
        self.assertEqual(directions({'oneway': '-1'}), ['reverse'])
        self.assertEqual(directions({'oneway': 'yes', 'oneway:bicycle': 'no'}), ['forward', 'reverse'])
        self.assertEqual(eligibility({'highway': 'service', 'service': 'alley'}), 'eligible')
        self.assertEqual(eligibility({'highway': 'service', 'service': 'parking_aisle'}), 'service_access')
        self.assertEqual(eligibility({'highway': 'path', 'bicycle': 'no'}), 'ineligible')
        self.assertEqual(eligibility({'highway': 'footway'}), 'access_unknown')

    def test_original_furth_crossing_table(self):
        self.assertEqual(furth_crossing(25, 5, False), 2)
        self.assertEqual(furth_crossing(25, 5, True), 1)
        self.assertEqual(furth_crossing(40, 2, False), 3)
        self.assertEqual(furth_crossing(35, 6, True), 4)
        self.assertIsNone(furth_crossing(None, 4, False))
        self.assertIsNone(furth_crossing(25, 4, None))
        with self.assertRaises(ValueError):
            furth_crossing(25, 0, False)

    def test_utah_scope_grade_and_reversed_match(self):
        geometry = LineString([(-111.66, 40.23), (-111.65, 40.23)])
        props = dict(OBJECTID=1, LTS_SCORE='2: Interested but concerned', SOURCE='Utah Roads',
                     Facility1='Bike lane (2B)', Facility2='Not Available', Facility1_Side='North Side')
        net = Ratings([dict(geometry=mapping(geometry), properties=props)], UTAH, 'test', geometry.buffer(.01))
        from shapely.ops import transform
        from scripts.route_stress import PROJECT, tangent
        line = transform(PROJECT, geometry)
        point = line.interpolate(line.length/2)
        match, reason = net.match(point, tangent(line, line.length/2), {'highway': 'residential'})
        self.assertEqual(reason, 'matched')
        self.assertFalse(net.observation(match, 'forward')['applicable'])
        self.assertTrue(net.observation(match, 'unspecified')['applicable'])
        self.assertEqual(net.match(point, tangent(line, line.length/2), {'highway': 'residential', 'bridge': 'yes'})[1], 'grade_not_documented')

    def test_topology_length_endpoints_and_model_gap_fill(self):
        coords = {'1': [-111.66, 40.23], '2': [-111.65, 40.23], '3': [-111.65, 40.24], '4': [-111.64, 40.23]}
        ways = [[10, [1, 2], {'highway': 'residential'}], [20, [2, 3], {'highway': 'residential'}], [30, [2, 4], {'highway': 'residential'}]]
        rows = []
        for wid, ns, _ in ways:
            rows.append(dict(geometry=mapping(LineString([coords[str(n)] for n in ns])), properties=dict(
                road_id=wid, osm_id=wid, one_way=None, ft_seg_stress=1, tf_seg_stress=3, ft_int_stress=3,
                tf_int_stress=1, intersection_from=ns[0], intersection_to=ns[-1])))
        inputs = dict(boundary=dict(features=[dict(geometry=mapping(box(-111.67,40.22,-111.63,40.25)))]),
                      network=dict(coords=coords, ways=ways), published=dict(features=[]), local=dict(features=rows),
                      utah=dict(features=[]), **{'city-streets': dict(features=[]), 'sgid-streets': dict(features=[])})
        meta = {key: dict(version='test') for key in ('published', 'local', 'utah')}
        segments, approaches, _, coverage = build(inputs, meta, [])
        self.assertEqual(len(approaches), 3)
        self.assertTrue(all(f['properties']['incomingSegments'] for f in approaches))
        self.assertTrue(all(f['properties']['source'] == LOCAL for f in segments))
        c = coverage['byRoadClass']['residential']
        self.assertAlmostEqual(c['eligibleDirectionMeters'], c['physicalMeters']*2, places=2)
        self.assertAlmostEqual(c['ratedPhysicalMeters'], c['physicalMeters'], places=2)
        self.assertEqual(coverage['approaches']['rated'], 3)
        inputs['local']['features'].reverse()
        self.assertEqual((segments, approaches), build(inputs, meta, [])[:2])

    def test_receipt_rejects_changed_source_before_build(self):
        import hashlib
        import json
        from scripts.prepare_traffic_stress import prepare
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'source.json').write_text('{}')
            (root/'receipt.json').write_text(json.dumps(dict(sources=dict(network=dict(path='source.json',sha256='0'*64)))))
            with self.assertRaisesRegex(ValueError, 'Source pin mismatch'):
                prepare(root/'receipt.json',root/'out')
            self.assertFalse((root/'out').exists())

    def test_source_only_published_ratings_survive_reference_gaps(self):
        coords = {'1': [-111.66,40.23], '2': [-111.65,40.23], '3': [-111.65,40.24], '4': [-111.64,40.23]}
        rows=[]
        for wid,ns in [(10,[1,2]),(20,[2,3]),(30,[2,4])]:
            rows.append(dict(geometry=mapping(LineString([coords[str(n)] for n in ns])),properties=dict(
                road_id=wid,osm_id=wid,one_way=None,ft_seg_stress=3,tf_seg_stress=1,ft_int_stress=3,tf_int_stress=1,
                speed_limit=40,ft_lanes=1,tf_lanes=1,functional_class='residential',intersection_from=ns[0],intersection_to=ns[-1])))
        inputs=dict(boundary=dict(features=[dict(geometry=mapping(box(-111.67,40.22,-111.63,40.25)))]),
                    network=dict(coords=coords,ways=[[10,[1,2],{'highway':'residential'}]]),
                    published=dict(features=rows),local=dict(features=[]),utah=dict(features=[]),
                    **{'city-streets':dict(features=[]),'sgid-streets':dict(features=[])})
        meta={k:dict(version='test') for k in ('published','local','utah')}
        segments,approaches,_,coverage=build(inputs,meta,[])
        self.assertEqual(coverage['approaches']['total'],0)
        self.assertEqual(coverage['approaches']['sourceNetworkAdditional'],3)
        self.assertTrue(any(f['properties']['eligibility']=='source_network' for f in segments))
        self.assertTrue(all(f['properties']['source']==PUBLISHED for f in approaches))
