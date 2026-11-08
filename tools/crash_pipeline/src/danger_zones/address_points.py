"""Offline exact-address lookup from a retained public UGRC Provo address snapshot."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import re

import requests

from .police_datastore import _street_network_label, _counts
from .util import utc_now, isoformat

LAYER = "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/UtahAddressPoints/FeatureServer/0"
WHERE = "UPPER(City)='PROVO' AND CountyID='49049'"
METHOD = "ugrc-exact-address"


def fetch():
    def query(**params):
        response = requests.get(LAYER + "/query", params={"f": "json", "where": WHERE, **params}, timeout=60)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise ValueError(f"Address service error: {data['error']}")
        return data

    ids = sorted(query(returnIdsOnly="true")["objectIds"])
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("Invalid address ID inventory")
    rows = []
    # Page by ordered offset, and compare every ID with the upstream inventory.
    for offset in range(0, len(ids), 1000):
        page = query(resultOffset=offset, resultRecordCount=1000, orderByFields="OBJECTID",
                     outFields="OBJECTID,FullAdd,UTAddPtID", outSR=4326)
        if page["spatialReference"]["wkid"] != 4326:
            raise ValueError("Unexpected address reference CRS")
        for f in page["features"]:
            a, p = f["attributes"], f["geometry"]
            rows.append([a["OBJECTID"], a["FullAdd"], a["UTAddPtID"], p["x"], p["y"]])
    if [r[0] for r in rows] != ids:
        raise ValueError("Incomplete or changed address inventory")
    return {"source": LAYER, "where": WHERE, "retrievedAt": isoformat(utc_now()), "rows": rows}


def apply_address_points(store, snapshot, digest):
    if snapshot["source"] != LAYER or snapshot["where"] != WHERE or not snapshot["rows"]:
        raise ValueError("Expected the Provo UGRC address reference")
    index = defaultdict(list)
    seen = set()
    for oid, address, source_id, x, y in snapshot["rows"]:
        if oid in seen or not (math.isfinite(x) and math.isfinite(y) and -115 < x < -108 and 36 < y < 43):
            raise ValueError("Invalid address point")
        seen.add(oid)
        if address:
            index[_street_network_label(address)].append((source_id, x, y))
    for r in store["records"]:
        loc = r["location"]
        previous = loc["geocoding"]
        address = loc.get("normalizedAddress") or ""
        if not re.match(r"^\d+\s", address) or "&" in (loc.get("addressPartRaw") or ""):
            continue
        if previous.get("mapEligible") and previous.get("method") != METHOD:
            continue
        hits = index.get(_street_network_label(address), [])
        points = {(x, y) for _, x, y in hits}
        if len(points) == 1:
            x, y = points.pop()
            point = {"lat": y, "lng": x}
        else:
            point = None
        loc["geocoding"] = {"status": "matched" if point else "review-required" if hits else "unmatched",
                            "mapEligible": point is not None, "coordinates": point, "method": METHOD,
                            "provider": "Utah Geospatial Resource Center", "referenceSHA256": digest,
                            "addressPointIDs": sorted(str(i) for i, _, _ in hits if i is not None),
                            "providerCandidates": []}
    store["counts"] = _counts(store["records"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("new_file", type=Path)
    args = parser.parse_args()
    snapshot = fetch()
    with args.new_file.open("x") as out:
        json.dump(snapshot, out, separators=(",", ":"), allow_nan=False)
