"""Package a verified Safe Routes candidate with its modeled stress resources."""

import argparse
import hashlib
import json
from pathlib import Path
from scripts.build_demo_counts import encoded
from scripts.safe_routes import DATASET, HOST

ROOT = Path(__file__).resolve().parents[1]


def package(base, stress, output, version, refreshed_sources=None):
    manifest = json.loads((base / "datapackage.json").read_bytes())
    if manifest["name"] != DATASET:
        raise ValueError("Wrong base package")
    files = {}
    for r in manifest["resources"]:
        name = r["path"]
        if Path(name).name != name or name in files:
            raise ValueError("Unexpected input file")
        raw = (base / name).read_bytes()
        if (
            hashlib.sha256(raw).hexdigest() != r["hash"].removeprefix("sha256:")
            or len(raw) != r["bytes"]
        ):
            raise ValueError("Invalid base pin")
        files[name] = raw
    pins = json.loads((stress / "stress-inputs.json").read_bytes())
    for name in ("safe-school-routes.geojson", "safe-route-plan-features.geojson"):
        if hashlib.sha256(files[name]).hexdigest() != pins[name]:
            raise ValueError("Stress annotations belong to different plan data")
    contract = ROOT / "data-definitions/safe-routes-to-school"
    inputs = refreshed_sources or json.loads(
        (contract / "stress-sources.json").read_bytes()
    )
    for name, expected in inputs["pinnedResources"].items():
        if pins.get(name) != expected:
            raise ValueError("Unreviewed stress source: " + name)
    for name in (
        "safe-route-stress-segments.geojson",
        "safe-route-stress-crossings.geojson",
        "stress-coverage.json",
        "stress-inputs.json",
    ):
        files[name] = (stress / name).read_bytes()
    sources = json.loads(files["sources.json"])
    sources["bicycleStress"] = inputs
    files["sources.json"] = encoded(sources)
    files["stress-method.md"] = (contract / "stress-method.md").read_bytes()
    if refreshed_sources:
        doc = files["stress-method.md"].decode().split("\n\n")
        doc[2] = (
            f"BikeWalk ran Brokenspoke {inputs['analyzerVersion']} on the Geofabrik Utah OSM snapshot {inputs['modelInputs']['utah.osm.pbf']['snapshot']}, with a 2,680 m buffer around the captured Provo boundary and {inputs['speed']} mph city residential default. The published Provo {inputs['publishedVersion']} network is a comparison input. Utah Bikeways ({inputs['utahBikeways']['date']}) supplies segment fallback within the route extent. See sources.json for image digests, source identities and checksums."
        )
        files["stress-method.md"] = "\n\n".join(doc).encode()
    dictionary = json.loads(files["dictionary.json"])
    dictionary["bicycleStress"] = json.loads(
        (contract / "stress-dictionary.json").read_bytes()
    )
    files["dictionary.json"] = encoded(dictionary)
    files["coverage.md"] += (
        b"\nBicycle stress coverage by school is in stress-coverage.json. Counts refer to route-associated approaches; a shared location may appear on multiple routes. See stress-method.md.\n"
    )
    files["changes.md"] = (
        b"Adds modeled bicycle stress along routes and at identified crossing approaches, including explicit unassessed portions. The school plan layers retain their original identities and geometry.\n"
    )
    if refreshed_sources:
        files["changes.md"] = (
            b"Refreshes the UDOT school plans, modeled bicycle approach and segment estimates, comparison sources and school coverage. Source vintages and checksums are recorded in sources.json.\n"
        )
    manifest.update(
        version=version,
        citation=f"BikeWalk Provo. Provo Safe Routes to School, {version}. {HOST}/datasets/{DATASET}/{version}/datapackage.json",
    )
    manifest["attribution"] += (
        " Stress estimates by BikeWalk Provo using PeopleForBikes Brokenspoke Analyzer, © OpenStreetMap contributors, and Utah Geospatial Resource Center / Utah Bikeways."
    )
    manifest["reuse"] += (
        " OSM-derived stress data: ODbL 1.0. Utah Bikeways: CC BY 4.0. See stress-method.md for attribution and source-specific terms."
    )
    manifest["resources"] = [
        dict(
            name=Path(n).stem,
            path=n,
            bytes=len(b),
            hash="sha256:" + hashlib.sha256(b).hexdigest(),
        )
        for n, b in sorted(files.items())
    ]
    files["datapackage.json"] = encoded(manifest)
    output.mkdir(parents=True, exist_ok=False)
    for n, b in files.items():
        (output / n).write_bytes(b)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("base", "stress", "output"):
        p.add_argument(arg, type=Path)
    p.add_argument("--version", required=True)
    package(**vars(p.parse_args()))
