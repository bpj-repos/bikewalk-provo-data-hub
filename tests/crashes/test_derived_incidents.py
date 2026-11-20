import copy
import unittest
from danger_zones.derived_incidents import derive, preview, read_rules


def row(table,id='1',source='utah-crash-portal',entity='crash',values=None,modes=None):
    return {'observationId':table+':'+id+':'+str(values),'source':source,'snapshotId':'snapshot','sourceRecordId':id,'table':table,'entity':entity,'values':values or {},'modes':modes or []}

def category(code,label=None):return {'value':{'code':code,'label':label},'state':'reported','columns':['test']}

def person(type,injury):return row('portal.persons',entity='person',values={'person.type':category(type),'person.injury_severity':category(injury)},modes=['bicycle'] if type=='4' else [])


class DerivedIncidentTests(unittest.TestCase):
    def setUp(self):self.rules=read_rules();self.primary=row('portal.crashes',modes=['bicycle'])

    def test_young_child_includes_passengers_and_handles_missing_ages(self):
        def child(ages):
            people = [person('2', '1') for age in ages]
            for p, age in zip(people, ages):
                p['values']['person.age'] = {'value': age, 'state': 'reported' if age is not None else 'null'}
            return derive(self.primary, [self.primary, *people], self.rules)['derived']['young_child']
        for age in [0, 1, 12]:
            self.assertIs(child([age])['value'], True)
        self.assertIs(child([13, 42])['value'], False)
        self.assertIs(child([12, None])['value'], True)
        for ages in [[], [None], [13, None], [200]]:
            self.assertIsNone(child(ages)['value'])

    def test_bike_lane_requires_role_and_position_on_the_same_person(self):
        def lane(pairs):
            people = []
            for role, setting in pairs:
                p = person(role, '1')
                p['values']['person.nonmotorist_location'] = category(setting)
                people.append(p)
            return derive(self.primary, [self.primary, *people], self.rules)['derived']['bike_lane']['value']
        for role in ['4', '5']:
            for setting in ['12', '17']:
                self.assertIs(lane([(role, setting)]), True)
        self.assertIs(lane([('4', '6'), ('3', '12')]), False)
        for setting in ['10', '13', '16', '18', '97']:
            self.assertIs(lane([('4', setting)]), False)
        self.assertIs(lane([('2', None)]), False)
        for pairs in [[], [('4', None)], [('4', '99')], [(None, '12')]]:
            self.assertIsNone(lane(pairs))
        self.assertIs(lane([('4', None), ('5', '12')]), True)

    def test_at_injury_does_not_substitute_occupant_or_crash_severity(self):
        people=[person('4','1'),person('1','5')]
        out=derive(self.primary,[self.primary,*people],self.rules)['derived']
        self.assertIs(out['at_serious_or_fatal']['value'],False)
        self.assertEqual(out['at_injury_summary']['value']['highestKnown'],'No injury')
        state=row('udot.arcgis',source='udot-crashes',values={'count.fatalities':{'value':3,'state':'reported'}},modes=['bicycle'])
        self.assertIsNone(derive(state,[state],self.rules)['derived']['at_serious_or_fatal']['value'])
        for people in ([person('4','89')],[person('4','1'),person(None,'1')],[]):
            self.assertIsNone(derive(self.primary,[self.primary,*people],self.rules)['derived']['at_serious_or_fatal']['value'])
        self.assertIs(derive(self.primary,[self.primary,person('4','4'),person('4','89')],self.rules)['derived']['at_serious_or_fatal']['value'],True)
        self.assertIsNone(derive(self.primary,[self.primary,person('3','1')],self.rules)['derived']['at_serious_or_fatal']['value'])

    def test_positive_person_modes_survive_negative_flags_as_conflict(self):
        primary=copy.deepcopy(self.primary);primary['values']['classification.bicycle_involved']={'value':False,'state':'reported'}
        out=derive(primary,[primary,person('4','1')],self.rules)['derived']
        self.assertIn('bicycle',out['active_modes']['value'])
        self.assertEqual(out['active_modes']['availability'],'conflicting')
        self.assertIsNone(out['at_serious_or_fatal']['value'])

    def test_lists_are_explicit_and_unknown_codes_raise_review_issues(self):
        driver=person('1','1');driver['values']['person.driver_contributing_first']=category('3','Failed to Yield Right-of-Way')
        nm=person('4','3');nm['values']['person.nonmotorist_location']=category('17','Separated Bike Lane')
        vehicle=row('portal.vehicles',entity='vehicle',values={'vehicle.maneuver':category('6','Turning Left')})
        out=derive(self.primary,[self.primary,driver,nm,vehicle],self.rules)
        self.assertEqual(out['issues'],[])
        self.assertEqual(out['derived']['reported_driver_circumstances']['value'],['failure-to-yield'])
        self.assertEqual(out['derived']['vehicle_movements_present']['value'],['left-turn'])
        self.assertEqual(out['derived']['nonmotorist_setting']['value'],['bicycle-facility'])
        vehicle['values']['vehicle.maneuver']=category('NEW','Unreviewed')
        self.assertIn('vehicle.maneuver:unmapped-code',derive(self.primary,[self.primary,vehicle],self.rules)['issues'])

    def test_date_precision_report_basis_and_local_calendar(self):
        primary=copy.deepcopy(self.primary)
        primary['values']['time.occurred_at']={'value':{'date':'2025-01-01','time':'01:00:00','offset':'+00:00','zone':'UTC','precision':'second'},'state':'reported'}
        t=derive(primary,[primary],self.rules)['derived']['time']['value']
        self.assertEqual((t['year'],t['date'],t['hour']),(2024,'2024-12-31',18))
        primary['values']={'time.reported_at':{'value':{'date':'2025-01-01','time':None,'offset':None,'zone':None,'precision':'date'},'state':'reported'}}
        t=derive(primary,[primary],self.rules)['derived']['time']['value']
        self.assertEqual(t['basis'],'report');self.assertIsNone(t['hour'])

    def test_source_and_snapshot_separation_and_audit_denominators(self):
        other=person('4','5');other['source']='other-source'
        records,audit=preview([self.primary,other],self.rules)
        self.assertIsNone(records[0]['derived']['at_serious_or_fatal']['value'])
        self.assertEqual(audit['sourceObservations'],1)
        self.assertEqual(audit['newCrossSourceLinks'],0)
        self.assertTrue(all(x['observations']==1 for x in audit['coverage']))
