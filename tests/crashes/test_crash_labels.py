from copy import deepcopy
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from danger_zones.crash_labels import export_display_fields, export_values
from scripts.migrate_crash_map_labels import apply, encoded, migrate


class CrashLabelTests(unittest.TestCase):
    def test_examples_labels_and_identifiers(self):
        source = {'Crash_ID': '00049', 'mannerCollision': 96, 'mannerCollision_label': 'Single Vehicle',
                  'roadwayContributingCircumstances': 89, 'weatherCondition': '01', 'County': 49,
                  'lightCondition': '01', 'roadwaySurfaceCondition': '01', 'roadwayJunction': 21,
                  'firstHarmfulEvent': 23, 'numberOfVehicles': 1, 'route': '00089'}
        before = deepcopy(source)
        result = export_values('portal.crashes', source)
        self.assertEqual(result['mannerCollision'], 'Single Vehicle')
        for key, value in {'roadwayContributingCircumstances': 'Not Provided', 'weatherCondition': 'Clear',
                           'County': 'Utah', 'lightCondition': 'Daylight', 'roadwaySurfaceCondition': 'Dry',
                           'roadwayJunction': 'T-Intersection', 'firstHarmfulEvent': 'Pedacycle',
                           'Crash_ID': '00049', 'route': '00089', 'numberOfVehicles': 1}.items():
            self.assertEqual(result[key], value)
        self.assertFalse(any(k.endswith('_label') for k in result))
        self.assertEqual(source, before)
        people = export_values('portal.persons', {'personType': 1, 'injuryLevel': 1,
                               'personDriverContribCircumstances1': 19, 'personDriverContribCircumstances2': 0})
        self.assertEqual(list(people.values()), ['Driver', 'No injury', 'Improper Turn', 'None'])

    def test_alias_orphan_missing_unknown_and_vehicle_labels(self):
        result = export_values('portal.crashes', {'roadwayContributingCircumstances': '3',
            'roadwayContribCircumstances_label': 'Recorded surface issue',
            'roadwayContribCircumstances2_label': 'Debris', 'weatherCondition': 12345, 'lightCondition': None})
        self.assertEqual(result, {'roadwayContributingCircumstances': 'Recorded surface issue',
            'roadwayContribCircumstances2': 'Debris', 'weatherCondition': 'Unmapped code: 12345', 'lightCondition': None})
        self.assertEqual(export_values('portal.vehicles', {'vehicleManeuver': 4, 'vehicleBodyType': 5}),
                         {'vehicleManeuver': 'Overtaking/Passing', 'vehicleBodyType': 'Sport Utility Vehicle'})
        with self.assertRaises(ValueError):
            export_display_fields('portal.crashes', [{'label': 'County', 'value': '49'}, {'label': 'County', 'value': '35'}])

    def test_migration_preserves_map_and_replays_and_rejects_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source'
            (source / 'versions').mkdir(parents=True)
            layer = {'dataset': 'a' * 64, 'features': [{'geometry': {'coordinates': [1, 2]}, 'properties': {'id': 'one'}}]}
            details = {'one': {'id': 'one', 'records': [{'source': 'Utah Crash Data Portal', 'recordId': '49',
                'sections': [{'title': 'Recorded crash attributes', 'fields': [
                    {'label': 'Weather condition', 'value': '01'},
                    {'label': 'Manner collision', 'value': '96'}, {'label': 'Manner collision label', 'value': 'Single Vehicle'}]}]}]}}
            (source / 'map.json').write_bytes(encoded(layer))
            (source / 'details.json.gz').write_bytes(gzip.compress(encoded(details)))
            archive = source / 'versions' / ('a' * 64 + '.json.gz')
            archive.write_bytes(gzip.compress(encoded({'map': layer, 'details': details})))
            first = Path(directory) / 'first'
            report = migrate(source, first)
            self.assertEqual(report['changedDetails'], 1)
            after = json.loads((first / 'map.json').read_bytes())
            self.assertEqual(after['features'], layer['features'])
            transformed = json.loads(gzip.decompress((first / 'details.json.gz').read_bytes()))
            self.assertEqual(transformed['one']['records'][0]['sections'][0]['fields'], [
                {'label': 'Weather condition', 'value': 'Clear'}, {'label': 'Manner collision', 'value': 'Single Vehicle'}])
            second = Path(directory) / 'second'
            self.assertEqual(migrate(first, second)['dataset'], report['dataset'])
            self.assertEqual((first / 'details.json.gz').read_bytes(), (second / 'details.json.gz').read_bytes())
            (source / 'map.json').write_bytes(b'{}')
            with self.assertRaises(ValueError):
                apply(source, first)
            (source / 'map.json').write_bytes(encoded(layer))
            # Recover a run interrupted after details switched but before the map pointer.
            (source / 'details.json.gz').write_bytes((first / 'details.json.gz').read_bytes())
            apply(source, first)
            apply(source, first)
            self.assertTrue(archive.exists())
            self.assertEqual((source / 'map.json').read_bytes(), (first / 'map.json').read_bytes())
            with self.assertRaises(ValueError):
                migrate(source, first)
            (source / 'versions' / (report['dataset'] + '.json.gz')).write_bytes(gzip.compress(b'{}'))
            with self.assertRaises(ValueError):
                migrate(source, Path(directory) / 'corrupt')

    def test_apply_rejects_tampering_and_unsafe_paths_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / 'candidate'
            candidate.mkdir()
            report = {'dataset': 'a' * 64, 'outputs': {'../outside': 'bad'}}
            (candidate / 'migration.json').write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                apply(root / 'source', candidate)
            report['outputs'] = {'map.json': 'bad', 'details.json.gz': 'bad', 'versions/' + 'a' * 64 + '.json.gz': 'bad'}
            (candidate / 'versions').mkdir()
            for name in report['outputs']:
                (candidate / name).write_bytes(b'tampered')
            (candidate / 'migration.json').write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                apply(root / 'source', candidate)
