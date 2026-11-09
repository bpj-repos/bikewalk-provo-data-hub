import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import publish_route_update as publish


class ReviewGate(unittest.TestCase):
    def test_wrong_review_hash_fails_before_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp)
            (d / "review.json").write_text(
                json.dumps({"version": "1.3.0", "sha256": "a" * 64})
            )
            with self.assertRaisesRegex(ValueError, "approved SHA"):
                publish.verify_candidate(d, "b" * 64)

    def test_superseded_candidate_cannot_replace_live_version(self):
        base = {"dataset": publish.DATASET, "version": "1.2.0", "sha256": "one"}
        next_entry = dict(base, version="1.3.0", sha256="two")
        with patch.object(
            publish,
            "load",
            return_value={
                "approved": [base, dict(base, version="1.2.1")],
                "withdrawn": [],
            },
        ):
            with self.assertRaisesRegex(ValueError, "superseded"):
                publish.ledger_check(next_entry, {"previous": base})

    def test_fallback_requires_independent_corridors(self):
        try:
            from scripts.calibrate_route_stress import fit
        except ModuleNotFoundError as e:
            self.skipTest(str(e))
        same_road = [(1, "lane", True, "same")] * 500
        self.assertIsNone(fit(same_road))
        self.assertEqual(
            fit([(1, "lane", True, f"street{i % 8}") for i in range(80)]), "busier"
        )
        self.assertIsNone(
            fit([(1, "lane", bool(i % 2), f"street{i % 8}") for i in range(80)])
        )
