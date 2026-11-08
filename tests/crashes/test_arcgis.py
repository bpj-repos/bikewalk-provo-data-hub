from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from danger_zones.arcgis import (
    ArcGISError, LayerDownload, _oid_field, _request_json,
    fetch_layer, fetch_service_metadata, field_fingerprint_payload, session,
)


def response(payload: object, status: int = 200) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result.url = "https://example.test/layer"
    result._content = json.dumps(payload).encode()
    return result


def feature(object_id: int) -> dict:
    return {"type": "Feature", "properties": {"OBJECTID": object_id}, "geometry": None}


class ArcGISDownloadTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.client = Mock(spec=requests.Session)
        factory = patch("danger_zones.arcgis.session").start()
        self.addCleanup(patch.stopall)
        factory.return_value.__enter__.return_value = self.client
        self.metadata = {"name": "Synthetic layer", "objectIdFieldName": "OBJECTID"}

    def test_id_batches_are_sorted_deduplicated_and_completely_reconciled(self) -> None:
        self.client.request.side_effect = [
            response(self.metadata), response({"objectIds": [3, 1, 2, 2]}),
            response({"features": [feature(1), feature(2)]}), response({"features": [feature(3)]}),
        ]
        result = fetch_layer("https://example.test/layer/", self.root, page_size=2, bbox=(0, 1, 2, 3), where="approved=1")
        self.assertEqual(result.features, [feature(1), feature(2), feature(3)])
        self.assertEqual(result.object_id_field, "OBJECTID")
        requests_made = self.client.request.call_args_list
        self.assertEqual(requests_made[1].kwargs["data"]["geometry"], "0,1,2,3")
        self.assertEqual(requests_made[1].kwargs["data"]["where"], "approved=1")
        self.assertEqual([call.kwargs["data"]["objectIds"] for call in requests_made[2:]], ["1,2", "3"])
        self.assertEqual(json.loads((self.root / "pages/page-0002.geojson").read_text())["features"], [feature(3)])

    def test_missing_requested_records_are_rejected(self) -> None:
        self.client.request.side_effect = [response(self.metadata), response({"objectIds": [1, 2]}), response({"features": [feature(1)]})]
        with self.assertRaisesRegex(ArcGISError, "omitted 1 requested object IDs"):
            fetch_layer("https://example.test/layer", self.root)

    def test_empty_layers_do_not_request_nonexistent_pages(self) -> None:
        self.client.request.side_effect = [response(self.metadata), response({"objectIds": []})]
        self.assertEqual(fetch_layer("https://example.test/layer", self.root).features, [])
        self.assertEqual(self.client.request.call_count, 2)

    def test_offset_fallback_continues_past_short_pages_with_transfer_limit(self) -> None:
        metadata = {"fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID"}]}
        self.client.request.side_effect = [response(metadata), response({"error": {"message": "IDs unavailable"}}),
            response({"features": [feature(1), feature(2)]}),
            response({"features": [feature(3)], "exceededTransferLimit": True}),
            response({"features": []})]
        result = fetch_layer("https://example.test/layer", self.root, page_size=2, bbox=(0, 1, 2, 3))
        self.assertEqual(result.features, [feature(1), feature(2), feature(3)])
        pages = self.client.request.call_args_list[2:]
        self.assertEqual([call.kwargs["data"]["resultOffset"] for call in pages], [0, 2, 3])
        self.assertTrue(all(call.kwargs["data"]["geometry"] == "0,1,2,3" for call in pages))
        self.assertEqual(json.loads((self.root / "ids-fallback.json").read_text())["strategy"], "result-offset-pagination")

    def test_malformed_feature_pages_fail_in_both_pagination_modes(self) -> None:
        for ids in [{"objectIds": [1]}, {"error": {"message": "IDs unavailable"}}]:
            with self.subTest(ids=ids):
                self.client.request.side_effect = [response(self.metadata), response(ids), response({"features": {"invalid": True}})]
                with self.assertRaisesRegex(ArcGISError, "did not contain a feature list"):
                    fetch_layer("https://example.test/layer", self.root)

    def test_service_metadata_preserves_the_received_bytes(self) -> None:
        raw = response({"layers": [{"id": 1}]})
        self.client.request.return_value = raw
        output = self.root / "nested/metadata.json"
        self.assertEqual(fetch_service_metadata("https://example.test/service", output), {"layers": [{"id": 1}]})
        self.assertEqual(output.read_bytes(), raw.content)


class ArcGISBoundaryTests(unittest.TestCase):
    def test_provider_errors_and_non_object_payloads_are_not_accepted(self) -> None:
        for payload in [[], None, "unexpected", {"error": {"code": 503}}]:
            with self.subTest(payload=payload):
                client = Mock(spec=requests.Session)
                client.request.return_value = response(payload)
                with self.assertRaises(ArcGISError):
                    _request_json(client, "GET", "https://example.test/layer")
        invalid = response({})
        invalid._content = b"not JSON"
        client.request.return_value = invalid
        with self.assertRaisesRegex(ArcGISError, "non-JSON content"):
            _request_json(client, "GET", "https://example.test/layer")
        client.request.return_value = response({}, 503)
        with self.assertRaises(requests.HTTPError):
            _request_json(client, "GET", "https://example.test/layer")

    def test_requests_have_finite_timeouts_and_return_exact_source_bytes(self) -> None:
        client = Mock(spec=requests.Session)
        raw = response({"ok": True})
        client.request.return_value = raw
        self.assertEqual(_request_json(client, "POST", "https://example.test/layer", data={"f": "json"}), ({"ok": True}, raw.content))
        self.assertEqual(client.request.call_args.kwargs["timeout"], (10, 120))

    def test_object_id_selection_and_fingerprint_exclude_unrelated_metadata(self) -> None:
        self.assertEqual(_oid_field({"objectIdFieldName": "metadata-id"}, {"objectIdFieldName": "response-id"}), "response-id")
        with self.assertRaisesRegex(ArcGISError, "Could not identify object ID"):
            _oid_field({"fields": [{"name": "name", "type": "string"}]}, {})
        metadata = {"name": "Synthetic", "geometryType": "point", "private": "omitted",
                    "fields": [{"name": "OBJECTID", "type": "OID", "length": 4, "alias": "omitted"}]}
        result = field_fingerprint_payload([LayerDownload(metadata, [], "OBJECTID", Path("unused"))])
        self.assertEqual(result, [{"layer": "Synthetic", "geometryType": "point",
                                  "fields": [{"name": "OBJECTID", "type": "OID", "length": 4}]}])

    def test_retries_are_bounded_and_honor_provider_backoff(self) -> None:
        with session() as client:
            retry = client.get_adapter("https://").max_retries
            self.assertEqual(retry.total, 5)
            self.assertTrue(retry.respect_retry_after_header)
            self.assertIn(429, retry.status_forcelist)
            self.assertIn(503, retry.status_forcelist)
