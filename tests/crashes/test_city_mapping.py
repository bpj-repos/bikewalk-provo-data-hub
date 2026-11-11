"""The portable city workflow works with only the lightweight requirements."""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
import zipfile

from scripts.demo_city_crashes import demo
from scripts.export_city_crashes import ROOT, export
from scripts.prepare_city_crashes import prepare
from danger_zones.city_history import read_city_workbook
from danger_zones.city_map import FIELDS, project


class CityMapping(unittest.TestCase):
    def setUp(self):
        (ROOT / "private").mkdir(exist_ok=True)
        self.temp = TemporaryDirectory(dir=ROOT / "private")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with redirect_stdout(io.StringIO()):
            self.result = demo(self.root / "demo")
        self.workbook = Path(self.result["inputs"]["workbook"])
        self.digest = self.result["inputs"]["sha256"]

    def test_real_pipeline_emits_minimized_geojson_and_complete_zip(self):
        result = self.result
        self.assertEqual(result["coverage"]["qualifying"], 3)
        self.assertEqual(result["coverage"]["mapped"], 2)
        self.assertEqual(result["excluded"]["missingCoordinates"], 1)
        self.assertEqual(result["excluded"]["noNonmotorist"], 1)
        path = Path(result["outputs"]["geojson"])
        layer = json.loads(path.read_bytes())
        self.assertEqual([f["id"] for f in layer["features"]],
                         ["utah-crash-portal:1", "utah-crash-portal:2"])
        for feature in layer["features"]:
            self.assertEqual(set(feature["properties"]), set(FIELDS))
            self.assertEqual(feature["geometry"]["type"], "Point")
        self.assertTrue(layer["features"][0]["properties"]["bike"])
        self.assertEqual(layer["features"][1]["properties"]["severity"], "Fatal")
        manifest = json.loads(Path(result["outputs"]["manifest"]).read_bytes())
        self.assertTrue(manifest["synthetic"])
        with zipfile.ZipFile(result["outputs"]["zip"]) as archive:
            self.assertIsNone(archive.testzip())
            prefix = manifest["name"] + "-" + manifest["version"] + "/"
            self.assertEqual(set(archive.namelist()),
                             {prefix + r["path"] for r in manifest["resources"]} | {prefix + "datapackage.json"})
            for resource in manifest["resources"]:
                data = archive.read(prefix + resource["path"])
                self.assertEqual(len(data), resource["bytes"])
                self.assertEqual("sha256:" + hashlib.sha256(data).hexdigest(), resource["hash"])
        with redirect_stdout(io.StringIO()):
            second = export(self.workbook, self.digest, self.root / "second",
                            "Example City", synthetic=True)
        self.assertEqual(result["outputs"]["sha256"], second["outputs"]["sha256"])
        self.assertEqual(result["outputs"]["zipSha256"], second["outputs"]["zipSha256"])

    def test_annual_population_includes_crashes_without_positions(self):
        with redirect_stdout(io.StringIO()):
            result = prepare(self.workbook, self.digest, self.root / "annual", "Example City", "1.0.0", 2025)
        self.assertEqual(result["coverage"]["crashes"], self.result["coverage"]["qualifying"])
        self.assertEqual(result["nextCommand"][2], "scripts.register_city_crashes")

    def test_invalid_coordinates_and_unknown_severity_remain_explicit(self):
        observations, *_ = read_city_workbook(self.workbook, self.digest, "Example City")
        first = observations[0]
        rows = []
        for i, coordinates in enumerate([(float("nan"), 40), (-111, 91), (True, 40),
                                         ("bad", 40), (-111.123456, 40.123456)]):
            row = deepcopy(first)
            row["sourceRecordId"] = str(i + 10)
            row["metadata"]["crash"].update(longitude=coordinates[0], latitude=coordinates[1],
                                             crashSeverity=None, roadName="Invented private text")
            rows.append(row)
        layer, excluded, count = project(rows, "Example City")
        self.assertEqual((count, len(layer["features"]), excluded["invalidCoordinates"]), (5, 1, 4))
        feature = layer["features"][0]
        self.assertEqual(feature["properties"]["severity"], "Unknown")
        self.assertNotIn("Invented private text", json.dumps(layer))
        self.assertEqual(feature["geometry"]["coordinates"], [-111.1235, 40.1235])
        self.assertEqual(project([], "Example City")[0]["features"], [])

    def test_json_success_and_failure_are_single_parseable_results(self):
        command = [sys.executable, "-m", "scripts.export_city_crashes", str(self.workbook),
                   self.digest, str(self.root / "cli"), "--city", "Example City", "--json"]
        env = {**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + str(ROOT / "pipelines/crashes/src")}
        good = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertEqual(json.loads(good.stdout)["status"], "ok")
        command[4] = "0" * 64
        command[5] = str(self.root / "bad-sha")
        bad = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(json.loads(bad.stdout)["status"], "error")
        self.assertIn("Checksum mismatch", json.loads(bad.stdout)["error"])
        self.assertEqual(bad.stderr, "")
        broken = self.root / "broken.xlsx"
        broken.write_bytes(b"invalid XLSX")
        command[3] = str(broken)
        command[4] = hashlib.sha256(broken.read_bytes()).hexdigest()
        command[5] = str(self.root / "bad-zip")
        invalid_zip = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
        self.assertEqual(invalid_zip.returncode, 2)
        self.assertEqual(json.loads(invalid_zip.stdout)["status"], "error")
        self.assertIn("zip file", json.loads(invalid_zip.stdout)["error"])
        self.assertEqual(invalid_zip.stderr, "")
        with self.assertRaisesRegex(ValueError, "fresh"):
            export(self.workbook, self.digest, Path(self.result["outputs"]["package"]).parents[1],
                   "Example City")

    def test_catalog_header_validation_is_kept_in_lightweight_flow(self):
        from openpyxl import load_workbook
        book = load_workbook(self.workbook)
        book["Crashes"].cell(1, 1, "unexpected_column")
        book.save(self.workbook)
        digest = hashlib.sha256(self.workbook.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "column drift"):
            export(self.workbook, digest, self.root / "bad-schema", "Example City")
        self.assertFalse((self.root / "bad-schema").exists())
