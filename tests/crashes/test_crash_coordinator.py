import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.coordinate_crash_update import Run, read, save
from scripts.review_crash_receipt import package_version


class CoordinatorTests(unittest.TestCase):
    def test_console_routes_to_guarded_wrapper_and_returns_status(self):
        from danger_zones.cli import main
        from types import SimpleNamespace
        with patch('danger_zones.cli.subprocess.run', return_value=SimpleNamespace(returncode=2)) as call, patch('sys.argv',['bwp-update-crashes','--offline']):
            self.assertEqual(main(),2)
            self.assertEqual(call.call_args.args[0][1:], ['-m','scripts.update_crashes','--offline'])
            self.assertIn('pipelines/crashes/src',call.call_args.kwargs['env']['PYTHONPATH'])

    def test_versions_reject_missing_withdrawn_and_reused_snapshot(self):
        dataset='provo-crash-occurrence-time'
        with self.assertRaisesRegex(ValueError,'explicit'):
            package_version(dataset,None,'new',{'approved':[],'withdrawn':[]})
        with self.assertRaisesRegex(ValueError,'Withdrawn'):
            package_version(dataset,'1.2.0','new',{'approved':[],'withdrawn':[{'dataset':dataset,'version':'1.2.0'}]})
        entry={'dataset':dataset,'version':'1.2.0','sha256':'pin'}
        ledger={'approved':[entry],'withdrawn':[]}
        with patch('scripts.review_crash_receipt.checked_package',return_value={'datapackage.json':b'{"crashDataset":"old"}'}):
            with self.assertRaisesRegex(ValueError,'another snapshot'):
                package_version(dataset,'1.2.0','new',ledger)
            self.assertEqual(package_version(dataset,'1.2.0','old',ledger),entry)

    def test_unchanged_snapshot_reuses_approved_version(self):
        from scripts.coordinate_crash_update import version_for_snapshot
        with patch('scripts.coordinate_crash_update.latest',return_value=(Path('/package'),{'version':'1.2.1'})), patch('scripts.coordinate_crash_update.read',return_value={'crashDataset':'same'}):
            self.assertEqual(version_for_snapshot('time','same'),'1.2.1')
            self.assertEqual(version_for_snapshot('time','new'),'1.2.2')

    def test_interrupted_stage_resumes_completed_work_and_preserves_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Run.__new__(Run); run.folder=Path(tmp);run.file=run.folder/'run.json'
            run.state={'stages':{}}
            def success(work):
                (work/'evidence').write_text('verified')
                return {'count':1921}
            self.assertEqual(run.step('intake',success),{'count':1921})
            def interrupted(work):
                (work/'partial').write_text('preserve')
                raise KeyboardInterrupt()
            with self.assertRaises(KeyboardInterrupt):run.step('consumer',interrupted)
            run.state=read(run.file)
            self.assertEqual(run.step('intake',lambda _:self.fail('Repeated completed stage')),{'count':1921})
            self.assertEqual(run.step('consumer',success),{'count':1921})
            self.assertEqual((run.folder/'consumer-1/partial').read_text(),'preserve')
            (run.folder/'intake-1/evidence').write_text('corrupted')
            with self.assertRaisesRegex(ValueError,'changed'):run.step('intake',success)


if __name__=='__main__':unittest.main()
