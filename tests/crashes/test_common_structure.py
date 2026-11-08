import copy
import tempfile
import unittest
from pathlib import Path
import yaml
from danger_zones.common_structure import read_contract, decision_report
from danger_zones.field_inventory import read_catalog
from danger_zones.normalize_incidents import normalize_row, selected_indices


class CommonStructureTests(unittest.TestCase):
    def test_every_field_has_one_decision_and_explicit_conversion(self):
        c=read_catalog();p=read_contract(catalog=c);report=decision_report(p,c)
        self.assertEqual(report['summary']['fields'],209)
        self.assertEqual(report['summary']['conceptDispositions']['exclude'],20)
        self.assertEqual(report['summary']['fieldDispositions']['exclude'],29)
        self.assertEqual(p['status'],'approved')

    def test_drift_bad_rule_and_redundant_targets_are_rejected(self):
        original=read_contract()
        cases=[]
        p=copy.deepcopy(original);p['bindings'].pop(next(iter(p['bindings'])));cases.append(p)
        p=copy.deepcopy(original);p['bindings'][next(iter(p['bindings']))]['rule']='guess';cases.append(p)
        p=copy.deepcopy(original);p['concepts']['person.age']['target']='person.sex';cases.append(p)
        p=copy.deepcopy(original);p['concepts'].pop('person.age');cases.append(p)
        p=copy.deepcopy(original);p['codebooks']['person.sex']['reference']='missing';cases.append(p)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'common.yml'
            for p in cases:
                path.write_text(yaml.safe_dump(p))
                with self.assertRaises(ValueError):read_contract(path)

    def test_row_conversion_combines_facets_and_equal_aliases_not_distinct_concepts(self):
        c=read_catalog();p=read_contract(catalog=c)
        source={'Crash_ID':'00089','crashDateandTime':'1/17/2020','crash_date':'1/17/2020',
                'route':'00089','latitude':'40.25','longitude':'-111.65','milePoint':'1.5','mile_point':'1.5',
                'crashSeverity':'1','crashSeverity_label':'No injury','weatherCondition':'01','pedestrian_involved':None}
        before=copy.deepcopy(source)
        values,errors=normalize_row('portal.crashes',source,c,p)
        self.assertEqual(errors,[])
        self.assertEqual(values['injury.crash_severity']['value'],{'code':'1','label':'No injury'})
        self.assertEqual(values['condition.weather']['value']['label'],'Clear')
        self.assertEqual(values['road.milepoint']['value'],1.5)
        self.assertEqual(values['classification.pedestrian_involved']['state'],'null')
        self.assertEqual(values['classification.bicycle_involved']['state'],'not-supplied')
        self.assertNotIn('road.exit_number',values)
        self.assertNotIn('time.occurrence_date',values)
        self.assertEqual(values['time.occurred_at']['value']['precision'],'date')
        self.assertEqual(values['road.route_number']['value'],'00089')
        self.assertTrue(all(v['value'] is not None for v in values.values() if v['state']=='reported'))
        self.assertEqual(source,before)
        source['crashSeverity_label']='Fatal';source['mile_point']='2'
        values,errors=normalize_row('portal.crashes',source,c,p)
        self.assertEqual(values['injury.crash_severity']['state'],'conflict')
        self.assertEqual(values['road.milepoint']['state'],'conflict')
        self.assertEqual(len(errors),2)

    def test_selection_uses_rollups_and_people_and_keeps_collision_partners(self):
        tables={'portal.crashes':{'rows':[{'Crash_ID':'a','cyclist_involved':None},{'Crash_ID':'b'},{'Crash_ID':'c'}]},
                'portal.rollups':{'rows':[{'Crash_ID':'a','cyclist_involved':'Y'}]},
                'portal.persons':{'rows':[{'Crash_ID':'a','personType':'1'},{'Crash_ID':'a','personType':'4'},{'Crash_ID':'b','personType':'5'},{'Crash_ID':'c','personType':'1'}]},
                'portal.vehicles':{'rows':[{'Crash_ID':'a'},{'Crash_ID':'b'},{'Crash_ID':'c'}]},
                'police.xlsx':{'rows':[{'id':'a'}]},'udot.arcgis':{'rows':[{'PEDESTRIAN_INVOLVED':'Y'},{'PEDESTRIAN_INVOLVED':'N'}]}}
        selected=selected_indices(tables)
        self.assertEqual(selected['portal.crashes'],[0,1])
        self.assertEqual(selected['portal.persons'],[0,1,2])
        self.assertEqual(selected['portal.vehicles'],[0,1])
        self.assertEqual(selected['police.xlsx'],[0])
        self.assertEqual(selected['udot.arcgis'],[0])
