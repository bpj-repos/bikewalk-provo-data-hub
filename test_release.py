import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import release


class ReleaseProof(unittest.TestCase):
    def test_reconstruct_every_year_and_check_missing_values(self):
        for version in release.VERSIONS:
            files = release.package(version)
            manifest = json.loads(files['datapackage.json'])
            def rows(path):
                return list(csv.DictReader(io.StringIO(files[path].decode())))
            annual = [r for y in manifest['coverage'] for r in rows(f'{y}.csv')]
            self.assertEqual(annual, rows('series.csv'))
            for r in annual:
                self.assertEqual(r['value'], '0' if r['status'] == 'observed' else '')
            self.assertEqual({r['status'] for r in annual}, {'observed','missing','unavailable'})

    def test_reject_changed_pin(self):
        original = release.package
        def modified(version):
            files = original(version)
            files['datapackage.json'] += b' '
            return files
        with patch.object(release, 'package', modified), self.assertRaisesRegex(ValueError, 'pin'):
            release.expected(release.VERSIONS)

    def test_corrupt_output_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for path, data in release.expected(release.VERSIONS).items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            release.validate(root, release.VERSIONS)
            next(root.rglob('series.csv')).write_bytes(b'correction')
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                release.validate(root, release.VERSIONS)

    def test_contract_version_examples(self):
        # Release owners supply the change classification after reviewing meaning.
        for change, version in [('correction', '1.0.1'), ('compatible', '1.1.0'),
                                ('breaking', '2.0.0')]:
            release.check_version('1.0.0', version, change)
            with self.assertRaises(ValueError):
                release.check_version('1.0.0', '1.0.0', change)
        with self.assertRaises(ValueError):
            release.check_version('1.0.0', '1.1.0', 'breaking')
