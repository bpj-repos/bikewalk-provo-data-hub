"""Prepare route-aligned bicycle stress resources from a pinned local BNA run and Utah Bikeways."""

import argparse
import gzip
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from pyproj import Transformer
from shapely import total_bounds
from shapely.geometry import box, mapping, shape
from shapely.ops import substring, transform
from shapely.strtree import STRtree

PROJECT = Transformer.from_crs(4326, 32612, always_xy=True).transform
UNPROJECT = Transformer.from_crs(32612, 4326, always_xy=True).transform
KEYS = ("safe-route-stress-segments", "safe-route-stress-crossings")
BNA = "Brokenspoke local"
UTAH = "Utah Bikeways"


def load(p):
    raw = p.read_bytes()
    return json.loads(gzip.decompress(raw) if p.suffix == ".gz" else raw)


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, value):
    p.write_text(
        json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        + "\n"
    )


def vec(a, b):
    dx, dy = b.x - a.x, b.y - a.y
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n else (0, 0)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def tangent(line, m):
    return vec(
        line.interpolate(max(0, m - 2)), line.interpolate(min(line.length, m + 2))
    )


def bearing(direction):
    return (
        "north",
        "northeast",
        "east",
        "southeast",
        "south",
        "southwest",
        "west",
        "northwest",
    )[round(math.atan2(*direction) * 4 / math.pi) % 8]


def category(scores):
    valid = [s for s in scores if s is not None]
    return ("higher" if max(valid) > 2 else "lower") if valid else "unassessed"


class Network:
    def __init__(self, rows, bounds):
        self.lines = []
        self.props = []
        for f in rows:
            g = shape(f["geometry"])
            if not g.intersects(bounds):
                continue
            if g.geom_type != "LineString":
                raise ValueError("Unexpected network geometry")
            self.lines.append(transform(PROJECT, g))
            self.props.append(f["properties"])
        self.tree = STRtree(self.lines)

    def match(self, point, direction):
        candidates = []
        for idx in self.tree.query(point, predicate="dwithin", distance=12):
            idx = int(idx)
            line = self.lines[idx]
            m = line.project(point)
            alignment = dot(direction, tangent(line, m))
            if abs(alignment) < 0.87 or not 0.05 < m < line.length - 0.05:
                continue
            candidates.append(
                (
                    line.distance(point) + 6 * (1 - abs(alignment)),
                    idx,
                    1 if alignment > 0 else -1,
                )
            )
        candidates.sort()
        if not candidates:
            return None, "unmatched"
        if len(candidates) > 1 and candidates[1][0] - candidates[0][0] < 3:
            return None, "ambiguous"
        return candidates[0][1:], "matched"


def bna_scores(p, field, sign):
    vals = [p.get("ft_" + field), p.get("tf_" + field)]
    if p.get("one_way") == "ft":
        vals[1] = None
    if p.get("one_way") == "tf":
        vals[0] = None
    if any(v not in (None, 1, 2, 3, 4) for v in vals):
        raise ValueError("Unknown BNA score")
    return vals if sign == 1 else vals[::-1]


def feature(id_, geom, props):
    return dict(
        type="Feature",
        id=id_,
        geometry=mapping(transform(UNPROJECT, geom)),
        properties=props,
    )


def build(base, ways, nodes, utah, output, *, osm_date="2026-11-07", utah_date="2026-10-09"):
    routes = load(base / "safe-school-routes.geojson")["features"]
    plans = load(base / "safe-route-plan-features.geojson")["features"]

    bounds = box(*total_bounds([shape(r["geometry"]) for r in routes])).buffer(0.002)
    nets = [Network(load(p)["features"], bounds) for p in (ways, utah)]
    arms = defaultdict(list)
    for p in nets[0].props:
        for node in (p["intersection_from"], p["intersection_to"]):
            arms[node].append(p)
    junctions = {f["properties"]["int_id"]: f for f in load(nodes)["features"]}
    segments = []
    crossings = []
    review = defaultdict(Counter)
    plan_points = defaultdict(list)
    for f in plans:
        if f["properties"]["featureType"].startswith("crosswalk-"):
            plan_points[f["properties"]["schoolId"]].append(
                (f, transform(PROJECT, shape(f["geometry"])))
            )
    for route in routes:
        school = route["properties"]["schoolId"]
        name = route["properties"]["schoolName"]
        parent = route["id"]
        common = dict(routeId=parent, schoolId=school, schoolName=name)
        geom = shape(route["geometry"])
        for part, raw in enumerate(
            geom.geoms if geom.geom_type == "MultiLineString" else [geom]
        ):
            line = transform(PROJECT, raw)
            n = max(1, math.ceil(line.length / 5))
            runs = []
            for i in range(n):
                m = (i + 0.5) * line.length / n
                pt = line.interpolate(m)
                direction = tangent(line, m)
                b, reason = nets[0].match(pt, direction)
                u, u_reason = nets[1].match(pt, direction)
                if b:
                    bp = nets[0].props[b[0]]
                    scores = bna_scores(bp, "seg_stress", b[1])
                    if u and nets[1].props[u[0]].get("LTS_SCORE"):
                        alt = int(str(nets[1].props[u[0]]["LTS_SCORE"])[0])
                        review[name]["comparedMeters"] += line.length / n
                        if category(scores) != category([alt]):
                            review[name]["disagreeMeters"] += line.length / n
                    if not any(s is not None for s in scores):
                        b = None
                key = (
                    (0, b, "matched")
                    if b
                    else (1, u, "matched")
                    if u
                    and nets[1].props[u[0]].get("LTS_SCORE")
                    and reason != "ambiguous"
                    else (
                        None,
                        None,
                        "ambiguous"
                        if "ambiguous" in (reason, u_reason)
                        else "unmatched",
                    )
                )
                if not runs or runs[-1][0] != key:
                    runs.append([key, i, i + 1])
                else:
                    runs[-1][2] = i + 1
            rid = f"{parent}:{part}"
            seen = []
            for ix, ((net, match, status), start, end) in enumerate(runs):
                props = dict(
                    common,
                    source=None,
                    sourceId=None,
                    street=None,
                    sourceDate=None,
                    matchStatus=status,
                    part=part,
                )
                scores = [None, None]
                if net is not None:
                    p = nets[net].props[match[0]]
                    props.update(
                        source=(BNA, UTAH)[net],
                        sourceDate=(osm_date, utah_date)[net],
                        sourceId=str(p["OBJECTID" if net else "road_id"]),
                        street=p.get("NAME" if net else "name"),
                    )
                    if net:
                        raw_score = p["LTS_SCORE"]
                        v = int(str(raw_score)[0])
                        if v not in range(5):
                            raise ValueError("Unknown Utah score")
                        props["utahLts"] = raw_score
                        props["directionBasis"] = "undirected"
                        scores = [v, v]
                    else:
                        scores = bna_scores(p, "seg_stress", match[1])
                        props["directionBasis"] = "route-coordinate-order"
                piece = substring(line, start * line.length / n, end * line.length / n)
                v = tangent(line, (start + end) * line.length / (2 * n))
                props.update(
                    forwardBearing=bearing(v),
                    reverseBearing=bearing((-v[0], -v[1])),
                    forward=scores[0],
                    reverse=scores[1],
                    stress=category(scores),
                    lengthMeters=round(piece.length, 3),
                )
                segments.append(feature(f"{rid}:s{ix}", piece, props))
                review[name][props["stress"] + "Meters"] += piece.length
                review[name][(props["source"] or "unassessed") + " source meters"] += (
                    piece.length
                )
            # Only straight continuations between connected, matched ways pass through an intersection.
            for ix, ((left, _, end), (right, start, _)) in enumerate(
                zip(runs, runs[1:])
            ):
                if left[0] != 0 or right[0] != 0:
                    continue
                lidx, ls = left[1]
                ridx, rs = right[1]
                a, b = nets[0].props[lidx], nets[0].props[ridx]
                node = a["intersection_to" if ls == 1 else "intersection_from"]
                if node != b["intersection_from" if rs == 1 else "intersection_to"]:
                    continue
                j = junctions.get(node)
                if not j or (j["properties"]["legs"] or 0) < 3:
                    continue
                point = transform(PROJECT, shape(j["geometry"]))
                m = end * line.length / n
                if point.distance(line.interpolate(m)) > 12:
                    continue
                turn = dot(
                    vec(line.interpolate(max(0, m - 14)), line.interpolate(m)),
                    vec(
                        line.interpolate(m), line.interpolate(min(line.length, m + 14))
                    ),
                )
                if turn < 0.87:
                    continue
                fs = bna_scores(a, "int_stress", ls)[0]
                rs_score = bna_scores(b, "int_stress", rs)[1]
                # Each value describes the approach ending at this node, in its travel direction.
                v = vec(line.interpolate(max(0, m - 14)), line.interpolate(m))
                w = vec(line.interpolate(min(line.length, m + 14)), line.interpolate(m))
                side_names = sorted(
                    {
                        p["name"]
                        for p in arms[node]
                        if p.get("name")
                        and p["name"] not in (a.get("name"), b.get("name"))
                    }
                )
                props = dict(
                    common,
                    crossStreet=" / ".join(side_names) or None,
                    forwardBearing=bearing(v),
                    reverseBearing=bearing(w),
                    source=BNA,
                    sourceDate=osm_date,
                    sourceId=str(node),
                    approachIds=[a["road_id"], b["road_id"]],
                    street=a.get("name") or b.get("name"),
                    forward=fs,
                    reverse=rs_score,
                    stress=category([fs, rs_score]),
                    matchStatus="connected-through",
                    planFeatureIds=[],
                )
                f = feature(f"{rid}:x{ix}", point, props)
                crossings.append(f)
                seen.append((point, f))
            for pf, point in plan_points[school]:
                if point.distance(line) > 10:
                    continue
                near = [f for q, f in seen if q.distance(point) <= 8]
                if len(near) == 1:
                    near[0]["properties"]["planFeatureIds"].append(pf["id"])
                    continue
                props = dict(
                    common,
                    source="UDOT school plan",
                    sourceId=pf["id"],
                    sourceDate=pf["properties"]["sourceRetrievedAt"][:10],
                    street=None,
                    forward=None,
                    reverse=None,
                    stress="unassessed",
                    matchStatus="plan-crosswalk",
                    planFeatureIds=[pf["id"]],
                )
                crossings.append(feature(f"{rid}:plan:{pf['id']}", point, props))
            if abs(
                sum(
                    f["properties"]["lengthMeters"]
                    for f in segments
                    if f["properties"]["routeId"] == parent
                    and f["properties"]["part"] == part
                )
                - line.length
            ) > 0.001 * len(runs):
                raise ValueError("Route length mismatch")
    output.mkdir(parents=True, exist_ok=False)
    for key, rows in zip(KEYS, (segments, crossings)):
        if len({f["id"] for f in rows}) != len(rows):
            raise ValueError("Duplicate child ID")
        write(
            output / (key + ".geojson"), dict(type="FeatureCollection", features=rows)
        )
    for f in crossings:
        review[f["properties"]["schoolName"]][
            f["properties"]["stress"] + "Crossings"
        ] += 1
    write(
        output / "stress-coverage.json",
        {
            k: {label: round(v, 2) for label, v in sorted(counts.items())}
            for k, counts in sorted(review.items())
        },
    )
    write(
        output / "stress-inputs.json",
        {
            p.name: digest(p)
            for p in [
                ways,
                nodes,
                utah,
                base / "safe-school-routes.geojson",
                base / "safe-route-plan-features.geojson",
            ]
        },
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for arg in ("base", "ways", "nodes", "utah", "output"):
        cli.add_argument(arg, type=Path)
    build(**vars(cli.parse_args()))
