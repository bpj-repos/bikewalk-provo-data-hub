"""Private, versioned incident observations and reviewed cross-source links."""
from __future__ import annotations

import argparse
import json
import subprocess
import shutil
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pyarrow.parquet as pq
from pyproj import Geod
from shapely import from_wkb

from .crash_portal import read_portal, enrich_state_records
from .config import DEFAULT_DATA_ROOT, DEFAULT_PRIVATE_DATA_ROOT
from .pipeline import import_udot_crashes, latest_artifact
from .util import isoformat, read_json, sha256_file, sha256_json, utc_now, write_json

LOCAL_ZONE = ZoneInfo("America/Denver")


def _date(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Observation timestamps must include a time zone")
    return result.astimezone(LOCAL_ZONE)


def observation_day(item):
    value = item['observedAt']
    if item['sourceKey'] == 'provo-police-incidents' and len(value) == 10:
        day = date.fromisoformat(value)
        meta = item['metadata']['observedAt']
        if meta['localDate'] != day.isoformat() or meta['localTime'] is not None or meta['utc'] is not None:
            raise ValueError('Conflicting date-only police observation')
        return day
    return _date(value).date()


def combine_observations(observations: list[dict], reviewed_links: list[dict]) -> dict:
    """Never infer identity: only explicit, reviewed links collapse observations."""
    by_id = {}
    for item in observations:
        identifier = item["id"]
        if identifier in by_id or identifier != f"{item['sourceKey']}:{item['sourceRecordId']}":
            raise ValueError("Observation IDs must be unique and source-namespaced")
        observation_day(item)
        if item["coordinates"] is not None:
            lng, lat = item["coordinates"]
            if not (-180 <= lng <= 180 and -90 <= lat <= 90):
                raise ValueError("Invalid observation coordinates")
        by_id[identifier] = item
    used = set()
    groups = []
    approved_pairs = set()
    for link in reviewed_links:
        police_id, udot_id = link["policeId"], link["udotId"]
        if (link.get("evidenceType") not in {"shared-identifier", "agency-crosswalk", "documentary-confirmation", "owner-authorized-circumstantial", "manual-case-review"}
                or not link.get("evidence")
                or not link.get("reviewer") or not link.get("reason") or not link.get("reviewedAt")
                or police_id not in by_id or udot_id not in by_id
                or by_id[police_id]["sourceKey"] != "provo-police-incidents"
                or by_id[udot_id]["sourceKey"] not in {"udot-crashes", "utah-crash-portal"}
                or police_id in used or udot_id in used):
            raise ValueError("Reviewed links require documented or owner-authorized strict-rule evidence, unused source IDs, and review provenance")
        if link['evidenceType'] == 'owner-authorized-circumstantial' and (
                link.get('rule') not in {'exact-clock-address','exact-clock'} or not link.get('reviewReportSha256') or not link.get('authorization')):
            raise ValueError('Circumstantial links require strict-rule report provenance and explicit owner authorization')
        if link['evidenceType'] == 'manual-case-review' and (
                link.get('confidence') not in {'strong','probable'} or not link.get('authorization')
                or not link.get('decisionReceiptSha256') or link.get('documentaryIdentityConfirmed') is not False):
            raise ValueError('Manual case review requires an authorized, graded decision receipt')
        _date(link["reviewedAt"])
        used.update([police_id, udot_id])
        approved_pairs.add((police_id, udot_id))
        state, police = by_id[udot_id], by_id[police_id]
        occurrence = state.get("statePortal") or state
        mode = police["metadata"].get("mode", {}).get("raw") or police.get("mode")
        resolved = {"occurredAt": occurrence["observedAt"], "occurrenceSource": occurrence["id"],
                    "coordinates": occurrence["coordinates"],
                    "coordinateSource": occurrence["id"] if occurrence["coordinates"] is not None else None,
                    "reportedTravelMode": mode, "modeSource": police_id}
        groups.append({"id": udot_id, "observations": [state, police], "reviewedLink": link, "resolvedCrash": resolved})
    groups.extend({"id": identifier, "observations": [item]} for identifier, item in by_id.items() if identifier not in used)

    geod = Geod(ellps="WGS84")
    udot = [item for item in observations if item["sourceKey"] in {"udot-crashes", "utah-crash-portal"}]
    candidates = []
    for police in (item for item in observations if item["sourceKey"] == "provo-police-incidents"):
        if police["coordinates"] is None:
            continue
        report_date = observation_day(police)
        for crash in udot:
            if (police["id"], crash["id"]) in approved_pairs:
                continue
            day_difference = abs((report_date - _date(crash["observedAt"]).date()).days)
            if day_difference > 1 or crash["coordinates"] is None:
                continue
            mode = police["mode"]
            if mode in {"bicycle", "electric-bicycle"} and "bicycle" not in crash["modes"]:
                continue
            if mode == "pedestrian-and-scooter" and "pedestrian" not in crash["modes"]:
                continue
            _, _, distance = geod.inv(*police["coordinates"], *crash["coordinates"])
            if distance <= 100:
                candidates.append({
                    "policeId": police["id"], "udotId": crash["id"],
                    "distanceMeters": round(distance, 1), "dateDifferenceDays": day_difference,
                    "status": "unreviewed", "method": "within-100m-and-one-calendar-day",
                })
    return {
        "records": sorted(groups, key=lambda group: group["id"]),
        "possibleMatches": sorted(candidates, key=lambda item: (item["policeId"], item["distanceMeters"], item["udotId"])),
        "counts": {"sourceObservations": len(observations), "records": len(groups),
                   "reviewedLinks": len(reviewed_links), "possibleMatches": len(candidates)},
    }


def check_managed_root(private_root):
    pointer = private_root / 'datastores/combined-incidents.json'
    if pointer.exists() and read_json(pointer).get('releaseManifest'):
        raise ValueError('Managed incident release: use python -m danger_zones.update_incidents; legacy rebuilds do not load staged cumulative inputs')


def build_snapshot(data_root: Path, private_root: Path, links_path: Path | None = None, portal_workbook: Path | None = None, advance_pointer: bool = True) -> dict:
    check_managed_root(private_root)
    crash_path = latest_artifact(data_root, "udot-crashes")
    police_path = private_root / "datastores/provo-police-incidents.json"
    police = read_json(police_path)
    if police["sourceKey"] != "provo-police-incidents" or police["storageClass"] != "private-owner-only":
        raise ValueError("Expected the private police datastore")
    manifest_path = data_root / "manifests/sources/udot-crashes" / f"{crash_path.parent.name}.json"
    crash_manifest = read_json(manifest_path)
    runs = [read_json(p) for p in (data_root / "runs").glob("udot-crashes-*.json")]
    run = max((r for r in runs if r.get("status") in {"accepted", "reused"}
               and r.get("snapshotId") == crash_path.parent.name), key=lambda r: r["completedAt"])
    expected_artifact = next(a for a in run["normalizedArtifacts"] if data_root / a["path"] == crash_path)
    if sha256_file(crash_path) != expected_artifact["sha256"]:
        raise ValueError("UDOT normalized artifact checksum mismatch")
    observations = []
    for row in pq.read_table(crash_path).to_pylist():
        if not (row["pedestrian_involved"] or row["bicyclist_involved"]):
            continue
        point = from_wkb(row["geometry"])
        observations.append({
            "id": f"udot-crashes:{row['crash_id']}", "sourceKey": "udot-crashes",
            "sourceRecordId": row["crash_id"], "sourceSnapshotId": row["source_snapshot_id"],
            "observedAt": isoformat(row["observed_at"]), "dateMeaning": "crash date/time",
            "coordinates": [point.x, point.y],
            "modes": [mode for mode, field in [("bicycle", "bicyclist_involved"), ("pedestrian", "pedestrian_involved")] if row[field]],
            "metadata": json.loads(row["attributes"]),
        })
    for row in police["records"]:
        geo = row["location"]["geocoding"]
        c = geo.get("coordinates")
        observations.append({
            "id": f"provo-police-incidents:{row['incidentId']}", "sourceKey": "provo-police-incidents",
            "sourceRecordId": row["incidentId"], "sourceSnapshotId": row["sourceVersions"][-1]["snapshotId"],
            "observedAt": row["observedAt"]["utc"] or row["observedAt"]["localDate"], "dateMeaning": "police workbook Date of Report",
            "coordinates": [c["lng"], c["lat"]] if c and geo["mapEligible"] else None,
            "mode": row["mode"]["category"], "metadata": row,
        })
    portal_pointer = private_root / "datastores/crash-portal.json"
    portal_source = None
    portal_summary = None
    if portal_workbook is None and portal_pointer.exists():
        cached = read_json(portal_pointer)
        portal_workbook = Path(cached["path"])
        if sha256_file(portal_workbook) != cached["sha256"]:
            raise ValueError("Stored portal workbook checksum mismatch")
    if portal_workbook:
        portal_records, portal_filters = read_portal(portal_workbook)
        digest = sha256_file(portal_workbook)
        retained = private_root / "sources/utah-crash-portal" / digest / "records.xlsx"
        retained.parent.mkdir(parents=True, exist_ok=True)
        if not retained.exists():
            shutil.copyfile(portal_workbook, retained)
        if sha256_file(retained) != digest:
            raise ValueError("Portal retained copy checksum mismatch")
        for row in portal_records:
            row["sourceSnapshotId"] = digest
        portal_summary = enrich_state_records(observations, portal_records)
        portal_source = {
            "sourceKey": "utah-crash-portal", "snapshotId": digest, "sha256": digest,
            "path": str(retained.resolve()), "checkedAt": isoformat(utc_now()),
            "sourceCurrentThrough": max(row["observedAt"] for row in portal_records),
            "warnings": [], "filters": portal_filters, **portal_summary,
        }
    if links_path is None:
        current_pointer = private_root / 'datastores/combined-incidents.json'
        prior_links = read_json(current_pointer).get('reviewedLinksSource') if current_pointer.exists() else None
        if prior_links:
            links_path = Path(prior_links['path'])
            if sha256_file(links_path) != prior_links['sha256']:
                raise ValueError('Persisted reviewed links checksum mismatch')
    reviewed_links = read_json(links_path) if links_path else []
    combined = combine_observations(observations, reviewed_links)
    sources = [
        {"sourceKey": "udot-crashes", "snapshotId": crash_path.parent.name,
         "path": str(crash_path.resolve()), "sha256": sha256_file(crash_path),
         "retrievedAt": crash_manifest["retrievedAt"], "checkedAt": run["completedAt"],
         "sourceCurrentThrough": crash_manifest["sourceCurrentThrough"], "warnings": run["warnings"]},
        {"sourceKey": "provo-police-incidents", "snapshotId": sha256_file(police_path),
         "path": str(police_path.resolve()), "sha256": sha256_file(police_path),
         "sourceCurrentThrough": police["sourceCurrentThrough"], "updatedAt": police["updatedAt"]},
    ]
    if portal_source:
        sources.append(portal_source)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent, text=True).strip()
    content = {"schemaVersion": 1, "storageClass": "private-owner-only", "producerCommit": commit,
               "toolSha256": sha256_file(Path(__file__)), "sources": sources, **combined, "statePortalSummary": portal_summary}
    snapshot_id = "combined-incidents-" + sha256_json(content)[:16]
    output = private_root / "combined-incidents/v1" / snapshot_id / "snapshot.json"
    if not output.exists():
        write_json(output, {"snapshotId": snapshot_id, "createdAt": isoformat(utc_now()),
                            "limitations": [
                                "Counts are source observations / reviewed groups, not deduplicated unique crashes while possible matches remain.",
                                "UDOT coverage uses pedestrian/bicyclist flags; scooters and other micromobility may be absent or categorized differently.",
                                "Query envelope includes neighboring jurisdictions; no exact municipal-boundary filtering is applied.",
                                "Police Date of Report is not necessarily crash date/time. Candidate links are suggestions, not identity evidence.",
                                "Additional sources require an explicit adapter that emits namespaced observations with provenance; never silently infer identity.",
                            ], **content})
    elif any(read_json(output).get(key) != value for key, value in content.items()):
        raise ValueError("Existing snapshot content mismatch")
    pointer = {"snapshotId": snapshot_id, "path": str(output.resolve()), "sha256": sha256_file(output), "counts": combined["counts"]}
    if links_path:
        pointer['reviewedLinksSource'] = {'path': str(links_path.resolve()), 'sha256': sha256_file(links_path)}
    if advance_pointer:
        write_json(private_root / "datastores/combined-incidents.json", pointer)
    if portal_source and advance_pointer:
        write_json(portal_pointer, portal_source)
    return pointer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--private-data-root", type=Path, default=DEFAULT_PRIVATE_DATA_ROOT)
    parser.add_argument("--refresh-udot", action="store_true", help="Check the public remote source before building; failure leaves current combined pointer unchanged")
    parser.add_argument("--portal-workbook", type=Path, help="Official Provo-filtered portal XLSX; accepted copy is retained and reused on later refreshes")
    parser.add_argument("--reviewed-links", type=Path, help="JSON array of explicit policeId/udotId/reviewer/reviewedAt/reason decisions")
    args = parser.parse_args()
    check_managed_root(args.private_data_root)
    if args.refresh_udot:
        import_udot_crashes(args.data_root)
    print(json.dumps(build_snapshot(args.data_root, args.private_data_root, args.reviewed_links, args.portal_workbook), indent=2))


if __name__ == "__main__":
    main()
