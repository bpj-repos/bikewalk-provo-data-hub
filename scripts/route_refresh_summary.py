"""Print a human-readable review of a Safe Routes refresh artifact."""

import argparse
from collections import Counter, defaultdict
import json
import shlex
from pathlib import Path


def summary(folder, run_id):
    r = json.loads((folder / "review.json").read_text())
    segments = json.loads(
        (folder / "package/safe-route-stress-segments.geojson").read_text()
    )["features"]
    meters = Counter()
    routes = defaultdict(set)
    for row in segments:
        p = row["properties"]
        meters[p["ridingCondition"]] += p["lengthMeters"]
        routes[p["routeId"]].add(p["ridingCondition"])
    none = sum(v == {"not-rated"} for v in routes.values())
    full = sum("not-rated" not in v for v in routes.values())
    switches = r["sourceSwitches"]
    coverage = r["coverage"].values()
    agreement = r["publishedAgreement"]
    s = r["sources"]
    text = [
        f"## Safe Routes {r['version']} · ready for review",
        "",
        f"Predecessor {r['previous']['version']}. Provo BNA {s['publishedVersion']}, Brokenspoke {s['analyzerVersion']}, OSM {s['modelInputs']['utah.osm.pbf']['snapshot']}, Utah Bikeways {s['utahBikeways']['date']}.",
        "",
        "| Riding condition | Route length |",
        "| --- | ---: |",
    ]
    for key, label in [
        ("calmer", "Calmer"),
        ("moderate", "Moderate"),
        ("busier", "Busier"),
        ("not-rated", "Not rated"),
    ]:
        text.append(f"| {label} | {meters[key]:,.1f} m |")
    text += [
        "",
        f"{full} routes are fully rated, {len(routes) - none - full} partially rated and {none} have no rating.",
        f"Native vs calibrated disagreements at {switches['boundaries']} adjacent source boundaries: {switches['nativeDifferences']} → {switches['calibratedDifferences']}. For {sum(v.get('sameWaySourceSwitches', 0) for v in coverage)} qualifying same-way boundaries: {sum(v.get('nativeSwitchDisagreements', 0) for v in coverage)} → {sum(v.get('displaySwitchDisagreements', 0) for v in coverage)}.",
        "",
        "Published BNA agreement on comparable segments (meters): "
        + json.dumps(agreement["segmentMeters"], sort_keys=True)
        + ". Crossing directions: "
        + json.dumps(agreement["crossingDirections"], sort_keys=True)
        + ".",
        "",
        "Unrated screen (meters): "
        + json.dumps(r["unratedScreen"], sort_keys=True)
        + ". Leads remain private and do not fill missing ratings.",
        "",
        "| Resource | Added | Removed | Changed |",
        "| --- | ---: | ---: | ---: |",
    ]
    text.extend(
        f"| {name} | {values['added']} | {values['removed']} | {values['changed']} |"
        for name, values in r["changes"].items()
    )
    text += [
        "",
        "Inspect review.json, changes.json, published-comparison.json, unrated-review.json and school-coverage-review.txt before approval.",
        "",
        "Only after approval, publish the Hub from its checkout. Then stage the approved pin in Streets Watch with npm run safe-routes:update -- stage VERSION and review its PR:",
        "",
        "\x60\x60\x60sh",
        f"python -m scripts.publish_route_update {shlex.quote(str(run_id))} {r['sha256']} --prepare-pr",
        "\x60\x60\x60",
    ]
    return "\n".join(text) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("run_id")
    args = parser.parse_args()
    print(summary(args.candidate, args.run_id), end="")
