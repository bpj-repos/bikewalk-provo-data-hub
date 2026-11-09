"""Privately compare the local model with People's published Provo BNA movements."""

from collections import Counter, defaultdict
import math

from shapely.geometry import Point, box, shape
from shapely import total_bounds
from shapely.ops import transform
from scripts.route_stress import (
    load,
    Network,
    PROJECT,
    tangent,
    dot,
    bna_scores,
    category,
)


def compare(stress, inputs):
    segments = load(stress / "safe-route-stress-segments.geojson")["features"]
    crossings = load(stress / "safe-route-stress-crossings.geojson")["features"]
    bounds = box(*total_bounds([shape(f["geometry"]) for f in segments])).buffer(0.002)
    ways = Network(load(inputs / "neighborhood_ways.geojson")["features"], bounds)
    local = {p["road_id"]: i for i, p in enumerate(ways.props)}
    published = Network(load(inputs / "published-ways.geojson")["features"], bounds)
    ends = defaultdict(list)
    for g, p in zip(published.lines, published.props):
        for m, sign in [(0, -1), (g.length, 1)]:
            dx, dy = tangent(g, m)
            ends[p["osm_id"]].append(
                (
                    g.interpolate(m),
                    (sign * dx, sign * dy),
                    bna_scores(p, "int_stress", sign)[0],
                )
            )
    meters = Counter()
    approaches = Counter()
    differences = []
    for f in segments:
        p = f["properties"]
        if p["source"] != "Brokenspoke local":
            continue
        way = ways.props[local[int(p["sourceId"])]]
        g = transform(PROJECT, shape(f["geometry"]))
        n = max(1, math.ceil(g.length / 5))
        for j in range(n):
            m = g.length * (j + 0.5) / n
            hit, _ = published.match(g.interpolate(m), tangent(g, m))
            outcome = "noComparableMovement"
            if hit:
                peer = published.props[hit[0]]
                scores = bna_scores(peer, "seg_stress", hit[1])
                if peer["osm_id"] == way["osm_id"] and any(
                    v is not None for v in scores
                ):
                    outcome = "agree" if category(scores) == p["stress"] else "differ"
            meters[outcome] += p["lengthMeters"] / n
    for f in crossings:
        p = f["properties"]
        if p["source"] != "Brokenspoke local":
            continue
        point = transform(PROJECT, shape(f["geometry"]))
        for rid, score in zip(p["approachIds"], [p["forward"], p["reverse"]]):
            if score is None:
                continue
            idx = local[rid]
            way = ways.props[idx]
            g = ways.lines[idx]
            is_to = way["intersection_to"] == int(p["sourceId"])
            bearing = tangent(g, g.length if is_to else 0)
            if not is_to:
                bearing = tuple(-v for v in bearing)
            matches = [
                v
                for pos, d, v in ends[way["osm_id"]]
                if pos.distance(point) <= 5 and dot(bearing, d) > 0.87 and v is not None
            ]
            result = (
                "noComparableMovement"
                if len(matches) != 1
                else "agree"
                if category([score]) == category(matches)
                else "differ"
            )
            approaches[result] += 1
            if result == "differ":
                differences.append(
                    dict(
                        id=f["id"],
                        local=score,
                        published=matches[0],
                        osmId=way["osm_id"],
                    )
                )
    return dict(
        segmentMeters={k: round(v, 2) for k, v in meters.items()},
        crossingDirections=dict(approaches),
        crossingDifferences=differences,
        method="Matched OSM way and unique aligned public segment, sampled at most every 5 m. Crossings compare one incoming direction on the same OSM way at an endpoint within 5 m and aligned within about 30 degrees. Different vintages and unmatched geometry limit comparison. These are model-to-model differences.",
    )
