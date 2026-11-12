from copy import deepcopy
from datetime import datetime
import unittest

from danger_zones.crash_context import GEOD, reported_darkness, school_at, school_context, load_register
from danger_zones.query_incidents import select


def fixture():
    return {'inventoryCoverage': [['2024-07-01', '2025-06-30']], 'calendars': {'term': {
        'from': '2024-07-01', 'through': '2025-06-30',
        'closedRanges': [['2024-12-23', '2025-01-03']], 'uncertainDates': ['2025-02-06']}},
        'schools': [{'id': 'school-1', 'opened': '2010-01-01', 'closed': None,
                     'locations': [{'id': 'campus', 'from': '2024-07-01', 'through': '2025-06-30',
                                    'point': [-111.66, 40.23]}],
                     'schedules': [{'id': 'bells', 'from': '2024-07-01', 'through': '2025-06-30',
                                    'calendar': 'term', 'weekdays': {
                                        **{str(d): [['08:30', '15:00']] for d in range(4)},
                                        '4': [['08:30', '13:00']]},
                                    'overrides': {'2025-02-07': [['10:30', '12:00']]}}]}]}


def observation(light=None, clock='08:15:00', basis='occurrence'):
    return {'observationId': 'o', 'fields': {
        'lighting': {'value': light},
        'time': {'value': {'date': '2025-02-03', 'clock': clock, 'precision': 'second', 'basis': basis}}}}


class ContextTests(unittest.TestCase):
    def classify(self, when, register=None, point=None):
        return school_at(point or [-111.66, 40.23], datetime.fromisoformat(when), register or fixture(), 402)

    def test_all_inclusive_time_boundaries_and_adjacent_seconds(self):
        for clock, expected in [('07:59:59', 'no match'), ('08:00:00', 'drop-off'),
                                ('08:30:00', 'drop-off'), ('08:30:01', 'no match'),
                                ('14:59:59', 'no match'), ('15:00:00', 'pickup'),
                                ('15:30:00', 'pickup'), ('15:30:01', 'no match')]:
            with self.subTest(clock=clock):
                self.assertEqual(self.classify('2025-02-03T' + clock)['value'], expected)

    def test_radius_boundary_and_adjacent_metres(self):
        for metres, expected in [(401.999, 'drop-off'), (402, 'drop-off'), (402.001, 'no match')]:
            lon, lat, _ = GEOD.fwd(-111.66, 40.23, 90, metres)
            self.assertEqual(self.classify('2025-02-03T08:15:00', point=[lon, lat])['value'], expected)

    def test_friday_holiday_weekend_and_override(self):
        self.assertEqual(self.classify('2025-02-14T13:15:00')['value'], 'pickup')
        self.assertEqual(self.classify('2025-02-14T15:15:00')['value'], 'no match')
        self.assertEqual(self.classify('2025-01-01T08:15:00')['value'], 'no match')
        self.assertEqual(self.classify('2025-02-08T08:15:00')['value'], 'no match')
        self.assertEqual(self.classify('2025-02-07T10:15:00')['value'], 'drop-off')
        self.assertEqual(self.classify('2025-02-07T12:15:00')['value'], 'pickup')
        self.assertEqual(self.classify('2025-02-06T08:15:00')['reasons'], ['exception-schedule-unavailable'])

    def test_missing_schedule_nearby_and_outside(self):
        register = fixture(); register['schools'][0]['schedules'] = []
        self.assertEqual(self.classify('2025-02-03T08:15:00', register)['value'], 'unknown')
        self.assertEqual(self.classify('2025-02-03T08:15:00', register, [-111.70, 40.23])['value'], 'no match')

    def test_relocation_and_unverified_history(self):
        register = fixture()
        register['schools'][0]['locations'].append({'id': 'old-campus', 'from': '2010-01-01',
                                                  'through': '2024-06-30', 'point': [-111.70, 40.23]})
        self.assertEqual(self.classify('2025-02-03T08:15:00', register, [-111.70, 40.23])['value'], 'no match')
        del register['schools'][0]['locations'][0]
        self.assertEqual(self.classify('2025-02-03T08:15:00', register, [-111.70, 40.23])['value'], 'unknown')

    def test_overlapping_schools_and_sessions(self):
        register = fixture(); second = deepcopy(register['schools'][0]); second['id'] = 'school-2'
        second['schedules'][0]['weekdays']['0'] = [['07:00', '08:00']]
        register['schools'].append(second)
        result = self.classify('2025-02-03T08:15:00', register)
        self.assertEqual(result['value'], 'both')
        self.assertEqual({m['schoolId'] for m in result['matches']}, {'school-1', 'school-2'})

    def test_conflicting_schedules(self):
        register = fixture(); second = deepcopy(register['schools'][0]['schedules'][0])
        second['weekdays']['0'] = [['10:00', '15:00']]
        register['schools'][0]['schedules'].append(second)
        self.assertEqual(self.classify('2025-02-03T08:15:00', register)['value'], 'unknown')

    def test_darkness_without_crossing_or_clock(self):
        for light in ['dark-lighted', 'dark-unlighted', 'dark-lighting-unknown']:
            result = reported_darkness([observation(light, None)])
            self.assertEqual(result['value'], 'dark'); self.assertEqual(result['lighting'], [light])
        self.assertEqual(reported_darkness([observation('daylight')])['value'], 'daylight')
        self.assertEqual(reported_darkness([observation('dawn-dusk')])['value'], 'dawn/dusk')
        self.assertEqual(reported_darkness([observation()])['value'], 'unknown')
        self.assertEqual(reported_darkness([observation(), observation('dark-lighted')])['value'], 'dark')
        result = reported_darkness([observation('daylight'), observation('dark-lighted')])
        self.assertEqual(result['value'], 'unknown'); self.assertEqual(result['reason'], 'source-conflict')

    def test_missing_crash_inputs_and_report_time(self):
        original = {'o': {'coordinates': [-111.66, 40.23]}}
        self.assertEqual(school_context({}, [observation(basis='report')], original, fixture())['reasons'],
                         ['occurrence-time-unavailable'])
        self.assertEqual(school_context({}, [observation(clock=None)], original, fixture())['value'], 'unknown')
        self.assertEqual(school_context({}, [observation()], {'o': {}}, fixture())['reasons'],
                         ['crash-location-unavailable'])

    def test_known_clock_supplies_missing_source_and_conflicting_results(self):
        one = observation(); two = observation(clock=None); two['observationId'] = 'two'
        originals = {'o': {'coordinates': [-111.66, 40.23]}, 'two': {'coordinates': [-111.66, 40.23]}}
        self.assertEqual(school_context({}, [one, two], originals, fixture())['value'], 'drop-off')
        two['fields']['time']['value']['clock'] = '15:15:00'
        result = school_context({}, [one, two], originals, fixture())
        self.assertEqual(result['value'], 'unknown')
        self.assertIn('crash-source-conflict', result['reasons'])

    def test_persisted_query_and_old_collection(self):
        group = {'id': 'g', 'observations': [{'id': 'o', 'sourceKey': 'udot-crashes', 'metadata': {}}],
                 'enrichment': {'context': {'darkness': {'value': 'dark'}, 'school': {
                     'value': 'pickup', 'matches': [{'schoolId': 'school-1'}, {'schoolId': 'school-2'}]}}}}
        query = {'all': [{'field': 'darkness', 'op': 'eq', 'value': 'dark'},
                         {'field': 'school_id', 'op': 'eq', 'value': 'school-2'}]}
        self.assertEqual(select([group], query)[1]['matched'], 1)
        del group['enrichment']['context']
        self.assertEqual(select([group], query)[1]['unknown'], 1)

    def test_real_register_validates(self):
        self.assertGreater(len(load_register()['schools']), 18)
