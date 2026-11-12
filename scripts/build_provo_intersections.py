"""Regenerate normalized resources from the versioned UDOT report extracts."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "releases/datasets/provo-intersections/1.0.0"


def read(name):
    return json.loads((PACKAGE / name).read_bytes())


def write(name, data):
    (PACKAGE / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def build():
    roster = {}
    for row in sorted(read("roster.json")["value"], key=lambda r: r["start"]):
        if row["start"][:10] <= "2026-11-02":
            roster[row["locationIdentifier"]] = row
    features = []
    for site, result in sorted(read("query-results.json").items()):
        row = roster[site]
        plans = []
        observed = False
        for path in sorted(PACKAGE.glob(site + "*.json")):
            if path.name.endswith("-replay.json"):
                continue
            for phase in read(path.name):
                observed |= any(phase.get(k) for k in ("gapOuts", "forceOffs", "maxOuts", "unknowns"))
                for plan in phase["plans"]:
                    plans.append(dict(phase=phase["phaseNumber"], movement=phase["phaseDescription"],
                                      plan=plan["planNumber"], label=plan["planDescription"],
                                      start=plan["start"], end=plan["end"], source=path.name,
                                      splitSeconds=plan["programmedSplit"] if (plan["programmedSplit"] or 0)>0 else None))
        properties = dict(siteId="udot-atspm-"+site, primary=row["primaryName"], secondary=row["secondaryName"],
                          provider="UDOT ATSPM", owner=None, operator=None, scheduledPeriods=None,
                          reportFailed=result=="failed", observedTerminations=observed, reportedPlans=plans)
        features.append(dict(type="Feature", id=properties["siteId"], properties=properties,
                             geometry=dict(type="Point",coordinates=[row["longitude"],row["latitude"]])))
    write("sites.geojson",dict(type="FeatureCollection",features=features))
    phases = read("6444-replay.json")
    labels = {1:"begin green", 3:"minimum green complete", 8:"begin yellow clearance",
              9:"end yellow clearance", 11:"end red clearance", 21:"begin walk",
              22:"begin pedestrian clearance", 23:"begin solid don't walk"}
    write("controller-events-v1.json", labels)
    events = sorted((e["start"], p["phaseNumber"], p["phaseType"], e["value"],
                     labels.get(e["value"], "unknown"), stream)
                    for p in phases for stream in ("cycleAllEvents", "pedestrianIntervals")
                    for e in p[stream])
    bounds = sorted({e[0] for e in events if e[1:4] == (2, "Protected", 1)})
    cycles = [dict(siteId="udot-atspm-6444",plan="7",start=a,end=b,events=[e for e in events if a<=e[0]<b])
              for a,b in zip(bounds,bounds[1:]) if a>"2026-11-10T09:00:00"]
    write("cycles-6444.json",cycles)
    resources=[]
    for path in sorted(PACKAGE.iterdir()):
        if path.name!="datapackage.json":
            raw=path.read_bytes()
            resources.append(dict(name=path.stem,path=path.name,bytes=len(raw),hash="sha256:"+hashlib.sha256(raw).hexdigest()))
    write("datapackage.json",dict(name="provo-intersections",version="1.0.0",title="Provo intersections and reported signal timing",resources=resources))


if __name__ == "__main__":
    build()
