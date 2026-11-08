from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from numbers_parser import Document
from openpyxl import load_workbook
from openpyxl.utils.cell import range_boundaries

from .config import DEFAULT_DATA_ROOT
from .geoparquet import write_parquet
from .normalize import POLICE_INCIDENT_SCHEMA, normalize_police_rows
from .pipeline import _artifact_entry, _finalize_raw_snapshot, _write_run_report, latest_artifact
from .police_datastore import (
    DEFAULT_DATASTORE_RELATIVE_PATH,
    MapTilerPoliceGeocoder,
    StreetIntersectionGeocoder,
    maptiler_api_key,
    merge_police_incident_datastore,
)
from .util import isoformat, sha256_file, sha256_json, timestamp_slug, utc_now


POLICE_HEADER_ALIASES = {
    "incident_id": {"case number", "case", "incident id", "incident number"},
    "observed_at": {"date of report", "report date", "date", "observed at"},
    "location_raw": {"address", "location", "incident location"},
    "mode_raw": {"type", "mode", "travel mode", "active transportation type"},
}


def _normalized_header(value: Any) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split())


def _police_column_mapping(headers: list[Any]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    normalized = [_normalized_header(value) for value in headers]
    for field, aliases in POLICE_HEADER_ALIASES.items():
        matches = [index for index, value in enumerate(normalized) if value in aliases]
        if len(matches) != 1:
            raise ValueError(
                f"Expected one {field} column, found {len(matches)} in headers: {headers}"
            )
        mapping[field] = matches[0]
    return mapping


def _source_row_from_values(
    values: list[Any],
    *,
    headers: list[Any],
    mapping: dict[str, int],
    sheet_name: str,
    table_name: str,
    row_number: int,
    source_format: str,
) -> dict[str, Any]:
    padded = list(values) + [None] * max(0, len(headers) - len(values))
    return {
        "source_cells": list(values),
        "source_headers": [str(value or "") for value in headers],
        "source_format": source_format,
        "incident_id": padded[mapping["incident_id"]],
        "observed_at": padded[mapping["observed_at"]],
        "location_raw": padded[mapping["location_raw"]],
        "mode_raw": padded[mapping["mode_raw"]],
        "unused_column": padded[4] if len(padded) > 4 else None,
        "source_sheet": sheet_name,
        "source_table": table_name,
        "source_row": row_number,
    }


def _read_numbers(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    document = Document(str(path))
    rows: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    for sheet in document.sheets:
        for table in sheet.tables:
            values = table.rows(values_only=True)
            tables.append(
                {
                    "sheet": sheet.name,
                    "table": table.name,
                    "rows": len(values),
                    "columns": max((len(row) for row in values), default=0),
                }
            )
            for row_number, value in enumerate(values, start=1):
                padded = list(value) + [None] * max(0, 5 - len(value))
                if not any(item is not None for item in padded):
                    continue
                rows.append(
                    {
                        "source_cells": list(value),
                        "source_headers": [],
                        "source_format": "numbers",
                        "incident_id": padded[0],
                        "observed_at": padded[1],
                        "location_raw": padded[2],
                        "mode_raw": padded[3],
                        "unused_column": padded[4],
                        "source_sheet": sheet.name,
                        "source_table": table.name,
                        "source_row": row_number,
                    }
                )
    return rows, tables


def _read_xlsx(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    workbook = load_workbook(path, data_only=False, read_only=False)
    rows: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    try:
        for sheet in workbook.worksheets:
            sheet_tables = list(sheet.tables.values())
            regions = [
                (table.name, *range_boundaries(table.ref))
                for table in sheet_tables
            ]
            if not regions:
                min_column, min_row, max_column, max_row = range_boundaries(
                    sheet.calculate_dimension()
                )
                if not any(
                    sheet.cell(row=row, column=column).value is not None
                    for row in range(min_row, max_row + 1)
                    for column in range(min_column, max_column + 1)
                ):
                    continue
                regions = [("UsedRange", min_column, min_row, max_column, max_row)]
            for table_name, min_column, min_row, max_column, max_row in regions:
                headers = [
                    sheet.cell(row=min_row, column=column).value
                    for column in range(min_column, max_column + 1)
                ]
                mapping = _police_column_mapping(headers)
                data_row_count = 0
                for row_number in range(min_row + 1, max_row + 1):
                    values = [
                        sheet.cell(row=row_number, column=column).value
                        for column in range(min_column, max_column + 1)
                    ]
                    if not any(value is not None for value in values):
                        continue
                    rows.append(
                        _source_row_from_values(
                            values,
                            headers=headers,
                            mapping=mapping,
                            sheet_name=sheet.title,
                            table_name=table_name,
                            row_number=row_number,
                            source_format="xlsx",
                        )
                    )
                    data_row_count += 1
                tables.append(
                    {
                        "sheet": sheet.title,
                        "table": table_name,
                        "rows": data_row_count,
                        "columns": max_column - min_column + 1,
                        "headers": [str(value or "") for value in headers],
                    }
                )
    finally:
        workbook.close()
    return rows, tables


def import_police_workbook(
    path: Path,
    private_data_root: Path,
    *,
    data_root: Path = DEFAULT_DATA_ROOT,
    datastore_path: Path | None = None,
    geocode: bool = False,
) -> dict[str, Any]:
    source_format = path.suffix.lower().lstrip(".")
    if source_format not in {"numbers", "xlsx"}:
        raise ValueError("The police importer accepts Apple Numbers or Excel .xlsx workbooks")
    if not path.is_file():
        raise FileNotFoundError(path)
    started_at = utc_now()
    staging = (
        private_data_root
        / ".staging"
        / f"provo-police-incidents-{timestamp_slug(started_at)}"
    )
    raw = staging / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    copied_path = raw / f"police-incidents.{source_format}"
    shutil.copyfile(path, copied_path)
    workbook_sha256 = sha256_file(copied_path)

    source_rows, table_inventory = (
        _read_numbers(copied_path)
        if source_format == "numbers"
        else _read_xlsx(copied_path)
    )
    for source_row in source_rows:
        source_row["source_file_name"] = path.name
        source_row["source_format"] = source_format
    completed_at = utc_now()
    schema_fingerprint = sha256_json(
        {
            "contract": [
                "incident_id",
                "observed_at",
                "location_raw",
                "mode_raw",
                "unused_column",
                "source_cells",
            ],
            "tables": table_inventory,
        }
    )
    content_fingerprint = sha256_json(
        {
            "schemaFingerprint": schema_fingerprint,
            "rows": sorted(source_rows, key=lambda row: str(row.get("incident_id"))),
        }
    )
    observed_dates = [
        row["observed_at"] for row in source_rows if isinstance(row.get("observed_at"), datetime)
    ]
    source_current_through = None
    if observed_dates:
        latest_observed = max(observed_dates)
        if latest_observed.tzinfo is None:
            latest_observed = latest_observed.replace(tzinfo=ZoneInfo("America/Denver"))
        source_current_through = isoformat(latest_observed)
    warnings = [
        "The workbook does not provide severity or event type.",
        "Original typed cell values are retained in the private JSON datastore alongside normalized fields.",
    ]
    missing_locations = sum(not row.get("location_raw") for row in source_rows)
    if missing_locations:
        warnings.append(f"{missing_locations} record has no incident location.")
    snapshot_id, _, manifest, raw_reused = _finalize_raw_snapshot(
        data_root=private_data_root,
        source_key="provo-police-incidents",
        staging_raw=raw,
        retrieved_at=started_at,
        retrieval_completed_at=completed_at,
        source_current_through=source_current_through,
        source_crs=None,
        record_count=len(source_rows),
        schema_fingerprint=schema_fingerprint,
        content_fingerprint=content_fingerprint,
        extent=None,
        warnings=warnings,
    )
    rows, rejected = normalize_police_rows(
        source_rows, snapshot_id=snapshot_id, retrieved_at=started_at
    )
    output_path = (
        private_data_root
        / "normalized"
        / "provo-police-incidents"
        / "v1"
        / snapshot_id
        / "records.parquet"
    )
    normalized_reused = output_path.exists()
    if not normalized_reused:
        write_parquet(output_path, rows, POLICE_INCIDENT_SCHEMA)
    incident_ids = [row["incident_id"] for row in rows]
    duplicate_count = len(incident_ids) - len(set(incident_ids))
    checks = [
        {
            "name": "record-reconciliation",
            "status": "passed" if len(rows) + len(rejected) == len(source_rows) else "failed",
            "detail": f"{len(rows)} normalized, {len(rejected)} rejected, {len(source_rows)} raw",
        },
        {
            "name": "incident-id-uniqueness",
            "status": "passed" if duplicate_count == 0 else "failed",
            "detail": f"{duplicate_count} duplicate incident IDs",
        },
        {
            "name": "location-completeness",
            "status": "passed" if missing_locations == 0 else "warning",
            "detail": f"{missing_locations} records without a location",
        },
        {
            "name": "restricted-storage",
            "status": "passed",
            "detail": "Raw and normalized records are stored under the separate private data root",
        },
    ]
    if any(check["status"] == "failed" for check in checks):
        raise ValueError(f"Police workbook validation failed: {checks}")

    destination = datastore_path or (private_data_root / DEFAULT_DATASTORE_RELATIVE_PATH)
    intersection_geocoder = None
    provider_geocoder = None
    if geocode:
        key = maptiler_api_key()
        if not key:
            raise ValueError(
                "MAPTILER_API_KEY or NEXT_PUBLIC_MAPTILER_API_KEY is required with --geocode"
            )
        try:
            intersection_geocoder = StreetIntersectionGeocoder(
                latest_artifact(data_root, "provo-streets")
            )
        except FileNotFoundError:
            warnings.append(
                "The Provo street-network artifact was unavailable; intersection locations used provider matching."
            )
        provider_geocoder = MapTilerPoliceGeocoder(key)
    datastore, datastore_summary = merge_police_incident_datastore(
        source_rows,
        datastore_path=destination,
        snapshot_id=snapshot_id,
        retrieved_at=started_at,
        source_current_through=source_current_through,
        workbook_sha256=workbook_sha256,
        source_file_name=path.name,
        source_format=source_format,
        intersection_geocoder=intersection_geocoder,
        provider_geocoder=provider_geocoder,
    )
    warnings.append(
        f"{datastore['counts']['mapEligible']} of {datastore['counts']['records']} cumulative records have accepted map coordinates."
    )
    report = _write_run_report(
        data_root=private_data_root,
        source_key="provo-police-incidents",
        snapshot_id=snapshot_id,
        started_at=started_at,
        raw_count=manifest["recordCount"],
        normalized_count=len(rows),
        rejected_count=len(rejected),
        artifacts=[
            _artifact_entry(output_path, private_data_root, len(rows)),
            _artifact_entry(destination, private_data_root, len(datastore["records"])),
        ],
        checks=checks,
        warnings=warnings,
        reused=(
            raw_reused
            and normalized_reused
            and datastore_summary["added"] == 0
            and datastore_summary["updated"] == 0
        ),
    )
    return {
        "manifest": manifest,
        "report": report,
        "normalizedPath": output_path,
        "datastorePath": destination,
        "datastoreSummary": datastore_summary,
        "tableInventory": table_inventory,
    }
