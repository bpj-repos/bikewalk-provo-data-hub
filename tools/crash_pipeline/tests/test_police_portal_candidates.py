import unittest
from datetime import date

from danger_zones.police_portal_candidates import month_boundary, portal_rows, search


def police(identifier='local', day='2025-03-31', coordinates=(-111.66, 40.23), mode='bicycle', address='400 E 800 NORTH ST'):
    return {'id': identifier, 'caseNumber': identifier, 'reportDate': day, 'mode': mode,
            'coordinates': coordinates, 'address': address, 'notes': None}


def crash(identifier='state', day='2025-03-01', coordinates=(-111.66, 40.23), modes=None, active=True, road='E 800 N S 400 E'):
    return {'id': identifier, 'date': day, 'coordinates': coordinates, 'modes': ['bicycle'] if modes is None else modes,
            'activeTransportationSelected': active, 'road': road, 'severity': 'No Injury/PDO'}


class PolicePortalCandidateTests(unittest.TestCase):
    def test_calendar_month_clamping_and_inclusive_window(self):
        self.assertEqual(month_boundary(date(2024, 3, 31), -1), date(2024, 2, 29))
        self.assertEqual(month_boundary(date(2025, 1, 31), -1), date(2024, 12, 31))
        rows = [crash('start', '2025-02-28'), crash('end', '2025-04-30'),
                crash('before', '2025-02-27'), crash('after', '2025-05-01')]
        r = search([police()], rows, 100)['records'][0]
        self.assertEqual({c['id'] for c in r['candidates']}, {'start', 'end'})
        self.assertEqual({c['id']: c['crashDateMinusReportDays'] for c in r['candidates']}, {'start': -31, 'end': 30})
        self.assertTrue(next(c for c in r['candidates'] if c['id'] == 'end')['afterReportDate'])

    def test_baseline_and_full_export_mode_mismatch_are_distinct(self):
        rows = [crash('near-day', '2025-03-30'), crash('delayed', '2025-03-15'),
                crash('car-only', '2025-03-31', modes=[], active=False),
                crash('far', coordinates=(-111.7, 40.23))]
        r = search([police()], rows, 100)['records'][0]
        self.assertFalse(r['inFocusCohort'])
        self.assertEqual(r['baselinePortalCandidates'], ['near-day'])
        self.assertEqual({c['id'] for c in r['candidates']}, {'near-day', 'delayed', 'car-only'})
        car = next(c for c in r['candidates'] if c['id'] == 'car-only')
        self.assertEqual(car['modeRelationship'], 'mode-mismatch-or-missing')
        self.assertFalse(car['withinEarlierOneDayRule'])

    def test_missing_geocodes_get_only_separate_exact_token_hints(self):
        r = search([police(coordinates=None)], [crash(), crash('wrong', road='E 1800 N S 400 E')], 100)
        self.assertEqual(r['summary']['focusUnresolvedLocations'], 1)
        self.assertEqual(r['summary']['focusWithSpatialCandidates'], 0)
        self.assertEqual([c['id'] for c in r['records'][0]['candidates']], ['state'])
        self.assertEqual(r['records'][0]['candidates'][0]['locationMethod'], 'text-only-unverified-location')
        self.assertEqual(search([police(coordinates=None, address=None)], [crash()], 100)['records'][0]['status'], 'location-unresolved')

    def test_errors_and_no_double_count_or_forced_assignment(self):
        for radius in [0, -1, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                search([], [], radius)
        for a, b in [([police(), police()], []), ([], [crash(), crash()]),
                     ([police(coordinates=(float('nan'), 40))], [])]:
            with self.assertRaises(ValueError):
                search(a, b, 100)
        r = search([police('a'), police('b')], [crash()], 100)
        self.assertEqual(r['summary']['focusWithCandidates'], 2)
        self.assertEqual(r['summary']['focusCandidatePairs'], 2)

    def test_portal_selection_uses_people_and_rollups_but_keeps_car_only(self):
        base = {'crashDateandTime': '2025-03-01 10:00:00', 'longitude': '-111.66', 'latitude': '40.23',
                'roadName': '400 E', 'crashSeverity_label': 'No Injury/PDO', 'officer_department': 'PROVO POLICE'}
        tables = {'portal.crashes': {'rows': [dict(base, Crash_ID='1'), dict(base, Crash_ID='2'), dict(base, Crash_ID='3')]},
                  'portal.rollups': {'rows': [{'Crash_ID': '2', 'cyclist_involved': 'Y'}]},
                  'portal.persons': {'rows': [{'Crash_ID': '1', 'personType': '5', 'personType_label': 'Other Pedestrian'}]}}
        rows = portal_rows(tables)
        self.assertEqual([r['activeTransportationSelected'] for r in rows], [True, True, False])
        self.assertEqual([r['modes'] for r in rows], [['other-conveyance'], ['bicycle'], []])

    def test_existing_tight_candidate_for_another_report_is_flagged(self):
        rows = [police('delayed', day='2025-03-31'), police('tight', day='2025-03-01')]
        r = search(rows, [crash()], 100)
        lead = r['records'][0]['candidates'][0]
        self.assertEqual(lead['otherPoliceWithTightCandidate'], [{'caseNumber': 'tight', 'reportDate': '2025-03-01', 'mode': 'bicycle'}])
        self.assertEqual(r['summary']['focusWithUncontestedCompatibleSpatialDateExpansion'], 0)


if __name__ == '__main__':
    unittest.main()
