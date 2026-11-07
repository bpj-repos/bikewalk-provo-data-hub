from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pyarrow as pa
from shapely.geometry import shape


LINEAGE_FIELDS = [
    pa.field("record_id", pa.string(), nullable=False),
    pa.field("source_key", pa.string(), nullable=False),
    pa.field("source_record_id", pa.string(), nullable=False),
    pa.field("source_snapshot_id", pa.string(), nullable=False),
    pa.field("retrieved_at", pa.timestamp("ms", tz="UTC"), nullable=False),
]


STREET_SCHEMA = pa.schema(
    LINEAGE_FIELDS
    + [
        pa.field("network_version", pa.string(), nullable=False),
        pa.field("segment_id", pa.string(), nullable=False),
        pa.field("street_id", pa.int64()),
        pa.field("local_uid", pa.string()),
        pa.field("owner", pa.string()),
        pa.field("classification", pa.string()),
        pa.field("udot_class", pa.string()),
        pa.field("num_lanes", pa.int32()),
        pa.field("from_road", pa.string()),
        pa.field("to_road", pa.string()),
        pa.field("name", pa.string()),
        pa.field("full_name", pa.string()),
        pa.field("one_way", pa.string()),
        pa.field("geometry", pa.binary(), nullable=False),
        pa.field("attributes", pa.string(), nullable=False),
    ]
)


CRASH_SCHEMA = pa.schema(
    LINEAGE_FIELDS
    + [
        pa.field("crash_id", pa.string(), nullable=False),
        pa.field("source_layer_year", pa.int32(), nullable=False),
        pa.field("observed_at", pa.timestamp("ms", tz="UTC")),
        pa.field("source_current_through", pa.timestamp("ms", tz="UTC")),
        pa.field("severity", pa.string()),
        pa.field("pedestrian_involved", pa.bool_()),
        pa.field("bicyclist_involved", pa.bool_()),
        pa.field("speed_related", pa.bool_()),
        pa.field("commercial_vehicle_involved", pa.bool_()),
        pa.field("fatalities", pa.int32()),
        pa.field("suspected_serious_injuries", pa.int32()),
        pa.field("suspected_minor_injuries", pa.int32()),
        pa.field("possible_injuries", pa.int32()),
        pa.field("main_road_name", pa.string()),
        pa.field("location_description", pa.string()),
        pa.field("light_condition", pa.string()),
        pa.field("weather_condition", pa.string()),
        pa.field("collision_manner", pa.string()),
        pa.field("junction_feature", pa.string()),
        pa.field("functional_class", pa.string()),
        pa.field("geometry", pa.binary(), nullable=False),
        pa.field("attributes", pa.string(), nullable=False),
    ]
)


STRESS_SCHEMA = pa.schema(
    LINEAGE_FIELDS
    + [
        pa.field("name", pa.string()),
        pa.field("city", pa.string()),
        pa.field("county", pa.string()),
        pa.field("facility_primary", pa.string()),
        pa.field("facility_secondary", pa.string()),
        pa.field("facility_primary_side", pa.string()),
        pa.field("facility_secondary_side", pa.string()),
        pa.field("lts_score", pa.string()),
        pa.field("provider_source", pa.string()),
        pa.field("geometry", pa.binary(), nullable=False),
        pa.field("attributes", pa.string(), nullable=False),
    ]
)


EXPECTED_SAFETY_SCHEMA = pa.schema(
    LINEAGE_FIELDS
    + [
        pa.field("facility_kind", pa.string(), nullable=False),
        pa.field("provider_object_id", pa.string(), nullable=False),
        pa.field("city", pa.string()),
        pa.field("county", pa.string()),
        pa.field("location_label", pa.string()),
        pa.field("provider_pedestrian_all", pa.float64()),
        pa.field("provider_pedestrian_ksi", pa.float64()),
        pa.field("provider_bicycle_all", pa.float64()),
        pa.field("provider_bicycle_ksi", pa.float64()),
        pa.field("empirical_bayes_pedestrian_all", pa.float64()),
        pa.field("empirical_bayes_pedestrian_ksi", pa.float64()),
        pa.field("empirical_bayes_bicycle_all", pa.float64()),
        pa.field("empirical_bayes_bicycle_ksi", pa.float64()),
        pa.field("estimated_daily_pedestrian_volume", pa.float64()),
        pa.field("estimated_daily_bicycle_volume", pa.float64()),
        pa.field("aadt_major", pa.float64()),
        pa.field("aadt_minor", pa.float64()),
        pa.field("aadt_segment", pa.float64()),
        pa.field("geometry", pa.binary(), nullable=False),
        pa.field("attributes", pa.string(), nullable=False),
    ]
)


AADT_SCHEMA = pa.schema(
    LINEAGE_FIELDS
    + [
        pa.field("provider_segment_id", pa.string(), nullable=False),
        pa.field("station", pa.string()),
        pa.field("route_id", pa.string()),
        pa.field("description", pa.string()),
        pa.field("begin_point", pa.float64()),
        pa.field("end_point", pa.float64()),
        pa.field("section_length", pa.float64()),
        pa.field("measure_year", pa.int32(), nullable=False),
        pa.field("aadt", pa.float64(), nullable=False),
        pa.field("single_unit_truck_share", pa.float64()),
        pa.field("combination_unit_truck_share", pa.float64()),
        pa.field("geometry", pa.binary(), nullable=False),
        pa.field("attributes", pa.string(), nullable=False),
    ]
)


AT_COUNTER_SITE_SCHEMA = pa.schema(
    LINEAGE_FIELDS
    + [
        pa.field("site_id", pa.int64(), nullable=False),
        pa.field("name", pa.string()),
        pa.field("description", pa.string()),
        pa.field("city", pa.string()),
        pa.field("county", pa.string()),
        pa.field("region", pa.string()),
        pa.field("travel_mode", pa.string()),
        pa.field("first_data", pa.string()),
        pa.field("last_data", pa.string()),
        pa.field("granularity", pa.string()),
        pa.field("directionality", pa.string()),
        pa.field("geometry", pa.binary(), nullable=False),
        pa.field("attributes", pa.string(), nullable=False),
    ]
)


AT_COUNTER_OBSERVATION_SCHEMA = pa.schema(
    LINEAGE_FIELDS
    + [
        pa.field("site_id", pa.int64(), nullable=False),
        pa.field("observed_date", pa.date32(), nullable=False),
        pa.field("travel_mode", pa.string()),
        pa.field("commuting_period", pa.string()),
        pa.field("count", pa.float64(), nullable=False),
        pa.field("provider_domain", pa.string()),
        pa.field("provider_weekday", pa.int32()),
        pa.field("attributes", pa.string(), nullable=False),
    ]
)


TRAFFIC_STUDY_MEASURE_SCHEMA = pa.schema(
    LINEAGE_FIELDS
    + [
        pa.field("study_id", pa.string(), nullable=False),
        pa.field("study_title", pa.string(), nullable=False),
        pa.field("published_date", pa.date32(), nullable=False),
        pa.field("monitoring_start", pa.date32(), nullable=False),
        pa.field("monitoring_end", pa.date32(), nullable=False),
        pa.field("monitoring_hours", pa.float64(), nullable=False),
        pa.field("location_label", pa.string(), nullable=False),
        pa.field("measure_type", pa.string(), nullable=False),
        pa.field("statistic", pa.string(), nullable=False),
        pa.field("direction", pa.string(), nullable=False),
        pa.field("value", pa.float64(), nullable=False),
        pa.field("unit", pa.string(), nullable=False),
        pa.field("source_page", pa.int32(), nullable=False),
        pa.field("review_status", pa.string(), nullable=False),
        pa.field("attributes", pa.string(), nullable=False),
    ]
)


SAFE_ROUTES_SCHOOL_SCHEMA = pa.schema(
    LINEAGE_FIELDS
    + [
        pa.field("school_id", pa.int64(), nullable=False),
        pa.field("school_name", pa.string(), nullable=False),
        pa.field("school_address", pa.string()),
        pa.field("city", pa.string()),
        pa.field("postal_code", pa.string()),
        pa.field("district", pa.string(), nullable=False),
        pa.field("approval_date", pa.timestamp("ms", tz="UTC"), nullable=False),
        pa.field("approved", pa.bool_(), nullable=False),
        pa.field("geometry", pa.binary(), nullable=False),
        pa.field("attributes", pa.string(), nullable=False),
    ]
)


SAFE_ROUTE_SCHEMA = pa.schema(
    LINEAGE_FIELDS
    + [
        pa.field("school_id", pa.int64()),
        pa.field("school_name", pa.string(), nullable=False),
        pa.field("school_address", pa.string()),
        pa.field("city", pa.string()),
        pa.field("postal_code", pa.string()),
        pa.field("district", pa.string(), nullable=False),
        pa.field("approval_date", pa.timestamp("ms", tz="UTC"), nullable=False),
        pa.field("approved", pa.bool_(), nullable=False),
        pa.field("geometry", pa.binary(), nullable=False),
        pa.field("attributes", pa.string(), nullable=False),
    ]
)


SAFE_ROUTE_FEATURE_SCHEMA = pa.schema(
    LINEAGE_FIELDS
    + [
        pa.field("feature_type", pa.string(), nullable=False),
        pa.field("school_id", pa.int64()),
        pa.field("school_name", pa.string(), nullable=False),
        pa.field("school_address", pa.string()),
        pa.field("city", pa.string()),
        pa.field("postal_code", pa.string()),
        pa.field("district", pa.string(), nullable=False),
        pa.field("approval_date", pa.timestamp("ms", tz="UTC"), nullable=False),
        pa.field("approved", pa.bool_(), nullable=False),
        pa.field("geometry", pa.binary(), nullable=False),
        pa.field("attributes", pa.string(), nullable=False),
    ]
)


CROSSWALK_SCHEMA = pa.schema(
    LINEAGE_FIELDS
    + [
        pa.field("crosswalk_id", pa.string(), nullable=False),
        pa.field("provider_object_id", pa.string(), nullable=False),
        pa.field("marking_type", pa.string()),
        pa.field("east_west_street", pa.string()),
        pa.field("north_south_street", pa.string()),
        pa.field("intersection_side", pa.string()),
        pa.field("created_at", pa.timestamp("ms", tz="UTC")),
        pa.field("last_edited_at", pa.timestamp("ms", tz="UTC")),
        pa.field("geometry", pa.binary(), nullable=False),
        pa.field("attributes", pa.string(), nullable=False),
    ]
)


FRA_CROSSING_SCHEMA = pa.schema(
    LINEAGE_FIELDS
    + [
        pa.field("crossing_id", pa.string(), nullable=False),
        pa.field("effective_at", pa.timestamp("ms", tz="UTC")),
        pa.field("railroad", pa.string()),
        pa.field("railroad_division", pa.string()),
        pa.field("railroad_subdivision", pa.string()),
        pa.field("highway", pa.string()),
        pa.field("street", pa.string()),
        pa.field("crossing_access", pa.string()),
        pa.field("crossing_position", pa.string()),
        pa.field("warning_device", pa.string()),
        pa.field("day_through_trains", pa.int32()),
        pa.field("night_through_trains", pa.int32()),
        pa.field("track_count", pa.int32()),
        pa.field("quiet_zone", pa.bool_()),
        pa.field("aadt", pa.float64()),
        pa.field("aadt_year", pa.int32()),
        pa.field("inventory_url", pa.string()),
        pa.field("accident_history_url", pa.string()),
        pa.field("last_updated", pa.string()),
        pa.field("geometry", pa.binary(), nullable=False),
        pa.field("attributes", pa.string(), nullable=False),
    ]
)


TRANSIT_STOP_SCHEMA = pa.schema(
    LINEAGE_FIELDS
    + [
        pa.field("stop_id", pa.string(), nullable=False),
        pa.field("stop_code", pa.string()),
        pa.field("stop_name", pa.string(), nullable=False),
        pa.field("city", pa.string()),
        pa.field("county", pa.string()),
        pa.field("mode", pa.string()),
        pa.field("routes", pa.string()),
        pa.field("route_count", pa.int32()),
        pa.field("weekday_boardings", pa.float64()),
        pa.field("weekday_alightings", pa.float64()),
        pa.field("weekday_activity", pa.float64()),
        pa.field("stop_kind", pa.string(), nullable=False),
        pa.field("major_transfer_point", pa.bool_(), nullable=False),
        pa.field("geometry", pa.binary(), nullable=False),
        pa.field("attributes", pa.string(), nullable=False),
    ]
)


TRAIL_SCHEMA = pa.schema(
    LINEAGE_FIELDS
    + [
        pa.field("trail_id", pa.string(), nullable=False),
        pa.field("path_name", pa.string()),
        pa.field("path_type", pa.string()),
        pa.field("surface", pa.string()),
        pa.field("width_feet", pa.int32()),
        pa.field("owner", pa.string()),
        pa.field("owner_type", pa.string()),
        pa.field("geometry", pa.binary(), nullable=False),
        pa.field("attributes", pa.string(), nullable=False),
    ]
)


TRAIL_ROAD_CROSSING_SCHEMA = pa.schema(
    LINEAGE_FIELDS
    + [
        pa.field("candidate_crossing_id", pa.string(), nullable=False),
        pa.field("trail_id", pa.string(), nullable=False),
        pa.field("trail_name", pa.string()),
        pa.field("street_segment_id", pa.string(), nullable=False),
        pa.field("street_name", pa.string()),
        pa.field("intersection_kind", pa.string(), nullable=False),
        pa.field("grade_separation_status", pa.string(), nullable=False),
        pa.field("geometry", pa.binary(), nullable=False),
        pa.field("attributes", pa.string(), nullable=False),
    ]
)


TRAFFIC_EVENT_SCHEMA = pa.schema(
    LINEAGE_FIELDS
    + [
        pa.field("event_id", pa.string(), nullable=False),
        pa.field("event_type", pa.string()),
        pa.field("category", pa.string()),
        pa.field("name", pa.string()),
        pa.field("roadway", pa.string()),
        pa.field("direction", pa.string()),
        pa.field("location_label", pa.string()),
        pa.field("reported_at", pa.timestamp("ms", tz="UTC")),
        pa.field("last_updated_at", pa.timestamp("ms", tz="UTC")),
        pa.field("starts_at", pa.timestamp("ms", tz="UTC")),
        pa.field("planned_end_at", pa.timestamp("ms", tz="UTC")),
        pa.field("lanes_affected", pa.string()),
        pa.field("full_closure", pa.bool_()),
        pa.field("geometry", pa.binary(), nullable=False),
        pa.field("attributes", pa.string(), nullable=False),
    ]
)


POLICE_INCIDENT_SCHEMA = pa.schema(
    LINEAGE_FIELDS
    + [
        pa.field("incident_id", pa.string(), nullable=False),
        pa.field("observed_at", pa.timestamp("ms", tz="America/Denver"), nullable=False),
        pa.field("location_raw", pa.string()),
        pa.field("mode_raw", pa.string(), nullable=False),
        pa.field("mode_category", pa.string(), nullable=False),
        pa.field("severity", pa.string()),
        pa.field("event_type", pa.string()),
        pa.field("source_sheet", pa.string(), nullable=False),
        pa.field("source_table", pa.string(), nullable=False),
        pa.field("source_row", pa.int32(), nullable=False),
        pa.field("attributes", pa.string(), nullable=False),
    ]
)


def _datetime_from_millis(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000, timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _integer(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    if value is None or str(value).strip().upper() in {"", "NA", "N/A", "NULL"}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _yes(value: Any) -> bool | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    if normalized in {"Y", "YES", "TRUE", "1"}:
        return True
    if normalized in {"N", "NO", "FALSE", "0"}:
        return False
    return None


SAFE_ROUTES_PUBLIC_FIELDS = {
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
    "FEATURE_TYPE",
}


def _safe_routes_attributes(properties: dict[str, Any]) -> str:
    safe = {
        key: value
        for key, value in properties.items()
        if key in SAFE_ROUTES_PUBLIC_FIELDS
    }
    return json.dumps(safe, sort_keys=True, separators=(",", ":"))


def _normalize_safe_routes_common(
    feature: dict[str, Any],
    *,
    source_id_fields: list[str],
    geometry_types: set[str],
) -> tuple[dict[str, Any], Any, str] | None:
    properties = feature.get("properties") or {}
    source_id = next(
        (properties.get(field) for field in source_id_fields if properties.get(field) is not None),
        None,
    )
    if source_id is None or not feature.get("geometry"):
        return None
    try:
        geometry = shape(feature["geometry"])
    except Exception:
        return None
    if geometry.is_empty or geometry.geom_type not in geometry_types:
        return None
    approval_date = _datetime_from_millis(properties.get("APPROVAL_DATE"))
    approved = _yes(properties.get("APPROVED"))
    school_name = properties.get("NAME_SCHOOL")
    district = properties.get("NAME_DISTRICT")
    if not approval_date or approved is None or not school_name or not district:
        return None
    common = {
        "school_id": _integer(properties.get("ID_SCHOOL")),
        "school_name": str(school_name),
        "school_address": properties.get("ADDRESS_SCHOOL"),
        "city": properties.get("CITY_SCHOOL"),
        "postal_code": properties.get("POSTAL_SCHOOL"),
        "district": str(district),
        "approval_date": approval_date,
        "approved": approved,
        "geometry": geometry.wkb,
        "attributes": _safe_routes_attributes(properties),
    }
    return common, geometry, str(source_id)


def normalize_safe_routes_schools(
    features: list[dict[str, Any]],
    *,
    snapshot_id: str,
    retrieved_at: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    rejected: list[str] = []
    for feature in features:
        properties = feature.get("properties") or {}
        normalized = _normalize_safe_routes_common(
            feature,
            source_id_fields=["GlobalID", "OBJECTID"],
            geometry_types={"Point"},
        )
        if not normalized:
            rejected.append(str(properties.get("GlobalID") or properties.get("OBJECTID") or "missing-id"))
            continue
        common, _, source_record_id = normalized
        if common["school_id"] is None:
            rejected.append(source_record_id)
            continue
        rows.append(
            {
                "record_id": f"udot-safe-routes-to-school:school:{source_record_id}",
                "source_key": "udot-safe-routes-to-school",
                "source_record_id": f"school:{source_record_id}",
                "source_snapshot_id": snapshot_id,
                "retrieved_at": retrieved_at,
                **common,
            }
        )
    rows.sort(key=lambda row: row["source_record_id"])
    return rows, rejected


def normalize_safe_routes(
    features: list[dict[str, Any]],
    *,
    snapshot_id: str,
    retrieved_at: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    rejected: list[str] = []
    for feature in features:
        properties = feature.get("properties") or {}
        normalized = _normalize_safe_routes_common(
            feature,
            source_id_fields=["GlobalID", "OBJECTID_12_13_14"],
            geometry_types={"LineString", "MultiLineString"},
        )
        if not normalized:
            rejected.append(
                str(properties.get("GlobalID") or properties.get("OBJECTID_12_13_14") or "missing-id")
            )
            continue
        common, _, source_record_id = normalized
        rows.append(
            {
                "record_id": f"udot-safe-routes-to-school:route:{source_record_id}",
                "source_key": "udot-safe-routes-to-school",
                "source_record_id": f"route:{source_record_id}",
                "source_snapshot_id": snapshot_id,
                "retrieved_at": retrieved_at,
                **common,
            }
        )
    rows.sort(key=lambda row: row["source_record_id"])
    return rows, rejected


def normalize_safe_route_features(
    features: list[dict[str, Any]],
    *,
    snapshot_id: str,
    retrieved_at: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    rejected: list[str] = []
    for feature in features:
        properties = feature.get("properties") or {}
        normalized = _normalize_safe_routes_common(
            feature,
            source_id_fields=["GlobalID", "OBJECTID_1"],
            geometry_types={"Point"},
        )
        feature_type = properties.get("FEATURE_TYPE")
        if not normalized or not feature_type:
            rejected.append(str(properties.get("GlobalID") or properties.get("OBJECTID_1") or "missing-id"))
            continue
        common, _, source_record_id = normalized
        rows.append(
            {
                "record_id": f"udot-safe-routes-to-school:feature:{source_record_id}",
                "source_key": "udot-safe-routes-to-school",
                "source_record_id": f"feature:{source_record_id}",
                "source_snapshot_id": snapshot_id,
                "retrieved_at": retrieved_at,
                "feature_type": str(feature_type),
                **common,
            }
        )
    rows.sort(key=lambda row: row["source_record_id"])
    return rows, rejected


def _public_attributes(properties: dict[str, Any], fields: set[str]) -> str:
    return json.dumps(
        {key: value for key, value in properties.items() if key in fields},
        sort_keys=True,
        separators=(",", ":"),
    )


def normalize_crosswalks(
    features: list[dict[str, Any]], *, snapshot_id: str, retrieved_at: datetime
) -> tuple[list[dict[str, Any]], list[str]]:
    fields = {
        "OBJECTID", "GlobalID", "Type", "EAST_WEST_STREET",
        "NORTH_SOUTH_STREET", "INTERSECTION_SIDE", "created_date",
        "last_edited_date",
    }
    rows, rejected = [], []
    for feature in features:
        properties = feature.get("properties") or {}
        source_id = properties.get("GlobalID") or properties.get("OBJECTID")
        try:
            geometry = shape(feature.get("geometry"))
        except Exception:
            geometry = None
        if source_id is None or geometry is None or geometry.is_empty or geometry.geom_type not in {"LineString", "MultiLineString"}:
            rejected.append(str(source_id or "missing-id"))
            continue
        source_record_id = str(source_id)
        rows.append({
            "record_id": f"provo-crosswalks:{source_record_id}",
            "source_key": "provo-crosswalks",
            "source_record_id": source_record_id,
            "source_snapshot_id": snapshot_id,
            "retrieved_at": retrieved_at,
            "crosswalk_id": source_record_id,
            "provider_object_id": str(properties.get("OBJECTID")),
            "marking_type": properties.get("Type"),
            "east_west_street": properties.get("EAST_WEST_STREET"),
            "north_south_street": properties.get("NORTH_SOUTH_STREET"),
            "intersection_side": properties.get("INTERSECTION_SIDE"),
            "created_at": _datetime_from_millis(properties.get("created_date")),
            "last_edited_at": _datetime_from_millis(properties.get("last_edited_date")),
            "geometry": geometry.wkb,
            "attributes": _public_attributes(properties, fields),
        })
    rows.sort(key=lambda row: row["source_record_id"])
    return rows, rejected


def normalize_fra_crossings(
    features: list[dict[str, Any]], *, snapshot_id: str, retrieved_at: datetime
) -> tuple[list[dict[str, Any]], list[str]]:
    fields = {
        "CROSSING", "EFFDATE", "RAILROAD", "RRDIV", "RRSUBDIV", "HIGHWAY",
        "STREET", "TYPEXING", "POSXING", "WHISTBAN", "INV_LINK", "ACC_LINK",
        "DAYTHRU", "NGHTTHRU", "MAINTRK", "SIDINGTRK", "YARDTRK",
        "TRANSITTRK", "INDUSTRYTR", "OTHRTRK", "WDCODE", "REVISIONDA",
        "LASTUPDATE", "AADT", "AADTYEAR", "COUNTYNAME", "CITYNAME",
    }
    rows, rejected = [], []
    for feature in features:
        properties = feature.get("properties") or {}
        source_id = properties.get("CROSSING")
        try:
            geometry = shape(feature.get("geometry"))
        except Exception:
            geometry = None
        if not source_id or geometry is None or geometry.is_empty or geometry.geom_type != "Point":
            rejected.append(str(source_id or properties.get("OBJECTID") or "missing-id"))
            continue
        track_count = sum(_integer(properties.get(field)) or 0 for field in [
            "MAINTRK", "SIDINGTRK", "YARDTRK", "TRANSITTRK", "INDUSTRYTR", "OTHRTRK"
        ])
        source_record_id = str(source_id)
        rows.append({
            "record_id": f"fra-grade-crossings:{source_record_id}",
            "source_key": "fra-grade-crossings",
            "source_record_id": source_record_id,
            "source_snapshot_id": snapshot_id,
            "retrieved_at": retrieved_at,
            "crossing_id": source_record_id,
            "effective_at": _datetime_from_millis(properties.get("EFFDATE")),
            "railroad": properties.get("RAILROAD"),
            "railroad_division": properties.get("RRDIV"),
            "railroad_subdivision": properties.get("RRSUBDIV"),
            "highway": properties.get("HIGHWAY"),
            "street": properties.get("STREET"),
            "crossing_access": properties.get("TYPEXING"),
            "crossing_position": properties.get("POSXING"),
            "warning_device": properties.get("WDCODE"),
            "day_through_trains": _integer(properties.get("DAYTHRU")),
            "night_through_trains": _integer(properties.get("NGHTTHRU")),
            "track_count": track_count,
            "quiet_zone": _yes(properties.get("WHISTBAN")),
            "aadt": _number(properties.get("AADT")),
            "aadt_year": _integer(properties.get("AADTYEAR")),
            "inventory_url": properties.get("INV_LINK"),
            "accident_history_url": properties.get("ACC_LINK"),
            "last_updated": properties.get("LASTUPDATE") or properties.get("REVISIONDA"),
            "geometry": geometry.wkb,
            "attributes": _public_attributes(properties, fields),
        })
    rows.sort(key=lambda row: row["source_record_id"])
    return rows, rejected


def normalize_transit_stops(
    features: list[dict[str, Any]], *, snapshot_id: str, retrieved_at: datetime
) -> tuple[list[dict[str, Any]], list[str]]:
    fields = {"fid", "stopabbr", "stopabbr_j", "stopname", "city", "county", "uta_stopid", "route", "mode", "zipcode", "avgboard2", "avgalight2"}
    rows, rejected = [], []
    for feature in features:
        properties = feature.get("properties") or {}
        source_id = properties.get("uta_stopid") or properties.get("fid")
        try:
            geometry = shape(feature.get("geometry"))
        except Exception:
            geometry = None
        if source_id is None or not properties.get("stopname") or geometry is None or geometry.is_empty or geometry.geom_type != "Point":
            rejected.append(str(source_id or "missing-id"))
            continue
        route_text = str(properties.get("route") or "").strip()
        routes = sorted({part.strip() for part in route_text.replace(";", ",").split(",") if part.strip()})
        boardings = _number(properties.get("avgboard2"))
        alightings = _number(properties.get("avgalight2"))
        activity = (boardings or 0) + (alightings or 0) if boardings is not None or alightings is not None else None
        mode = str(properties.get("mode") or "").strip()
        stop_code = str(properties.get("stopabbr_j") or properties.get("stopabbr") or "").strip()
        stop_name = str(properties["stopname"])
        if mode.lower() == "frontrunner":
            stop_kind = "rail-station"
        elif stop_code.upper().startswith("BB") or " bay " in f" {stop_name.lower()} ":
            stop_kind = "bus-bay"
        elif mode.lower() == "brt":
            stop_kind = "brt-station"
        else:
            stop_kind = "bus-stop"
        major = stop_kind in {"rail-station", "bus-bay"} or len(routes) >= 2 or (activity or 0) >= 500
        source_record_id = str(source_id)
        rows.append({
            "record_id": f"uta-transit-stops:{source_record_id}",
            "source_key": "uta-transit-stops",
            "source_record_id": source_record_id,
            "source_snapshot_id": snapshot_id,
            "retrieved_at": retrieved_at,
            "stop_id": source_record_id,
            "stop_code": stop_code or None,
            "stop_name": stop_name,
            "city": properties.get("city"),
            "county": properties.get("county"),
            "mode": mode or None,
            "routes": ",".join(routes) or None,
            "route_count": len(routes),
            "weekday_boardings": boardings,
            "weekday_alightings": alightings,
            "weekday_activity": activity,
            "stop_kind": stop_kind,
            "major_transfer_point": major,
            "geometry": geometry.wkb,
            "attributes": _public_attributes(properties, fields),
        })
    rows.sort(key=lambda row: row["source_record_id"])
    return rows, rejected


def normalize_trails(
    features: list[dict[str, Any]], *, snapshot_id: str, retrieved_at: datetime
) -> tuple[list[dict[str, Any]], list[str]]:
    fields = {"OBJECTID", "PATHID", "PATH_NAME", "PATH_TYPE", "SURFACE", "WIDTH_FT", "OWNER", "OWNERTYPE"}
    rows, rejected = [], []
    for feature in features:
        properties = feature.get("properties") or {}
        source_id = properties.get("PATHID") or properties.get("OBJECTID")
        try:
            geometry = shape(feature.get("geometry"))
        except Exception:
            geometry = None
        if source_id is None or geometry is None or geometry.is_empty or geometry.geom_type not in {"LineString", "MultiLineString"}:
            rejected.append(str(source_id or "missing-id"))
            continue
        source_record_id = str(source_id)
        rows.append({
            "record_id": f"provo-trails:{source_record_id}",
            "source_key": "provo-trails",
            "source_record_id": source_record_id,
            "source_snapshot_id": snapshot_id,
            "retrieved_at": retrieved_at,
            "trail_id": source_record_id,
            "path_name": properties.get("PATH_NAME"),
            "path_type": properties.get("PATH_TYPE"),
            "surface": properties.get("SURFACE"),
            "width_feet": _integer(properties.get("WIDTH_FT")),
            "owner": properties.get("OWNER"),
            "owner_type": properties.get("OWNERTYPE"),
            "geometry": geometry.wkb,
            "attributes": _public_attributes(properties, fields),
        })
    rows.sort(key=lambda row: row["source_record_id"])
    return rows, rejected


def _event_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return _datetime_from_millis(numeric * 1000 if abs(numeric) < 1_000_000_000_000 else numeric)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def normalize_traffic_events(
    events: list[dict[str, Any]], *, snapshot_id: str, retrieved_at: datetime
) -> tuple[list[dict[str, Any]], list[str]]:
    rows, rejected = [], []
    for event in events:
        source_id = event.get("ID") or event.get("id")
        latitude = _number(event["Latitude"] if "Latitude" in event else event.get("latitude"))
        longitude = _number(event["Longitude"] if "Longitude" in event else event.get("longitude"))
        if source_id is None or latitude is None or longitude is None:
            rejected.append(str(source_id or "missing-id"))
            continue
        from shapely.geometry import Point
        geometry = Point(longitude, latitude)
        source_record_id = str(source_id)
        safe_attributes = {
            key: event.get(key)
            for key in ["ID", "EventType", "Category", "RoadwayName", "DirectionOfTravel", "IsFullClosure"]
            if event.get(key) is not None
        }
        rows.append({
            "record_id": f"udot-traffic-events:{source_record_id}",
            "source_key": "udot-traffic-events",
            "source_record_id": source_record_id,
            "source_snapshot_id": snapshot_id,
            "retrieved_at": retrieved_at,
            "event_id": source_record_id,
            "event_type": event.get("EventType") or event.get("eventType"),
            "category": event.get("Category") or event.get("category"),
            "name": event.get("Name") or event.get("name"),
            "roadway": event.get("RoadwayName") or event.get("roadway"),
            "direction": event.get("DirectionOfTravel") or event.get("direction"),
            "location_label": event.get("Location") or event.get("location"),
            "reported_at": _event_datetime(event.get("Reported") or event.get("reported")),
            "last_updated_at": _event_datetime(event.get("LastUpdated") or event.get("lastUpdated")),
            "starts_at": _event_datetime(event.get("StartDate") or event.get("startDate")),
            "planned_end_at": _event_datetime(event.get("PlannedEndDate") or event.get("plannedEndDate")),
            "lanes_affected": event.get("LanesAffected") or event.get("lanesAffected"),
            "full_closure": _yes(
                event["IsFullClosure"] if "IsFullClosure" in event else event.get("isFullClosure")
            ),
            "geometry": geometry.wkb,
            "attributes": json.dumps(safe_attributes, sort_keys=True, separators=(",", ":")),
        })
    rows.sort(key=lambda row: row["source_record_id"])
    return rows, rejected


def normalize_streets(
    features: list[dict[str, Any]],
    *,
    snapshot_id: str,
    retrieved_at: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    rejected: list[str] = []
    for feature in features:
        properties = feature.get("properties") or {}
        source_id = properties.get("LOCAL_UID") or properties.get("OBJECTID")
        if source_id is None or not feature.get("geometry"):
            rejected.append(str(properties.get("OBJECTID", "missing-id")))
            continue
        try:
            geometry = shape(feature["geometry"])
        except Exception:
            rejected.append(str(source_id))
            continue
        if geometry.is_empty or geometry.geom_type not in {"LineString", "MultiLineString"}:
            rejected.append(str(source_id))
            continue
        source_record_id = str(source_id)
        rows.append(
            {
                "record_id": f"provo-streets:{source_record_id}",
                "source_key": "provo-streets",
                "source_record_id": source_record_id,
                "source_snapshot_id": snapshot_id,
                "retrieved_at": retrieved_at,
                "network_version": snapshot_id,
                "segment_id": f"psw-segment:{source_record_id}",
                "street_id": _integer(properties.get("STREETID")),
                "local_uid": str(properties["LOCAL_UID"]) if properties.get("LOCAL_UID") else None,
                "owner": properties.get("OWNER"),
                "classification": properties.get("CLASSIFICATION"),
                "udot_class": properties.get("UDOT_CLASS"),
                "num_lanes": _integer(properties.get("NUM_LANES")),
                "from_road": properties.get("FROM_ROAD"),
                "to_road": properties.get("TO_ROAD"),
                "name": properties.get("NAME"),
                "full_name": properties.get("FULLNAME") or properties.get("LABEL"),
                "one_way": properties.get("ONEWAY"),
                "geometry": geometry.wkb,
                "attributes": json.dumps(properties, sort_keys=True, separators=(",", ":")),
            }
        )
    rows.sort(key=lambda row: row["source_record_id"])
    return rows, rejected


def normalize_crashes(
    features_by_year: list[tuple[int, dict[str, Any]]],
    *,
    snapshot_id: str,
    retrieved_at: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    rejected: list[str] = []
    for year, feature in features_by_year:
        properties = feature.get("properties") or {}
        crash_id = properties.get("CRASH_ID")
        if crash_id is None or not feature.get("geometry"):
            rejected.append(str(properties.get("OBJECTID", "missing-id")))
            continue
        try:
            geometry = shape(feature["geometry"])
        except Exception:
            rejected.append(str(crash_id))
            continue
        if geometry.is_empty or geometry.geom_type != "Point":
            rejected.append(str(crash_id))
            continue
        crash_id_string = str(int(crash_id) if isinstance(crash_id, float) and crash_id.is_integer() else crash_id)
        rows.append(
            {
                "record_id": f"udot-crashes:{crash_id_string}",
                "source_key": "udot-crashes",
                "source_record_id": crash_id_string,
                "source_snapshot_id": snapshot_id,
                "retrieved_at": retrieved_at,
                "crash_id": crash_id_string,
                "source_layer_year": year,
                "observed_at": _datetime_from_millis(properties.get("CRASH_DATETIME")),
                "source_current_through": _datetime_from_millis(properties.get("CURRENT_AS_OF_DATE")),
                "severity": properties.get("CRASH_SEVERITY_DESC"),
                "pedestrian_involved": _yes(properties.get("PEDESTRIAN_INVOLVED")),
                "bicyclist_involved": _yes(properties.get("BICYCLIST_INVOLVED")),
                "speed_related": _yes(properties.get("SPEED_RELATED")),
                "commercial_vehicle_involved": _yes(properties.get("COMMERCIAL_MOTOR_VEH_INVOLVED")),
                "fatalities": _integer(properties.get("NUMBER_FATALITIES")),
                "suspected_serious_injuries": _integer(properties.get("NUMBER_FOUR_INJURIES")),
                "suspected_minor_injuries": _integer(properties.get("NUMBER_THREE_INJURIES")),
                "possible_injuries": _integer(properties.get("NUMBER_TWO_INJURIES")),
                "main_road_name": properties.get("MAIN_ROAD_NAME"),
                "location_description": properties.get("LOCATION_DESC"),
                "light_condition": properties.get("LIGHT_CONDITION_DESC"),
                "weather_condition": properties.get("WEATHER_CONDITION_DESC"),
                "collision_manner": properties.get("MANNER_COLLISION_DESC"),
                "junction_feature": properties.get("ROADWAY_JUNCT_FEATURE_DESC"),
                "functional_class": properties.get("FUNCTIONAL_CLASS"),
                "geometry": geometry.wkb,
                "attributes": json.dumps(properties, sort_keys=True, separators=(",", ":")),
            }
        )
    rows.sort(key=lambda row: (row["source_layer_year"], row["source_record_id"]))
    return rows, rejected


def normalize_stress(
    features: list[dict[str, Any]],
    *,
    snapshot_id: str,
    retrieved_at: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    rejected: list[str] = []
    for feature in features:
        properties = feature.get("properties") or {}
        source_id = properties.get("OBJECTID")
        if source_id is None or not feature.get("geometry"):
            rejected.append(str(source_id or "missing-id"))
            continue
        try:
            geometry = shape(feature["geometry"])
        except Exception:
            rejected.append(str(source_id))
            continue
        if geometry.is_empty or geometry.geom_type not in {"LineString", "MultiLineString"}:
            rejected.append(str(source_id))
            continue
        source_record_id = str(source_id)
        rows.append(
            {
                "record_id": f"ugrc-bikeways-lts:{source_record_id}",
                "source_key": "ugrc-bikeways-lts",
                "source_record_id": source_record_id,
                "source_snapshot_id": snapshot_id,
                "retrieved_at": retrieved_at,
                "name": properties.get("NAME"),
                "city": properties.get("CITY"),
                "county": properties.get("COUNTY"),
                "facility_primary": properties.get("Facility1"),
                "facility_secondary": properties.get("Facility2"),
                "facility_primary_side": properties.get("Facility1_Side"),
                "facility_secondary_side": properties.get("Facility2_Side"),
                "lts_score": str(properties["LTS_SCORE"]) if properties.get("LTS_SCORE") is not None else None,
                "provider_source": properties.get("SOURCE"),
                "geometry": geometry.wkb,
                "attributes": json.dumps(properties, sort_keys=True, separators=(",", ":")),
            }
        )
    rows.sort(key=lambda row: row["source_record_id"])
    return rows, rejected


AT_LAYER_CONFIG = {
    "signalized-intersection": ("sig_pred", "sig_pred_table"),
    "non-signalized-intersection": ("jct_pred", "jct_pred_table"),
    "roadway-segment": ("seg_pred", "seg_pred_table"),
}


def normalize_expected_safety(
    features_by_kind: list[tuple[str, dict[str, Any]]],
    *,
    snapshot_id: str,
    retrieved_at: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    rejected: list[str] = []
    for facility_kind, feature in features_by_kind:
        model_prefix, table_prefix = AT_LAYER_CONFIG[facility_kind]
        properties = feature.get("properties") or {}
        source_id = properties.get(f"{model_prefix}.OBJECTID") or properties.get(
            f"{table_prefix}.OBJECTID"
        )
        if source_id is None or not feature.get("geometry"):
            rejected.append(str(source_id or "missing-id"))
            continue
        try:
            geometry = shape(feature["geometry"])
        except Exception:
            rejected.append(str(source_id))
            continue
        if geometry.is_empty or geometry.geom_type not in {"Point", "LineString", "MultiLineString"}:
            rejected.append(str(source_id))
            continue
        source_record_id = f"{facility_kind}:{source_id}"
        if facility_kind == "signalized-intersection":
            east_west = properties.get(f"{model_prefix}.ST_EW") or properties.get(
                f"{table_prefix}.ST_EW"
            )
            north_south = properties.get(f"{model_prefix}.ST_NS") or properties.get(
                f"{table_prefix}.ST_NS"
            )
            location_label = " / ".join(value for value in [east_west, north_south] if value)
        elif facility_kind == "roadway-segment":
            location_label = properties.get(f"{model_prefix}.ROUTE") or properties.get(
                f"{table_prefix}.ROUTE"
            )
        else:
            location_label = None
        rows.append(
            {
                "record_id": f"udot-at-intersection-safety:{source_record_id}",
                "source_key": "udot-at-intersection-safety",
                "source_record_id": source_record_id,
                "source_snapshot_id": snapshot_id,
                "retrieved_at": retrieved_at,
                "facility_kind": facility_kind,
                "provider_object_id": str(source_id),
                "city": properties.get(f"{model_prefix}.CITY")
                or properties.get(f"{table_prefix}.CITY"),
                "county": properties.get(f"{table_prefix}.COUNTY"),
                "location_label": location_label or None,
                "provider_pedestrian_all": _number(properties.get(f"{model_prefix}.P_All")),
                "provider_pedestrian_ksi": _number(properties.get(f"{model_prefix}.P_KA")),
                "provider_bicycle_all": _number(properties.get(f"{model_prefix}.B_All")),
                "provider_bicycle_ksi": _number(properties.get(f"{model_prefix}.B_KA")),
                "empirical_bayes_pedestrian_all": _number(
                    properties.get(f"{model_prefix}.P_All_EB")
                ),
                "empirical_bayes_pedestrian_ksi": _number(
                    properties.get(f"{model_prefix}.P_KA_EB")
                ),
                "empirical_bayes_bicycle_all": _number(
                    properties.get(f"{model_prefix}.B_All_EB")
                ),
                "empirical_bayes_bicycle_ksi": _number(
                    properties.get(f"{model_prefix}.B_KA_EB")
                ),
                "estimated_daily_pedestrian_volume": _number(
                    properties.get(f"{table_prefix}.AADP")
                ),
                "estimated_daily_bicycle_volume": _number(
                    properties.get(f"{table_prefix}.AADB")
                ),
                "aadt_major": _number(properties.get(f"{table_prefix}.AADT_MAJ")),
                "aadt_minor": _number(properties.get(f"{table_prefix}.AADT_MIN")),
                "aadt_segment": _number(properties.get(f"{table_prefix}.AADT")),
                "geometry": geometry.wkb,
                "attributes": json.dumps(properties, sort_keys=True, separators=(",", ":")),
            }
        )
    rows.sort(key=lambda row: row["source_record_id"])
    return rows, rejected


def normalize_aadt(
    features: list[dict[str, Any]],
    *,
    snapshot_id: str,
    retrieved_at: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    rejected: list[str] = []
    for feature in features:
        properties = feature.get("properties") or {}
        source_id = properties.get("OBJECTID")
        if source_id is None or not feature.get("geometry"):
            rejected.append(str(source_id or "missing-id"))
            continue
        try:
            geometry = shape(feature["geometry"])
        except Exception:
            rejected.append(str(source_id))
            continue
        if geometry.is_empty or geometry.geom_type not in {"LineString", "MultiLineString"}:
            rejected.append(str(source_id))
            continue
        attributes = json.dumps(properties, sort_keys=True, separators=(",", ":"))
        segment_has_measure = False
        for year in range(1981, 2025):
            aadt = _number(properties.get(f"AADT{year}"))
            if aadt is None:
                continue
            segment_has_measure = True
            source_record_id = f"{source_id}:{year}"
            rows.append(
                {
                    "record_id": f"udot-traffic:{source_record_id}",
                    "source_key": "udot-traffic",
                    "source_record_id": source_record_id,
                    "source_snapshot_id": snapshot_id,
                    "retrieved_at": retrieved_at,
                    "provider_segment_id": str(source_id),
                    "station": str(properties["Station"]) if properties.get("Station") is not None else None,
                    "route_id": properties.get("RouteID"),
                    "description": properties.get("DESC_"),
                    "begin_point": _number(properties.get("BeginPoint")),
                    "end_point": _number(properties.get("EndPoint")),
                    "section_length": _number(properties.get("SectionLength")),
                    "measure_year": year,
                    "aadt": aadt,
                    "single_unit_truck_share": _number(properties.get(f"SUTRK{year}")),
                    "combination_unit_truck_share": _number(properties.get(f"CUTRK{year}")),
                    "geometry": geometry.wkb,
                    "attributes": attributes,
                }
            )
        if not segment_has_measure:
            rejected.append(str(source_id))
    rows.sort(key=lambda row: (row["provider_segment_id"], row["measure_year"]))
    return rows, rejected


def normalize_at_counter_sites(
    features: list[dict[str, Any]],
    *,
    snapshot_id: str,
    retrieved_at: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    rejected: list[str] = []
    for feature in features:
        properties = feature.get("properties") or {}
        site_id = _integer(properties.get("unitid"))
        if site_id is None or not feature.get("geometry"):
            rejected.append(str(site_id or properties.get("OBJECTID") or "missing-id"))
            continue
        try:
            geometry = shape(feature["geometry"])
        except Exception:
            rejected.append(str(site_id))
            continue
        if geometry.is_empty or geometry.geom_type != "Point":
            rejected.append(str(site_id))
            continue
        source_record_id = str(site_id)
        rows.append(
            {
                "record_id": f"udot-at-counts:site:{source_record_id}",
                "source_key": "udot-at-counts",
                "source_record_id": f"site:{source_record_id}",
                "source_snapshot_id": snapshot_id,
                "retrieved_at": retrieved_at,
                "site_id": site_id,
                "name": properties.get("name"),
                "description": properties.get("descriptio"),
                "city": properties.get("city"),
                "county": properties.get("county"),
                "region": properties.get("region"),
                "travel_mode": properties.get("travelmode"),
                "first_data": properties.get("firstdata"),
                "last_data": properties.get("lastdata"),
                "granularity": properties.get("granularit"),
                "directionality": properties.get("directiona"),
                "geometry": geometry.wkb,
                "attributes": json.dumps(properties, sort_keys=True, separators=(",", ":")),
            }
        )
    rows.sort(key=lambda row: row["site_id"])
    return rows, rejected


def normalize_at_counter_observations(
    features: list[dict[str, Any]],
    *,
    snapshot_id: str,
    retrieved_at: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    from datetime import date

    rows: list[dict[str, Any]] = []
    rejected: list[str] = []
    for feature in features:
        properties = feature.get("properties") or {}
        object_id = properties.get("ObjectId")
        site_id = _integer(properties.get("siteId"))
        year = _integer(properties.get("year"))
        month = _integer(properties.get("month"))
        day = _integer(properties.get("dayofmonth"))
        count = _number(properties.get("count_sum"))
        if object_id is None or site_id is None or count is None:
            rejected.append(str(object_id or "missing-id"))
            continue
        try:
            observed_date = date(int(year), int(month), int(day))
        except (TypeError, ValueError):
            rejected.append(str(object_id))
            continue
        source_record_id = str(object_id)
        rows.append(
            {
                "record_id": f"udot-at-counts:observation:{source_record_id}",
                "source_key": "udot-at-counts",
                "source_record_id": f"observation:{source_record_id}",
                "source_snapshot_id": snapshot_id,
                "retrieved_at": retrieved_at,
                "site_id": site_id,
                "observed_date": observed_date,
                "travel_mode": properties.get("travelmode"),
                "commuting_period": properties.get("commuting_hours"),
                "count": count,
                "provider_domain": properties.get("domain_name"),
                "provider_weekday": _integer(properties.get("weekday")),
                "attributes": json.dumps(properties, sort_keys=True, separators=(",", ":")),
            }
        )
    rows.sort(key=lambda row: (row["site_id"], row["observed_date"], row["source_record_id"]))
    return rows, rejected


def normalize_traffic_study_measures(
    study: dict[str, Any],
    *,
    snapshot_id: str,
    retrieved_at: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    from datetime import date

    rows: list[dict[str, Any]] = []
    rejected: list[str] = []
    try:
        published_date = date.fromisoformat(study["publishedDate"])
        monitoring_start = date.fromisoformat(study["monitoringStart"])
        monitoring_end = date.fromisoformat(study["monitoringEnd"])
    except (KeyError, TypeError, ValueError):
        return [], ["study-dates"]
    for index, measure in enumerate(study.get("measures", []), start=1):
        required = ["id", "measureType", "statistic", "direction", "value", "unit", "sourcePage"]
        if any(measure.get(field) is None for field in required):
            rejected.append(str(measure.get("id") or f"measure-{index}"))
            continue
        source_record_id = f"{study['studyId']}:{measure['id']}"
        rows.append(
            {
                "record_id": f"provo-traffic-studies:{source_record_id}",
                "source_key": "provo-traffic-studies",
                "source_record_id": source_record_id,
                "source_snapshot_id": snapshot_id,
                "retrieved_at": retrieved_at,
                "study_id": study["studyId"],
                "study_title": study["title"],
                "published_date": published_date,
                "monitoring_start": monitoring_start,
                "monitoring_end": monitoring_end,
                "monitoring_hours": float(study["monitoringHours"]),
                "location_label": study["locationLabel"],
                "measure_type": measure["measureType"],
                "statistic": measure["statistic"],
                "direction": measure["direction"],
                "value": float(measure["value"]),
                "unit": measure["unit"],
                "source_page": int(measure["sourcePage"]),
                "review_status": measure.get("reviewStatus", "unreviewed"),
                "attributes": json.dumps(
                    {"providerLabel": measure.get("providerLabel")},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        )
    rows.sort(key=lambda row: row["source_record_id"])
    return rows, rejected


def normalize_police_mode(value: str) -> str:
    normalized = " ".join(value.strip().lower().split())
    if normalized == "bicycle":
        return "bicycle"
    if normalized in {"e-bike", "ebike", "electric bicycle", "electric pocket bike"}:
        return "electric-bicycle"
    if normalized == "electric wheelchair":
        return "mobility-device"
    if normalized == "pedestrian & electric scooter":
        return "pedestrian-and-scooter"
    if normalized in {
        "electric scooter",
        "motoroized foot scooter",
        "motorolized scooter",
        "scooter",
    }:
        return "scooter"
    if normalized == "electric bike or scooter, unknown":
        return "unknown-electric-micromobility"
    if normalized == "longboard":
        return "skateboard"
    return "other-micromobility"


def normalize_police_rows(
    source_rows: list[dict[str, Any]],
    *,
    snapshot_id: str,
    retrieved_at: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    rejected: list[str] = []
    for source in source_rows:
        incident_id = source.get("incident_id")
        observed_at = source.get("observed_at")
        mode_raw = source.get("mode_raw")
        if not incident_id or not isinstance(observed_at, datetime) or not mode_raw:
            rejected.append(str(incident_id or f"row-{source.get('source_row')}"))
            continue
        if observed_at.tzinfo is None:
            from zoneinfo import ZoneInfo

            observed_at = observed_at.replace(tzinfo=ZoneInfo("America/Denver"))
        source_record_id = str(incident_id).strip()
        attributes = {
            "unusedColumn": source.get("unused_column"),
            "hasLocation": bool(source.get("location_raw")),
        }
        rows.append(
            {
                "record_id": f"provo-police-incidents:{source_record_id}",
                "source_key": "provo-police-incidents",
                "source_record_id": source_record_id,
                "source_snapshot_id": snapshot_id,
                "retrieved_at": retrieved_at,
                "incident_id": source_record_id,
                "observed_at": observed_at,
                "location_raw": str(source["location_raw"]).strip()
                if source.get("location_raw")
                else None,
                "mode_raw": str(mode_raw).strip(),
                "mode_category": normalize_police_mode(str(mode_raw)),
                "severity": None,
                "event_type": None,
                "source_sheet": str(source["source_sheet"]),
                "source_table": str(source["source_table"]),
                "source_row": int(source["source_row"]),
                "attributes": json.dumps(attributes, sort_keys=True, separators=(",", ":")),
            }
        )
    rows.sort(key=lambda row: row["incident_id"])
    return rows, rejected
