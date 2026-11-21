import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from danger_zones.arcgis import LayerDownload
from danger_zones.incident_updates import upsert, candidate_rows
from danger_zones.normalize import normalize_crashes
from danger_zones.pipeline import import_udot_crashes, UDOT_CRASHES_URL, UDOT_HOSTED_CRASHES_URL
from tests.crashes.test_update_incidents import state_record


class HostedCrashesTests(unittest.TestCase):
    def test_hosted_schema_and_wall_clock_are_normalized(self):
        feature = {'geometry': {'type': 'Point', 'coordinates': [-111.66, 40.25]},
                   'properties': {'crash_id': 123, 'crash_datetime': '2026-11-05T18:13:25+00:00',
                                  'route_id': '2968PM', 'route_direction': 'P', 'roadway_type_cd': 'M', 'beg_mileage': 1.5, 'pedestrian_involved': 'Y'}}
        rows, rejected = normalize_crashes([(2026, feature)], snapshot_id='source', retrieved_at=datetime.now(timezone.utc))
        self.assertFalse(rejected)
        self.assertEqual(rows[0]['observed_at'], datetime(2026, 11, 6, 1, 13, 25, tzinfo=timezone.utc))
        self.assertTrue(rows[0]['pedestrian_involved'])
        import json
        self.assertEqual(json.loads(rows[0]['attributes'])['ROUTE'], '2968')
        self.assertIn('crash_datetime', feature['properties'])

    def test_hosted_precedes_overlapping_archive_years(self):
        def metadata(url, output):
            return {'layers': ([{'id': 1, 'name': 'Crash Locations 2018'}, {'id': 2, 'name': 'Crash Locations 2019'}]
                               if url == UDOT_CRASHES_URL else [{'id': 5, 'name': '2019 Crash Locations'}])}
        def layer(url, output, **kwargs):
            return LayerDownload({'name': 'test'}, [], 'OBJECTID', output)
        with tempfile.TemporaryDirectory() as tmp, patch('danger_zones.pipeline.fetch_service_metadata', side_effect=metadata), \
             patch('danger_zones.pipeline.fetch_layer', side_effect=layer) as fetch, \
             patch('danger_zones.pipeline._finalize_raw_snapshot', side_effect=RuntimeError('stop after acquisition')):
            with self.assertRaisesRegex(RuntimeError, 'stop after acquisition'):
                import_udot_crashes(Path(tmp))
        self.assertEqual([c.args[0] for c in fetch.call_args_list], [UDOT_CRASHES_URL+'/1', UDOT_HOSTED_CRASHES_URL+'/5'])

    def test_reprojection_noise_preserves_old_observation_but_corrections_replace_it(self):
        from copy import deepcopy
        original = state_record()
        received = deepcopy(original)
        received['coordinates'][0] += 1e-10
        received['metadata'].update(ROUTE_DIR_ID='provider-linear-reference', UNUSED=None)
        store = {original['id']: original}
        upsert(store, [received])
        self.assertIs(store[original['id']], original)
        received['metadata']['WEATHER'] = 'Rain'
        upsert(store, [received])
        self.assertIs(store[original['id']], received)

    def test_police_candidates_use_local_occurrence_day_and_time(self):
        record = state_record(time='2026-11-06T01:13:25Z')
        candidate = candidate_rows({'portal': {}, 'observations': {record['id']: record}})[0]
        self.assertEqual((candidate['date'], candidate['time']), ('2026-11-05', '18:13:25'))

    def test_missing_hosted_inventory_fails_before_archive_adoption(self):
        with tempfile.TemporaryDirectory() as tmp, patch('danger_zones.pipeline.fetch_service_metadata', return_value={'layers': []}), \
             patch('danger_zones.pipeline.fetch_layer') as fetch:
            with self.assertRaisesRegex(ValueError, 'Missing hosted'):
                import_udot_crashes(Path(tmp))
            fetch.assert_not_called()
