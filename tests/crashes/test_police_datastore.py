from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from danger_zones.police_datastore import (
    merge_police_incident_datastore,
    normalize_police_location,
)
from danger_zones.police import _police_column_mapping, _source_row_from_values
from danger_zones.normalize import normalize_police_mode
from danger_zones.util import sha256_file


NOW = datetime(2026, 8, 12, 18, 30, tzinfo=timezone.utc)


class FakeProviderGeocoder:
    def geocode(self, query: str | None) -> dict:
        return {
            "status": "matched",
            "mapEligible": True,
            "method": "fixture",
            "provider": "fixture",
            "query": query,
            "providerLabel": "Normalized provider label",
            "coordinates": {"lat": 40.23, "lng": -111.66},
            "confidence": 0.95,
            "providerPlaceType": "address",
            "providerCandidates": [
                {
                    "center": [-111.66, 40.23],
                    "place_name": "Normalized provider label",
                    "relevance": 0.95,
                }
            ],
        }


def source_row(*, location: str = "123 S 500 WEST ST; LOCATION NOTE", mode: str = "Bicycle"):
    return {
        "incident_id": "incident-1",
        "observed_at": datetime(2025, 1, 3, 8, 30),
        "location_raw": location,
        "mode_raw": mode,
        "unused_column": None,
        "source_sheet": "Sheet 1",
        "source_table": "Table 1",
        "source_row": 7,
    }


class PoliceDatastoreTests(unittest.TestCase):
    def test_excel_headers_map_by_name_and_preserve_extra_cells(self) -> None:
        headers = ["Type:", "Address:", "Case Number:", "Date of Report:", "Future detail"]
        mapping = _police_column_mapping(headers)
        observed_at = datetime(2026, 7, 29, 22, 21)
        row = _source_row_from_values(
            ["Scooter", "W CENTER ST & W INDEPENDENCE AVE", "26PR08232", observed_at, 7],
            headers=headers,
            mapping=mapping,
            sheet_name="Collisions",
            table_name="CollisionTable",
            row_number=32,
            source_format="xlsx",
        )

        self.assertEqual(row["incident_id"], "26PR08232")
        self.assertEqual(row["observed_at"], observed_at)
        self.assertEqual(row["location_raw"], "W CENTER ST & W INDEPENDENCE AVE")
        self.assertEqual(row["mode_raw"], "Scooter")
        self.assertEqual(row["source_cells"][4], 7)
        self.assertEqual(row["source_headers"], headers)
        self.assertEqual(row["source_format"], "xlsx")
        self.assertEqual(row["source_row"], 32)

    def test_excel_header_mapping_rejects_missing_required_column(self) -> None:
        with self.assertRaisesRegex(ValueError, "mode_raw"):
            _police_column_mapping(["Case Number:", "Date of Report:", "Address:"])

    def test_collision_modes_are_normalized_without_losing_combined_type(self) -> None:
        self.assertEqual(normalize_police_mode("e-bike"), "electric-bicycle")
        self.assertEqual(normalize_police_mode("Electric wheelchair"), "mobility-device")
        self.assertEqual(
            normalize_police_mode("Pedestrian & electric scooter"),
            "pedestrian-and-scooter",
        )

    def test_location_normalization_preserves_source_text_and_note(self) -> None:
        value = normalize_police_location("123 S 500 WEST ST; LOCATION NOTE")
        self.assertEqual(value["raw"], "123 S 500 WEST ST; LOCATION NOTE")
        self.assertEqual(value["addressPartRaw"], "123 S 500 WEST ST")
        self.assertEqual(value["noteRaw"], "LOCATION NOTE")
        self.assertEqual(value["normalizedAddress"], "123 S 500 W")
        self.assertEqual(value["geocodeQuery"], "123 S 500 W, Provo, UT")

    def test_repeat_import_is_idempotent_and_keeps_typed_source_cells(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "police.json"
            datastore, summary = merge_police_incident_datastore(
                [source_row()],
                datastore_path=path,
                snapshot_id="snapshot-1",
                retrieved_at=NOW,
                source_current_through="2025-01-03T15:30:00Z",
                workbook_sha256="a" * 64,
                provider_geocoder=FakeProviderGeocoder(),
            )
            first_checksum = sha256_file(path)
            repeated, repeated_summary = merge_police_incident_datastore(
                [source_row()],
                datastore_path=path,
                snapshot_id="snapshot-1",
                retrieved_at=NOW,
                source_current_through="2025-01-03T15:30:00Z",
                workbook_sha256="a" * 64,
                provider_geocoder=FakeProviderGeocoder(),
            )

            self.assertEqual(summary["added"], 1)
            self.assertEqual(repeated_summary["added"], 0)
            self.assertEqual(repeated_summary["updated"], 0)
            self.assertEqual(first_checksum, sha256_file(path))
            self.assertEqual(datastore, repeated)
            record = datastore["records"][0]
            self.assertEqual(record["observedAt"]["local"], "2025-01-03T08:30:00-07:00")
            self.assertEqual(record["observedAt"]["utc"], "2025-01-03T15:30:00Z")
            self.assertEqual(record["sourceVersions"][0]["cells"][1], {
                "type": "datetime",
                "value": "2025-01-03T08:30:00",
            })
            self.assertEqual(record["sourceVersions"][0]["cells"][4], {
                "type": "null",
                "value": None,
            })
            self.assertEqual(record["location"]["raw"], "123 S 500 WEST ST; LOCATION NOTE")
            self.assertEqual(record["location"]["geocoding"]["providerCandidates"][0]["relevance"], 0.95)

    def test_corrected_delivery_keeps_both_source_versions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "police.json"
            merge_police_incident_datastore(
                [source_row()],
                datastore_path=path,
                snapshot_id="snapshot-1",
                retrieved_at=NOW,
                source_current_through="2025-01-03T15:30:00Z",
                workbook_sha256="a" * 64,
                provider_geocoder=FakeProviderGeocoder(),
            )
            corrected, summary = merge_police_incident_datastore(
                [source_row(location="125 S 500 WEST ST", mode="Electric Bicycle")],
                datastore_path=path,
                snapshot_id="snapshot-2",
                retrieved_at=datetime(2026, 8, 13, 18, 30, tzinfo=timezone.utc),
                source_current_through="2025-01-03T15:30:00Z",
                workbook_sha256="b" * 64,
                provider_geocoder=FakeProviderGeocoder(),
            )

            record = corrected["records"][0]
            self.assertEqual(summary["updated"], 1)
            self.assertTrue(record["hasSourceConflict"])
            self.assertEqual(len(record["sourceVersions"]), 2)
            self.assertEqual(record["location"]["raw"], "125 S 500 WEST ST")
            self.assertEqual(
                record["sourceVersions"][0]["cells"][2]["value"],
                "123 S 500 WEST ST; LOCATION NOTE",
            )
            self.assertEqual(record["mode"]["category"], "electric-bicycle")
            self.assertEqual(corrected["counts"]["sourceConflicts"], 1)

    def test_new_delivery_of_unchanged_record_adds_provenance_without_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "police.json"
            first_row = source_row()
            first_row["source_cells"] = [
                first_row["incident_id"],
                first_row["observed_at"],
                first_row["location_raw"],
                first_row["mode_raw"],
                first_row["unused_column"],
                "future source detail",
            ]
            merge_police_incident_datastore(
                [first_row],
                datastore_path=path,
                snapshot_id="snapshot-1",
                retrieved_at=NOW,
                source_current_through="2025-01-03T15:30:00Z",
                workbook_sha256="a" * 64,
                provider_geocoder=FakeProviderGeocoder(),
            )
            second, summary = merge_police_incident_datastore(
                [first_row],
                datastore_path=path,
                snapshot_id="snapshot-2",
                retrieved_at=datetime(2026, 8, 13, 18, 30, tzinfo=timezone.utc),
                source_current_through="2025-01-03T15:30:00Z",
                workbook_sha256="b" * 64,
                provider_geocoder=FakeProviderGeocoder(),
            )

            record = second["records"][0]
            self.assertEqual(summary["updated"], 1)
            self.assertFalse(record["hasSourceConflict"])
            self.assertEqual(len(record["sourceVersions"]), 2)
            self.assertEqual(record["sourceVersions"][0]["cells"][5]["value"], "future source detail")


if __name__ == "__main__":
    unittest.main()
