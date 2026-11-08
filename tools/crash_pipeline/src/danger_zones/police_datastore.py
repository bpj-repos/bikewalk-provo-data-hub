from __future__ import annotations

import os
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pyarrow.parquet as pq
import requests
from pyproj import Transformer
from shapely import wkb
from shapely.geometry import Point
from shapely.ops import nearest_points, transform, unary_union

from .config import ANALYSIS_EPSG, PROVO_AREA_BBOX, REPO_ROOT, WGS84_EPSG
from .normalize import normalize_police_mode
from .registry import validate_document
from .util import isoformat, read_json, sha256_json, write_json


LOCAL_TIME_ZONE = ZoneInfo("America/Denver")
DATASTORE_SCHEMA_VERSION = 1
DEFAULT_DATASTORE_RELATIVE_PATH = Path("datastores/provo-police-incidents.json")
MAPTILER_ENDPOINT = "https://api.maptiler.com/geocoding"
MAPTILER_ACCEPTED_TYPES = {"address", "poi", "road", "street"}


def _typed_json_value(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null", "value": None}
    if isinstance(value, datetime):
        return {"type": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"type": "date", "value": value.isoformat()}
    if isinstance(value, bool):
        return {"type": "boolean", "value": value}
    if isinstance(value, int):
        return {"type": "integer", "value": value}
    if isinstance(value, float):
        return {"type": "number", "value": value}
    if isinstance(value, str):
        return {"type": "string", "value": value}
    return {"type": type(value).__name__, "value": str(value)}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def normalize_police_location(value: Any) -> dict[str, Any]:
    raw = _text(value)
    if not raw:
        return {
            "raw": None,
            "addressPartRaw": None,
            "noteRaw": None,
            "normalizedAddress": None,
            "geocodeQuery": None,
        }

    address_part, separator, note = raw.partition(";")
    address_part = " ".join(address_part.strip().split())
    note_raw = note.strip() if separator and note.strip() else None

    normalized = re.sub(
        r"\b(\d+)\s+(NORTH|SOUTH|EAST|WEST)\s+ST\b",
        lambda match: f"{match.group(1)} {match.group(2)[0]}",
        address_part,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"(?:(?<=^)|(?<=&))\s*[NSEW]\s+(\d+\s+[NSEW])\b",
        lambda match: f" {match.group(1)}",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = " ".join(normalized.split()).title().replace(" & ", " and ")
    return {
        "raw": raw,
        "addressPartRaw": address_part,
        "noteRaw": note_raw,
        "normalizedAddress": normalized,
        "geocodeQuery": f"{normalized}, Provo, UT",
    }


def _street_network_label(value: str) -> str:
    label = " ".join(value.upper().strip().split())
    replacements = {
        "NORTH": "N",
        "SOUTH": "S",
        "EAST": "E",
        "WEST": "W",
        "STREET": "ST",
        "DRIVE": "DR",
        "ROAD": "RD",
        "LANE": "LN",
        "AVENUE": "AVE",
        "BOULEVARD": "BLVD",
        "PARKWAY": "PKWY",
    }
    words = [replacements.get(word, word) for word in label.split()]
    if words and words[-1] == "ST" and len(words) >= 2 and words[-2] in {"N", "S", "E", "W"}:
        words.pop()
    return " ".join(words)


class StreetIntersectionGeocoder:
    def __init__(self, street_records_path: Path):
        rows = pq.read_table(street_records_path, columns=["source_snapshot_id", "full_name", "geometry"]).to_pylist()
        self.snapshot_id = rows[0]["source_snapshot_id"] if rows else None
        self._by_name: dict[str, list[Any]] = {}
        for row in rows:
            name = _text(row.get("full_name"))
            geometry = row.get("geometry")
            if not name or not geometry:
                continue
            self._by_name.setdefault(_street_network_label(name), []).append(wkb.loads(geometry))
        self._to_analysis = Transformer.from_crs(WGS84_EPSG, ANALYSIS_EPSG, always_xy=True)
        self._to_wgs84 = Transformer.from_crs(ANALYSIS_EPSG, WGS84_EPSG, always_xy=True)

    def geocode(self, address_part: str | None) -> dict[str, Any] | None:
        if not address_part or "&" not in address_part:
            return None
        labels = [_street_network_label(part) for part in address_part.split("&", 1)]
        left = self._by_name.get(labels[0], [])
        right = self._by_name.get(labels[1], [])
        if not left or not right:
            return None
        left_projected = transform(self._to_analysis.transform, unary_union(left))
        right_projected = transform(self._to_analysis.transform, unary_union(right))
        first, second = nearest_points(left_projected, right_projected)
        distance_meters = first.distance(second)
        if distance_meters > 40:
            return None
        midpoint = Point((first.x + second.x) / 2, (first.y + second.y) / 2)
        center = transform(self._to_wgs84.transform, midpoint)
        return {
            "status": "matched",
            "mapEligible": True,
            "method": "provo-street-network-intersection",
            "provider": "Provo Streets",
            "providerLabel": f"{labels[0]} and {labels[1]}",
            "coordinates": {"lat": round(center.y, 7), "lng": round(center.x, 7)},
            "confidence": "high" if distance_meters <= 10 else "medium",
            "matchDistanceMeters": round(distance_meters, 1),
            "streetLabels": labels,
            "streetNetworkSnapshotId": self.snapshot_id,
            "providerCandidates": [],
        }


def _dotenv_value(name: str) -> str | None:
    direct = os.environ.get(name)
    if direct:
        return direct
    for path in (REPO_ROOT / ".env.local", REPO_ROOT / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            if not line.startswith(f"{name}="):
                continue
            value = line.split("=", 1)[1].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            return value or None
    return None


def maptiler_api_key() -> str | None:
    return _dotenv_value("MAPTILER_API_KEY") or _dotenv_value("NEXT_PUBLIC_MAPTILER_API_KEY")


class MapTilerPoliceGeocoder:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ProvoStreetsWatch/owner-police-import"})

    def geocode(self, query: str | None) -> dict[str, Any]:
        if not query:
            return {
                "status": "missing-location",
                "mapEligible": False,
                "method": "maptiler-forward-geocode",
                "provider": "maptiler",
                "providerCandidates": [],
            }
        response = self.session.get(
            f"{MAPTILER_ENDPOINT}/{requests.utils.quote(query, safe='')}.json",
            params={
                "key": self.api_key,
                "language": "en",
                "limit": "5",
                "autocomplete": "false",
                "country": "US",
                "bbox": ",".join(str(item) for item in PROVO_AREA_BBOX),
                "proximity": "-111.6585,40.2338",
            },
            timeout=30,
        )
        response.raise_for_status()
        features = response.json().get("features") or []
        candidates = [feature for feature in features if isinstance(feature, dict)]
        if not candidates:
            return {
                "status": "unmatched",
                "mapEligible": False,
                "method": "maptiler-forward-geocode",
                "provider": "maptiler",
                "query": query,
                "providerCandidates": [],
            }

        selected = candidates[0]
        center = selected.get("center")
        relevance = selected.get("relevance")
        place_type = (selected.get("place_type") or [None])[0]
        inside = bool(
            isinstance(center, list)
            and len(center) >= 2
            and all(isinstance(item, (int, float)) for item in center[:2])
            and PROVO_AREA_BBOX[0] <= center[0] <= PROVO_AREA_BBOX[2]
            and PROVO_AREA_BBOX[1] <= center[1] <= PROVO_AREA_BBOX[3]
        )
        accepted = bool(
            inside
            and place_type in MAPTILER_ACCEPTED_TYPES
            and isinstance(relevance, (int, float))
            and relevance >= 0.7
        )
        return {
            "status": "matched" if accepted else "review-required",
            "mapEligible": accepted,
            "method": "maptiler-forward-geocode",
            "provider": "maptiler",
            "query": query,
            "providerLabel": selected.get("place_name") or selected.get("text"),
            "coordinates": {"lat": center[1], "lng": center[0]} if inside else None,
            "confidence": relevance if isinstance(relevance, (int, float)) else None,
            "providerPlaceType": place_type,
            "providerCandidates": candidates,
        }


def _normalized_datetime(value: Any) -> dict[str, Any]:
    if isinstance(value, date) and not isinstance(value, datetime):
        return {"sourceValue": _typed_json_value(value), "local": None, "utc": None,
                "localDate": value.isoformat(), "localTime": None, "timeZone": "America/Denver",
                "status": "date-only"}
    if not isinstance(value, datetime):
        return {
            "sourceValue": _typed_json_value(value),
            "local": None,
            "utc": None,
            "localDate": None,
            "localTime": None,
            "timeZone": "America/Denver",
            "status": "invalid-or-missing",
        }
    local = value if value.tzinfo else value.replace(tzinfo=LOCAL_TIME_ZONE)
    local = local.astimezone(LOCAL_TIME_ZONE)
    return {
        "sourceValue": _typed_json_value(value),
        "local": local.isoformat(),
        "utc": isoformat(local),
        "localDate": local.date().isoformat(),
        "localTime": local.time().isoformat(),
        "timeZone": "America/Denver",
        "status": "normalized",
    }


def _source_version(
    source: dict[str, Any],
    *,
    snapshot_id: str,
    retrieved_at: datetime,
    workbook_sha256: str,
) -> dict[str, Any]:
    source_cells = source.get("source_cells")
    if not isinstance(source_cells, list):
        source_cells = [
            source.get(field)
            for field in ["incident_id", "observed_at", "location_raw", "mode_raw", "unused_column"]
        ]
    cells = [_typed_json_value(value) for value in source_cells]
    content_hash = sha256_json({"cells": cells})
    content = {
        "snapshotId": snapshot_id,
        "workbookSha256": workbook_sha256,
        "sourceSheet": str(source.get("source_sheet") or ""),
        "sourceTable": str(source.get("source_table") or ""),
        "sourceRow": int(source.get("source_row") or 0),
        "sourceFileName": str(source.get("source_file_name") or ""),
        "sourceFormat": str(source.get("source_format") or ""),
        "sourceHeaders": [str(value) for value in (source.get("source_headers") or [])],
        "cells": cells,
    }
    return {
        "versionHash": sha256_json(
            {
                "workbookSha256": workbook_sha256,
                "sourceSheet": content["sourceSheet"],
                "sourceTable": content["sourceTable"],
                "sourceRow": content["sourceRow"],
                "contentHash": content_hash,
            }
        ),
        "contentHash": content_hash,
        "retrievedAt": isoformat(retrieved_at),
        **content,
    }


def _record_id(source: dict[str, Any], version: dict[str, Any]) -> str:
    incident_id = _text(source.get("incident_id"))
    return (
        f"provo-police-incidents:{incident_id}"
        if incident_id
        else f"provo-police-incidents:source-row:{version['versionHash'][:16]}"
    )


def _normalized_record(
    source: dict[str, Any],
    version: dict[str, Any],
    *,
    existing: dict[str, Any] | None,
    intersection_geocoder: StreetIntersectionGeocoder | None,
    provider_geocoder: MapTilerPoliceGeocoder | None,
) -> dict[str, Any]:
    incident_id = _text(source.get("incident_id"))
    mode_raw = _text(source.get("mode_raw"))
    location = normalize_police_location(source.get("location_raw"))
    previous_geocoding = existing.get("location", {}).get("geocoding") if existing else None
    previous_query = existing.get("location", {}).get("geocodeQuery") if existing else None
    if previous_geocoding and previous_query == location["geocodeQuery"]:
        geocoding = previous_geocoding
    else:
        geocoding = (
            intersection_geocoder.geocode(location["addressPartRaw"])
            if intersection_geocoder
            else None
        )
        if geocoding is None and provider_geocoder:
            geocoding = provider_geocoder.geocode(location["geocodeQuery"])
        if geocoding is None:
            geocoding = {
                "status": "not-geocoded" if location["raw"] else "missing-location",
                "mapEligible": False,
                "method": None,
                "provider": None,
                "providerCandidates": [],
            }

    source_versions = [dict(item) for item in existing.get("sourceVersions", [])] if existing else []
    for item in source_versions:
        if not item.get("contentHash"):
            item["contentHash"] = sha256_json({"cells": item.get("cells", [])})
    if not any(item.get("versionHash") == version["versionHash"] for item in source_versions):
        source_versions.append(version)
    source_versions.sort(key=lambda item: (item.get("retrievedAt") or "", item.get("versionHash") or ""))
    return {
        "id": _record_id(source, version),
        "incidentId": incident_id,
        "observedAt": _normalized_datetime(source.get("observed_at")),
        "location": {**location, "geocoding": geocoding},
        "mode": {
            "raw": mode_raw,
            "category": normalize_police_mode(mode_raw) if mode_raw else None,
            "status": "normalized" if mode_raw else "missing",
        },
        "severity": {"value": None, "availability": "not-provided-by-source"},
        "eventType": {"value": None, "availability": "not-provided-by-source"},
        "latestSourceVersionHash": version["versionHash"],
        "sourceVersions": source_versions,
        "hasSourceConflict": len({item["contentHash"] for item in source_versions}) > 1,
    }


def _counts(records: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(record["location"]["geocoding"]["status"] for record in records)
    modes = Counter(record["mode"]["category"] or "missing" for record in records)
    return {
        "records": len(records),
        "mapEligible": sum(bool(record["location"]["geocoding"].get("mapEligible")) for record in records),
        "locationStatuses": dict(sorted(statuses.items())),
        "modeCategories": dict(sorted(modes.items())),
        "sourceConflicts": sum(bool(record.get("hasSourceConflict")) for record in records),
    }


def merge_police_incident_datastore(
    source_rows: list[dict[str, Any]],
    *,
    datastore_path: Path,
    snapshot_id: str,
    retrieved_at: datetime,
    source_current_through: str | None,
    workbook_sha256: str,
    source_file_name: str | None = None,
    source_format: str | None = None,
    intersection_geocoder: StreetIntersectionGeocoder | None = None,
    provider_geocoder: MapTilerPoliceGeocoder | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    existing_store = read_json(datastore_path) if datastore_path.is_file() else None
    if existing_store and existing_store.get("schemaVersion") != DATASTORE_SCHEMA_VERSION:
        raise ValueError(f"Unsupported police datastore schema: {existing_store.get('schemaVersion')}")
    existing_records = {record["id"]: record for record in (existing_store or {}).get("records", [])}
    records_by_id = dict(existing_records)
    added = 0
    updated = 0

    for source in source_rows:
        version = _source_version(
            source,
            snapshot_id=snapshot_id,
            retrieved_at=retrieved_at,
            workbook_sha256=workbook_sha256,
        )
        record_id = _record_id(source, version)
        existing = records_by_id.get(record_id)
        record = _normalized_record(
            source,
            version,
            existing=existing,
            intersection_geocoder=intersection_geocoder,
            provider_geocoder=provider_geocoder,
        )
        if existing is None:
            added += 1
        elif sha256_json(existing) != sha256_json(record):
            updated += 1
        records_by_id[record_id] = record

    records = sorted(records_by_id.values(), key=lambda item: (item["observedAt"]["utc"] or "", item["id"]))
    ingestions = list((existing_store or {}).get("ingestions", []))
    if not any(item.get("workbookSha256") == workbook_sha256 for item in ingestions):
        ingestion = {
            "snapshotId": snapshot_id,
            "workbookSha256": workbook_sha256,
            "retrievedAt": isoformat(retrieved_at),
            "sourceCurrentThrough": source_current_through,
            "sourceRows": len(source_rows),
        }
        if source_file_name:
            ingestion["sourceFileName"] = source_file_name
        if source_format:
            ingestion["sourceFormat"] = source_format
        ingestions.append(ingestion)
    ingestions.sort(key=lambda item: (item.get("retrievedAt") or "", item.get("snapshotId") or ""))

    updated_at = max(
        [item.get("retrievedAt") or "" for item in ingestions]
        + [(existing_store or {}).get("updatedAt") or ""],
    )
    datastore = {
        "schemaVersion": DATASTORE_SCHEMA_VERSION,
        "sourceKey": "provo-police-incidents",
        "storageClass": "private-owner-only",
        "updatedAt": updated_at,
        "sourceCurrentThrough": max(
            [item.get("sourceCurrentThrough") or "" for item in ingestions],
            default="",
        ) or None,
        "counts": _counts(records),
        "limitations": [
            "The provider workbook does not include severity or event type.",
            "Provider location text is retained exactly; normalized and matched locations are separate fields.",
            "MapTiler results below the acceptance threshold remain review-required and are not mapped.",
            "This datastore is restricted to the owner workspace and is not a public release artifact.",
        ],
        "ingestions": ingestions,
        "records": records,
    }
    summary = {
        "path": str(datastore_path),
        "sourceRows": len(source_rows),
        "added": added,
        "updated": updated,
        "unchanged": len(source_rows) - added - updated,
        **datastore["counts"],
    }
    schema_errors = validate_document(datastore, "police-incident-datastore.schema.json")
    if schema_errors:
        raise ValueError(f"Police datastore validation failed: {schema_errors}")
    if not existing_store or sha256_json(existing_store) != sha256_json(datastore):
        write_json(datastore_path, datastore)
    return datastore, summary
