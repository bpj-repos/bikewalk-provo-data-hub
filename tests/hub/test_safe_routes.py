import unittest

from scripts.safe_routes import features, fetch, validate_geometry

KEY='safe-school-routes'
SOURCE={KEY+'.json':dict(retrievedAt='2026-11-07',url='current'),
        'archive-'+KEY+'.json':dict(retrievedAt='2026-07-21',url='archive')}


def row(i,school=257):
    return dict(properties=dict(OBJECTID_12_13_14=i,GlobalID=str(i),APPROVED='Yes',
                NAME_DISTRICT='Provo',NAME_SCHOOL='Example',ID_SCHOOL=school,APPROVAL_DATE=1000),
                geometry=dict(type='LineString',coordinates=[[-111.65,40.24],[-111.64,40.24]]))


class SafeRoutes(unittest.TestCase):
    def test_source_order_and_pagination(self):
        ids=list(range(105))
        def request(_,p):
            if 'returnIdsOnly' in p:
                return {'objectIds':ids[::-1]}
            return {'features':[row(int(i)) for i in reversed(p['objectIds'].split(','))]}
        self.assertEqual([r['properties']['OBJECTID_12_13_14'] for r in fetch(KEY,request)],ids)
        with self.assertRaisesRegex(ValueError,'Incomplete'):
            fetch(KEY,lambda url,p:request(url,p) if 'returnIdsOnly' in p else {'features':[]})

    def test_archive_and_return(self):
        old=row(2)
        output,_=features(KEY,[row(1,None)],[old],SOURCE)
        self.assertEqual([r['properties']['schoolId'] for r in output],[None,257])
        self.assertEqual(output[1]['properties']['sourceStatus'],'archived-udot-school-confirmed')
        self.assertIn('schoolApprovalEvidenceUrl',output[1]['properties'])
        returned,_=features(KEY,[row(2),row(1,None)],[old],SOURCE)
        self.assertEqual(len(returned),2)
        self.assertEqual(returned[1]['properties']['sourceStatus'],'current-udot')
        self.assertEqual(returned,features(KEY,[row(1,None),row(2)],[old],SOURCE)[0])

    def test_geometry_rejections(self):
        bad=row(1)
        bad['geometry']=None
        rows,rejected=features(KEY,[bad],[],SOURCE)
        self.assertFalse(rows)
        self.assertEqual(len(rejected),1)
        with self.assertRaises(ValueError):
            validate_geometry(dict(type='Point',coordinates=[0,0]),KEY)


class PlannedCampus(unittest.TestCase):
    def test_reviewed_release_adds_only_planned_geometry(self):
        import json
        from pathlib import Path
        from scripts.safe_routes import DATASET, LAYERS, PLANNED_CAMPUS, reviewed_treeside
        base=Path(__file__).resolve().parents[2]/'releases/datasets'/DATASET
        for key,count in zip(LAYERS,(1,7,0)):
            def records(version):
                return json.loads((base/version/(key+'.geojson')).read_bytes())['features']
            old,new=records('1.0.0'),records('1.1.0')
            self.assertEqual([r for r in new if r['properties']['schoolId']!=773],old)
            added=[r for r in new if r['properties']['schoolId']==773]
            self.assertEqual(len(added),count)
            for r in added:
                self.assertTrue(PLANNED_CAMPUS.items() <= r['properties'].items())
        with self.assertRaisesRegex(ValueError,'records changed'):
            reviewed_treeside('safe-school-routes',[], 'review-next')
