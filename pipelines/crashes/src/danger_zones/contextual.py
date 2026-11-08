from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pyproj import Transformer
from shapely import from_wkb
from shapely.geometry import GeometryCollection, MultiPoint, Point
from shapely.ops import transform
from shapely.strtree import STRtree


def _intersection_points(geometry: Any) -> list[Point]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, Point):
        return [geometry]
    if isinstance(geometry, MultiPoint):
        return list(geometry.geoms)
    if isinstance(geometry, GeometryCollection):
        return [point for part in geometry.geoms for point in _intersection_points(part)]
    return []


def build_trail_road_crossings(
    trail_rows: list[dict[str, Any]],
    street_rows: list[dict[str, Any]],
    *,
    snapshot_id: str,
    retrieved_at: datetime,
) -> list[dict[str, Any]]:
    """Build geometry-only candidates. Grade separation remains explicitly unknown."""
    project = Transformer.from_crs(4326, 26912, always_xy=True).transform
    unproject = Transformer.from_crs(26912, 4326, always_xy=True).transform
    street_geometries = [transform(project, from_wkb(row["geometry"])) for row in street_rows]
    street_tree = STRtree(street_geometries)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, float, float]] = set()

    for trail_row in trail_rows:
        trail_geometry = transform(project, from_wkb(trail_row["geometry"]))
        for street_index in street_tree.query(trail_geometry, predicate="intersects"):
            index = int(street_index)
            street_row = street_rows[index]
            intersection = trail_geometry.intersection(street_geometries[index])
            for point in _intersection_points(intersection):
                wgs_point = transform(unproject, point)
                dedupe_key = (
                    trail_row["trail_id"],
                    street_row["segment_id"],
                    round(wgs_point.x, 6),
                    round(wgs_point.y, 6),
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                digest = hashlib.sha256("|".join(map(str, dedupe_key)).encode()).hexdigest()[:16]
                crossing_id = f"trail-road:{digest}"
                endpoint_touch = point.distance(trail_geometry.boundary) <= 1.5
                rows.append(
                    {
                        "record_id": f"provo-trails:{crossing_id}",
                        "source_key": "provo-trails",
                        "source_record_id": crossing_id,
                        "source_snapshot_id": snapshot_id,
                        "retrieved_at": retrieved_at,
                        "candidate_crossing_id": crossing_id,
                        "trail_id": trail_row["trail_id"],
                        "trail_name": trail_row["path_name"],
                        "street_segment_id": street_row["segment_id"],
                        "street_name": street_row["full_name"] or street_row["name"],
                        "intersection_kind": "trail-endpoint-touch" if endpoint_touch else "interior-line-crossing",
                        "grade_separation_status": "unknown-requires-verification",
                        "geometry": wgs_point.wkb,
                        "attributes": json.dumps(
                            {
                                "derivation": "planar line intersection",
                                "gradeSeparationStatus": "unknown-requires-verification",
                                "streetNetworkSnapshotId": street_row["source_snapshot_id"],
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    }
                )
    rows.sort(key=lambda row: row["source_record_id"])
    return rows
