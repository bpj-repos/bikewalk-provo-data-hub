import json
from pathlib import Path
import tempfile
import unittest
from incident_map import ROOT, build


class IncidentMapCandidate(unittest.TestCase):
    @unittest.skipUnless((ROOT/'private/crashes/incident-map-20261108/receipt.json').exists(), 'retained private map receipt required')
    def test_restore_repeat_and_corruption(self):
        receipt=ROOT/'private/crashes/incident-map-20261108/receipt.json'
        with tempfile.TemporaryDirectory(dir=ROOT/'private') as temp:
            root=Path(temp)
            build(receipt,root/'first')
            build(receipt,root/'second')
            first={f.name:f.read_bytes() for f in (root/'first').iterdir()}
            self.assertEqual(first,{f.name:f.read_bytes() for f in (root/'second').iterdir()})
            self.assertEqual(json.loads(first['datapackage.json'])['records'],1195)
            data=json.loads(receipt.read_bytes())
            for key in ('normalized','derived','base','mapManifest'):
                data[key]['path']=str((receipt.parent/data[key]['path']).resolve())
            bad=root/'corrupted.json';bad.write_text('{}')
            data['base']['path']=str(bad)
            new=root/'bad-receipt.json';new.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):
                build(new,root/'failed')
            self.assertFalse((root/'failed').exists())
            self.assertEqual(first,{f.name:f.read_bytes() for f in (root/'first').iterdir()})
