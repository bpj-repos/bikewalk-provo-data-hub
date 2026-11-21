from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from shapely.geometry import Point, LineString, box, mapping
from shapely.ops import transform

from danger_zones.road_segments import assign, changes, encoded, TO_METERS, TO_WGS84
from scripts import crash_road_segments as pipeline

RULES=json.loads(pipeline.RULES.read_bytes())
X,Y=TO_METERS(-111.66,40.25)

def xy(x,y):return list(TO_WGS84(X+x,Y+y))
def road(key,points,name='Center Street',**fields):
    return {'type':'Feature','geometry':mapping(LineString([xy(*p) for p in points])),
            'properties':{'OBJECTID':key,'NAME':name,'FULLNAME':name,'OWNER':'Provo','VERT_LEVEL':None,'SPEED_LMT':None,'UPDATEDBY':'private-editor',**fields}}
def crash(key='1',point=(50,1),name='Center St'):
    return {'id':'udot-crashes:'+key,'enrichment':{'reviewedSummary':{'brief':'Reviewed crash.'}},'observations':[
        {'id':'udot-crashes:'+key,'sourceKey':'udot-crashes','sourceRecordId':key,
         'coordinates':xy(*point) if point else None,'metadata':{'MAIN_ROAD_NAME':name}}]}
BOUNDARY=mapping(transform(TO_WGS84,box(X-200,Y-200,X+300,Y+300)))

def run(roads,crashes=None):return assign({'records':crashes or [crash()]},roads,BOUNDARY,RULES,'source-pin')


class RoadSegmentsTest(unittest.TestCase):
    def test_complete_attributes_nulls_zero_crash_inventory_and_reproducibility(self):
        roads=[road(1,[(0,0),(100,0)],BIKE_L=None,EXTRA='retained'),road(2,[(0,120),(100,120)],'Other Road')]
        original=deepcopy(roads);result=run(roads)
        self.assertEqual(result,run(list(reversed(roads))))
        self.assertEqual(roads,original)
        self.assertEqual(result['assignments.json'][0]['status'],'matched')
        self.assertEqual(result['coverage.json']['eligibleSegments'],2)
        props=result['segments.geojson']['features'][0]['properties']
        self.assertIsNone(props['source']['SPEED_LMT']);self.assertEqual(props['source']['EXTRA'],'retained')
        self.assertNotIn('UPDATEDBY',props['source'])
        self.assertAlmostEqual(props['derived']['lengthMeters'],100,places=2)

    def test_junction_parallel_divided_and_frontage_ambiguity(self):
        arrangements=[([road(1,[(0,0),(50,0)]),road(2,[(50,0),(100,0)])],(50,1)),
                      ([road(1,[(0,0),(100,0)]),road(2,[(0,5),(100,5)],'Frontage Road')],(50,1)),
                      ([road(1,[(0,0),(100,0)]),road(2,[(0,12),(100,12)])],(50,6))]
        for roads,point in arrangements:
            with self.subTest(point=point,roads=len(roads)):
                r=run(roads,[crash(point=point)])['assignments.json'][0]
                self.assertEqual(r['status'],'ambiguous');self.assertIsNone(r['segmentId']);self.assertEqual(len(r['candidates']),2)

    def test_recorded_junction_remains_ambiguous_when_only_one_line_is_nearby(self):
        r=run([road(1,[(0,0),(100,0)])],[crash(name='Center Street & Freedom Blvd')])['assignments.json'][0]
        self.assertEqual(r['status'],'ambiguous');self.assertIn('recorded-junction',r['reasons'])

    def test_spaced_intersection_names_and_source_identity_uncertainty(self):
        roads=[road(1,[(0,0),(100,0)]),road(2,[(200,0),(200,100)],'Freedom Blvd')]
        row=run(roads,[crash(name='Center St  Freedom Blvd')])['assignments.json'][0]
        self.assertEqual(row['status'],'ambiguous');self.assertTrue(row['junctionReported'])
        duplicate=crash();duplicate['id']='utah-crash-portal:1'
        rows=run(roads,[crash(),duplicate])['assignments.json']
        self.assertTrue(all(r['identityStatus']=='ambiguous-state-id' and r['status']=='ambiguous' for r in rows))

    def test_crossing_bridge_is_not_a_topological_junction(self):
        roads=[road(1,[(0,0),(100,0)],VERT_LEVEL=1),road(2,[(50,-50),(50,50)],'Underpass Road',VERT_LEVEL=0)]
        r=run(roads)
        self.assertTrue(all(len(ids)==1 for ids in r['endpoints.json'].values()))
        self.assertEqual(r['assignments.json'][0]['status'],'ambiguous')
        self.assertFalse(r['coverage.json']['confirmedConnectivity'])

    def test_parallel_path_is_retained_and_marked_ineligible(self):
        roads=[road(1,[(0,0),(100,0)]),road(2,[(0,4),(100,4)],'Walkway',CLASSIFICATION='Walkway')]
        r=run(roads)
        self.assertEqual(len(r['segments.geojson']['features']),2)
        self.assertFalse(r['assignments.json'][0]['candidates'][1]['eligible'])
        self.assertEqual(r['assignments.json'][0]['status'],'ambiguous')

    def test_reverse_duplicates_do_not_double_mileage(self):
        r=run([road(1,[(0,0),(100,0)]),road(2,[(100,0),(0,0)])])
        self.assertEqual(r['coverage.json']['physicalGeometryCount'],1)
        self.assertAlmostEqual(r['coverage.json']['physicalLengthMeters'],100,places=2)
        self.assertEqual(r['assignments.json'][0]['status'],'matched')

    def test_missing_unknown_road_and_conflicting_positions(self):
        roads=[road(1,[(0,0),(100,0)])]
        self.assertEqual(run(roads,[crash(point=None)])['assignments.json'][0]['status'],'missing-location')
        self.assertEqual(run(roads,[crash(name='Unknown')])['assignments.json'][0]['status'],'unmatched')
        g=crash();o=deepcopy(g['observations'][0]);o.update(id='utah-crash-portal:1',sourceKey='utah-crash-portal',coordinates=xy(50,100),metadata={'crash':{'roadName':'Center St'}});g['observations'].append(o)
        self.assertNotEqual(run(roads,[g])['assignments.json'][0]['status'],'matched')

    def test_source_splits_and_renumbering_report_reassignment(self):
        old=run([road(1,[(0,0),(100,0)])]);new=run([road(2,[(0,0),(50,0)]),road(3,[(50,0),(100,0)])])
        report=changes(old,new)
        self.assertEqual(report['removedSegmentIds'],['provo-city:1']);self.assertEqual(len(report['addedSegmentIds']),2)
        self.assertEqual(report['changedAssignments'][0]['after']['status'],'ambiguous')

    def test_full_pipeline_dependency_invalidation_noop_and_failure_preserves_pointer(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp); roads=[road(1,[(0,0),(100,0)])]
            def write(name,obj):p=root/name;p.write_bytes(encoded(obj));return p
            raw=write('collection.json',{'snapshotId':'test','records':[crash()]})
            pointer=write('pointer.json',{'path':str(raw),'sha256':pipeline.sha(raw),'snapshotId':'test'})
            road_path=write('roads.json',{'features':roads});meta=write('metadata.json',{'fields':[{'name':k} for k in roads[0]['properties']]})
            rule=write('rules.json',{**RULES,'minimumSourceSegments':1,'reviewedSourceFields':sorted(roads[0]['properties'])})
            boundary=write('boundary.json',{'features':[{'geometry':BOUNDARY}]})
            from shapely.geometry import shape
            receipt=write('receipt.json',{'road':{'path':str(road_path),'sha256':pipeline.sha(road_path)},'metadata':{'path':str(meta),'sha256':pipeline.sha(meta)},'source':{'query':{'geometry':','.join(map(str,shape(BOUNDARY).bounds))}}})
            with patch.object(pipeline,'RULES',rule):
                args=dict(offline=True,source_receipt=receipt,root=root/'operations',pointer=pointer,boundary=boundary,version='1.0.0')
                first=pipeline.refresh(**args);second=pipeline.refresh(**args)
                self.assertEqual(second['status'],'unchanged');self.assertEqual(first['sha256'],second['sha256'])
                roads[0]['properties']['SPEED_LMT']=30;road_path.write_bytes(encoded({'features':roads}))
                data=pipeline.read(receipt);data['road']['sha256']=pipeline.sha(road_path);receipt.write_bytes(encoded(data))
                changed=pipeline.refresh(**args);self.assertNotEqual(changed['sha256'],first['sha256'])
                import zipfile
                with zipfile.ZipFile(changed['zip']) as archive:
                    manifest=pipeline.read(Path(changed['path'])/'datapackage.json')
                    self.assertIsNone(archive.testzip())
                    self.assertEqual(len(archive.namelist()),len(manifest['resources'])+1)
                for dependency in ('crash', 'rules', 'boundary'):
                    before=changed['sha256']
                    if dependency=='crash':
                        raw.write_bytes(encoded({'records':[crash(point=(60,2))]}))
                        pin=pipeline.read(pointer);pin['sha256']=pipeline.sha(raw);pointer.write_bytes(encoded(pin))
                    elif dependency=='rules':
                        r=pipeline.read(rule);r['maximumDistanceMeters']=20;rule.write_bytes(encoded(r))
                    else:
                        # Preserve capture envelope but change the municipal shape.
                        polygon=pipeline.read(boundary)
                        polygon['features'][0]['geometry']['coordinates'].append([xy(10,10),xy(20,10),xy(20,20),xy(10,20),xy(10,10)])
                        boundary.write_bytes(encoded(polygon))
                    changed=pipeline.refresh(**args)
                    self.assertNotEqual(changed['sha256'],before,dependency)
                saved=(root/'operations/candidate.json').read_bytes()
                road_path.write_bytes(b'corrupt')
                with self.assertRaisesRegex(ValueError,'checksum'):pipeline.refresh(**args)
                self.assertEqual((root/'operations/candidate.json').read_bytes(),saved)
                self.assertTrue(Path(first['path']).exists())

    def test_update_wrapper_rebuilds_after_ready_even_on_offline_noop(self):
        from scripts.update_crashes import run as update
        with patch('scripts.update_crashes.main'),patch('scripts.crash_summaries.pending_work',return_value={'pending':[]}),patch('scripts.crash_road_segments.refresh',return_value={'status':'unchanged'}) as rebuild,patch('sys.argv',['update_crashes.py','--offline']),patch('builtins.print'):
            self.assertEqual(update(),0);rebuild.assert_called_once_with(offline=True)

    def test_online_update_captures_roads_before_intake_and_fails_closed(self):
        from scripts.update_crashes import run as update
        order=[]
        with patch('scripts.update_crashes.main',side_effect=lambda parsed:order.append('crashes')) as intake,patch('scripts.crash_road_segments.capture_for_update',side_effect=lambda:order.append('roads')) as capture,patch('scripts.crash_summaries.pending_work',return_value={'pending':['1']}),patch('sys.argv',['update_crashes.py']),patch('builtins.print'):
            self.assertEqual(update(),2);self.assertEqual(order,['roads','crashes'])
            intake.reset_mock();capture.side_effect=ValueError('incomplete street capture')
            with self.assertRaises(ValueError):update()
            intake.assert_not_called()

    def test_help_and_invalid_arguments_never_capture(self):
        from scripts.update_crashes import run as update
        for arguments, code in [(['--help'], 0), (['--not-an-option'], 2), (['--rollback', '--offline'], 2)]:
            with patch('sys.argv', ['update_crashes.py', *arguments]), patch('scripts.crash_road_segments.capture_for_update') as capture, patch('builtins.print'):
                with self.assertRaises(SystemExit) as exited: update()
                self.assertEqual(exited.exception.code, code)
                capture.assert_not_called()

    def test_source_classified_intersections_are_never_midblock_matches(self):
        for label in RULES['intersectionClassifications']:
            g=crash();g['observations'][0]['metadata']['ROADWAY_JUNCT_FEATURE_DESC']=label
            r=run([road(1,[(0,0),(100,0)])],[g])['assignments.json'][0]
            self.assertEqual(r['status'],'ambiguous');self.assertTrue(r['junctionReported'])
            self.assertEqual(r['junctionEvidence'][0]['value'],label)
        g=crash();g['observations'][0].update(sourceKey='utah-crash-portal',metadata={'crash':{'roadName':'Center St','roadwayJunction_label':'4-Leg Intersection'}})
        self.assertEqual(run([road(1,[(0,0),(100,0)])],[g])['assignments.json'][0]['status'],'ambiguous')
