from __future__ import annotations

import json
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import pyarrow.parquet as pq
from shapely import from_wkb
from shapely.geometry import shape

from . import __version__
from .arcgis import LayerDownload, fetch_layer, fetch_service_metadata, field_fingerprint_payload
from .config import PROVO_AREA_BBOX
from .contextual import build_trail_road_crossings
from .geoparquet import parquet_geometry_summary, write_geoparquet, write_parquet
from .normalize import (
    AADT_SCHEMA,
    AT_COUNTER_OBSERVATION_SCHEMA,
    AT_COUNTER_SITE_SCHEMA,
    CRASH_SCHEMA,
    CROSSWALK_SCHEMA,
    EXPECTED_SAFETY_SCHEMA,
    FRA_CROSSING_SCHEMA,
    SAFE_ROUTE_FEATURE_SCHEMA,
    SAFE_ROUTE_SCHEMA,
    SAFE_ROUTES_SCHOOL_SCHEMA,
    STREET_SCHEMA,
    STRESS_SCHEMA,
    TRAFFIC_EVENT_SCHEMA,
    TRAFFIC_STUDY_MEASURE_SCHEMA,
    TRAIL_ROAD_CROSSING_SCHEMA,
    TRAIL_SCHEMA,
    TRANSIT_STOP_SCHEMA,
    normalize_aadt,
    normalize_at_counter_observations,
    normalize_at_counter_sites,
    normalize_crashes,
    normalize_crosswalks,
    normalize_expected_safety,
    normalize_fra_crossings,
    normalize_safe_route_features,
    normalize_safe_routes,
    normalize_safe_routes_schools,
    normalize_streets,
    normalize_stress,
    normalize_traffic_events,
    normalize_traffic_study_measures,
    normalize_trails,
    normalize_transit_stops,
)
from .judgment import _local_environment_value
from .registry import source_config, validate_document
from .util import (
    epoch_millis_to_iso,
    isoformat,
    read_json,
    sha256_file,
    sha256_json,
    timestamp_slug,
    utc_now,
    write_json,
)


PROVO_STREETS_URL = (
    "https://gispublicweb.provo.gov/ArcGIS/rest/services/Other/"
    "Streets_for_Imagery/MapServer/0"
)
PROVO_CROSSWALKS_URL = (
    "https://gispublicweb.provo.gov/ArcGIS/rest/services/Public_Works/"
    "Crosswalks/MapServer/1"
)
FRA_GRADE_CROSSINGS_URL = (
    "https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/"
    "NTAD_Railroad_Grade_Crossings/FeatureServer/0"
)
UTA_TRANSIT_STOPS_URL = (
    "https://maps.rideuta.com/server/rest/services/Hosted/"
    "UTA_Stops_and_Most_Recent_Ridership/FeatureServer/0"
)
PROVO_TRAILS_URL = (
    "https://gispublicweb.provo.gov/ArcGIS/rest/services/Recreation/"
    "ParksTrails/FeatureServer/1"
)
UDOT_TRAFFIC_EVENTS_URL = "https://www.udottraffic.utah.gov/api/v2/get/event"
UDOT_CRASHES_URL = (
    "https://maps.udot.utah.gov/central/rest/services/TrafficAndSafety/"
    "Crash_Locations/MapServer"
)
UGRC_BIKEWAYS_URL = (
    "https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/"
    "Bikeways/FeatureServer/0"
)
UDOT_AT_SAFETY_URL = (
    "https://maps.udot.utah.gov/central/rest/services/TrafficAndSafety/"
    "AT_Intersection_Safety_Data/MapServer"
)
UDOT_AADT_URL = (
    "https://services.arcgis.com/pA2nEVnB6tquxgOW/arcgis/rest/services/"
    "AADT2024_Unrounded/FeatureServer/3"
)
UDOT_AT_COUNTER_SITES_URL = (
    "https://services.arcgis.com/pA2nEVnB6tquxgOW/arcgis/rest/services/"
    "EcoCounterSites/FeatureServer/8"
)
UDOT_AT_COUNTER_OBSERVATIONS_URL = (
    "https://services.arcgis.com/pA2nEVnB6tquxgOW/arcgis/rest/services/"
    "Transit_and_Trails_Counter_Summary/FeatureServer/0"
)
UDOT_SAFE_ROUTES_SCHOOLS_URL = (
    "https://services.arcgis.com/pA2nEVnB6tquxgOW/arcgis/rest/services/"
    "SR2S_Schools_Public_View/FeatureServer/3"
)
UDOT_SAFE_ROUTES_ROUTES_URL = (
    "https://services.arcgis.com/pA2nEVnB6tquxgOW/arcgis/rest/services/"
    "SR2S_Routes_Public_View/FeatureServer/2"
)
UDOT_SAFE_ROUTES_FEATURES_URL = (
    "https://services.arcgis.com/pA2nEVnB6tquxgOW/arcgis/rest/services/"
    "SR2S_Features_Public_View/FeatureServer/1"
)
UDOT_SAFE_ROUTES_WHERE = "NAME_DISTRICT = 'Provo' AND APPROVED = 'Yes'"
UDOT_SAFE_ROUTES_SCHOOL_FIELDS = ",".join(
    [
        "OBJECTID",
        "ID_SCHOOL",
        "NAME_SCHOOL",
        "ADDRESS_SCHOOL",
        "ADDRESS_SCHOOL_2",
        "CITY_SCHOOL",
        "POSTAL_SCHOOL",
        "NAME_DISTRICT",
        "APPROVAL_DATE",
        "GlobalID",
        "APPROVED",
    ]
)
UDOT_SAFE_ROUTES_ROUTE_FIELDS = ",".join(
    [
        "OBJECTID_12_13_14",
        "ID_SCHOOL",
        "NAME_SCHOOL",
        "ADDRESS_SCHOOL",
        "ADDRESS_SCHOOL_2",
        "CITY_SCHOOL",
        "POSTAL_SCHOOL",
        "NAME_DISTRICT",
        "NAME_REGION",
        "APPROVAL_DATE",
        "GlobalID",
        "APPROVED",
    ]
)
UDOT_SAFE_ROUTES_FEATURE_FIELDS = ",".join(
    [
        "OBJECTID_1",
        "FEATURE_TYPE",
        "ID_SCHOOL",
        "NAME_SCHOOL",
        "ADDRESS_SCHOOL",
        "ADDRESS_SCHOOL_2",
        "CITY_SCHOOL",
        "POSTAL_SCHOOL",
        "NAME_DISTRICT",
        "NAME_REGION",
        "APPROVAL_DATE",
        "GlobalID",
        "APPROVED",
    ]
)
PROVO_700_EAST_STUDY_URL = "https://www.provo.gov/DocumentCenter/View/5247"
PROVO_700_EAST_EXTRACTION = (
    Path(__file__).resolve().parents[2] / "traffic_studies" / "700-east-2025.json"
)


def _feature_extent(features: list[dict[str, Any]]) -> list[float] | None:
    bounds: list[tuple[float, float, float, float]] = []
    for feature in features:
        geometry = feature.get("geometry")
        if not geometry:
            continue
        try:
            bounds.append(shape(geometry).bounds)
        except Exception:
            continue
    if not bounds:
        return None
    return [
        min(item[0] for item in bounds),
        min(item[1] for item in bounds),
        max(item[2] for item in bounds),
        max(item[3] for item in bounds),
    ]


def _feature_content_fingerprint(
    features: list[dict[str, Any]],
    schema_fingerprint: str,
    *,
    partition: str | None = None,
) -> str:
    canonical = sorted(
        features,
        key=lambda feature: json_sort_key(feature),
    )
    return sha256_json(
        {
            "partition": partition,
            "schemaFingerprint": schema_fingerprint,
            "features": canonical,
        }
    )


def json_sort_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _snapshot_file_entries(snapshot_dir: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(item for item in snapshot_dir.rglob("*") if item.is_file()):
        relative = str(path.relative_to(snapshot_dir))
        if relative.endswith("-request.json"):
            role = "request"
        elif "metadata" in relative:
            role = "provider-metadata"
        else:
            role = "provider-response"
        entries.append(
            {
                "path": relative,
                "role": role,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return entries


def _finalize_raw_snapshot(
    *,
    data_root: Path,
    source_key: str,
    staging_raw: Path,
    retrieved_at: datetime,
    retrieval_completed_at: datetime,
    source_current_through: str | None,
    source_crs: str | None,
    record_count: int,
    schema_fingerprint: str,
    content_fingerprint: str,
    extent: list[float] | None,
    warnings: list[str],
) -> tuple[str, Path, dict[str, Any], bool]:
    # Raw responses retain their own checksums in the manifest. Snapshot identity
    # uses canonical records so provider response ordering does not create a
    # duplicate normalized dataset.
    snapshot_id = f"{source_key}-{content_fingerprint[:16]}"
    snapshot_root = data_root / "sources" / source_key / "snapshots"
    existing_matches = list(snapshot_root.glob(f"*/{snapshot_id}"))
    if len(existing_matches) > 1:
        raise ValueError(f"Found duplicate raw snapshot directories for {snapshot_id}")
    snapshot_dir = (
        existing_matches[0]
        if existing_matches
        else snapshot_root / timestamp_slug(retrieved_at) / snapshot_id
    )
    existing = bool(existing_matches)
    if existing:
        shutil.rmtree(staging_raw.parent, ignore_errors=True)
    else:
        snapshot_dir.parent.mkdir(parents=True, exist_ok=True)
        staging_raw.replace(snapshot_dir)
        shutil.rmtree(staging_raw.parent, ignore_errors=True)

    config = source_config(source_key)
    manifest_path = data_root / "manifests" / "sources" / source_key / f"{snapshot_id}.json"
    if existing and manifest_path.exists():
        return snapshot_id, snapshot_dir, read_json(manifest_path), True

    manifest = {
        "schemaVersion": 1,
        "snapshotId": snapshot_id,
        "sourceKey": source_key,
        "retrievedAt": isoformat(retrieved_at),
        "retrievalCompletedAt": isoformat(retrieval_completed_at),
        "sourceCurrentThrough": source_current_through,
        "accessClass": config["accessClass"],
        "sourceCrs": source_crs,
        "recordCount": record_count,
        "schemaFingerprint": schema_fingerprint,
        "geographicExtent": extent,
        "files": _snapshot_file_entries(snapshot_dir),
        "warnings": warnings,
    }
    errors = validate_document(manifest, "snapshot-manifest.schema.json")
    if errors:
        raise ValueError("Invalid snapshot manifest:\n" + "\n".join(errors))
    if not manifest_path.exists():
        write_json(manifest_path, manifest)
    return snapshot_id, snapshot_dir, manifest, existing


def _artifact_entry(path: Path, data_root: Path, rows: int) -> dict[str, Any]:
    return {"path": str(path.relative_to(data_root)), "rows": rows, "sha256": sha256_file(path)}


def _write_run_report(
    *,
    data_root: Path,
    source_key: str,
    snapshot_id: str,
    started_at: datetime,
    raw_count: int,
    normalized_count: int,
    rejected_count: int,
    artifacts: list[dict[str, Any]],
    checks: list[dict[str, str]],
    warnings: list[str],
    reused: bool,
) -> dict[str, Any]:
    completed_at = utc_now()
    run_id = f"{source_key}-{timestamp_slug(started_at)}-{snapshot_id[-8:]}"
    report = {
        "schemaVersion": 1,
        "runId": run_id,
        "sourceKey": source_key,
        "snapshotId": snapshot_id,
        "startedAt": isoformat(started_at),
        "completedAt": isoformat(completed_at),
        "importerVersion": __version__,
        "status": "reused" if reused else "accepted",
        "rawRecordCount": raw_count,
        "normalizedRecordCount": normalized_count,
        "rejectedRecordCount": rejected_count,
        "normalizedArtifacts": artifacts,
        "checks": checks,
        "warnings": warnings,
    }
    errors = validate_document(report, "run-report.schema.json")
    if errors:
        raise ValueError("Invalid run report:\n" + "\n".join(errors))
    write_json(data_root / "runs" / f"{run_id}.json", report)
    return report


def _arcgis_context_import(
    *,
    data_root: Path,
    source_key: str,
    layer_url: str,
    where: str,
    normalizer: Any,
    schema: Any,
    geometry_types: list[str],
    filename: str,
    warnings: list[str],
    out_fields: str = "*",
) -> dict[str, Any]:
    started_at = utc_now()
    staging = data_root / ".staging" / f"{source_key}-{timestamp_slug(started_at)}"
    raw = staging / "raw"
    download = fetch_layer(layer_url, raw / "layer", where=where, out_fields=out_fields)
    completed_at = utc_now()
    extent = _feature_extent(download.features)
    schema_fingerprint = sha256_json(field_fingerprint_payload([download]))
    content_fingerprint = _feature_content_fingerprint(download.features, schema_fingerprint)
    editing_date = (download.metadata.get("editingInfo") or {}).get("lastEditDate")
    source_current_through = epoch_millis_to_iso(editing_date)
    if not source_current_through:
        record_edit_dates = [
            epoch_millis_to_iso((feature.get("properties") or {}).get("last_edited_date"))
            for feature in download.features
        ]
        record_edit_dates = [value for value in record_edit_dates if value]
        source_current_through = max(record_edit_dates) if record_edit_dates else None
    snapshot_id, _, manifest, raw_reused = _finalize_raw_snapshot(
        data_root=data_root,
        source_key=source_key,
        staging_raw=raw,
        retrieved_at=started_at,
        retrieval_completed_at=completed_at,
        source_current_through=source_current_through,
        source_crs="Provider feature layer queried as EPSG:4326",
        record_count=len(download.features),
        schema_fingerprint=schema_fingerprint,
        content_fingerprint=content_fingerprint,
        extent=extent,
        warnings=warnings,
    )
    rows, rejected = normalizer(
        download.features, snapshot_id=snapshot_id, retrieved_at=started_at
    )
    output_path = data_root / "normalized" / source_key / "v1" / snapshot_id / filename
    normalized_reused = output_path.exists()
    if not normalized_reused:
        write_geoparquet(
            output_path,
            rows,
            schema,
            geometry_types=geometry_types,
            bbox=extent,
        )
    summary = parquet_geometry_summary(output_path)
    checks = [
        {
            "name": "record-reconciliation",
            "status": "passed" if len(rows) + len(rejected) == len(download.features) else "failed",
            "detail": f"{len(rows)} normalized, {len(rejected)} rejected, {len(download.features)} raw",
        },
        {
            "name": "geometry-validity",
            "status": "passed" if summary["invalidGeometryCount"] == 0 else "failed",
            "detail": f"{summary['invalidGeometryCount']} invalid geometries",
        },
        {
            "name": "source-record-presence",
            "status": "passed" if rows else "failed",
            "detail": f"{len(rows)} usable source records",
        },
    ]
    if any(check["status"] == "failed" for check in checks):
        raise ValueError(f"{source_key} validation failed: {checks}")
    report = _write_run_report(
        data_root=data_root,
        source_key=source_key,
        snapshot_id=snapshot_id,
        started_at=started_at,
        raw_count=manifest["recordCount"],
        normalized_count=len(rows),
        rejected_count=len(rejected),
        artifacts=[_artifact_entry(output_path, data_root, len(rows))],
        checks=checks,
        warnings=warnings,
        reused=raw_reused and normalized_reused,
    )
    return {"manifest": manifest, "report": report, "normalizedPath": output_path}


def import_provo_crosswalks(data_root: Path) -> dict[str, Any]:
    return _arcgis_context_import(
        data_root=data_root,
        source_key="provo-crosswalks",
        layer_url=PROVO_CROSSWALKS_URL,
        where="1=1",
        normalizer=normalize_crosswalks,
        schema=CROSSWALK_SCHEMA,
        geometry_types=["LineString", "MultiLineString"],
        filename="crosswalks.parquet",
        out_fields=(
            "OBJECTID,GlobalID,Type,EAST_WEST_STREET,NORTH_SOUTH_STREET,"
            "INTERSECTION_SIDE,created_date,last_edited_date"
        ),
        warnings=[
            "Crosswalk inventory is physical context. Its presence does not establish safety, and absence does not establish danger.",
            "Provider editor usernames are not requested or retained.",
        ],
    )


def import_fra_grade_crossings(data_root: Path) -> dict[str, Any]:
    return _arcgis_context_import(
        data_root=data_root,
        source_key="fra-grade-crossings",
        layer_url=FRA_GRADE_CROSSINGS_URL,
        where="UPPER(CITYNAME) = 'PROVO' AND STATEAB = 'UT'",
        normalizer=normalize_fra_crossings,
        schema=FRA_CROSSING_SCHEMA,
        geometry_types=["Point"],
        filename="crossings.parquet",
        out_fields=(
            "OBJECTID,CROSSING,EFFDATE,RAILROAD,RRDIV,RRSUBDIV,HIGHWAY,STREET,"
            "TYPEXING,POSXING,WHISTBAN,INV_LINK,ACC_LINK,DAYTHRU,NGHTTHRU,"
            "MAINTRK,SIDINGTRK,YARDTRK,TRANSITTRK,INDUSTRYTR,OTHRTRK,WDCODE,"
            "REVISIONDA,LASTUPDATE,AADT,AADTYEAR,COUNTYNAME,CITYNAME,STATEAB"
        ),
        warnings=[
            "The inventory includes at-grade and grade-separated records; crossing position must be read before interpretation.",
            "Warning controls and train counts are context and do not independently establish active transportation danger.",
            "Railroad and police contact fields are not requested or retained.",
        ],
    )


def import_uta_transit_stops(data_root: Path) -> dict[str, Any]:
    return _arcgis_context_import(
        data_root=data_root,
        source_key="uta-transit-stops",
        layer_url=UTA_TRANSIT_STOPS_URL,
        where="UPPER(city) = 'PROVO'",
        normalizer=normalize_transit_stops,
        schema=TRANSIT_STOP_SCHEMA,
        geometry_types=["Point"],
        filename="stops.parquet",
        warnings=[
            "Stops and ridership describe transit activity, not unsafe conditions.",
            "Major transfer points are an explicit display grouping: rail stations, bus bays, stops serving multiple listed routes, or stops with at least 500 average weekday boardings plus alightings.",
            "Provider ridership values may reflect a different update schedule than stop geometry.",
        ],
    )


def import_provo_trails(data_root: Path) -> dict[str, Any]:
    street_path = latest_artifact(data_root, "provo-streets")
    street_rows = pq.read_table(street_path).to_pylist()
    started_at = utc_now()
    staging = data_root / ".staging" / f"provo-trails-{timestamp_slug(started_at)}"
    raw = staging / "raw"
    download = fetch_layer(
        PROVO_TRAILS_URL,
        raw / "layer",
        out_fields="OBJECTID,PATHID,PATH_NAME,PATH_TYPE,SURFACE,WIDTH_FT,OWNER,OWNERTYPE",
    )
    completed_at = utc_now()
    schema_fingerprint = sha256_json(field_fingerprint_payload([download]))
    content_fingerprint = sha256_json(
        {
            "trailContent": _feature_content_fingerprint(download.features, schema_fingerprint),
            "streetNetworkSnapshotId": street_path.parent.name,
        }
    )
    warnings = [
        "Trail-road points are geometry-only screening candidates, not verified at-grade crossings.",
        "Line overlaps are excluded. Bridge, tunnel, signal, curb-ramp, and crossing-control conditions require verification.",
        f"Candidates use Provo street network snapshot {street_path.parent.name}.",
    ]
    snapshot_id, _, manifest, raw_reused = _finalize_raw_snapshot(
        data_root=data_root,
        source_key="provo-trails",
        staging_raw=raw,
        retrieved_at=started_at,
        retrieval_completed_at=completed_at,
        source_current_through=None,
        source_crs="Provider trail layer and Provo streets queried as EPSG:4326; intersections computed in EPSG:26912",
        record_count=len(download.features),
        schema_fingerprint=schema_fingerprint,
        content_fingerprint=content_fingerprint,
        extent=_feature_extent(download.features),
        warnings=warnings,
    )
    trail_rows, rejected = normalize_trails(
        download.features, snapshot_id=snapshot_id, retrieved_at=started_at
    )
    crossing_rows = build_trail_road_crossings(
        trail_rows,
        street_rows,
        snapshot_id=snapshot_id,
        retrieved_at=started_at,
    )
    output_dir = data_root / "normalized" / "provo-trails" / "v1" / snapshot_id
    trails_path = output_dir / "trails.parquet"
    crossings_path = output_dir / "road-crossings.parquet"
    normalized_reused = trails_path.exists() and crossings_path.exists()
    if not trails_path.exists():
        write_geoparquet(
            trails_path,
            trail_rows,
            TRAIL_SCHEMA,
            geometry_types=["LineString", "MultiLineString"],
            bbox=_feature_extent(download.features),
        )
    if not crossings_path.exists():
        crossing_extent = None
        if crossing_rows:
            geometries = [from_wkb(row["geometry"]) for row in crossing_rows]
            crossing_extent = [
                min(item.x for item in geometries),
                min(item.y for item in geometries),
                max(item.x for item in geometries),
                max(item.y for item in geometries),
            ]
        write_geoparquet(
            crossings_path,
            crossing_rows,
            TRAIL_ROAD_CROSSING_SCHEMA,
            geometry_types=["Point"],
            bbox=crossing_extent,
        )
    trail_summary = parquet_geometry_summary(trails_path)
    crossing_summary = parquet_geometry_summary(crossings_path)
    checks = [
        {
            "name": "record-reconciliation",
            "status": "passed" if len(trail_rows) + len(rejected) == len(download.features) else "failed",
            "detail": f"{len(trail_rows)} normalized, {len(rejected)} rejected, {len(download.features)} raw trails",
        },
        {
            "name": "geometry-validity",
            "status": "passed" if trail_summary["invalidGeometryCount"] + crossing_summary["invalidGeometryCount"] == 0 else "failed",
            "detail": f"{trail_summary['invalidGeometryCount'] + crossing_summary['invalidGeometryCount']} invalid geometries",
        },
        {
            "name": "candidate-grade-status",
            "status": "passed" if all(row["grade_separation_status"] == "unknown-requires-verification" for row in crossing_rows) else "failed",
            "detail": f"{len(crossing_rows)} candidates retain unknown grade-separation status",
        },
    ]
    if any(check["status"] == "failed" for check in checks):
        raise ValueError(f"provo-trails validation failed: {checks}")
    artifacts = [
        _artifact_entry(trails_path, data_root, len(trail_rows)),
        _artifact_entry(crossings_path, data_root, len(crossing_rows)),
    ]
    report = _write_run_report(
        data_root=data_root,
        source_key="provo-trails",
        snapshot_id=snapshot_id,
        started_at=started_at,
        raw_count=manifest["recordCount"],
        normalized_count=len(trail_rows) + len(crossing_rows),
        rejected_count=len(rejected),
        artifacts=artifacts,
        checks=checks,
        warnings=warnings,
        reused=raw_reused and normalized_reused,
    )
    return {"manifest": manifest, "report": report, "trailPath": trails_path, "crossingPath": crossings_path}


def _event_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ["Events", "events", "Items", "items"]:
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, dict)]
    return []


def _event_xml(raw: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(raw)
    events = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() != "event":
            continue
        events.append({child.tag.rsplit("}", 1)[-1]: child.text for child in element})
    return events


def import_udot_traffic_events(data_root: Path) -> dict[str, Any]:
    api_key = _local_environment_value("UDOT_TRAFFIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "UDOT_TRAFFIC_API_KEY is required for the official temporary construction and closure feed. "
            "Request a developer key at https://udottraffic.utah.gov/developers/doc and place it in .env.local."
        )
    started_at = utc_now()
    staging = data_root / ".staging" / f"udot-traffic-events-{timestamp_slug(started_at)}"
    raw_dir = staging / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    write_json(raw_dir / "events-request.json", {"endpoint": UDOT_TRAFFIC_EVENTS_URL, "credential": "UDOT_TRAFFIC_API_KEY"})
    response = requests.get(
        UDOT_TRAFFIC_EVENTS_URL,
        params={"key": api_key, "format": "json"},
        headers={"Accept": "application/json", "User-Agent": "ProvoStreetsWatch-DangerZones/0.1 (admin@provostreets.watch)"},
        timeout=(10, 120),
    )
    response.raise_for_status()
    (raw_dir / "events-response.bin").write_bytes(response.content)
    try:
        all_events = _event_list(response.json())
    except requests.JSONDecodeError:
        all_events = _event_xml(response.content)
    min_x, min_y, max_x, max_y = PROVO_AREA_BBOX
    selected = []
    for event in all_events:
        try:
            latitude = float(event.get("Latitude") or event.get("latitude"))
            longitude = float(event.get("Longitude") or event.get("longitude"))
        except (TypeError, ValueError):
            continue
        category = str(event.get("Category") or event.get("category") or "").lower()
        event_type = str(event.get("EventType") or event.get("eventType") or "").lower()
        if min_x <= longitude <= max_x and min_y <= latitude <= max_y and (
            "construction" in category or "closure" in category or event_type in {"roadwork", "closures"}
        ):
            selected.append(event)
    completed_at = utc_now()
    schema_fingerprint = sha256_json({"format": "UDOT Traffic API v2 event", "normalizedVersion": 1})
    content_fingerprint = sha256_json({"schemaFingerprint": schema_fingerprint, "events": sorted(selected, key=json_sort_key)})
    updated_values = [
        event.get("LastUpdated") or event.get("lastUpdated")
        for event in selected
        if event.get("LastUpdated") or event.get("lastUpdated")
    ]
    warnings = [
        "This is a changing operational feed. Expired events remain only in versioned local snapshots.",
        "Descriptions, comments, contacts, and detour narratives are not retained in normalized public-context artifacts.",
        "Construction and closure presence is context and does not independently establish active transportation danger.",
    ]
    snapshot_id, _, manifest, raw_reused = _finalize_raw_snapshot(
        data_root=data_root,
        source_key="udot-traffic-events",
        staging_raw=raw_dir,
        retrieved_at=started_at,
        retrieval_completed_at=completed_at,
        source_current_through=max(map(str, updated_values)) if updated_values else isoformat(completed_at),
        source_crs="Provider coordinates interpreted as EPSG:4326",
        record_count=len(selected),
        schema_fingerprint=schema_fingerprint,
        content_fingerprint=content_fingerprint,
        extent=list(PROVO_AREA_BBOX),
        warnings=warnings,
    )
    rows, rejected = normalize_traffic_events(selected, snapshot_id=snapshot_id, retrieved_at=started_at)
    output_path = data_root / "normalized" / "udot-traffic-events" / "v1" / snapshot_id / "events.parquet"
    normalized_reused = output_path.exists()
    if not normalized_reused:
        write_geoparquet(output_path, rows, TRAFFIC_EVENT_SCHEMA, geometry_types=["Point"], bbox=list(PROVO_AREA_BBOX))
    summary = parquet_geometry_summary(output_path)
    checks = [
        {
            "name": "record-reconciliation",
            "status": "passed" if len(rows) + len(rejected) == len(selected) else "failed",
            "detail": f"{len(rows)} normalized, {len(rejected)} rejected, {len(selected)} selected",
        },
        {
            "name": "geometry-validity",
            "status": "passed" if summary["invalidGeometryCount"] == 0 else "failed",
            "detail": f"{summary['invalidGeometryCount']} invalid geometries",
        },
    ]
    if any(check["status"] == "failed" for check in checks):
        raise ValueError(f"udot-traffic-events validation failed: {checks}")
    report = _write_run_report(
        data_root=data_root,
        source_key="udot-traffic-events",
        snapshot_id=snapshot_id,
        started_at=started_at,
        raw_count=manifest["recordCount"],
        normalized_count=len(rows),
        rejected_count=len(rejected),
        artifacts=[_artifact_entry(output_path, data_root, len(rows))],
        checks=checks,
        warnings=warnings,
        reused=raw_reused and normalized_reused,
    )
    return {"manifest": manifest, "report": report, "normalizedPath": output_path}


def import_provo_streets(data_root: Path) -> dict[str, Any]:
    started_at = utc_now()
    staging = data_root / ".staging" / f"provo-streets-{timestamp_slug(started_at)}"
    raw = staging / "raw"
    download = fetch_layer(PROVO_STREETS_URL, raw / "layer")
    completed_at = utc_now()
    extent = _feature_extent(download.features)
    schema_fingerprint = sha256_json(field_fingerprint_payload([download]))
    content_fingerprint = _feature_content_fingerprint(
        download.features, schema_fingerprint
    )
    snapshot_id, _, manifest, raw_reused = _finalize_raw_snapshot(
        data_root=data_root,
        source_key="provo-streets",
        staging_raw=raw,
        retrieved_at=started_at,
        retrieval_completed_at=completed_at,
        source_current_through=None,
        source_crs="EPSG:3566 provider geometry, queried as EPSG:4326",
        record_count=len(download.features),
        schema_fingerprint=schema_fingerprint,
        content_fingerprint=content_fingerprint,
        extent=extent,
        warnings=[],
    )
    rows, rejected = normalize_streets(
        download.features, snapshot_id=snapshot_id, retrieved_at=started_at
    )
    output_path = data_root / "normalized" / "provo-streets" / "v1" / snapshot_id / "records.parquet"
    normalized_reused = output_path.exists()
    if not normalized_reused:
        write_geoparquet(
            output_path,
            rows,
            STREET_SCHEMA,
            geometry_types=["LineString", "MultiLineString"],
            bbox=extent,
        )
    summary = parquet_geometry_summary(output_path)
    checks = [
        {
            "name": "record-reconciliation",
            "status": "passed" if len(rows) + len(rejected) == len(download.features) else "failed",
            "detail": f"{len(rows)} normalized, {len(rejected)} rejected, {len(download.features)} raw",
        },
        {
            "name": "geometry-validity",
            "status": "passed" if summary["invalidGeometryCount"] == 0 else "failed",
            "detail": f"{summary['invalidGeometryCount']} invalid geometries",
        },
        {
            "name": "minimum-network-size",
            "status": "passed" if len(rows) >= 1000 else "failed",
            "detail": f"{len(rows)} street segments",
        },
    ]
    if any(check["status"] == "failed" for check in checks):
        raise ValueError(f"Provo streets validation failed: {checks}")
    artifact = _artifact_entry(output_path, data_root, len(rows))
    report = _write_run_report(
        data_root=data_root,
        source_key="provo-streets",
        snapshot_id=snapshot_id,
        started_at=started_at,
        raw_count=manifest["recordCount"],
        normalized_count=len(rows),
        rejected_count=len(rejected),
        artifacts=[artifact],
        checks=checks,
        warnings=[],
        reused=raw_reused and normalized_reused,
    )
    return {"manifest": manifest, "report": report, "normalizedPath": output_path}


def _crash_layer_year(layer: dict[str, Any]) -> int | None:
    name = str(layer.get("name", ""))
    parts = name.rsplit(" ", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    return int(parts[1])


def import_udot_crashes(data_root: Path) -> dict[str, Any]:
    started_at = utc_now()
    staging = data_root / ".staging" / f"udot-crashes-{timestamp_slug(started_at)}"
    raw = staging / "raw"
    service_metadata = fetch_service_metadata(UDOT_CRASHES_URL, raw / "service-metadata.json")
    layer_pairs = sorted(
        (
            (year, layer)
            for layer in service_metadata.get("layers", [])
            if (year := _crash_layer_year(layer)) is not None
        ),
        key=lambda item: item[0],
    )
    downloads: list[tuple[int, LayerDownload]] = []
    for year, layer in layer_pairs:
        downloads.append(
            (
                year,
                fetch_layer(
                    f"{UDOT_CRASHES_URL}/{layer['id']}",
                    raw / f"layer-{year}",
                    bbox=PROVO_AREA_BBOX,
                ),
            )
        )
    completed_at = utc_now()
    features_by_year = [
        (year, feature)
        for year, download in downloads
        for feature in download.features
    ]
    all_features = [feature for _, feature in features_by_year]
    current_dates = [
        value
        for _, feature in features_by_year
        if (value := (feature.get("properties") or {}).get("CURRENT_AS_OF_DATE")) is not None
    ]
    source_current_through = epoch_millis_to_iso(max(current_dates)) if current_dates else None
    layer_years = [year for year, _ in downloads]
    warnings: list[str] = []
    if datetime.now(timezone.utc).year not in layer_years:
        warnings.append(
            f"The service has no layer for {datetime.now(timezone.utc).year}; newest discovered layer is "
            f"{max(layer_years) if layer_years else 'none'}."
        )
    schema_fingerprint = sha256_json(
        {
            "serviceLayers": [
                {"id": layer.get("id"), "name": layer.get("name")} for _, layer in layer_pairs
            ],
            "fields": field_fingerprint_payload([download for _, download in downloads]),
        }
    )
    content_fingerprint = sha256_json(
        {
            "schemaFingerprint": schema_fingerprint,
            "partitions": [
                {
                    "year": year,
                    "features": sorted(
                        download.features,
                        key=lambda feature: json_sort_key(feature),
                    ),
                }
                for year, download in downloads
            ],
        }
    )
    extent = _feature_extent(all_features)
    snapshot_id, _, manifest, raw_reused = _finalize_raw_snapshot(
        data_root=data_root,
        source_key="udot-crashes",
        staging_raw=raw,
        retrieved_at=started_at,
        retrieval_completed_at=completed_at,
        source_current_through=source_current_through,
        source_crs="EPSG:26912 provider geometry, queried as EPSG:4326",
        record_count=len(features_by_year),
        schema_fingerprint=schema_fingerprint,
        content_fingerprint=content_fingerprint,
        extent=extent,
        warnings=warnings,
    )
    rows, rejected = normalize_crashes(
        features_by_year, snapshot_id=snapshot_id, retrieved_at=started_at
    )
    output_path = data_root / "normalized" / "udot-crashes" / "v1" / snapshot_id / "records.parquet"
    normalized_reused = output_path.exists()
    if not normalized_reused:
        write_geoparquet(
            output_path,
            rows,
            CRASH_SCHEMA,
            geometry_types=["Point"],
            bbox=extent,
        )
    summary = parquet_geometry_summary(output_path)
    crash_ids = [row["crash_id"] for row in rows]
    duplicate_count = len(crash_ids) - len(set(crash_ids))
    active_count = sum(
        1 for row in rows if row["pedestrian_involved"] or row["bicyclist_involved"]
    )
    checks = [
        {
            "name": "record-reconciliation",
            "status": "passed" if len(rows) + len(rejected) == len(features_by_year) else "failed",
            "detail": f"{len(rows)} normalized, {len(rejected)} rejected, {len(features_by_year)} raw",
        },
        {
            "name": "geometry-validity",
            "status": "passed" if summary["invalidGeometryCount"] == 0 else "failed",
            "detail": f"{summary['invalidGeometryCount']} invalid geometries",
        },
        {
            "name": "crash-id-uniqueness",
            "status": "passed" if duplicate_count == 0 else "failed",
            "detail": f"{duplicate_count} duplicate crash IDs across annual layers",
        },
        {
            "name": "active-transportation-presence",
            "status": "passed" if active_count > 0 else "warning",
            "detail": f"{active_count} pedestrian or bicyclist crashes in the query area",
        },
    ]
    if any(check["status"] == "failed" for check in checks):
        raise ValueError(f"UDOT crashes validation failed: {checks}")
    artifact = _artifact_entry(output_path, data_root, len(rows))
    report = _write_run_report(
        data_root=data_root,
        source_key="udot-crashes",
        snapshot_id=snapshot_id,
        started_at=started_at,
        raw_count=manifest["recordCount"],
        normalized_count=len(rows),
        rejected_count=len(rejected),
        artifacts=[artifact],
        checks=checks,
        warnings=warnings,
        reused=raw_reused and normalized_reused,
    )
    return {"manifest": manifest, "report": report, "normalizedPath": output_path}


def import_ugrc_bikeways_lts(data_root: Path) -> dict[str, Any]:
    started_at = utc_now()
    staging = data_root / ".staging" / f"ugrc-bikeways-lts-{timestamp_slug(started_at)}"
    raw = staging / "raw"
    download = fetch_layer(UGRC_BIKEWAYS_URL, raw / "layer", where="CITY = 'Provo'")
    completed_at = utc_now()
    extent = _feature_extent(download.features)
    schema_fingerprint = sha256_json(field_fingerprint_payload([download]))
    content_fingerprint = _feature_content_fingerprint(
        download.features, schema_fingerprint
    )
    editing_date = (download.metadata.get("editingInfo") or {}).get("lastEditDate")
    source_current_through = epoch_millis_to_iso(editing_date)
    warnings = [] if source_current_through else ["The service did not expose a usable last-edit date."]
    snapshot_id, _, manifest, raw_reused = _finalize_raw_snapshot(
        data_root=data_root,
        source_key="ugrc-bikeways-lts",
        staging_raw=raw,
        retrieved_at=started_at,
        retrieval_completed_at=completed_at,
        source_current_through=source_current_through,
        source_crs="Provider feature layer queried as EPSG:4326",
        record_count=len(download.features),
        schema_fingerprint=schema_fingerprint,
        content_fingerprint=content_fingerprint,
        extent=extent,
        warnings=warnings,
    )
    rows, rejected = normalize_stress(
        download.features, snapshot_id=snapshot_id, retrieved_at=started_at
    )
    output_path = (
        data_root / "normalized" / "ugrc-bikeways-lts" / "v1" / snapshot_id / "records.parquet"
    )
    normalized_reused = output_path.exists()
    if not normalized_reused:
        write_geoparquet(
            output_path,
            rows,
            STRESS_SCHEMA,
            geometry_types=["LineString", "MultiLineString"],
            bbox=extent,
        )
    summary = parquet_geometry_summary(output_path)
    with_stress = sum(1 for row in rows if row["lts_score"] is not None)
    checks = [
        {
            "name": "record-reconciliation",
            "status": "passed" if len(rows) + len(rejected) == len(download.features) else "failed",
            "detail": f"{len(rows)} normalized, {len(rejected)} rejected, {len(download.features)} raw",
        },
        {
            "name": "geometry-validity",
            "status": "passed" if summary["invalidGeometryCount"] == 0 else "failed",
            "detail": f"{summary['invalidGeometryCount']} invalid geometries",
        },
        {
            "name": "stress-coverage",
            "status": "passed" if with_stress > 0 else "failed",
            "detail": f"{with_stress} of {len(rows)} records have an LTS score",
        },
    ]
    if any(check["status"] == "failed" for check in checks):
        raise ValueError(f"UGRC bikeways validation failed: {checks}")
    report = _write_run_report(
        data_root=data_root,
        source_key="ugrc-bikeways-lts",
        snapshot_id=snapshot_id,
        started_at=started_at,
        raw_count=manifest["recordCount"],
        normalized_count=len(rows),
        rejected_count=len(rejected),
        artifacts=[_artifact_entry(output_path, data_root, len(rows))],
        checks=checks,
        warnings=warnings,
        reused=raw_reused and normalized_reused,
    )
    return {"manifest": manifest, "report": report, "normalizedPath": output_path}


def import_udot_safe_routes(data_root: Path) -> dict[str, Any]:
    started_at = utc_now()
    staging = data_root / ".staging" / f"udot-safe-routes-to-school-{timestamp_slug(started_at)}"
    raw = staging / "raw"
    downloads = {
        "schools": fetch_layer(
            UDOT_SAFE_ROUTES_SCHOOLS_URL,
            raw / "schools",
            where=UDOT_SAFE_ROUTES_WHERE,
            out_fields=UDOT_SAFE_ROUTES_SCHOOL_FIELDS,
        ),
        "routes": fetch_layer(
            UDOT_SAFE_ROUTES_ROUTES_URL,
            raw / "routes",
            where=UDOT_SAFE_ROUTES_WHERE,
            out_fields=UDOT_SAFE_ROUTES_ROUTE_FIELDS,
        ),
        "features": fetch_layer(
            UDOT_SAFE_ROUTES_FEATURES_URL,
            raw / "features",
            where=UDOT_SAFE_ROUTES_WHERE,
            out_fields=UDOT_SAFE_ROUTES_FEATURE_FIELDS,
        ),
    }
    completed_at = utc_now()
    all_features = [
        feature
        for download in downloads.values()
        for feature in download.features
    ]
    schema_fingerprint = sha256_json(field_fingerprint_payload(downloads.values()))
    content_fingerprint = sha256_json(
        {
            "schemaFingerprint": schema_fingerprint,
            "partitions": [
                {
                    "kind": kind,
                    "features": sorted(download.features, key=json_sort_key),
                }
                for kind, download in sorted(downloads.items())
            ],
        }
    )
    approval_dates = [
        epoch_millis_to_iso(feature.get("properties", {}).get("APPROVAL_DATE"))
        for feature in all_features
    ]
    approval_dates = [value for value in approval_dates if value]
    source_current_through = max(approval_dates) if approval_dates else None
    warnings = [
        "UDOT marks this source as informational and requires field verification before project use.",
        "Approved school routes and mapped plan features are context, not proof that a location is safe or dangerous.",
        "School-zone speed-limit extents are not included in the public Safe Routes export.",
    ]
    orphan_route_count = sum(
        feature.get("properties", {}).get("ID_SCHOOL") is None
        for feature in downloads["routes"].features
    )
    if orphan_route_count:
        warnings.append(
            f"{orphan_route_count} approved route segments have no provider school ID and remain linked by school name."
        )
    missing_geometry_count = sum(not feature.get("geometry") for feature in all_features)
    if missing_geometry_count:
        record_label = "record has" if missing_geometry_count == 1 else "records have"
        action = "is" if missing_geometry_count == 1 else "are"
        warnings.append(
            f"{missing_geometry_count} approved provider {record_label} no geometry and {action} rejected from map layers."
        )
    snapshot_id, _, manifest, raw_reused = _finalize_raw_snapshot(
        data_root=data_root,
        source_key="udot-safe-routes-to-school",
        staging_raw=raw,
        retrieved_at=started_at,
        retrieval_completed_at=completed_at,
        source_current_through=source_current_through,
        source_crs="Provider feature layers queried as EPSG:4326",
        record_count=len(all_features),
        schema_fingerprint=schema_fingerprint,
        content_fingerprint=content_fingerprint,
        extent=_feature_extent(all_features),
        warnings=warnings,
    )

    school_rows, school_rejected = normalize_safe_routes_schools(
        downloads["schools"].features,
        snapshot_id=snapshot_id,
        retrieved_at=started_at,
    )
    route_rows, route_rejected = normalize_safe_routes(
        downloads["routes"].features,
        snapshot_id=snapshot_id,
        retrieved_at=started_at,
    )
    feature_rows, feature_rejected = normalize_safe_route_features(
        downloads["features"].features,
        snapshot_id=snapshot_id,
        retrieved_at=started_at,
    )
    normalized_specs = [
        ("schools.parquet", school_rows, SAFE_ROUTES_SCHOOL_SCHEMA, ["Point"]),
        ("routes.parquet", route_rows, SAFE_ROUTE_SCHEMA, ["LineString", "MultiLineString"]),
        ("features.parquet", feature_rows, SAFE_ROUTE_FEATURE_SCHEMA, ["Point"]),
    ]
    output_directory = (
        data_root
        / "normalized"
        / "udot-safe-routes-to-school"
        / "v1"
        / snapshot_id
    )
    artifacts = []
    normalized_reused = True
    for filename, rows, schema, geometry_types in normalized_specs:
        output_path = output_directory / filename
        existed = output_path.exists()
        normalized_reused = normalized_reused and existed
        if not existed:
            write_geoparquet(
                output_path,
                rows,
                schema,
                geometry_types=geometry_types,
                bbox=_feature_extent(
                    [
                        feature
                        for feature in downloads[filename.removesuffix(".parquet")].features
                    ]
                ),
            )
        artifacts.append(_artifact_entry(output_path, data_root, len(rows)))

    rejected = school_rejected + route_rejected + feature_rejected
    summaries = [parquet_geometry_summary(output_directory / spec[0]) for spec in normalized_specs]
    attributes = [row["attributes"] for rows in [school_rows, route_rows, feature_rows] for row in rows]
    privacy_fields = [
        "PARENT_CONTACT_NAME_SCHOOL",
        "PARENT_CONTACT_PHONE_SCHOOL",
        "PARENT_CONTACT_EMAIL_SCHOOL",
    ]
    checks = [
        {
            "name": "record-reconciliation",
            "status": "passed" if len(school_rows) + len(route_rows) + len(feature_rows) + len(rejected) == len(all_features) else "failed",
            "detail": f"{len(school_rows) + len(route_rows) + len(feature_rows)} normalized, {len(rejected)} rejected, {len(all_features)} raw",
        },
        {
            "name": "geometry-validity",
            "status": "passed" if sum(summary["invalidGeometryCount"] for summary in summaries) == 0 else "failed",
            "detail": f"{sum(summary['invalidGeometryCount'] for summary in summaries)} invalid geometries",
        },
        {
            "name": "approved-provo-only",
            "status": "passed" if all(row["approved"] and row["district"] == "Provo" for rows in [school_rows, route_rows, feature_rows] for row in rows) else "failed",
            "detail": "Every normalized record is approved and assigned to the Provo district.",
        },
        {
            "name": "privacy-fields-excluded",
            "status": "passed" if not any(field in value for value in attributes for field in privacy_fields) else "failed",
            "detail": "School contact names, phone numbers, and email addresses are excluded from normalized attributes.",
        },
        {
            "name": "layer-presence",
            "status": "passed" if school_rows and route_rows and feature_rows else "failed",
            "detail": f"{len(school_rows)} schools, {len(route_rows)} route segments, {len(feature_rows)} mapped features",
        },
    ]
    if any(check["status"] == "failed" for check in checks):
        raise ValueError(f"UDOT Safe Routes validation failed: {checks}")
    report = _write_run_report(
        data_root=data_root,
        source_key="udot-safe-routes-to-school",
        snapshot_id=snapshot_id,
        started_at=started_at,
        raw_count=manifest["recordCount"],
        normalized_count=len(school_rows) + len(route_rows) + len(feature_rows),
        rejected_count=len(rejected),
        artifacts=artifacts,
        checks=checks,
        warnings=warnings,
        reused=raw_reused and normalized_reused,
    )
    return {
        "manifest": manifest,
        "report": report,
        "normalizedPaths": {
            "schools": output_directory / "schools.parquet",
            "routes": output_directory / "routes.parquet",
            "features": output_directory / "features.parquet",
        },
    }


def import_udot_at_safety(data_root: Path) -> dict[str, Any]:
    started_at = utc_now()
    staging = data_root / ".staging" / f"udot-at-safety-{timestamp_slug(started_at)}"
    raw = staging / "raw"
    service_metadata = fetch_service_metadata(UDOT_AT_SAFETY_URL, raw / "service-metadata.json")
    layer_specs = [
        ("signalized-intersection", 1, "sig_pred.CITY = 'Provo'"),
        ("non-signalized-intersection", 2, "jct_pred_table.CITY = 'Provo'"),
        ("roadway-segment", 3, "seg_pred_table.CITY = 'Provo'"),
    ]
    downloads: list[tuple[str, LayerDownload]] = []
    for facility_kind, layer_id, where in layer_specs:
        downloads.append(
            (
                facility_kind,
                fetch_layer(
                    f"{UDOT_AT_SAFETY_URL}/{layer_id}",
                    raw / f"layer-{layer_id}-{facility_kind}",
                    where=where,
                ),
            )
        )
    completed_at = utc_now()
    features_by_kind = [
        (facility_kind, feature)
        for facility_kind, download in downloads
        for feature in download.features
    ]
    all_features = [feature for _, feature in features_by_kind]
    warnings = [
        "The service does not expose a reliable current-through date; retain the documented study vintage."
    ]
    schema_fingerprint = sha256_json(
        {
            "serviceLayers": service_metadata.get("layers", []),
            "fields": field_fingerprint_payload([download for _, download in downloads]),
        }
    )
    content_fingerprint = sha256_json(
        {
            "schemaFingerprint": schema_fingerprint,
            "partitions": [
                {
                    "facilityKind": facility_kind,
                    "features": sorted(
                        download.features,
                        key=lambda feature: json_sort_key(feature),
                    ),
                }
                for facility_kind, download in downloads
            ],
        }
    )
    extent = _feature_extent(all_features)
    snapshot_id, _, manifest, raw_reused = _finalize_raw_snapshot(
        data_root=data_root,
        source_key="udot-at-intersection-safety",
        staging_raw=raw,
        retrieved_at=started_at,
        retrieval_completed_at=completed_at,
        source_current_through=None,
        source_crs="Provider model layers queried as EPSG:4326",
        record_count=len(features_by_kind),
        schema_fingerprint=schema_fingerprint,
        content_fingerprint=content_fingerprint,
        extent=extent,
        warnings=warnings,
    )
    rows, rejected = normalize_expected_safety(
        features_by_kind, snapshot_id=snapshot_id, retrieved_at=started_at
    )
    output_path = (
        data_root
        / "normalized"
        / "udot-at-intersection-safety"
        / "v1"
        / snapshot_id
        / "records.parquet"
    )
    normalized_reused = output_path.exists()
    if not normalized_reused:
        write_geoparquet(
            output_path,
            rows,
            EXPECTED_SAFETY_SCHEMA,
            geometry_types=["Point", "LineString", "MultiLineString"],
            bbox=extent,
        )
    summary = parquet_geometry_summary(output_path)
    with_expected = sum(
        1
        for row in rows
        if any(
            row[field] is not None
            for field in [
                "empirical_bayes_pedestrian_all",
                "empirical_bayes_pedestrian_ksi",
                "empirical_bayes_bicycle_all",
                "empirical_bayes_bicycle_ksi",
            ]
        )
    )
    checks = [
        {
            "name": "record-reconciliation",
            "status": "passed" if len(rows) + len(rejected) == len(features_by_kind) else "failed",
            "detail": f"{len(rows)} normalized, {len(rejected)} rejected, {len(features_by_kind)} raw",
        },
        {
            "name": "geometry-validity",
            "status": "passed" if summary["invalidGeometryCount"] == 0 else "failed",
            "detail": f"{summary['invalidGeometryCount']} invalid geometries",
        },
        {
            "name": "expected-measure-coverage",
            "status": "passed" if with_expected > 0 else "failed",
            "detail": f"{with_expected} of {len(rows)} records have an Empirical Bayes measure",
        },
    ]
    if any(check["status"] == "failed" for check in checks):
        raise ValueError(f"UDOT active transportation safety validation failed: {checks}")
    report = _write_run_report(
        data_root=data_root,
        source_key="udot-at-intersection-safety",
        snapshot_id=snapshot_id,
        started_at=started_at,
        raw_count=manifest["recordCount"],
        normalized_count=len(rows),
        rejected_count=len(rejected),
        artifacts=[_artifact_entry(output_path, data_root, len(rows))],
        checks=checks,
        warnings=warnings,
        reused=raw_reused and normalized_reused,
    )
    return {"manifest": manifest, "report": report, "normalizedPath": output_path}


def import_udot_aadt(data_root: Path) -> dict[str, Any]:
    started_at = utc_now()
    staging = data_root / ".staging" / f"udot-traffic-{timestamp_slug(started_at)}"
    raw = staging / "raw"
    download = fetch_layer(UDOT_AADT_URL, raw / "layer", bbox=PROVO_AREA_BBOX)
    completed_at = utc_now()
    extent = _feature_extent(download.features)
    schema_fingerprint = sha256_json(field_fingerprint_payload([download]))
    content_fingerprint = _feature_content_fingerprint(download.features, schema_fingerprint)
    warnings = [
        "The latest measure is annual average daily traffic for 2024; a later service edit date does not make the measure newer."
    ]
    snapshot_id, _, manifest, raw_reused = _finalize_raw_snapshot(
        data_root=data_root,
        source_key="udot-traffic",
        staging_raw=raw,
        retrieved_at=started_at,
        retrieval_completed_at=completed_at,
        source_current_through="2024-12-31T23:59:59Z",
        source_crs="Provider feature layer queried as EPSG:4326",
        record_count=len(download.features),
        schema_fingerprint=schema_fingerprint,
        content_fingerprint=content_fingerprint,
        extent=extent,
        warnings=warnings,
    )
    rows, rejected = normalize_aadt(
        download.features, snapshot_id=snapshot_id, retrieved_at=started_at
    )
    output_path = data_root / "normalized" / "udot-traffic" / "v1" / snapshot_id / "records.parquet"
    normalized_reused = output_path.exists()
    if not normalized_reused:
        write_geoparquet(
            output_path,
            rows,
            AADT_SCHEMA,
            geometry_types=["LineString", "MultiLineString"],
            bbox=extent,
        )
    summary = parquet_geometry_summary(output_path)
    latest_rows = [row for row in rows if row["measure_year"] == 2024]
    represented_segments = {row["provider_segment_id"] for row in rows}
    checks = [
        {
            "name": "source-segment-reconciliation",
            "status": "passed"
            if len(represented_segments) + len(rejected) == len(download.features)
            else "failed",
            "detail": (
                f"{len(represented_segments)} source segments represented, "
                f"{len(rejected)} rejected, {len(download.features)} raw"
            ),
        },
        {
            "name": "geometry-validity",
            "status": "passed" if summary["invalidGeometryCount"] == 0 else "failed",
            "detail": f"{summary['invalidGeometryCount']} invalid geometries",
        },
        {
            "name": "latest-year-coverage",
            "status": "passed" if latest_rows else "failed",
            "detail": f"{len(latest_rows)} segments have a 2024 AADT measure",
        },
    ]
    if any(check["status"] == "failed" for check in checks):
        raise ValueError(f"UDOT AADT validation failed: {checks}")
    report = _write_run_report(
        data_root=data_root,
        source_key="udot-traffic",
        snapshot_id=snapshot_id,
        started_at=started_at,
        raw_count=manifest["recordCount"],
        normalized_count=len(rows),
        rejected_count=len(rejected),
        artifacts=[_artifact_entry(output_path, data_root, len(rows))],
        checks=checks,
        warnings=warnings,
        reused=raw_reused and normalized_reused,
    )
    return {"manifest": manifest, "report": report, "normalizedPath": output_path}


def import_udot_at_counts(data_root: Path) -> dict[str, Any]:
    started_at = utc_now()
    staging = data_root / ".staging" / f"udot-at-counts-{timestamp_slug(started_at)}"
    raw = staging / "raw"
    site_download = fetch_layer(
        UDOT_AT_COUNTER_SITES_URL,
        raw / "sites",
        where="UPPER(city) = 'PROVO'",
    )
    site_ids = sorted(
        {
            int(value)
            for feature in site_download.features
            if (value := (feature.get("properties") or {}).get("unitid")) is not None
        }
    )
    if not site_ids:
        raise ValueError("The UDOT active transportation counter layer returned no Provo sites")
    observation_download = fetch_layer(
        UDOT_AT_COUNTER_OBSERVATIONS_URL,
        raw / "observations",
        where=f"siteId IN ({','.join(str(value) for value in site_ids)})",
    )
    completed_at = utc_now()
    schema_fingerprint = sha256_json(
        field_fingerprint_payload([site_download, observation_download])
    )
    content_fingerprint = sha256_json(
        {
            "schemaFingerprint": schema_fingerprint,
            "sites": sorted(site_download.features, key=json_sort_key),
            "observations": sorted(observation_download.features, key=json_sort_key),
        }
    )
    observation_dates: list[datetime] = []
    for feature in observation_download.features:
        properties = feature.get("properties") or {}
        try:
            observation_dates.append(
                datetime(
                    int(properties["year"]),
                    int(properties["month"]),
                    int(properties["dayofmonth"]),
                    23,
                    59,
                    59,
                    tzinfo=timezone.utc,
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    source_current_through = isoformat(max(observation_dates)) if observation_dates else None
    extent = _feature_extent(site_download.features)
    warnings = [
        f"Only {len(site_ids)} Provo counter sites were available at retrieval time.",
        "Travel mode values are retained exactly; undefined mode observations are not bicycle counts.",
        "AM, PM, and Other are partial-day buckets and must be summed by site and date before use as daily counts.",
    ]
    snapshot_id, _, manifest, raw_reused = _finalize_raw_snapshot(
        data_root=data_root,
        source_key="udot-at-counts",
        staging_raw=raw,
        retrieved_at=started_at,
        retrieval_completed_at=completed_at,
        source_current_through=source_current_through,
        source_crs="Counter sites queried as EPSG:4326; observation table has no geometry",
        record_count=len(site_download.features) + len(observation_download.features),
        schema_fingerprint=schema_fingerprint,
        content_fingerprint=content_fingerprint,
        extent=extent,
        warnings=warnings,
    )
    sites, rejected_sites = normalize_at_counter_sites(
        site_download.features, snapshot_id=snapshot_id, retrieved_at=started_at
    )
    observations, rejected_observations = normalize_at_counter_observations(
        observation_download.features, snapshot_id=snapshot_id, retrieved_at=started_at
    )
    output_dir = data_root / "normalized" / "udot-at-counts" / "v1" / snapshot_id
    sites_path = output_dir / "sites.parquet"
    observations_path = output_dir / "observations.parquet"
    normalized_reused = sites_path.exists() and observations_path.exists()
    if not sites_path.exists():
        write_geoparquet(
            sites_path,
            sites,
            AT_COUNTER_SITE_SCHEMA,
            geometry_types=["Point"],
            bbox=extent,
        )
    if not observations_path.exists():
        write_parquet(observations_path, observations, AT_COUNTER_OBSERVATION_SCHEMA)
    site_summary = parquet_geometry_summary(sites_path)
    observation_ids = [row["source_record_id"] for row in observations]
    duplicate_observation_count = len(observation_ids) - len(set(observation_ids))
    checks = [
        {
            "name": "site-reconciliation",
            "status": "passed"
            if len(sites) + len(rejected_sites) == len(site_download.features)
            else "failed",
            "detail": f"{len(sites)} normalized, {len(rejected_sites)} rejected",
        },
        {
            "name": "observation-reconciliation",
            "status": "passed"
            if len(observations) + len(rejected_observations)
            == len(observation_download.features)
            else "failed",
            "detail": f"{len(observations)} normalized, {len(rejected_observations)} rejected",
        },
        {
            "name": "site-geometry-validity",
            "status": "passed" if site_summary["invalidGeometryCount"] == 0 else "failed",
            "detail": f"{site_summary['invalidGeometryCount']} invalid site geometries",
        },
        {
            "name": "observation-id-uniqueness",
            "status": "passed" if duplicate_observation_count == 0 else "failed",
            "detail": f"{duplicate_observation_count} duplicate provider observation IDs",
        },
    ]
    if any(check["status"] == "failed" for check in checks):
        raise ValueError(f"UDOT active transportation counter validation failed: {checks}")
    rejected_count = len(rejected_sites) + len(rejected_observations)
    report = _write_run_report(
        data_root=data_root,
        source_key="udot-at-counts",
        snapshot_id=snapshot_id,
        started_at=started_at,
        raw_count=manifest["recordCount"],
        normalized_count=len(sites) + len(observations),
        rejected_count=rejected_count,
        artifacts=[
            _artifact_entry(sites_path, data_root, len(sites)),
            _artifact_entry(observations_path, data_root, len(observations)),
        ],
        checks=checks,
        warnings=warnings,
        reused=raw_reused and normalized_reused,
    )
    return {
        "manifest": manifest,
        "report": report,
        "sitePath": sites_path,
        "observationPath": observations_path,
    }


def import_provo_traffic_study(data_root: Path) -> dict[str, Any]:
    started_at = utc_now()
    staging = data_root / ".staging" / f"provo-traffic-studies-{timestamp_slug(started_at)}"
    raw = staging / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    request_details = {
        "method": "GET",
        "url": PROVO_700_EAST_STUDY_URL,
        "accept": "application/pdf",
    }
    write_json(raw / "study-request.json", request_details)
    response = requests.get(
        PROVO_700_EAST_STUDY_URL,
        headers={
            "User-Agent": "ProvoStreetsWatch-DangerZones/0.1 (admin@provostreets.watch)",
            "Accept": "application/pdf",
        },
        timeout=(10, 120),
    )
    response.raise_for_status()
    if not response.content.startswith(b"%PDF-"):
        raise ValueError("The Provo traffic study response was not a PDF")
    pdf_path = raw / "study.pdf"
    pdf_path.write_bytes(response.content)
    write_json(
        raw / "response-metadata.json",
        {
            "contentLength": len(response.content),
            "contentType": response.headers.get("Content-Type"),
            "finalUrl": response.url,
            "statusCode": response.status_code,
        },
    )
    completed_at = utc_now()
    study = read_json(PROVO_700_EAST_EXTRACTION)
    schema_fingerprint = sha256_json(
        {
            "studyFields": sorted(key for key in study if key != "measures"),
            "measureFields": sorted(
                {key for measure in study.get("measures", []) for key in measure}
            ),
        }
    )
    content_fingerprint = sha256_json(
        {
            "pdfSha256": sha256_file(pdf_path),
            "reviewedExtraction": study,
            "schemaFingerprint": schema_fingerprint,
        }
    )
    warnings = list(study.get("reviewNotes", []))
    snapshot_id, _, manifest, raw_reused = _finalize_raw_snapshot(
        data_root=data_root,
        source_key="provo-traffic-studies",
        staging_raw=raw,
        retrieved_at=started_at,
        retrieval_completed_at=completed_at,
        source_current_through=f"{study['monitoringEnd']}T23:59:59Z",
        source_crs=None,
        record_count=len(study.get("measures", [])),
        schema_fingerprint=schema_fingerprint,
        content_fingerprint=content_fingerprint,
        extent=None,
        warnings=warnings,
    )
    rows, rejected = normalize_traffic_study_measures(
        study, snapshot_id=snapshot_id, retrieved_at=started_at
    )
    output_path = (
        data_root
        / "normalized"
        / "provo-traffic-studies"
        / "v1"
        / snapshot_id
        / "measures.parquet"
    )
    normalized_reused = output_path.exists()
    if not normalized_reused:
        write_parquet(output_path, rows, TRAFFIC_STUDY_MEASURE_SCHEMA)
    pages = [row["source_page"] for row in rows]
    reviewed = sum(1 for row in rows if row["review_status"] == "visually-reviewed")
    checks = [
        {
            "name": "record-reconciliation",
            "status": "passed"
            if len(rows) + len(rejected) == len(study.get("measures", []))
            else "failed",
            "detail": f"{len(rows)} normalized, {len(rejected)} rejected",
        },
        {
            "name": "page-provenance",
            "status": "passed" if pages and min(pages) >= 1 and max(pages) <= 11 else "failed",
            "detail": f"Source pages range from {min(pages) if pages else 'none'} to {max(pages) if pages else 'none'}",
        },
        {
            "name": "visual-review",
            "status": "passed" if reviewed == len(rows) else "failed",
            "detail": f"{reviewed} of {len(rows)} measures visually reviewed",
        },
        {
            "name": "provider-arithmetic",
            "status": "warning",
            "detail": "Published overall and directional volume values do not reconcile exactly; no values were corrected.",
        },
    ]
    if any(check["status"] == "failed" for check in checks):
        raise ValueError(f"Provo traffic study validation failed: {checks}")
    report = _write_run_report(
        data_root=data_root,
        source_key="provo-traffic-studies",
        snapshot_id=snapshot_id,
        started_at=started_at,
        raw_count=manifest["recordCount"],
        normalized_count=len(rows),
        rejected_count=len(rejected),
        artifacts=[_artifact_entry(output_path, data_root, len(rows))],
        checks=checks,
        warnings=warnings,
        reused=raw_reused and normalized_reused,
    )
    return {"manifest": manifest, "report": report, "normalizedPath": output_path}


def latest_artifact(data_root: Path, source_key: str) -> Path:
    reports = []
    for path in (data_root / "runs").glob(f"{source_key}-*.json"):
        report = read_json(path)
        if report.get("status") in {"accepted", "reused"} and report.get("normalizedArtifacts"):
            reports.append(report)
    if not reports:
        raise FileNotFoundError(f"No accepted import found for {source_key}")
    latest = max(reports, key=lambda report: report["completedAt"])
    return data_root / latest["normalizedArtifacts"][0]["path"]
