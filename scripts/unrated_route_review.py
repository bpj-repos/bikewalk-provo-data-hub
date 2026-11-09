"""Screen unrated plan geometry for reviewable street context. Never assigns a public rating."""

import argparse
from collections import Counter
from pathlib import Path

from shapely.geometry import box, shape
from shapely.ops import transform
from shapely import total_bounds

from scripts.route_stress import load, Network, PROJECT, tangent, bna_scores, write
import math


def band(values):
    data = [v for v in values if v is not None]
    if not data:
        return None
    return "calmer" if max(data) <= 1 else "moderate" if max(data) == 2 else "busier"


def review(stress, ways, utah):
    rows = load(stress)["features"]
    bounds = box(*total_bounds([shape(f["geometry"]) for f in rows])).buffer(0.002)
    b, u = [Network(load(p)["features"], bounds) for p in (ways, utah)]
    stats = Counter()
    leads = []
    for i, f in enumerate(rows):
        p = f["properties"]
        if p["stress"] != "unassessed":
            continue
        length = p["lengthMeters"]
        stats[p["matchStatus"] + "Meters"] += length
        if p["matchStatus"] != "unmatched":
            continue
        # Bounded interpolation is only a lead when the same source way brackets a tiny gap.
        if 0 < i < len(rows) - 1 and length <= 15:
            a, c = (rows[idx]["properties"] for idx in (i - 1, i + 1))
            if (
                a["sourceId"] is not None
                and all(
                    a[k] == c[k]
                    for k in (
                        "source",
                        "sourceId",
                        "routeId",
                        "part",
                        "forward",
                        "reverse",
                    )
                )
                and (a["routeId"], a["part"]) == (p["routeId"], p["part"])
            ):
                leads.append(
                    dict(
                        id=f["id"],
                        school=p["schoolName"],
                        kind="short-gap",
                        meters=length,
                        road=a["street"],
                        context=band([a["forward"], a["reverse"]]),
                    )
                )
                stats["shortGapMeters"] += length
        # A wider search can identify the adjacent roadway. It cannot establish which facility the plan uses.
        g = transform(PROJECT, shape(f["geometry"]))
        n = max(1, math.ceil(g.length / 5))
        context = None
        for j in range(n):
            m = g.length * (j + 0.5) / n
            pt = g.interpolate(m)
            direction = tangent(g, m)
            bm, _ = b.match(pt, direction, distance=25)
            um, _ = u.match(pt, direction, distance=25)
            if not bm or not um:
                break
            bp, up = b.props[bm[0]], u.props[um[0]]
            street = " ".join((bp.get("name") or "").casefold().split())
            if (
                not street
                or street != " ".join((up.get("NAME") or "").casefold().split())
                or not up.get("LTS_SCORE")
            ):
                break
            scores = bna_scores(bp, "seg_stress", bm[1])
            value = band(scores)
            if None in scores or value != band([int(str(up["LTS_SCORE"])[0])]):
                break
            sample = (street, value)
            if context is not None and sample != context:
                break
            context = sample
        else:
            if context:
                leads.append(
                    dict(
                        id=f["id"],
                        school=p["schoolName"],
                        kind="adjacent-road",
                        meters=length,
                        road=context[0],
                        context=context[1],
                    )
                )
                stats["adjacentRoadMeters"] += length
    return dict(summary={k: round(v, 2) for k, v in stats.items()}, leads=leads)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("segments", "ways", "utah", "output"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    write(args.output, review(args.segments, args.ways, args.utah))
