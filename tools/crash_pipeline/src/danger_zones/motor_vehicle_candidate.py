"""Build a private annual candidate from pinned, full Provo portal workbook receipts."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from .crash_portal import read_portal
from .util import sha256_file

DATASET = "annual-motor-vehicle-crashes-without-nonmotorists"
PERSON = {"1": "Driver", "2": "Passenger", "3": "Pedestrian", "4": "Pedalcyclist",
          "5": "Other Pedestrian (wheelchair, skater, personal conveyance, etc.)"}
FIELDS = [
    {"name": "year", "type": "integer", "description": "Local calendar year of the portal crash date."},
    {"name": "crashes", "type": "integer", "description": "Distinct Provo state crash IDs meeting the candidate rule."},
    {"name": "complete_year", "type": "boolean", "description": "Year treated as a full calendar year in this series."},
]
METHOD = """One crash counts once by state crash ID. Use full Provo city portal receipts in managed intake order.
A newer delivery replaces overlapping records and preserves earlier history outside its delivery.
Include any reported motor vehicle type, including trucks and motorcycles, and single-vehicle crashes.
Require a positive reported vehicle count, a matching roster of distinct vehicle units, known driver/passenger
roles linked to those units, and explicit negative pedestrian and cyclist involvement for both flags
in the available crash or rollup fields. For this conservative candidate, each vehicle unit must have
a linked reported occupant. An unoccupied or incompletely documented vehicle goes to review.
A directly reported nonmotorist or corroborated positive involvement flag excludes the crash. Contradictory
flags, uncertain roles, incomplete rosters and otherwise insufficient participant evidence go to private review.
The portal export supplies recorded participants and has no independent participant-completeness indicator.
Counts describe reported crashes meeting this rule. The most recent year is partial. A covered year with
no included crashes has a zero; a year with no city records has no row.
"""


def classify(meta):
    crash, people, vehicles = meta["crash"], meta["persons"], meta["vehicles"]
    sources = [crash, *meta["rollups"]]
    flags = [{s.get(key) for s in sources if s.get(key) not in (None, "")}
             for key in ("cyclist_involved", "pedestrian_involved")]
    roles = {str(p.get("personType")) for p in people}
    labels_agree = all(PERSON.get(str(p.get("personType"))) == p.get("personType_label")
                       and str(p.get("personType")) in PERSON for p in people)
    if not labels_agree:
        return "unresolved", "unmapped or inconsistent participant role"
    if roles & {"3", "4", "5"}:
        return "excluded", "reported nonmotorist participant"
    if any(f - {"N", "Y"} or f == {"N", "Y"} for f in flags):
        return "unresolved", "conflicting or unrecognized involvement flags"
    if any("Y" in f for f in flags):
        if people:
            return "unresolved", "positive nonmotorist flag with only reported motorists"
        return "excluded", "positive nonmotorist flag"
    if not people:
        return "unresolved", "missing participant roster"
    if any(f != {"N"} for f in flags):
        return "unresolved", "missing negative involvement flag"
    n = str(crash.get("numberOfVehicles"))
    if not n.isdecimal() or int(n) < 1 or int(n) != len(vehicles):
        return "unresolved", "missing or inconsistent vehicle count"
    units = {str(v.get("vehicleNumber")) for v in vehicles}
    if len(units) != len(vehicles) or any(not u.isdecimal() or int(u) < 1 for u in units):
        return "unresolved", "incomplete vehicle roster"
    if units != {str(p.get("vehicleNumber")) for p in people}:
        return "unresolved", "incomplete participant-to-vehicle links"
    return "included", "motorists only"


def json_file(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build(manifest_path, manifest_hash, receipts, output, complete_through):
    repo = Path(__file__).resolve().parents[4]
    output = output.resolve()
    if output.is_relative_to(repo) and not output.is_relative_to(repo / "private"):
        raise ValueError("Use the ignored private directory or a private location outside the hub")
    if output.exists():
        raise FileExistsError(output)
    data = manifest_path.read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest_hash:
        raise ValueError("Private manifest checksum mismatch")
    manifest = json.loads(data)
    rows = {}
    deliveries = []
    for source in manifest["inputs"]:
        if source.get("kind") != "portal" or source.get("scope") != "collection":
            continue
        digest = source["sha256"]
        if not re.fullmatch("[0-9a-f]{64}", digest) or any(d["sha256"] == digest for d in deliveries):
            raise ValueError("Invalid or repeated city receipt")
        path = receipts / digest / "records.xlsx"
        if sha256_file(path) != digest:
            raise ValueError("City workbook checksum mismatch")
        records, filters = read_portal(path, include_all=True, validate=True)
        if filters != source["filters"] or filters["City"] != "Provo":
            raise ValueError("City workbook scope differs from its pinned receipt")
        required = {"Age Range": "All Ages Included", "Agency": "All", "Counties": "All",
                    "Days": "Mon, Tue, Wed, Thu, Fri, Sat, Sun", "Hours": "12:00 AM to 11:59 PM",
                    "Months": "All Months", "Number of Vehicles": "All Vehicle Counts Included"}
        if any(filters.get(k) != v for k, v in required.items()):
            raise ValueError("City receipt contains an unreviewed source filter")
        for record in records:
            key = record["sourceRecordId"]
            if record["metadata"]["crash"]["City_Geo"] != "Provo":
                rows.pop(key, None)
                continue
            status, reason = classify(record["metadata"])
            rows[key] = (record["observedAt"][:10], status, reason)
        deliveries.append({"sha256": digest, "selection": filters["Date Selection"], "records": len(records)})
    if not rows:
        raise ValueError("No qualifying city delivery")
    annual = {}
    reasons = Counter()
    unresolved = []
    for key, (day, status, reason) in sorted(rows.items()):
        year = int(day[:4])
        annual.setdefault(year, Counter())[status] += 1
        reasons[(status, reason)] += 1
        if status == "unresolved":
            unresolved.append({"year": year, "state_crash_id": key, "reason": reason})
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temp:
        stage = Path(temp) / "candidate"
        stage.mkdir(mode=0o700)
        csv_path = stage / "annual.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([field["name"] for field in FIELDS])
            for year, statuses in sorted(annual.items()):
                writer.writerow([year, statuses["included"], str(year <= complete_through).lower()])
        json_file(stage / "dictionary.json", {"fields": FIELDS, "primaryKey": "year"})
        (stage / "method.txt").write_text(METHOD, encoding="utf-8")
        files = [{"name": name.split(".")[0], "path": name, "bytes": (stage/name).stat().st_size,
                  "hash": "sha256:" + sha256_file(stage/name)}
                 for name in ("annual.csv", "dictionary.json", "method.txt")]
        json_file(stage / "datapackage.json", {"name": DATASET, "status": "private-candidate",
                  "resources": files, "source": "Utah Crash Data Portal, City of Provo exports",
                  "upstreamRelease": manifest["releaseId"], "upstreamManifestSHA256": manifest_hash,
                  "candidateToolSHA256": sha256_file(Path(__file__)),
                  "parserSHA256": sha256_file(Path(__file__).with_name("crash_portal.py")),
                  "receipts": deliveries, "completeThrough": complete_through,
                  "latestCityEvent": max(row[0] for row in rows.values()),
                  "years": sorted(annual)})
        json_file(stage / "private-review.json", {"scope": "Private review only", "byYear": annual,
                  "population": len(rows), "receipts": deliveries, "unresolved": unresolved,
                  "reasons": [{"status": s, "reason": r, "records": n} for (s, r), n in sorted(reasons.items())]})
        if output.exists():
            raise FileExistsError(output)
        stage.rename(output)
    return sha256_file(output / "datapackage.json")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("manifest", type=Path)
    p.add_argument("manifest_sha256")
    p.add_argument("receipts", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--complete-through", type=int, required=True)
    a = p.parse_args()
    print(build(a.manifest, a.manifest_sha256, a.receipts, a.output, a.complete_through))
