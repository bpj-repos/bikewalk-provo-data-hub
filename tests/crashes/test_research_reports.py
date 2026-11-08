import unittest
from danger_zones.research_reports import crash_report


def portal(id,types,year=2025,vehicles=1):
    return {'id':'utah-crash-portal:'+id,'sourceKey':'utah-crash-portal','sourceRecordId':id,
            'observedAt':f'{year}-01-06T09:00:00-07:00','timePrecision':'second',
            'metadata':{'crash':{'City_Geo':'Provo','numberOfVehicles':vehicles,'crashSeverity':'2'},
                        'persons':[{'personType':t} for t in types],'rollups':[{'pedestrian_involved':'Y'}]}}

class ResearchReportTests(unittest.TestCase):
    def test_modes_do_not_double_count_total_or_call_other_a_walker(self):
        rows=[portal('1',['3','4']),portal('2',['5']),portal('3',['4'],vehicles=0),portal('4',['3'],year=2026)]
        s={'records':[{'observations':[r]} for r in rows]};data=crash_report(s,2025)
        a=data['annual'][0];self.assertEqual((a['total'],a['bike'],a['ped'],a['other']),(2,1,1,1))
        self.assertFalse(data['annual'][1]['complete']);self.assertEqual(sum(map(sum,a['hours'])),2)
    def test_scope_deduplicates_nested_state_source_and_excludes_other_cities(self):
        p=portal('1',['4']);outside=portal('2',['3']);outside['metadata']['crash']['City_Geo']='Orem'
        s={'records':[{'observations':[{'id':'udot-crashes:1','sourceKey':'udot-crashes','statePortal':p}]},{'observations':[outside]}]}
        self.assertEqual(crash_report(s,2025)['annual'][0]['total'],1)
