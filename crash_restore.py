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


def exercise_writer(dest, producer_src, retained):
    """Run the real CLI against restored files, denying access to original data."""
    release, digest = next(iter(PINS.items()))
    relative = RELEASES / release
    manifest = json.loads(verified(dest / relative / "manifest.json", digest))
    historical = ORIGINAL / relative
    pointer = {
        "snapshotId": release, "counts": manifest["counts"],
        "path": str(historical / "collection.json"), "sha256": manifest["files"]["collection.json"],
        "releaseManifest": {"path": str(historical / "manifest.json"), "sha256": digest},
        "reviewedLinksSource": {"path": str(historical / "reviewed-links.json"),
                                "sha256": manifest["files"]["reviewed-links.json"]},
    }
    active = dest / PRIVATE / "datastores/combined-incidents.json"
    active.parent.mkdir()
    active.write_text(json.dumps(pointer))
    blocked = [root / path for root in {ORIGINAL, retained} for path in
               (PRIVATE, "tools/.danger-zone-data", "docs/incidents-metadata/reconciliation-20261103")]
    driver = """
import json, os, runpy, sys
from pathlib import Path
blocked = [Path(p) for p in json.loads(sys.argv[1])]
def deny_original(event, args):
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path = Path(os.fsdecode(args[0])).resolve()
        if any(path.is_relative_to(root) for root in blocked):
            raise PermissionError('Attempted to open original data during recovery')
sys.addaudithook(deny_original)
sys.path.insert(0, sys.argv[2])
sys.argv = sys.argv[2:]
runpy.run_module('danger_zones.update_incidents', run_name='__main__')
"""
    def invoke(action):
        output = subprocess.check_output(
            [sys.executable, "-IB", "-c", driver, json.dumps(list(map(str, blocked))), str(producer_src),
             "--restore-path", str(ORIGINAL), str(dest), action], cwd=dest, text=True)
        return json.loads(output)

    first = invoke("--offline")
    if first["status"] != "accepted":
        raise ValueError("Expected a release with the updated producer identity")
    bundle = Path(first["bundle"])
    changes = json.loads((bundle / "changes.json").read_bytes())
    if any(changes[k] for k in ("changedSourceRecords", "newLinks", "newIncidentGroups", "enrichmentChangedGroups")):
        raise ValueError("Unexpected changes after relocation")
    from danger_zones.research_reports import crash_report
    before = json.loads((dest / relative / "collection.json").read_bytes())
    after = json.loads((bundle / "collection.json").read_bytes())
    if before["records"] != after["records"] or crash_report(before, 2025) != crash_report(after, 2025):
        raise ValueError("Relocation changed incident records or annual aggregates")
    accepted = active.read_bytes()
    if invoke("--offline")["status"] != "unchanged" or active.read_bytes() != accepted:
        raise ValueError("Repeated offline run changed the active pointer")
    if invoke("--rollback")["releaseId"] != release:
        raise ValueError("Failed to restore the original pin")
    restored = json.loads(active.read_bytes())
    for ref in (restored, restored["reviewedLinksSource"], restored["releaseManifest"]):
        path = Path(ref["path"])
        if not path.is_relative_to(dest):
            raise ValueError("Rollback left a pointer outside the restored tree")
        verified(path, ref["sha256"])
    if invoke("--rollback")["releaseId"] != manifest["predecessor"]["snapshotId"]:
        raise ValueError("Rollback through a historical absolute pointer failed")
    for name, expected in PINS.items():
        verified(dest / RELEASES / name / "manifest.json", expected)
    print("Verified offline update, repeat, and two rollbacks with original data inaccessible")


def run(checkout, retained, producer_src, writer=False):
    if subprocess.check_output(["git", "-C", checkout, "rev-parse", "HEAD"], text=True).strip() != COMMIT:
        raise ValueError("Use the documented baseline checkout")
    if subprocess.check_output(["git", "-C", checkout, "status", "--porcelain", "--", "tools/danger_zone_pipeline"]):
        raise ValueError("Use a clean producer checkout")
    producer_src = producer_src or checkout / "tools/danger_zone_pipeline/src"
    if not (producer_src / "danger_zones/research_reports.py").is_file():
        raise ValueError("Missing producer source package")
    producer_src = producer_src.resolve()
    sys.path.insert(0, str(producer_src))
    from danger_zones.research_reports import crash_report
    from danger_zones.incident_updates import flatten
    from danger_zones.update_incidents import load_state

    expected = verified(checkout / "apps/maps/public/data/research/crashes.csv", CSV_HASH)
    with tempfile.TemporaryDirectory(prefix="bwp-crash-restore-") as temp:
        dest = Path(temp).resolve()
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
        if writer:
            exercise_writer(dest, producer_src, retained)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path, help="Clean canonical code checkout at baseline commit")
    parser.add_argument("retained", type=Path, help="Recovery root containing tools/.danger-zone-private")
    parser.add_argument("--producer-src", type=Path, help="Test a trusted relocated danger_zones package against the same fixture")
    parser.add_argument("--exercise-writer", action="store_true", help="Also exercise the portable producer CLI with original data inaccessible")
    args = parser.parse_args()
    run(args.checkout.resolve(), args.retained.resolve(), args.producer_src, args.exercise_writer)
