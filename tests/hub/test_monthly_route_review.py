"""The local job serializes candidates and keeps failures visible."""
import fcntl
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import monthly_route_review as review


class MonthlyReview(unittest.TestCase):
    def test_concurrent_review_is_rejected_before_acquisition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "private/candidates"
            runs.mkdir(parents=True)
            with (runs / "monthly-route-review.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(review, "ROOT", root), self.assertRaises(BlockingIOError):
                    review.main()
            self.assertEqual(list(runs.glob("*safe-routes*")), [])

    def test_provider_failure_retains_log_without_success_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(review, "ROOT", root), patch.object(
                review.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "provider")
            ), self.assertRaises(subprocess.CalledProcessError):
                review.main()
            self.assertEqual(len(list(root.rglob("run.log"))), 1)
            self.assertEqual(list(root.rglob("review.md")), [])
