import copy
import unittest
from danger_zones.incident_summary import add_summaries, display, sections


class IncidentSummaryTests(unittest.TestCase):
    def test_exact_existing_feature_binding_deduplication_and_point_exclusion(self):
        layer={'type':'FeatureCollection','features':[{'geometry':{'type':'Point','coordinates':[-111.6501,40.2501]},'properties':{'mode':'bicycle','month':'2025-01','source':'UDOT','details':{'UDOT: CRASH_ID':'1','Portal: Crash_ID':'2'}}}]}
        def row(table,id,source):
            return {'table':table,'sourceRecordId':id,'source':source,'values':{'injury.crash_severity':{'value':{'code':'3' if table.startswith('portal') else None,'label':'Suspected Minor Injury'},'state':'reported','columns':['severity']},'location.point':{'value':{'longitude':-111.650123456,'latitude':40.250123456,'crs':'EPSG:4326'},'state':'reported','columns':['point']}}}
        records=[row('udot.arcgis','1','udot-crashes'),row('portal.crashes','2','utah-crash-portal')]
        original=copy.deepcopy(layer);out=add_summaries(layer,records)
        self.assertEqual(layer,original)
        self.assertEqual(out['features'][0]['geometry'],original['features'][0]['geometry'])
        entries=out['features'][0]['properties']['summary'][0]['entries']
        self.assertEqual(len(entries),1);self.assertEqual(len(entries[0]['values']),1)
        self.assertEqual(len(entries[0]['values'][0]['sources']),2)
        self.assertNotIn('-111.650123456',str(out))
        with self.assertRaises(ValueError):add_summaries(layer,records[:1])
        with self.assertRaises(ValueError):add_summaries(layer,records+[records[0]])

    def test_report_time_and_missing_outcomes_are_not_invented(self):
        rows=[{'source':'provo-police-incidents','table':'police.xlsx','values':{'time.reported_at':{'value':{'date':'2025-01-01','time':None,'offset':None,'precision':'date','zone':None},'state':'reported'}}}]
        result=sections(rows)
        when=next(s for s in result if s['heading']=='When')
        self.assertEqual(when['entries'][0]['values'][0]['text'],'2025-01-01')
        self.assertEqual(when['entries'][1]['values'][0]['text'],'Not supplied by this source')
        self.assertEqual(display({'value':False,'state':'reported'}),'No')
        self.assertIsNone(display({'value':None,'state':'null'}))
