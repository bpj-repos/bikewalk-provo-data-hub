from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .util import write_json


USER_AGENT = "ProvoStreetsWatch-DangerZones/0.1 (admin@provostreets.watch)"


@dataclass(frozen=True)
class LayerDownload:
    metadata: dict[str, Any]
    features: list[dict[str, Any]]
    object_id_field: str
    layer_directory: Path


class ArcGISError(RuntimeError):
    pass


def _request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bytes]:
    response = session.request(method, url, params=params, data=data, timeout=(10, 120))
    response.raise_for_status()
    raw = response.content
    try:
        value = response.json()
    except requests.JSONDecodeError as exc:
        raise ArcGISError(f"ArcGIS returned non-JSON content from {url}") from exc
    if not isinstance(value, dict):
        raise ArcGISError(f"ArcGIS returned an unexpected value from {url}")
    if "error" in value:
        raise ArcGISError(f"ArcGIS error from {url}: {json.dumps(value['error'], sort_keys=True)}")
    return value, raw


def session() -> requests.Session:
    value = requests.Session()
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=0.75,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET", "POST"]),
        respect_retry_after_header=True,
    )
    value.mount("https://", HTTPAdapter(max_retries=retry))
    value.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return value


def fetch_service_metadata(service_url: str, output_path: Path) -> dict[str, Any]:
    with session() as client:
        value, raw = _request_json(client, "GET", service_url, params={"f": "pjson"})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(raw)
    return value


def _oid_field(metadata: dict[str, Any], ids_response: dict[str, Any]) -> str:
    explicit = ids_response.get("objectIdFieldName") or metadata.get("objectIdFieldName")
    if explicit:
        return str(explicit)
    for field in metadata.get("fields", []):
        if field.get("type") == "esriFieldTypeOID":
            return str(field["name"])
    raise ArcGISError(f"Could not identify object ID field for {metadata.get('name', 'layer')}")


def fetch_layer(
    layer_url: str,
    output_dir: Path,
    *,
    where: str = "1=1",
    bbox: tuple[float, float, float, float] | None = None,
    page_size: int = 1000,
    out_fields: str = "*",
) -> LayerDownload:
    output_dir.mkdir(parents=True, exist_ok=True)
    query_url = f"{layer_url.rstrip('/')}/query"
    with session() as client:
        metadata, metadata_raw = _request_json(client, "GET", layer_url, params={"f": "pjson"})
        (output_dir / "layer-metadata.json").write_bytes(metadata_raw)

        id_params: dict[str, Any] = {"f": "json", "where": where, "returnIdsOnly": "true"}
        if bbox:
            id_params.update(
                {
                    "geometry": ",".join(str(value) for value in bbox),
                    "geometryType": "esriGeometryEnvelope",
                    "inSR": "4326",
                    "spatialRel": "esriSpatialRelIntersects",
                }
            )
        write_json(output_dir / "ids-request.json", id_params)
        features: list[dict[str, Any]] = []
        pages_dir = output_dir / "pages"
        pages_dir.mkdir(exist_ok=True)
        requested_ids: set[Any] | None = None
        try:
            ids_response, ids_raw = _request_json(client, "POST", query_url, data=id_params)
        except ArcGISError as exc:
            write_json(
                output_dir / "ids-fallback.json",
                {"reason": str(exc), "strategy": "result-offset-pagination"},
            )
            object_id_field = _oid_field(metadata, {})
            offset = 0
            page_number = 1
            while True:
                page_params = {
                    "f": "geojson",
                    "where": where,
                    "outFields": out_fields,
                    "returnGeometry": "true",
                    "outSR": "4326",
                    "resultOffset": offset,
                    "resultRecordCount": page_size,
                }
                if bbox:
                    page_params.update(
                        {
                            "geometry": ",".join(str(value) for value in bbox),
                            "geometryType": "esriGeometryEnvelope",
                            "inSR": "4326",
                            "spatialRel": "esriSpatialRelIntersects",
                        }
                    )
                write_json(pages_dir / f"page-{page_number:04d}-request.json", page_params)
                page, page_raw = _request_json(client, "POST", query_url, data=page_params)
                (pages_dir / f"page-{page_number:04d}.geojson").write_bytes(page_raw)
                page_features = page.get("features", [])
                if not isinstance(page_features, list):
                    raise ArcGISError(f"Feature page {page_number} did not contain a feature list")
                features.extend(page_features)
                if not page_features or (
                    len(page_features) < page_size and not page.get("exceededTransferLimit", False)
                ):
                    break
                offset += len(page_features)
                page_number += 1
        else:
            (output_dir / "ids-response.json").write_bytes(ids_raw)
            object_id_field = _oid_field(metadata, ids_response)
            object_ids = sorted(set(ids_response.get("objectIds") or []))
            requested_ids = set(object_ids)
            for page_number, offset in enumerate(range(0, len(object_ids), page_size), start=1):
                page_ids = object_ids[offset : offset + page_size]
                page_params = {
                    "f": "geojson",
                    "objectIds": ",".join(str(value) for value in page_ids),
                    "outFields": out_fields,
                    "returnGeometry": "true",
                    "outSR": "4326",
                    "orderByFields": object_id_field,
                }
                write_json(pages_dir / f"page-{page_number:04d}-request.json", page_params)
                page, page_raw = _request_json(client, "POST", query_url, data=page_params)
                (pages_dir / f"page-{page_number:04d}.geojson").write_bytes(page_raw)
                page_features = page.get("features", [])
                if not isinstance(page_features, list):
                    raise ArcGISError(f"Feature page {page_number} did not contain a feature list")
                features.extend(page_features)

    returned_ids = {
        feature.get("properties", {}).get(object_id_field)
        for feature in features
        if isinstance(feature, dict)
    }
    missing = sorted((requested_ids or set()) - returned_ids)
    if missing:
        raise ArcGISError(f"Layer response omitted {len(missing)} requested object IDs")
    return LayerDownload(metadata, features, object_id_field, output_dir)


def field_fingerprint_payload(downloads: Iterable[LayerDownload]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for download in downloads:
        payload.append(
            {
                "layer": download.metadata.get("name"),
                "geometryType": download.metadata.get("geometryType"),
                "fields": [
                    {
                        "name": field.get("name"),
                        "type": field.get("type"),
                        "length": field.get("length"),
                    }
                    for field in download.metadata.get("fields", [])
                ],
            }
        )
    return payload
