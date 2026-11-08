import json
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy
from danger_zones.query_incidents import select, validate


def condition(field,value,op='eq'):return {'field':field,'op':op,'value':value}


def fixture():
    portal={'id':'utah-crash-portal:1','sourceKey':'utah-crash-portal','observedAt':'2021-07-01T14:00:00-06:00','coordinates':[-111.66,40.23],
            'modes':['bicycle','pedestrian'],'metadata':{'crash':{'City_Geo':'Provo','roadName':'W CENTER ST','crashSeverity':'5'},
            'vehicles':[{'vehicleBodyType':'1','vehicleManeuver':'1','vehicleNumber':'1'},
                        {'vehicleBodyType':'4','vehicleManeuver':'6','vehicleNumber':'2'}],
            'persons':[{'personType':'4','personNmLocation':'12','injuryLevel':'5'},
                       {'personType':'3','personNmLocation':'1','injuryLevel':'1'}]}}
    return {'id':'udot-crashes:1','reviewedLink':{'example':'retained'},'observations':[
        {'id':'udot-crashes:1','sourceKey':'udot-crashes','observedAt':'2021-07-01T20:00:00Z','coordinates':[-111.66,40.23],
         'modes':['bicycle'],'metadata':{'MAIN_ROAD_NAME':'W CENTER ST','CRASH_SEVERITY_DESC':'Fatal'},'statePortal':portal}]}


class QueryTests(unittest.TestCase):
    def test_full_entry_and_nested_portal_are_returned_once_unchanged(self):
        group=fixture();before=deepcopy(group)
        result,counts,evidence=select([group],condition('mode','bicycle'))
        self.assertEqual(result,[before]);self.assertEqual(group,before)
        self.assertEqual(counts['matched'],1);self.assertEqual(len(evidence[group['id']]),2)
    def test_all_and_empty_results(self):
        self.assertEqual(select([fixture()],{'all':[]})[0],[fixture()])
        self.assertEqual(select([fixture()],condition('year',2015))[0],[])
    def test_year_city_and_street(self):
        q={'all':[condition('year',[2020,2022],'between'),condition('city','provo'),condition('street','center','contains')]}
        self.assertEqual(len(select([fixture()],q)[0]),1)
    def test_same_vehicle_scope_does_not_combine_car_and_other_vehicle_left_turn(self):
        q={'vehicle':{'all':[condition('body_code',['1','2','3'],'in'),condition('maneuver','left-turn')]}}
        self.assertEqual(select([fixture()],q)[0],[])
        g=fixture();g['observations'][0]['statePortal']['metadata']['vehicles'][0]['vehicleManeuver']='6'
        self.assertEqual(len(select([g],q)[0]),1)
    def test_same_person_scope(self):
        q={'person':{'all':[condition('mode','bicycle'),condition('setting','crosswalk')]}}
        self.assertEqual(select([fixture()],q)[0],[])
        q['person']['all'][1]=condition('setting','on-street-bike-lane')
        self.assertEqual(len(select([fixture()],q)[0]),1)
    def test_compound_bicycle_fatal_bike_lane(self):
        q={'all':[condition('year',2021),condition('mode','bicycle'),condition('fatal',True),
                  {'person':{'all':[condition('mode','bicycle'),condition('setting',['on-street-bike-lane','separated-bike-lane'],'in')]}}]}
        self.assertEqual(len(select([fixture()],q)[0]),1)
    def test_unknown_not_does_not_turn_missing_city_into_not_provo(self):
        g=fixture();del g['observations'][0]['statePortal']
        result,counts,_=select([g],{'not':condition('city','Provo')})
        self.assertEqual(result,[]);self.assertEqual(counts['unknown'],1)
    def test_near_uses_metres_and_inclusive_center(self):
        q={'near':{'longitude':-111.66,'latitude':40.23,'metres':1}}
        self.assertEqual(len(select([fixture()],q)[0]),1)
        q['near']['latitude']=40.24
        self.assertEqual(select([fixture()],q)[0],[])
    def test_street_only_police_point_is_unknown_not_trusted_geometry(self):
        g={'id':'p','observations':[{'id':'p','sourceKey':'provo-police-incidents','observedAt':'2021-07-01T20:00:00Z',
            'coordinates':[-111.66,40.23],'mode':'bicycle','metadata':{'location':{'geocoding':{
            'status':'matched','providerCandidates':[{'properties':{'kind':'street'}}]}}}}]}
        result,counts,_=select([g],{'near':{'longitude':-111.66,'latitude':40.23,'metres':5}})
        self.assertEqual(result,[]);self.assertEqual(counts['unknown'],1)
        self.assertEqual(len(select([g],condition('report_year',2021))[0]),1)
        self.assertEqual(select([g],condition('year',2021))[0],[])
    def test_same_source_conjunction(self):
        g=fixture();g['observations'][0]['statePortal']['metadata']['crash']['roadName']='OTHER ROAD'
        q={'all':[condition('city','Provo'),condition('street','Center','contains')]}
        self.assertEqual(select([g],q)[0],[])
    def test_polygon_boundary_and_invalid_crs(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'boundary.json';geometry={'type':'Polygon','coordinates':[[[-111.66,40.23],[-111.65,40.23],[-111.65,40.24],[-111.66,40.23]]]}
            path.write_text(json.dumps(geometry));self.assertEqual(len(select([fixture()],{'within':str(path)})[0]),1)
            geometry['crs']={'properties':{'name':'EPSG:3857'}};path.write_text(json.dumps(geometry))
            with self.assertRaises(ValueError):select([fixture()],{'within':str(path)})
    def test_invalid_queries_fail_even_for_empty_collection(self):
        for q in [condition('unsupported','x'),condition('year','2021'),condition('fatal','yes'),condition('year',[2022,2020],'between'),
                  {'near':{'longitude':float('nan'),'latitude':40,'metres':1}}, {'vehicle':condition('city','Provo')}]:
            with self.assertRaises(ValueError):select([],q)

if __name__=='__main__':unittest.main()
