"""Build a private Safe Routes update from the providers, including the local BNA model."""

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from urllib.parse import urlencode
from uuid import uuid4

from scripts import safe_routes, route_stress, package_stress, review_campus
from scripts.review_routes import compare

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "data-definitions/safe-routes-to-school"
PBF = "https://download.geofabrik.de/north-america/us/utah-latest.osm.pbf"
GIS = "https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/"
BIKES = GIS + "Bikeways/FeatureServer/0"
BOUNDARY = GIS + "UtahMunicipalBoundaries/FeatureServer/0"
CITY = "https://bna.peopleforbikes.org/api/city-ratings/United%20States/Utah/Provo"
ANALYZER = (
    "https://api.github.com/repos/PeopleForBikes/brokenspoke-analyzer/releases/latest"
)
ARCHIVE_SHA = "82073f45eb74cf9b5e68777e03fdd26f506e63ad8967bc9d7401a93560e69354"
REPO = "bpj-repos/bikewalk-provo-data-hub"


def run(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def fetch(url, path=None):
    args = [
        "curl",
        "--fail",
        "--silent",
        "--show-error",
        "--location",
        "--retry",
        "3",
        "--max-time",
        "300",
        url,
    ]
    if path is not None:
        run(*args, "-o", path)
    else:
        return run(*args, capture_output=True).stdout


def api(url, **params):
    obj = json.loads(fetch(url + "?" + urlencode(params)) if params else fetch(url))
    if "error" in obj:
        raise ValueError(obj["error"])
    return obj


def write(p, obj):
    p.write_bytes(safe_routes.encoded(obj))


def digest(path, algorithm="sha256"):
    h = hashlib.new(algorithm)
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def date_ms(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).date().isoformat()


def capture_bikes(out, routes):
    # Query the statewide layer spatially; municipal labels omit roads on school plans.
    from shapely import total_bounds
    from shapely.geometry import shape

    x, y, X, Y = total_bounds([shape(f["geometry"]) for f in routes])
    area = dict(
        geometry=f"{x - 0.005},{y - 0.005},{X + 0.005},{Y + 0.005}",
        geometryType="esriGeometryEnvelope",
        inSR=4326,
        spatialRel="esriSpatialRelIntersects",
        where="1=1",
    )
    url = BIKES + "/query"

    def ids():
        values = api(url, **area, returnIdsOnly="true", f="json")["objectIds"]
        if not values or len(values) != len(set(values)):
            raise ValueError("Incomplete bikeway ID inventory")
        return sorted(values)

    meta = api(BIKES, f="json")
    stamp = meta["editingInfo"]["lastEditDate"]
    oid = meta["objectIdField"]
    expected = ids()
    rows = []
    for i in range(0, len(expected), 200):
        batch = expected[i : i + 200]
        result = api(
            url,
            objectIds=",".join(map(str, batch)),
            outFields="*",
            returnGeometry="true",
            outSR=4326,
            f="geojson",
        )
        page = result["features"]
        if (
            result.get("exceededTransferLimit")
            or sorted(f["properties"][oid] for f in page) != batch
        ):
            raise ValueError("Incomplete bikeway page")
        if any(not f.get("geometry") for f in page):
            raise ValueError("Missing bikeway geometry")
        rows.extend(page)
    if (
        expected != ids()
        or stamp != api(BIKES, f="json")["editingInfo"]["lastEditDate"]
    ):
        raise ValueError("Bikeways changed during capture")
    rows.sort(key=lambda f: f["properties"][oid])
    out.write_bytes(
        gzip.compress(
            safe_routes.encoded(dict(type="FeatureCollection", features=rows)), mtime=0
        )
    )
    return dict(
        url=BIKES,
        date=date_ms(stamp),
        extent=area["geometry"],
        count=len(rows),
        sha256=digest(out),
    )


def capture(out, base):
    policy = json.loads((CONTRACT / "stress-sources.json").read_bytes())
    bounds = api(
        BOUNDARY + "/query",
        where="UPPER(NAME)='PROVO'",
        outFields="NAME",
        returnGeometry="true",
        outSR="4326",
        f="geojson",
    )
    if (
        len(bounds["features"]) != 1
        or bounds["features"][0]["properties"]["NAME"].lower() != "provo"
        or bounds["features"][0]["geometry"]["type"] not in ("Polygon", "MultiPolygon")
    ):
        raise ValueError("Unexpected municipal boundary")
    write(out / "boundary.json", bounds)
    city = api(CITY)
    if (city["city"]["name"], city["city"]["state"]) != ("Provo", "Utah"):
        raise ValueError("Unexpected BNA city")
    version = city["ratings"][0]["version"]
    if not re.fullmatch(r"\d{2}\.\d{2}", version):
        raise ValueError("Unexpected BNA vintage")
    speed = (
        city["ratings"][0].get("residential_speed_limit_override")
        or city["city"]["residential_speed_limit"]
    )
    if type(speed) != int or not 5 <= speed <= 55:
        raise ValueError("Unexpected residential model default")
    comp = f"https://files.storage.bna.peopleforbikes.org/united%20states/utah/provo/{version}/neighborhood_ways.geojson"
    published = out / "published-ways.geojson"
    fetch(comp, published)
    rows = json.loads(published.read_bytes())["features"]
    fields = ("ft_seg_stress", "tf_seg_stress", "ft_int_stress", "tf_int_stress")
    if not rows or any(not set(fields) <= f["properties"].keys() for f in rows):
        raise ValueError("Incomplete Provo analysis")
    latest = api(ANALYZER)["tag_name"].lstrip("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+", latest):
        raise ValueError("Unexpected analyzer release")
    tag = f"ghcr.io/peopleforbikes/brokenspoke-analyzer:{latest}"
    run("docker", "pull", tag)
    refs = json.loads(
        run(
            "docker",
            "image",
            "inspect",
            "--format",
            "{{json .RepoDigests}}",
            tag,
            capture_output=True,
        ).stdout
    )
    img = next(
        r
        for r in refs
        if r.startswith("ghcr.io/peopleforbikes/brokenspoke-analyzer@sha256:")
    )
    pbf = out / "utah.osm.pbf"
    expected = fetch(PBF + ".md5").decode().split()[0]
    fetch(PBF, pbf)
    if digest(pbf, "md5") != expected:
        raise ValueError("Geofabrik checksum mismatch; retry with a stable delivery")
    timestamp = run(
        "docker",
        "run",
        "--rm",
        "-v",
        f"{pbf}:/utah.osm.pbf:ro",
        "--entrypoint",
        "osmium",
        img,
        "fileinfo",
        "-g",
        "header.option.osmosis_replication_timestamp",
        "/utah.osm.pbf",
        capture_output=True,
        text=True,
    ).stdout.strip()
    datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    roads = capture_bikes(
        out / "utah-bikeways.geojson.gz",
        json.loads((base / "safe-school-routes.geojson").read_bytes())["features"],
    )
    write(out / "city-rating.json", city)
    return dict(
        method=f"BikeWalk local Brokenspoke Analyzer {latest}",
        analyzer=img,
        analyzerVersion=latest,
        database=policy["database"],
        publishedComparison=comp,
        publishedVersion=version,
        comparisonSha256=digest(published),
        speed=speed,
        utahBikeways=roads,
        modelInputs={
            "utah.osm.pbf": dict(origin=PBF, snapshot=timestamp, sha256=digest(pbf)),
            "boundary.json": dict(
                origin=BOUNDARY, sha256=digest(out / "boundary.json")
            ),
        },
    )


def model(inputs, source):
    name = "bwp-stress-" + uuid4().hex[:12]
    db = name + "-db"
    worker = name + "-worker"
    url = "postgresql://postgres:postgres@stressdb:5432/postgres"
    image = source["analyzer"]
    run("docker", "network", "create", name)
    try:
        run(
            "docker",
            "run",
            "-d",
            "--name",
            db,
            "--network",
            name,
            "--network-alias",
            "stressdb",
            "--tmpfs",
            "/var/lib/postgresql:rw,size=4g",
            "-e",
            "POSTGRES_PASSWORD=postgres",
            source["database"],
        )
        run(
            "docker",
            "exec",
            db,
            "sh",
            "-ec",
            "for i in $(seq 1 60); do pg_isready -h localhost -U postgres && exit 0; sleep 1; done; exit 1",
        )
        opts = ["--network", name, "-e", "DATABASE_URL=" + url]
        run(
            "docker",
            "run",
            "--rm",
            *opts,
            image,
            "configure",
            "custom",
            "2",
            "2048",
            "postgres",
        )
        run(
            "docker",
            "create",
            "--name",
            worker,
            *opts,
            "-e",
            f"BWP_CITY_SPEED={source['speed']}",
            "--tmpfs",
            "/scratch:rw,size=2g",
            "-e",
            "BWP_MODEL_XML=/scratch/provo.osm",
            "-v",
            f"{inputs}:/tmp/inputs:ro",
            "-v",
            f"{ROOT}/scripts/model_bicycle_stress.py:/model.py:ro",
            "--entrypoint",
            "sh",
            image,
            "-ec",
            "mkdir /tmp/outputs && python /model.py",
        )
        run("docker", "start", "-a", worker)
        if (
            run(
                "docker",
                "inspect",
                "--format",
                "{{.State.ExitCode}}",
                worker,
                capture_output=True,
                text=True,
            ).stdout.strip()
            != "0"
        ):
            raise ValueError("Model failed")
        run("docker", "cp", worker + ":/tmp/outputs/.", inputs)
    finally:
        for container in (worker, db):
            subprocess.run(
                ["docker", "rm", "-fv", container],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        run("docker", "network", "rm", name)


def current():
    ledger = json.loads((ROOT / "releases/release-ledger.json").read_bytes())
    withdrawn = {
        e["version"] for e in ledger["withdrawn"] if e["dataset"] == safe_routes.DATASET
    }
    return next(
        e
        for e in reversed(ledger["approved"])
        if e["dataset"] == safe_routes.DATASET and e["version"] not in withdrawn
    )


def main(out):
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    previous = current()
    old = ROOT / "releases/datasets" / safe_routes.DATASET / previous["version"]
    major, minor, patch = map(int, previous["version"].split("."))
    version = f"{major}.{minor}.{patch + 1}"
    archive = out / "safe-routes-july.tar.gz"
    run(
        "gh",
        "release",
        "download",
        "source-receipts-safe-routes-20261107",
        "-R",
        REPO,
        "-p",
        archive.name,
        "-D",
        out,
    )
    if digest(archive) != ARCHIVE_SHA:
        raise ValueError("July archive checksum mismatch")
    with tarfile.open(archive) as t:
        t.extractall(out, filter="data")
    receipt = out / "receipt"
    base = out / "base"
    safe_routes.receive(receipt, out / safe_routes.ARCHIVE_ID)
    review = review_campus.review(receipt)
    write(out / "campus.json", review)
    if review["changedIDs"] or review["addressNow"] != review["addressBefore"]:
        raise ValueError("Review changed Treeside campus evidence")
    safe_routes.prepare(receipt, base, version)
    inputs = out / "inputs"
    inputs.mkdir()
    source = capture(inputs, base)
    model(inputs, source)
    network = [
        "neighborhood_ways.geojson",
        "neighborhood_ways_intersections.geojson",
        "utah-bikeways.geojson.gz",
    ]
    source["pinnedResources"] = {n: digest(inputs / n) for n in network}
    osm_date = source["modelInputs"]["utah.osm.pbf"]["snapshot"][:10]
    utah_date = source["utahBikeways"]["date"]
    stress = out / "stress"
    route_stress.build(
        base,
        *(inputs / n for n in network),
        stress,
        osm_date=osm_date,
        utah_date=utah_date,
    )
    package = out / "package"
    package_stress.package(base, stress, package, version, source)
    changes = compare(old, package, layers=[*safe_routes.LAYERS, *route_stress.KEYS])
    write(out / "changes.json", changes)
    summary = {
        k: {kind: len(ids) for kind, ids in counts.items()}
        for k, counts in changes.items()
    }
    report = dict(
        previous=previous,
        version=version,
        sha256=digest(package / "datapackage.json"),
        changes=summary,
        coverage=json.loads((stress / "stress-coverage.json").read_bytes()),
        sources=source,
    )
    write(out / "review.json", report)
    print(
        json.dumps({k: report[k] for k in ("version", "sha256", "changes")}, indent=2)
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("new_directory", type=Path)
    main(parser.parse_args().new_directory)
