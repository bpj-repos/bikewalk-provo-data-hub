from datetime import datetime
import unittest

from danger_zones.event_context import EventMatcher, local_time
from scripts.capture_byu_events import parse_schedule


class EventContextTests(unittest.TestCase):
    def setUp(self):
        self.m = EventMatcher()
        self.m.events['byu_mens_basketball'] = [dict(event_id='test', series='byu_mens_basketball',
            event_date='2026-01-10', status='held', start_local='2026-01-10T18:00:00-07:00',
            arrival_start='2026-01-10T17:00:00-07:00', arrival_end='2026-01-10T18:10:00-07:00',
            departure_start='2026-01-10T20:00:00-07:00', departure_end='2026-01-10T21:00:00-07:00')]
        self.o = {'id':'portal:1', 'sourceKey':'utah-crash-portal', 'coordinates':[-111.65611,40.25578]}
        self.rows = [{'observationId':'portal:1', 'values':{'time.occurred_at':{'value':{
            'date':'2026-01-10','time':'21:00:00','offset':'-07:00'}}}},
            {'observationId':'person:1', 'values':{'person.type':{'value':{'code':'3'}},
                                                'person.nonmotorist_location':{'value':{'code':'1'}}}}]

    def value(self):
        return self.m.observation(self.o,self.rows)['byu_mens_basketball_event_context']

    def test_inclusive_departure_boundary(self):
        self.assertEqual(self.value()['value'],'likely_match')
        self.rows[0]['values']['time.occurred_at']['value']['time']='21:00:01'
        self.assertEqual(self.value()['value'],'no_match')

    def test_missing_mechanism_and_report_clock(self):
        self.rows.pop()
        self.assertEqual(self.value()['value'],'indeterminate')
        self.rows[0]['values']['time.reported_at']=self.rows[0]['values'].pop('time.occurred_at')
        self.assertEqual(self.value()['value'],'indeterminate')

    def test_cancelled_and_missing_end(self):
        e=self.m.events['byu_mens_basketball'][0]
        e['status']='canceled'
        self.assertEqual(self.value()['value'],'no_match')
        e['status']='held';e['departure_start']='';e['departure_end']=''
        self.assertEqual(self.value()['value'],'indeterminate')

    def test_historical_and_boundary_location(self):
        self.rows[0]['values']['time.occurred_at']['value']['date']='2011-01-10'
        self.m.events['byu_mens_basketball'][0]={k:v.replace('2026','2011') if isinstance(v,str) else v for k,v in self.m.events['byu_mens_basketball'][0].items()}
        self.assertEqual(self.value()['value'],'indeterminate')
        self.o['coordinates']=[-111.70,40.25]
        self.assertEqual(self.value()['value'],'no_match')

    def test_parked_or_backing_alone(self):
        for code in ['2','13']:
            rows=[{'observationId':'v','values':{'vehicle.maneuver':{'value':{'code':code}}}}]
            self.assertEqual(self.m.mechanism(rows),[])

    def test_conflicting_sources_and_old_queries(self):
        field='byu_mens_basketball_event_context'
        observations=[]
        for value in ['likely_match','no_match']:
            observations.append({'fields':{s['field']:{'value':value,'matches':[],'reasons':[]} for s in self.m.series.values()}})
        self.assertEqual(self.m.group(observations)['fields'][field]['value'],'indeterminate')

    def test_midnight_and_overtime_recorded_end(self):
        e=self.m.events['byu_mens_basketball'][0]
        e.update(departure_start='2026-01-10T23:30:00-07:00',departure_end='2026-01-11T00:30:00-07:00')
        self.rows[0]['values']['time.occurred_at']['value'].update(date='2026-01-11',time='00:30:00')
        self.assertEqual(self.value()['value'],'likely_match')
        self.assertEqual(local_time('2026-01-11T07:30:00+00:00').hour,0)

    def test_capture_nested_result_and_decorated_item(self):
        html='<div class="schedule-event-item special"><time datetime="2026-01-10T18:00:00-07:00"></time><time class="schedule-event-date__clock">6:00 PM MST</time><strong class="schedule-event-item__opponent-name">Utah</strong><span class="schedule-event-location schedule-event-item__location-venue">Marriott Center</span><div class="schedule-event-item-result__label"><strong>W</strong> 90-80</div>'
        rows,total=parse_schedule(html,'byu_mens_basketball','2025-2026','https://example.com','hash',datetime(2026,10,27).date())
        self.assertEqual(total,1);self.assertEqual(rows[0]['status'],'held')
        self.assertTrue(rows[0]['arrival_start'])

class EventQueryTests(unittest.TestCase):
    def test_stored_fields_and_prior_snapshots(self):
        from danger_zones.query_incidents import select
        from tests.crashes.test_query_incidents import fixture
        group=fixture()
        q={'field':'byu_football_event_context','op':'eq','value':'likely_match'}
        self.assertEqual(select([group],q)[1]['unknown'],1)
        group['eventContext']={'fields':{'byu_football_event_context':{'value':'likely_match'}}}
        self.assertEqual(select([group],q)[0],[group])
