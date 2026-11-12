import unittest
from scripts.prepare_crash_time import derive, local_value


class CrashTimeTests(unittest.TestCase):
    def test_local_boundaries(self):
        for stamp, weekday, minute in [
            ('2026-01-01T06:59:59Z', 3, 1439), ('2026-01-01T07:00:00Z', 4, 0),
            ('2026-03-08T08:59:59Z', 7, 119), ('2026-03-08T09:00:00Z', 7, 180),
            ('2026-03-08T02:30:00', 7, None), ('2026-11-01T01:30:00-06:00', 7, 90),
            ('2026-11-01T01:30:00-07:00', 7, 90), ('10/18/2012', 4, None),
            ('10/18/2012 12:00:00 AM', 4, 0)]:
            day, actual = local_value(stamp)
            self.assertEqual((day.isoweekday(), actual), (weekday, minute))

    def test_evidence_precision_and_conflict(self):
        record = dict(source='Utah Crash Data Portal', dateMeaning='state crash date/time in America/Denver',
                      date='2012-10-18T00:00:00-06:00', sections=[dict(fields=[dict(label='Crash dateand time', value='10/18/2012')])])
        self.assertEqual(derive([record])['status'], 'date-only')
        udot = dict(source='UDOT', dateMeaning='crash date/time', date='2012-10-18T06:00:00Z')
        self.assertEqual(derive([record, udot])['localMinuteOfDay'], 0)
        self.assertEqual(derive([udot, dict(udot, date='2012-10-18T06:01:00Z')])['status'], 'minute-conflict')
        self.assertEqual(derive([record, dict(udot, date='2012-10-18T05:59:00Z')])['status'], 'date-conflict')
        self.assertEqual(derive([dict(udot, source='Provo Police')])['status'], 'no-occurrence-evidence')
