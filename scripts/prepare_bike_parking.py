"""Prepare a versioned Provo City bike parking candidate from a complete ArcGIS query."""
import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from uuid import UUID

SOURCE = "https://www.arcgis.com/home/item.html?id=0ef3b3178f5f4d3d8ee5ce88318e3437"
ROOT = "Provo Bike Parking/Provo Bike Parking/"
FOLDERS = {
    "Ideal Bike Racks": {"", "Westridge"},
    "Racks that can be improved": {"", "BYU Campus Floral", "Law School", "Taylor Building"},
    "Places where racks should be added": {"", "Baseball", "County", "Einstein"},
    "Lockers, Maintenance, Etc.": {"", "FOB", "Richards Building"},
}


def normalize(data, ids):
    if data.get("exceededTransferLimit"):
        raise ValueError("Incomplete feature query")
    wkid = data["spatialReference"].get("latestWkid", data["spatialReference"]["wkid"])
    if wkid == 3566:
        from pyproj import Transformer
        convert = Transformer.from_crs(3566, 4326, always_xy=True).transform
    elif wkid == 4326:
        convert = lambda x, y: (x, y)
    else:
        raise ValueError(f"Unexpected source CRS {wkid}")

    features, new_folders, globals_seen = [], set(), set()
    for record in data["features"]:
        a = record["attributes"]
        oid, gid = a["OBJECTID"], a["GlobalID"]
        identity = UUID(gid)
        if type(oid) is not int or identity in globals_seen:
            raise ValueError("Invalid or repeated source ID")
        globals_seen.add(identity)
        folder = (a["FOLDERPATH"] or "").strip()
        parent, _, child = folder.removeprefix(ROOT).partition("/")
        known = folder.startswith(ROOT) and parent in FOLDERS
        if folder and (not known or child not in FOLDERS[parent]):
            new_folders.add(folder)
        category = parent if known else "Unclassified"
        name, caption = ((a[key] or "").strip() for key in ("NAME", "CAPTION"))
        if re.search(r"<[!/a-zA-Z]|https?://", name + " " + caption, re.I):
            raise ValueError(f"Review non-plain source text for {oid}")
        x, y = convert(record["geometry"]["x"], record["geometry"]["y"])
        if not (-111.85 < x < -111.48 and 40.10 < y < 40.37):
            raise ValueError(f"Review coordinates outside Provo for {oid}")
        features.append({"type": "Feature", "id": oid,
                         "geometry": {"type": "Point", "coordinates": [round(x, 7), round(y, 7)]},
                         "properties": {"globalId": gid, "name": name, "category": category, "caption": caption}})
    received = {f["id"] for f in features}
    if not received or received != set(ids) or len(received) != len(features) or len(ids) != len(received):
        raise ValueError("ID inventory and point membership disagree")
    return sorted(features, key=lambda f: f["id"]), sorted(new_folders)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("features", "ids", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    points, flags = normalize(json.loads(args.features.read_bytes()), json.loads(args.ids.read_bytes())["objectIds"])
    if flags:
        parser.error(f"Review new folder paths before packaging: {flags}")
    body = (json.dumps({"type": "FeatureCollection", "features": points}, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    manifest = {"name": "provo-bike-parking", "version": args.version, "title": "Bike Parking in Provo",
                "snapshot": str(args.date), "source": SOURCE, "credit": "Provo City GIS",
                "counts": dict(Counter(f["properties"]["category"] for f in points)),
                "resources": [{"name": "locations", "path": "locations.geojson", "bytes": len(body),
                               "hash": "sha256:" + hashlib.sha256(body).hexdigest()}]}
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "locations.geojson").write_bytes(body)
    (args.output / "datapackage.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
