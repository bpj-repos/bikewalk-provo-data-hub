"""Rebuild a downloaded review from its retained receipts and compare every package byte."""

import argparse
from pathlib import Path
from scripts import safe_routes, route_stress, package_stress
from scripts.build_catalog import checked_package
import json


def rebuild(folder, tmp):
    report = json.loads((folder / "review.json").read_bytes())
    version = report["version"]
    base = tmp / "base"
    stress = tmp / "stress"
    out = tmp / "package"
    safe_routes.prepare(folder / "receipt", base, version)
    s = report["sources"]
    i = folder / "inputs"
    if "calibration" in s:
        from scripts.calibrate_route_stress import calibrate

        if (
            calibrate(
                base / "safe-school-routes.geojson",
                i / "neighborhood_ways.geojson",
                i / "utah-bikeways.geojson.gz",
            )
            != s["calibration"]
        ):
            raise ValueError("Calibration did not reproduce")
    route_stress.build(
        base,
        i / "neighborhood_ways.geojson",
        i / "neighborhood_ways_intersections.geojson",
        i / "utah-bikeways.geojson.gz",
        stress,
        osm_date=s["modelInputs"]["utah.osm.pbf"]["snapshot"][:10],
        utah_date=s["utahBikeways"]["date"],
        riding_conditions=bool(s.get("ridingCondition")),
        calibration=s.get("calibration"),
    )
    package_stress.package(base, stress, out, version, s)
    entry = {
        "version": version,
        "dataset": safe_routes.DATASET,
        "sha256": report["sha256"],
    }
    if checked_package(out, entry) != checked_package(folder / "package", entry):
        raise ValueError("Independent rebuild differs")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folder", type=Path)
    p.add_argument("temp", type=Path)
    args = p.parse_args()
    rebuild(args.folder, args.temp)
