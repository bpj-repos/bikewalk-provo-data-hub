"""Read the official filtered XLSX and corroborate state crash identities."""
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import load_workbook
from pyproj import Geod
from .incident_conversions import temporal

ZONE = ZoneInfo("America/Denver")


def portal_time(value):
    if isinstance(value, datetime):
        result = value
    else:
        try:
            result = datetime.fromisoformat(str(value))
        except ValueError:
            parsed = temporal(str(value))
            result = datetime.fromisoformat(parsed['date'] + 'T' + (parsed['time'] or '00:00:00') + (parsed['offset'] or ''))
    return result.replace(tzinfo=ZONE) if result.tzinfo is None else result


def portal_tables(path, *, city, allow_county, validate):
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        tables = {}
        for name in ["Crashes", "Persons", "Vehicles", "Rollups", "Filters"]:
            sheet = workbook[name]
            sheet.reset_dimensions()  # R's XLSX writer emits an A1-only dimension.
            rows = iter(sheet.values)
            header = next(rows)
            if len(header) != len(set(header)):
                raise ValueError("Duplicate portal column names")
            if validate:
                from .field_inventory import read_catalog
                expected = read_catalog()['tables']['portal.' + name.lower()]['fields']
                if set(header) != set(expected):
                    raise ValueError('Portal column drift: ' + name)
            tables[name] = [dict(zip(header, row)) for row in rows]
        filters = {row["Filter"]: row["Value"] for row in tables["Filters"]}
        if filters.get("City") != city and not (allow_county and filters.get("City") == "All" and filters.get("Counties") == "Utah"):
            raise ValueError(f"Expected an explicitly filtered {city} city export")
        if validate and (filters.get('Vehicle Types') != 'All' or {x.strip() for x in filters.get('Crash Severity','').split(',')} != {'1','2','3','4','5'}):
            raise ValueError('Portal export must include all vehicle types and severities')
        if len({row["Crash_ID"] for row in tables["Crashes"]}) != len(tables["Crashes"]):
            raise ValueError("Duplicate portal crash identifiers")
        related = {}
        for name in ["Persons", "Vehicles", "Rollups"]:
            related[name] = defaultdict(list)
            for row in tables[name]:
                related[name][str(row.get("Crash_ID") or row.get("crash_id"))].append(row)
        if validate:
            ids = {str(row['Crash_ID']) for row in tables['Crashes']}
            for name in ['Persons', 'Vehicles', 'Rollups']:
                if any(str(row.get('Crash_ID') or row.get('crash_id')) not in ids for row in tables[name]):
                    raise ValueError('Orphan portal rows: ' + name)
        return tables, related, filters
    finally:
        workbook.close()


def read_portal(path: Path, *, include_all=False, allow_county=False, validate=False):
    tables, related, filters = portal_tables(path, city="Provo", allow_county=allow_county, validate=validate)
    records = []
    for crash in tables["Crashes"]:
        identifier = str(crash["Crash_ID"])
        if not identifier.isdecimal():
            raise ValueError("Invalid portal crash ID")
        people = related["Persons"][identifier]
        modes = set()
        involvement = [crash, *related["Rollups"][identifier]]
        if any(r.get("cyclist_involved") == "Y" for r in involvement) or any(str(p.get("personType")) == "4" or p.get("personType_label") == "Pedalcyclist" for p in people):
            modes.add("bicycle")
        if any(r.get("pedestrian_involved") == "Y" for r in involvement) or any(str(p.get("personType")) == "3" or p.get("personType_label") == "Pedestrian" for p in people):
            modes.add("pedestrian")
        if any(str(p.get("personType")) == "5" or str(p.get("personType_label", "")).startswith("Other Pedestrian") for p in people):
            modes.add("other-micromobility")
        if not modes and not include_all:
            continue
        coordinates = [float(crash["longitude"]), float(crash["latitude"])]
        if not (-180 <= coordinates[0] <= 180 and -90 <= coordinates[1] <= 90):
            raise ValueError("Invalid portal coordinates")
        records.append({
            "id": "utah-crash-portal:" + identifier, "sourceKey": "utah-crash-portal",
            "sourceRecordId": identifier, "observedAt": portal_time(crash["crashDateandTime"]).isoformat(),
            "dateMeaning": "state crash date/time in America/Denver",
            "timePrecision": temporal(crash['crashDateandTime'])['precision'],
            "coordinates": coordinates,
            "modes": sorted(modes),
            "metadata": {"crash": crash, "persons": people, "vehicles": related["Vehicles"][identifier],
                         "rollups": related["Rollups"][identifier]},
        })
    if not records and not include_all:
        raise ValueError("The export has no active transportation records")
    return records, filters


def state_join_evidence(existing, portal):
    """Shared state ID/time; road text can corroborate modest coordinate differences."""
    if existing['sourceRecordId'] != portal['sourceRecordId'] or portal.get('timePrecision', 'second') != 'second':
        return None
    delta = abs((portal_time(existing['observedAt']) - portal_time(portal['observedAt'])).total_seconds())
    distance = Geod(ellps='WGS84').inv(*existing['coordinates'], *portal['coordinates'])[2]
    left = ' '.join((existing.get('metadata', {}).get('MAIN_ROAD_NAME') or '').upper().split())
    right = ' '.join((portal.get('metadata', {}).get('crash', {}).get('roadName') or '').upper().split())
    same_road = bool(left) and left == right
    if delta > 1 or not (distance <= 10 or distance <= 100 and same_road):
        return None
    return {'method': 'same-state-crash-id-and-corroborated-time-location',
            'timeDifferenceSeconds': delta, 'distanceMeters': round(distance, 3),
            'roadTextAgreement': same_road, 'coordinateDisagreement': distance > 10}


def enrich_state_records(observations, portal_records):
    by_id = {o["sourceRecordId"]: o for o in observations if o["sourceKey"] == "udot-crashes"}
    geod = Geod(ellps="WGS84")
    joined, conflicts = 0, []
    for portal in portal_records:
        existing = by_id.get(portal["sourceRecordId"])
        if existing:
            evidence = state_join_evidence(existing, portal)
            if evidence:
                existing['statePortal'] = portal
                existing['stateJoinEvidence'] = evidence
                joined += 1
                continue
            conflicts.append(portal["sourceRecordId"])
        observations.append(portal)
    return {"joined": joined, "conflictingStateIds": conflicts, "portalRecords": len(portal_records)}
