from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import CRS
from shapely import from_wkb

from .util import sha256_file


def _geo_metadata(
    *,
    geometry_types: Iterable[str],
    bbox: list[float] | None,
    epsg: int,
) -> bytes:
    value: dict[str, Any] = {
        "version": "1.1.0",
        "primary_column": "geometry",
        "columns": {
            "geometry": {
                "encoding": "WKB",
                "geometry_types": sorted(set(geometry_types)),
                "crs": CRS.from_epsg(epsg).to_json_dict(),
            }
        },
    }
    if bbox:
        value["columns"]["geometry"]["bbox"] = bbox
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def write_geoparquet(
    path: Path,
    rows: list[dict[str, Any]],
    schema: pa.Schema,
    *,
    geometry_types: Iterable[str],
    bbox: list[float] | None,
    epsg: int = 4326,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = dict(schema.metadata or {})
    metadata[b"geo"] = _geo_metadata(geometry_types=geometry_types, bbox=bbox, epsg=epsg)
    metadata[b"danger_zones_schema_version"] = b"1"
    table = pa.Table.from_pylist(rows, schema=schema.with_metadata(metadata))
    temporary = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(
        table,
        temporary,
        compression="zstd",
        use_dictionary=True,
        write_statistics=True,
        version="2.6",
    )
    temporary.replace(path)
    return {"path": str(path), "rows": table.num_rows, "sha256": sha256_file(path)}


def write_parquet(path: Path, rows: list[dict[str, Any]], schema: pa.Schema) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(
        rows,
        schema=schema.with_metadata({b"danger_zones_schema_version": b"1"}),
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(
        table,
        temporary,
        compression="zstd",
        use_dictionary=True,
        write_statistics=True,
        version="2.6",
    )
    temporary.replace(path)
    return {"path": str(path), "rows": table.num_rows, "sha256": sha256_file(path)}


def parquet_geometry_summary(path: Path) -> dict[str, Any]:
    table = pq.read_table(path, columns=["geometry"])
    types: dict[str, int] = {}
    invalid = 0
    for value in table.column("geometry").to_pylist():
        try:
            geometry = from_wkb(value)
            name = geometry.geom_type
            types[name] = types.get(name, 0) + 1
            if not geometry.is_valid:
                invalid += 1
        except Exception:
            invalid += 1
    return {"rows": table.num_rows, "geometryTypes": types, "invalidGeometryCount": invalid}
