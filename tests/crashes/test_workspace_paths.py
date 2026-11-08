import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from danger_zones.update_incidents import RestorePaths
from danger_zones import update_incidents
from danger_zones.config import PACKAGE_ROOT
from danger_zones.field_inventory import CATALOG, read_catalog


class WorkspacePaths(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'workspace'
        self.collection = self.root / 'collection'
        self.geography = self.root / 'geography'
        self.collection.mkdir(parents=True)
        self.geography.mkdir()
        self.old = self.base / 'original'

    def test_multiple_destinations_and_checked_reference(self):
        path = self.collection / 'record.json'
        path.write_text('{}')
        resolver = RestorePaths([(self.old / 'private', self.collection),
                                 (self.old / 'data', self.geography)], root=self.root)
        reference = {'path': str(self.old / 'private/record.json'),
                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        self.assertEqual(resolver.ref(reference)['path'], str(path))
        self.assertEqual(resolver.local(self.old / 'data/map.json'), self.geography / 'map.json')
        self.assertEqual(resolver.local(path), path)
        reference['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'checksum'):
            resolver.ref(reference)

    def test_existing_single_destination(self):
        resolver = RestorePaths([(self.old, self.root)])
        self.assertEqual(resolver.local(self.old / 'record.json'), self.root / 'record.json')
        with self.assertRaises(ValueError):
            RestorePaths([(self.old, self.collection), (self.base / 'other', self.geography)])

    def test_catalog_accepts_relative_definition_root(self):
        relative = Path(os.path.relpath(PACKAGE_ROOT))
        self.assertEqual(read_catalog(CATALOG, relative), read_catalog())

    def test_installed_command_uses_workspace_mappings(self):
        mapping_file = self.root / 'path-map.json'
        mapping_file.write_text(json.dumps([{'from': str(self.old), 'to': str(self.collection)}]))
        configured = {'workspace': self.root, 'collection': self.collection,
                      'geography': self.geography, 'mappings': mapping_file}
        with patch.object(update_incidents, 'WORKSPACE_PATHS', configured), \
                patch.object(sys, 'argv', ['bwp-update-crashes', '--offline']), \
                patch.object(update_incidents, 'run_update', return_value={'status': 'unchanged'}) as run:
            update_incidents.main()
        self.assertEqual(run.call_args.args, (self.collection, self.geography))
        self.assertEqual(run.call_args.kwargs['restore'].local(self.old / 'record.json'),
                         self.collection / 'record.json')

    def test_reject_ambiguous_unmapped_and_traversal(self):
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            RestorePaths([(self.old, self.collection), (self.old / 'nested', self.geography)], root=self.root)
        resolver = RestorePaths([(self.old, self.collection)], root=self.root)
        for path in [self.base / 'unmapped/file', self.old / '../escape', Path('relative')]:
            with self.assertRaises(ValueError):
                resolver.local(path)

    def test_reject_destination_and_symlink_escape(self):
        outside = self.base / 'outside'
        outside.mkdir()
        with self.assertRaises(ValueError):
            RestorePaths([(self.old, outside)], root=self.root)
        (self.collection / 'escape').symlink_to(outside, target_is_directory=True)
        resolver = RestorePaths([(self.old, self.collection)], root=self.root)
        with self.assertRaisesRegex(ValueError, 'escapes'):
            resolver.local(self.old / 'escape/file')

    def test_compatibility_entrypoints_from_another_directory(self):
        hub = Path(__file__).resolve().parents[2]
        for old, module in [('update_crashes.py', 'update_crashes'), ('adopt_routes.py', 'adopt_routes')]:
            old_result = subprocess.run([sys.executable, '-B', str(hub / old), '--help'],
                                        cwd=self.base, capture_output=True, text=True)
            new_result = subprocess.run([sys.executable, '-B', '-m', 'scripts.' + module, '--help'],
                                        cwd=hub, capture_output=True, text=True)
            self.assertEqual(old_result.returncode, 0, old_result.stderr)
            self.assertEqual(new_result.returncode, 0, new_result.stderr)
            self.assertEqual(old_result.stdout.split('\n\n', 1)[1],
                             new_result.stdout.split('\n\n', 1)[1])
