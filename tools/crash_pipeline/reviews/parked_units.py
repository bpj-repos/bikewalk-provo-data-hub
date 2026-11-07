"""Compare the parked-unit exception with the pinned private annual candidate."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from danger_zones.crash_portal import read_portal
from danger_zones.motor_vehicle_candidate import classify
from danger_zones.util import sha256_file

PIN = "c05fa83f8afa979ca1b5c0026ef35c8d488060d4966adc7cf7b2a10fbe48a6c8"


def review(candidate, receipts):
    package = candidate / "datapackage.json"
    if sha256_file(package) != PIN:
        raise ValueError("Unexpected baseline candidate")
    manifest = json.loads(package.read_bytes())
    for resource in manifest["resources"]:
        if "sha256:" + sha256_file(candidate / resource["path"]) != resource["hash"]:
            raise ValueError("Baseline resource mismatch")
    baseline = {int(r["year"]): int(r["crashes"]) for r in csv.DictReader((candidate / "annual.csv").read_text().splitlines())}
    old = json.loads((candidate / "private-review.json").read_bytes())
    cases = {}
    for receipt in manifest["receipts"]:
        path = receipts / receipt["sha256"] / "records.xlsx"
        if sha256_file(path) != receipt["sha256"]:
            raise ValueError("Workbook checksum mismatch")
        rows, filters = read_portal(path, include_all=True, validate=True)
        if filters["City"] != "Provo" or filters["Date Selection"] != receipt["selection"] or len(rows) != receipt["records"]:
            raise ValueError("Unexpected workbook coverage")
        for r in rows:
            key = r["sourceRecordId"]
            m = r["metadata"]
            if m["crash"]["City_Geo"] != "Provo":
                cases.pop(key, None)
                continue
            status, reason = classify(m)
            events = [m["crash"]["firstHarmfulEvent"], *[v["mostHarmfulEvent"] for v in m["vehicles"]]]
            nonmotorist_event = any(str(e) in {"22", "23", "24"} for e in events)
            parked = False
            evidence = {}
            if reason == "incomplete participant-to-vehicle links":
                persons = {str(p["vehicleNumber"]) for p in m["persons"]}
                units = {str(v["vehicleNumber"]) for v in m["vehicles"]}
                unlinked = [v for v in m["vehicles"] if str(v["vehicleNumber"]) not in persons]
                parked = bool(unlinked) and persons <= units and all(
                    str(v["vehicleManeuver"]) == "13" and v["vehicleManeuver_label"] == "Parked" for v in unlinked)
                if parked:
                    sources = [m["crash"], *m["rollups"]]
                    for flag in ["pedestrian_involved", "cyclist_involved"]:
                        if {s[flag] for s in sources if s[flag] not in (None, "")} != {"N"}:
                            raise ValueError("Flags disagree")
                    if not m["persons"] or any(str(p["personType"]) not in {"1","2"} for p in m["persons"]):
                        raise ValueError("Unexpected person type")
                    evidence = {
                        "rollup_supplies_missing_crash_flag": any(m["crash"][f] in (None, "") for f in ["pedestrian_involved","cyclist_involved"]),
                        "no_nonparked_unit": all(v["vehicleManeuver_label"] == "Parked" for v in m["vehicles"]),
                        "nonmotorist_event": nonmotorist_event}
            if status == "included":
                evidence["baseline_event_conflict"] = nonmotorist_event
                evidence["baseline_all_parked"] = all(str(v["vehicleManeuver"]) == "13" for v in m["vehicles"])
            cases[key] = (int(r["observedAt"][:4]), status, reason, parked, evidence)
    years = {}
    diagnostics = Counter()
    unresolved = {key: (y, reason) for key,(y, status, reason, _, _) in cases.items() if status == "unresolved"}
    if unresolved != {r["state_crash_id"]: (r["year"],r["reason"]) for r in old["unresolved"]}:
        raise ValueError("Unresolved population differs from the pinned review")
    for year, status, reason, parked, evidence in cases.values():
        values = years.setdefault(year, Counter())
        values[status] += 1
        if evidence.get("baseline_event_conflict") or evidence.get("baseline_all_parked"):
            values["baseline_hold"] += 1
        if parked:
            values["added"] += 1
            if not evidence["no_nonparked_unit"] and not evidence["nonmotorist_event"]:
                values["recommend"] += 1
        diagnostics.update({k: int(v) for k,v in evidence.items()})
    if baseline != {year:v["included"] for year,v in years.items()}:
        raise ValueError("Annual baseline differs")
    print("year current literal_add parked_add existing_hold recommended_total")
    for year, v in sorted(years.items()):
        print(year, v["included"], v["added"], v["recommend"], v["baseline_hold"],
              v["included"] + v["recommend"] - v["baseline_hold"])
    print("checks", dict(diagnostics))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("candidate", type=Path)
    p.add_argument("receipts", type=Path)
    a = p.parse_args()
    review(a.candidate, a.receipts)
