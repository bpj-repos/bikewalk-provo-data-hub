import hashlib
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from openpyxl import load_workbook

from danger_zones.city_history import portal_report, udot_summary
from scripts.prepare_crash_releases import write_package
from scripts.register_city_crashes import register, START, END, city_write_lock
from tests.crashes.test_update_incidents import portal_record, portal_workbook


class CityHistoryTests(unittest.TestCase):
    def test_workbook_summary_and_registered_zip(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            private = root / 'private'
            private.mkdir()
            record = portal_record()
            record['metadata']['crash']['numberOfVehicles'] = 1
            path = portal_workbook(private / 'Provo.xlsx', [record])
            wb = load_workbook(path)
            for k, v in {'Date Selection': 'Jan 01, 2017 to Dec 31, 2025 for ' + ', '.join(map(str, range(2017, 2026))),
                         'Age Range': 'All Ages Included', 'Agency': 'All',
                         'Days': 'Mon, Tue, Wed, Thu, Fri, Sat, Sun', 'Hours': '12:00 AM to 11:59 PM',
                         'Number of Vehicles': 'All Vehicle Counts Included'}.items():
                wb['Filters'].append([k, v])
            wb.save(path)
            receipt = dict(city='Provo', file=path.name, dates=['01/01/2017', '12/31/2025'],
                           years=list(map(str, range(2017, 2026))), expectedCrashes=1, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            path.with_suffix('.xlsx.json').write_text(json.dumps(receipt))
            stats = portal_report(private, 'Provo')
            self.assertEqual((stats['count'], stats['latest']), (1, '2025-03-04'))
            self.assertEqual(stats['report']['annual'][-1]['bike'], 1)
            with patch('scripts.prepare_crash_releases.ROOT', root):
                write_package(stats['report'], [stats['sourceSelection']], private / 'candidate',
                              '1.1.0', 2024, city='Provo', dataset='provo-annual-at-crash-aggregates')
            package = private / 'candidate/provo-annual-at-crash-aggregates/1.1.0'
            (root / 'releases').mkdir()
            ledger = root / 'releases/release-ledger.json'
            ledger.write_text('{"approved": [], "withdrawn": []}')
            definitions = root / 'data-definitions/crashes'
            definitions.mkdir(parents=True)
            (definitions / 'city-coverage.json').write_text('[]')
            (root / 'README.md').write_text(START + '\n' + END)
            digest = hashlib.sha256((package / 'datapackage.json').read_bytes()).hexdigest()
            with city_write_lock(root):
                with self.assertRaisesRegex(ValueError, 'Another city update'):
                    register(package, digest, root)
            result = register(package, digest, root)
            self.assertEqual(result['outputs']['sha256'], digest)
            self.assertEqual(result['coverage']['city'], 'Provo')
            register(package, digest, root)
            self.assertEqual(len(json.loads(ledger.read_text())['approved']), 1)
            archive = next((root / 'releases').rglob('*.zip'))
            with zipfile.ZipFile(archive) as zipped:
                self.assertIsNone(zipped.testzip())
                prefix = 'provo-annual-at-crash-aggregates-1.1.0/'
                header, older, *recent = zipped.read(prefix + 'annual.csv').splitlines(keepends=True)
                self.assertTrue(older.startswith(b'2017,'))
                self.assertEqual(zipped.read(prefix + 'annual-from-2018.csv'), header + b''.join(recent))
            self.assertNotIn('[Generated ZIP]', (root / 'README.md').read_text())
            state = json.loads(ledger.read_bytes())
            state['publicCityReleases'] = [dict(dataset='provo-annual-at-crash-aggregates', version='1.1.0')]
            ledger.write_text(json.dumps(state))
            register(package, digest, root)
            self.assertIn('[Generated ZIP](releases/datasets/provo-', (root / 'README.md').read_text())
            state['withdrawn'] = [dict(dataset='provo-annual-at-crash-aggregates', version='1.1.0')]
            ledger.write_text(json.dumps(state))
            from scripts.register_city_crashes import readme
            coverage = json.loads((root / 'data-definitions/crashes/city-coverage.json').read_bytes())
            self.assertNotIn('[Generated ZIP]', readme(coverage, root))
            receipt['expectedCrashes'] = 2
            path.with_suffix('.xlsx.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'dashboard'):
                portal_report(private, 'Provo')

    def test_udot_deduplicates_identical_state_ids_and_rejects_conflicts(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            city = {'type': 'Feature', 'properties': {'NAME': 'Provo'},
                    'geometry': {'type': 'Polygon', 'coordinates': [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}}
            crash = {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [.5, .5]},
                     'properties': {'crash_id': 1, 'crash_datetime': '2025-01-01T01:00:00-07:00',
                                    'number_vehicles_involved': 1}}
            def save(rows):
                files = {}
                for name, value in [('cities.json', [city]), ('2025.json', rows)]:
                    raw = json.dumps(value).encode()
                    (root / name).write_bytes(raw)
                    files[name] = hashlib.sha256(raw).hexdigest()
                (root / 'receipt.json').write_text(json.dumps(dict(layers={'2025': 'fixture'}, files=files)))
            save([crash, crash])
            self.assertEqual(udot_summary(root, ['Provo'])['Provo'][0], 1)
            changed = {**crash, 'geometry': {'type': 'Point', 'coordinates': [.6, .5]}}
            save([crash, changed])
            with self.assertRaisesRegex(ValueError, 'conflicting'):
                udot_summary(root, ['Provo'])

    def test_provo_links_to_its_original_public_product(self):
        from scripts.register_city_crashes import readme
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'releases').mkdir()
            ledger = root / 'releases/release-ledger.json'
            state = dict(approved=[dict(dataset='annual-at-crash-aggregates', version='1.1.0')],
                         withdrawn=[], publicCityReleases=[])
            ledger.write_text(json.dumps(state))
            (root / 'README.md').write_text(START + '\n' + END)
            rows = [dict(city='Provo', dataset=dict(id='provo-annual-at-crash-aggregates',
                                                  version='1.0.0', zip='summary.zip'))]
            expected = 'https://bikewalk-provo-data-hub.vercel.app/downloads/annual-at-crash-aggregates/1.1.0/annual-at-crash-aggregates-1.1.0.zip'
            self.assertIn(expected, readme(rows, root))
            self.assertNotIn('summary.zip', readme(rows, root))
            state['withdrawn'] = [dict(dataset='annual-at-crash-aggregates', version='1.1.0')]
            ledger.write_text(json.dumps(state))
            self.assertNotIn(expected, readme(rows, root))

    def test_committed_city_packages_match_the_table_and_zip(self):
        from scripts.build_catalog import checked_package, download_zip
        from scripts.register_city_crashes import ROOT
        coverage = ROOT / 'data-definitions/crashes/city-coverage.json'
        for row in json.loads(coverage.read_bytes()):
            package = row.get('dataset')
            if not package:
                continue
            with self.subTest(city=row['city']):
                dataset, version = package['id'], package['version']
                directory = ROOT / 'releases/datasets' / dataset / version
                files = checked_package(directory, dict(dataset=dataset, version=version, sha256=package['sha256']))
                manifest = json.loads(files['datapackage.json'])
                annual = list(csv.DictReader(io.StringIO(files['annual.csv'].decode())))
                self.assertEqual(sum(int(r['total']) for r in annual), row['portal']['count'])
                self.assertEqual(manifest['latestEvent'], row['portal']['latest'])
                prefix = f'datasets/{dataset}/{version}/'
                expected = download_zip({prefix + k: v for k, v in files.items()},
                                        dict(manifest='/' + prefix + 'datapackage.json'))
                self.assertEqual((ROOT / package['zip']).read_bytes(), expected)
