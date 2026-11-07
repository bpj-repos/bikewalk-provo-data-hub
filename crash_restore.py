"""Offline restore and parity fixture for the two Wave 6 crash collection pins."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile

COMMIT = "fff781bd28e8ec96f01210e0589c2b6225a40486"
ORIGINAL = Path("/Users/test/Documents/ChatGPT/bikewalk-provo")
PRIVATE = Path("tools/.danger-zone-private")
RELEASES = PRIVATE / "incident-updates/releases"
PINS = {
    "incidents-e5a4665997a4cac4f5be": "c614ca99200bc25ce4d77491061e0d23529f59be24e42bcbff0f16759f4ca979",
    "incidents-484f3b69f31351340636": "7279e006d9882cde133f41f9d09436c125741bdef8f2b13b5108fc0f96bd64bf",
}
CSV_HASH = "7daf9244f56900f05e9691914f3fc1be633fbe1adf0770fd84b1477a2105598a"


def verified(path, digest):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"Checksum mismatch: {path.name}")
    return data


def restore(retained, checkout, dest):
    def copy(relative, digest):
        if ".." in relative.parts or not (relative.is_relative_to(PRIVATE) or relative.parts[:2] == ("docs", "incidents-metadata")):
            raise ValueError("Invalid retained path")
        root = checkout if relative.parts[0] == "docs" else retained
        source = (root / relative).resolve()
        if not source.is_relative_to(root):
            raise ValueError("Source escaped recovery root")
        data = verified(source, digest)
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            verified(target, digest)
        else:
            target.write_bytes(data)
        return data

    release = next(iter(PINS))
    digest = PINS[release]
    restored = set()
    while release:
        if release in restored or PINS.get(release, digest) != digest:
            raise ValueError("Unexpected predecessor chain")
        restored.add(release)
        directory = RELEASES / release
        manifest = json.loads(copy(directory / "manifest.json", digest))
        if manifest["releaseId"] != release:
            raise ValueError("Unexpected release ID")
        for name, expected in manifest["files"].items():
            if Path(name).name != name:
                raise ValueError("Unexpected bundle member")
            copy(directory / name, expected)
        previous = manifest["predecessor"]["pointer"]
        for ref in [*manifest["sources"], *manifest["inputs"], previous, previous["reviewedLinksSource"]]:
            copy(Path(ref["path"]).relative_to(ORIGINAL), ref["sha256"])
        release = previous["snapshotId"] if "releaseManifest" in previous else None
        if release:
            digest = previous["releaseManifest"]["sha256"]
    if not PINS.keys() <= restored:
        raise ValueError("Missing report pin")
    return len(restored)


def run(checkout, retained, producer_src):
    if subprocess.check_output(["git", "-C", checkout, "rev-parse", "HEAD"], text=True).strip() != COMMIT:
        raise ValueError("Use the documented baseline checkout")
    if subprocess.check_output(["git", "-C", checkout, "status", "--porcelain", "--", "tools/danger_zone_pipeline"]):
        raise ValueError("Use a clean producer checkout")
    producer_src = producer_src or checkout / "tools/danger_zone_pipeline/src"
    if not (producer_src / "danger_zones/research_reports.py").is_file():
        raise ValueError("Missing producer source package")
    sys.path.insert(0, str(producer_src))
    from danger_zones.research_reports import crash_report
    from danger_zones.incident_updates import flatten
    from danger_zones.update_incidents import load_state

    expected = verified(checkout / "apps/maps/public/data/research/crashes.csv", CSV_HASH)
    with tempfile.TemporaryDirectory(prefix="bwp-crash-restore-") as temp:
        dest = Path(temp)
        count = restore(retained, checkout, dest)
        for release, digest in PINS.items():
            bundle = dest / RELEASES / release
            collection = json.loads((bundle / "collection.json").read_bytes())
            ref = {"path": str(bundle / "manifest.json"), "sha256": digest}
            load_state({"releaseManifest": ref}, collection, dest / PRIVATE)
            report = crash_report(collection, 2025)
            rows = report["annual"]
            out = io.StringIO(newline="")
            writer = csv.writer(out)
            writer.writerow(["year", "total", "bike", "ped", "other", "complete_year"])
            writer.writerows([r[k] for k in ("year", "total", "bike", "ped", "other", "complete")] for r in rows)
            if out.getvalue().encode() != expected or report["coverageEnd"] != "2026-09-30":
                raise ValueError(f"Annual parity failed: {release}")
            counts = (len(collection["records"]), len(flatten(collection)),
                      len(json.loads((bundle / "reviewed-links.json").read_bytes())))
            if counts != (1139, 1755, 50):
                raise ValueError(f"Private collection parity failed: {release}")
            print(release, *counts, len(rows), CSV_HASH)
        print(f"Verified {count} managed releases and their predecessor references")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path, help="Clean canonical code checkout at baseline commit")
    parser.add_argument("retained", type=Path, help="Recovery root containing tools/.danger-zone-private")
    parser.add_argument("--producer-src", type=Path, help="Test a trusted relocated danger_zones package against the same fixture")
    args = parser.parse_args()
    run(args.checkout.resolve(), args.retained.resolve(), args.producer_src)
