import csv
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from openpyxl import load_workbook

from scripts.prepare_city_crashes import prepare
from tests.crashes.test_update_incidents import portal_record, portal_workbook


class CityPackageTests(unittest.TestCase):
    def test_city_workbook_to_annual_package(self):
        with TemporaryDirectory() as tmp, patch('scripts.prepare_crash_releases.ROOT', Path(tmp).resolve()):
            directory = Path(tmp) / 'private'
            directory.mkdir()
            bike = portal_record('1', city='Orem')
            bike['metadata']['crash'].update(numberOfVehicles=1, latitude=None, longitude=None)
            outside = portal_record('2', city='Provo')
            outside['metadata']['crash']['numberOfVehicles'] = 1
            path = portal_workbook(directory / 'input.xlsx', [bike, outside], city='Orem')
            book = load_workbook(path)
            filters = {'Date Selection': 'Jan 01, 2023 to Jun 30, 2026 for 2023, 2025, 2026',
                       'Age Range': 'All Ages Included', 'Agency': 'All',
                       'Days': 'Mon, Tue, Wed, Thu, Fri, Sat, Sun', 'Hours': '12:00 AM to 11:59 PM',
                       'Number of Vehicles': 'All Vehicle Counts Included'}
            for item in filters.items():
                book['Filters'].append(item)
            book.save(path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            output = directory / 'package'
            with self.assertRaisesRegex(ValueError, 'Orem|Provo'):
                prepare(path, digest, output, 'Provo', '1.0.0', 2025)
            with self.assertRaisesRegex(ValueError, 'Checksum'):
                prepare(path, '0' * 64, output, 'Orem', '1.0.0', 2025)
            prepare(path, digest, output, 'Orem', '1.0.0', 2025)
            package = output / 'orem-annual-at-crash-aggregates/1.0.0'
            manifest = json.loads((package / 'datapackage.json').read_text())
            self.assertEqual({r['path'] for r in manifest['resources']}, {'annual.csv', 'dictionary.json', 'method.txt'})
            with (package / 'annual.csv').open() as stream:
                self.assertEqual(list(csv.reader(stream)), [
                    ['year', 'total', 'bike', 'ped', 'other', 'complete_year'],
                    ['2023', '0', '0', '0', '0', 'True'],
                    ['2025', '1', '1', '0', '0', 'True'],
                    ['2026', '0', '0', '0', '0', 'False']])
            book['Filters'].append(['Agency', 'One agency'])
            book.save(path)
            with self.assertRaisesRegex(ValueError, 'unrestricted'):
                prepare(path, hashlib.sha256(path.read_bytes()).hexdigest(), directory / 'bad', 'Orem', '1.0.0', 2025)
