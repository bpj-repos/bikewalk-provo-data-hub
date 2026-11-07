from email.message import EmailMessage
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest

read_forward = runpy.run_path(str(Path(__file__).resolve().parents[1]/'reviews/forwarded_police.py'))['read_forward']


class ForwardedReportTests(unittest.TestCase):
    def test_report_date_preserves_missing_clock_and_case_letters(self):
        msg = EmailMessage()
        msg.set_content('forward')
        msg.add_alternative('<table><tr><td>number</td><td>dtrepor</td><td>agency</td><td>street</td><td>desc</td></tr>'
                            '<tr><td>26PRW1234</td><td>10/5/2026</td><td>PRPD</td><td></td><td>Bicycle</td></tr></table>',subtype='html')
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'forward.eml'
            path.write_bytes(msg.as_bytes())
            self.assertEqual(read_forward(path),[dict(id='26PRW1234',date='2026-10-05',time=None,address='',modeRaw='Bicycle')])
