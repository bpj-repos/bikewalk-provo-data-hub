"""Export one validated Utah city workbook as a local GeoJSON package and ZIP."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from danger_zones.city_history import read_city_workbook
from danger_zones.city_map import FIELDS, project
from scripts.build_catalog import checked_package, download_zip
from scripts.build_demo_counts import encoded
from scripts.city_cli import package_result, run

ROOT = Path(__file__).resolve().parents[1]


def export(workbook, digest, output, city, version="1.0.0", *, synthetic=False):
    output = output.resolve()
    if output.exists() or not output.is_relative_to(ROOT / "private"):
        raise ValueError("Use a fresh output directory under private/")
    if not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", version):
        raise ValueError("Expected a numeric release version")
    observations, start, end, years, selection = read_city_workbook(workbook, digest, city)
    layer, excluded, qualifying = project(observations, city)
    dataset = re.sub(r"[^a-z]+", "-", city.lower()) + "-crash-points"
    files = {
        "crashes.geojson": encoded(layer),
        "dictionary.json": encoded(dict(
            geometry="WGS 84 longitude/latitude, rounded to four decimal places",
            fields=[dict(name=name, type=kind, description=description)
                    for name, (kind, description) in FIELDS.items()])),
        "method.md": (ROOT / "data-definitions/crashes/city-crash-points.md").read_bytes(),
    }
    coverage = dict(city=city, **{"from": str(start), "to": str(end)}, years=years,
                    input=len(observations), qualifying=qualifying, mapped=len(layer["features"]))
    manifest = dict(name=dataset, version=version, title=f"{city} active transportation crash points",
                    publicationStatus="local-candidate", synthetic=synthetic,
                    source="https://utaps.shinyapps.io/DataPortalAWS/", sourceSha256=digest,
                    sourceSelection=selection, coverage=coverage, excluded=excluded,
                    attribution="Utah Crash Data Portal. Prepared with BikeWalk Provo Data Hub.",
                    reuse="Source-specific Utah Crash Data Portal terms apply. Review rights and disclosure before publishing.",
                    resources=[dict(name=Path(name).stem, path=name, bytes=len(data),
                                    hash="sha256:" + hashlib.sha256(data).hexdigest())
                               for name, data in sorted(files.items())])
    if synthetic:
        manifest.update(source="Invented offline example; no observed crashes.",
                        reuse="Synthetic example data may be freely reused.")
    files["datapackage.json"] = encoded(manifest)
    pin = hashlib.sha256(files["datapackage.json"]).hexdigest()
    prefix = f"datasets/{dataset}/{version}/"
    archive = download_zip({prefix + name: data for name, data in files.items()},
                           {"manifest": "/" + prefix + "datapackage.json"})
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temporary:
        stage = Path(temporary) / "candidate"
        directory = stage / dataset / version
        directory.mkdir(parents=True)
        for name, data in files.items():
            (directory / name).write_bytes(data)
        checked_package(directory, dict(dataset=dataset, version=version, sha256=pin))
        zip_name = f"{dataset}-{version}.zip"
        (directory / zip_name).write_bytes(archive)
        stage.rename(output)
    package = output / dataset / version
    result = package_result(package, pin,
                            inputs=dict(workbook=str(workbook.resolve()), sha256=digest, city=city),
                            coverage=coverage, excluded=excluded)
    result["outputs"].update(geojson=str(package / "crashes.geojson"), zip=str(package / zip_name),
                              zipSha256=hashlib.sha256(archive).hexdigest())
    print(f"Exported {coverage['mapped']} of {qualifying} qualifying crashes to {package / 'crashes.geojson'}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("sha256")
    parser.add_argument("output", type=Path)
    parser.add_argument("--city", required=True)
    parser.add_argument("--version", default="1.0.0")
    run(parser, lambda args: export(args.workbook, args.sha256, args.output, args.city, args.version))
