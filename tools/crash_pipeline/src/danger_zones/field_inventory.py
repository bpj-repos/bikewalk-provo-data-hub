"""Offline source-field profiling. Reads retained inputs and never links records."""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

import jsonschema
import pyarrow.parquet as pq
import yaml
from shapely import from_wkb

from .config import DEFAULT_DATA_ROOT, DEFAULT_PRIVATE_DATA_ROOT, PACKAGE_ROOT
from .pipeline import latest_artifact
from .police import _read_numbers, _read_xlsx
from .util import read_json, sha256_file, utc_now, isoformat, write_json

REPO = PACKAGE_ROOT.parent.parent
CATALOG = PACKAGE_ROOT / "catalog/incident-metadata/fields.yml"
SCHEMA = PACKAGE_ROOT / "schemas/incident-field-catalog.schema.json"


def occurrence_year(value):
    if isinstance(value, (datetime, date)):
        return value.year
    text = str(value or "").strip()
    try:
        if re.match(r"^\d{4}-\d{2}-\d{2}", text):
            return date.fromisoformat(text[:10]).year
        return datetime.strptime(text.split(" ")[0], "%m/%d/%Y").year
    except ValueError:
        return "unparsed"


def timestamp_format(value):
    if isinstance(value, datetime):
        return "native-datetime"
    if isinstance(value, (int, float)):
        return "numeric-provider-timestamp"
    text = str(value).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        if text.endswith((" AM", " PM")):
            return "iso-date-with-12-hour-time"
        if len(text) == 10:
            return "iso-date-only"
        return "iso-timestamp-with-offset" if re.search(r"(Z|[+-]\d{2}:\d{2})$", text) else "iso-timestamp-without-offset"
    if re.match(r"^\d{1,2}/\d{1,2}/\d{4}", text):
        return "us-date-with-12-hour-time" if ":" in text else "us-date-only"
    return "unrecognized"


def profile_field(rows, column, years, include_values=False, temporal=False):
    present = sum(column in row for row in rows)
    nulls = sum(column in row and row[column] is None for row in rows)
    blanks = sum(isinstance(row.get(column), str) and not row[column].strip() for row in rows)
    values = [row[column] for row in rows if column in row and row[column] is not None
              and not (isinstance(row[column], str) and not row[column].strip())]
    counts = Counter(json.dumps(value, sort_keys=True, default=str) for value in values)
    types = Counter(type(row[column]).__name__ for row in rows if column in row and row[column] is not None)
    grouped = defaultdict(list)
    for row, year in zip(rows, years, strict=True):
        grouped[str(year)].append(row)
    by_year = {}
    for year, items in sorted(grouped.items()):
        by_year[year] = {
            "rows": len(items), "present": sum(column in row for row in items),
            "null": sum(column in row and row[column] is None for row in items),
            "blank": sum(isinstance(row.get(column), str) and not row[column].strip() for row in items),
            "populated": sum(column in row and row[column] is not None and
                             not (isinstance(row[column], str) and not row[column].strip()) for row in items),
        }
    result = {
        "rows": len(rows), "present": present, "missingColumn": len(rows) - present,
        "null": nulls, "blank": blanks, "populated": len(values),
        "distinctPopulatedValues": len(counts), "observedTypes": dict(sorted(types.items())),
        "byYear": by_year,
    }
    if temporal:
        result["timestampFormats"] = dict(sorted(Counter(timestamp_format(v) for v in values).items()))
    if include_values and len(counts) <= 100:
        result["valueCounts"] = [{"value": json.loads(key), "count": count} for key, count in sorted(counts.items())]
    return result


def source_tables(data_root, private_root, *, with_locators=False):
    tables = {}
    crash_path = latest_artifact(data_root, "udot-crashes")
    crash_rows = pq.read_table(crash_path, columns=["source_layer_year", "attributes", "geometry"]).to_pylist()
    rows = [{**json.loads(row["attributes"]), "geometry": from_wkb(row["geometry"]).__geo_interface__}
            for row in crash_rows]
    tables["udot.arcgis"] = {
        "rows": rows, "years": [row["source_layer_year"] for row in crash_rows],
        "input": str(crash_path.relative_to(REPO)) if crash_path.is_absolute() else str(crash_path),
        "sha256": sha256_file(crash_path), "snapshotId": crash_path.parent.name,
    }

    for catalog_file in sorted((PACKAGE_ROOT / "catalog/provo-police-incidents").glob("*.json")):
        delivery = read_json(catalog_file)
        expected = delivery["sourceFile"]["sha256"]
        candidates = sorted((private_root / "sources/provo-police-incidents").rglob(delivery["sourceFile"]["storedFilename"]))
        path = next((p for p in candidates if sha256_file(p) == expected and p.parent.name == delivery["snapshotId"]), None)
        if path is None:
            raise ValueError(f"Missing verified police input for {delivery['snapshotId']}")
        source_rows, _ = (_read_numbers(path) if path.suffix == ".numbers" else _read_xlsx(path))
        key = "police.numbers" if path.suffix == ".numbers" else "police.xlsx"
        headers = source_rows[0]["source_headers"]
        width = max(len(row["source_cells"]) for row in source_rows)
        columns = headers if headers else [f"column_{i + 1}" for i in range(width)]
        values = [{name: row["source_cells"][i] if i < len(row["source_cells"]) else None
                   for i, name in enumerate(columns)} for row in source_rows]
        tables[key] = {"rows": values, "years": [row["observed_at"].year for row in source_rows],
                       "input": str(path), "sha256": expected, "snapshotId": delivery["snapshotId"]}

        if with_locators:
            tables[key]["receivedAt"] = delivery["receivedAt"]
            tables[key]["locators"] = [{"sheet": row["source_sheet"], "table": row["source_table"], "row": row["source_row"]} for row in source_rows]

    if with_locators:
        tables["udot.arcgis"]["locators"] = [{"parquetRow": i, "layerYear": row["source_layer_year"]} for i, row in enumerate(crash_rows)]

    pointer = read_json(private_root / "datastores/crash-portal.json")
    portal_path = Path(pointer["path"])
    if sha256_file(portal_path) != pointer["sha256"]:
        raise ValueError("Portal workbook checksum mismatch")
    from openpyxl import load_workbook
    workbook = load_workbook(portal_path, read_only=True, data_only=True)
    try:
        portal = {}
        for sheet in workbook:
            sheet.reset_dimensions()
            values = iter(sheet.values)
            headers = list(next(values))
            if len(headers) != len(set(headers)):
                raise ValueError(f"Repeated headers in {sheet.title}")
            portal[sheet.title] = [dict(zip(headers, row)) for row in values]
        crash_years = {str(row["Crash_ID"]): occurrence_year(row["crashDateandTime"]) for row in portal["Crashes"]}
        for name, values in portal.items():
            years = [crash_years.get(str(row.get("Crash_ID") or row.get("crash_id")), "not-applicable")
                     for row in values]
            tables["portal." + name.lower()] = {
                "rows": values, "years": years, "input": str(portal_path.relative_to(REPO)),
                "sha256": pointer["sha256"], "snapshotId": pointer["snapshotId"],
            }
            if with_locators:
                tables["portal." + name.lower()]["sourceCheckedAt"] = pointer["checkedAt"]
                tables["portal." + name.lower()]["retrievedAt"] = None
                tables["portal." + name.lower()]["locators"] = [{"sheet": name, "row": i + 2} for i in range(len(values))]
    finally:
        workbook.close()
    for table in tables.values():
        path = Path(table["input"])
        if path.is_absolute():
            table["input"] = str(path.relative_to(REPO))
    return tables


def inventory(catalog, tables):
    concepts = catalog["concepts"]
    fields = []
    code_labels = []
    aliases = []
    for table_id, table in tables.items():
        definitions = catalog["tables"][table_id]["fields"]
        observed = {key for row in table["rows"] for key in row}
        undocumented = observed - definitions.keys()
        absent = definitions.keys() - observed
        if undocumented or absent:
            raise ValueError(f"Catalog drift in {table_id}: undocumented={sorted(undocumented)}, absent={sorted(absent)}")
        for column, binding in definitions.items():
            if binding["concept"] not in concepts:
                raise ValueError(f"Unknown concept {binding['concept']}")
            fields.append({
                "id": table_id + "." + column, "table": table_id, "column": column, **binding,
                "profile": profile_field(table["rows"], column, table["years"],
                                         binding["representation"] in {"code", "flag", "label"},
                                         binding["representation"] == "timestamp"),
            })
        for left, right in catalog["tables"][table_id].get("aliasPairs", []):
            if left not in definitions or right not in definitions:
                raise ValueError("Alias field is absent from the catalog")
            both = [row for row in table["rows"] if row.get(left) is not None and row.get(right) is not None]
            aliases.append({"table": table_id, "left": left, "right": right,
                            "jointlyPopulated": len(both), "equalOriginalValues": sum(row[left] == row[right] for row in both),
                            "differentOriginalValues": sum(row[left] != row[right] for row in both),
                            "oneSidedNull": sum((row.get(left) is None) != (row.get(right) is None) for row in table["rows"])})
        for pair in catalog["tables"][table_id].get("codeLabelPairs", []):
            code, label = pair
            if code not in definitions or label not in definitions:
                raise ValueError("Code/label pair field is absent from catalog")
            counts = Counter((json.dumps(row.get(code), default=str), json.dumps(row.get(label), default=str), str(year))
                             for row, year in zip(table["rows"], table["years"], strict=True))
            code_labels.append({"table": table_id, "codeField": code, "labelField": label,
                                "observedPairs": [{"code": json.loads(c), "label": json.loads(label_value),
                                                  "year": year, "count": count}
                                                 for (c, label_value, year), count in sorted(counts.items())]})
    groups = defaultdict(list)
    for field in fields:
        groups[field["concept"]].append(field)
    matches = []
    for concept, bindings in sorted(groups.items()):
        sources = sorted({catalog["tables"][b["table"]]["source"] for b in bindings})
        if len(bindings) > 1:
            matches.append({"concept": concept, "entity": concepts[concept]["entity"],
                            "crossSource": len(sources) > 1, "sources": sources,
                            "bindings": [{"field": b["id"], "relationship": b["relationship"],
                                          "representation": b["representation"]} for b in bindings]})
    relationship_checks = {}
    if {"portal.crashes", "portal.persons", "portal.vehicles", "portal.rollups"}.issubset(tables):
        crash_ids = {row["Crash_ID"] for row in tables["portal.crashes"]["rows"]}
        for table in ["portal.persons", "portal.vehicles", "portal.rollups"]:
            relationship_checks[table + ".orphanCrashReferences"] = sum(row["Crash_ID"] not in crash_ids for row in tables[table]["rows"])
        vehicle_keys = Counter((row["Crash_ID"], row["vehicleNumber"]) for row in tables["portal.vehicles"]["rows"])
        relationship_checks["portal.vehicles.duplicateCompoundKeys"] = sum(count - 1 for count in vehicle_keys.values() if count > 1)
        relationship_checks["portal.persons.nullVehicleReferences"] = sum(row["vehicleNumber"] is None for row in tables["portal.persons"]["rows"])
        relationship_checks["portal.persons.unmatchedPopulatedVehicleReferences"] = sum(row["vehicleNumber"] is not None and (row["Crash_ID"], row["vehicleNumber"]) not in vehicle_keys for row in tables["portal.persons"]["rows"])
    return {
        "schemaVersion": 1, "catalogVersion": catalog["version"],
        "tables": {key: {k: v for k, v in value.items() if k not in {"rows", "years"}} |
                   {"rows": len(value["rows"]), "columns": len(catalog["tables"][key]["fields"])}
                   for key, value in tables.items()},
        "concepts": concepts, "fields": fields, "matches": matches, "observedCodeLabels": code_labels,
        "sourceRelationshipChecks": relationship_checks, "aliasComparisons": aliases, "conceptRelations": catalog["conceptRelations"], "knownGaps": catalog["knownGaps"],
    }


def write_outputs(result, output):
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "inventory.json", result)
    write_json(output / "observed-code-labels.json", result["observedCodeLabels"])
    with (output / "fields.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["field", "concept", "representation", "relationship", "rows", "populated", "null", "blank",
                         "missing_column", "distinct_values", "observed_types", "definition", "notes"])
        for field in result["fields"]:
            p = field["profile"]
            writer.writerow([field["id"], field["concept"], field["representation"], field["relationship"],
                             p["rows"], p["populated"], p["null"], p["blank"], p["missingColumn"],
                             p["distinctPopulatedValues"], "|".join(p["observedTypes"]),
                             result["concepts"][field["concept"]]["definition"], field.get("notes", "")])
    with (output / "matches.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["concept", "entity", "cross_source", "fields", "relationships"])
        for match in result["matches"]:
            writer.writerow([match["concept"], match["entity"], match["crossSource"],
                             " | ".join(b["field"] for b in match["bindings"]),
                             " | ".join(b["relationship"] for b in match["bindings"])])
    bindings_by_concept = defaultdict(list)
    for field in result["fields"]:
        bindings_by_concept[field["concept"]].append(field["id"])
    with (output / "related-fields.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["from_concept", "to_concept", "relationship", "from_fields", "to_fields", "reason"])
        for relation in result["conceptRelations"]:
            writer.writerow([relation["from"], relation["to"], relation["relationship"],
                             " | ".join(bindings_by_concept[relation["from"]]),
                             " | ".join(bindings_by_concept[relation["to"]]), relation["reason"]])
    match_lines = ["# Metadata field matches", "",
                   "Shared concepts identify candidate semantic matches. Representations, entity grain, rule versions and missingness must be retained when normalizing.", "",
                   "| Concept | Definition | Fields across sources | Binding relationships |",
                   "| --- | --- | --- | --- |"]
    for match in result["matches"]:
        if match["crossSource"]:
            match_lines.append("| " + match["concept"] + " | " + result["concepts"][match["concept"]]["definition"] +
                               " | " + "<br>".join(b["field"] for b in match["bindings"]) +
                               " | " + ", ".join(sorted({b["relationship"] for b in match["bindings"]})) + " |")
    match_lines += ["", "## Related concepts requiring a transformation or review", "",
                    "| From | To | Relationship | Reason |", "| --- | --- | --- | --- |"]
    for relation in result["conceptRelations"]:
        match_lines.append(f"| {relation['from']} | {relation['to']} | {relation['relationship']} | {relation['reason']} |")
    (output / "matches.md").write_text("\n".join(match_lines) + "\n")
    lines = ["# Incident source inventory", "", "Generated offline from retained, checksum-verified inputs.",
             "", "Field equivalence describes metadata concepts. Record linking remains paused.", "",
             "| Table | Rows | Columns |", "| --- | ---: | ---: |"]
    for table, data in result["tables"].items():
        lines.append(f"| {table} | {data['rows']:,} | {data['columns']} |")
    for table in result["tables"]:
        lines += ["", "## " + table, "", "| Column | Populated / rows | Concept | Relationship |",
                  "| --- | ---: | --- | --- |"]
        for f in result["fields"]:
            if f["table"] == table:
                lines.append(f"| {f['column']} | {f['profile']['populated']:,} / {f['profile']['rows']:,} | {f['concept']} | {f['relationship']} |")
    (output / "inventory.md").write_text("\n".join(lines) + "\n")


def read_catalog(path=CATALOG):
    catalog = yaml.safe_load(path.read_text())
    jsonschema.Draft202012Validator(read_json(SCHEMA)).validate(catalog)
    for concept in catalog["concepts"].values():
        for reference in concept["references"]:
            if reference["reference"] not in catalog["references"]:
                raise ValueError("Concept has an unknown reference")
    for relation in catalog["conceptRelations"]:
        if relation["from"] not in catalog["concepts"] or relation["to"] not in catalog["concepts"]:
            raise ValueError("Relationship references an unknown concept")
    for reference in catalog["references"].values():
        if sha256_file(PACKAGE_ROOT / reference["capture"]) != reference["sha256"]:
            raise ValueError(f"Reference capture checksum mismatch: {reference['capture']}")
    for table in catalog["tables"].values():
        for binding in table["fields"].values():
            if binding["concept"] not in catalog["concepts"]:
                raise ValueError("Binding references an unknown concept")
    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--private-data-root", type=Path, default=DEFAULT_PRIVATE_DATA_ROOT)
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-catalog", action="store_true", help="Validate definitions and reference captures without private inputs")
    args = parser.parse_args()
    if args.output and args.output.resolve().is_relative_to((REPO / "apps/maps").resolve()):
        raise ValueError("Inventory outputs belong outside the public application")
    catalog = read_catalog(args.catalog)
    if args.check_catalog:
        print(json.dumps({"ok": True, "concepts": len(catalog["concepts"]), "tables": len(catalog["tables"])}))
        return
    if args.output is None:
        parser.error("--output is required for source profiling")
    result = inventory(catalog, source_tables(args.data_root, args.private_data_root))
    result["generatedAt"] = isoformat(utc_now())
    result["catalogSha256"] = sha256_file(args.catalog)
    result["scriptSha256"] = sha256_file(Path(__file__))
    write_outputs(result, args.output)
    print(json.dumps({"tables": len(result["tables"]), "fields": len(result["fields"]),
                      "concepts": len(result["concepts"]),
                      "crossSourceConcepts": sum(m["crossSource"] for m in result["matches"]),
                      "output": str(args.output)}))


if __name__ == "__main__":
    main()
