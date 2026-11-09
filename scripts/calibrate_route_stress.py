"""Fit Utah fallback categories to paired local BNA segments and test held-out corridors."""

from collections import Counter, defaultdict
import math
from shapely import total_bounds
from shapely.geometry import box, shape
from shapely.ops import transform
from scripts.route_stress import PROJECT, Network, load, tangent, bna_scores


def samples(routes, ways, utah):
    routes = load(routes)["features"]
    bounds = box(*total_bounds([shape(r["geometry"]) for r in routes])).buffer(0.002)
    b, u = [Network(load(path)["features"], bounds) for path in (ways, utah)]
    bins = {}
    for route in routes:
        geom = shape(route["geometry"])
        for raw in geom.geoms if geom.geom_type == "MultiLineString" else [geom]:
            line = transform(PROJECT, raw)
            n = max(1, math.ceil(line.length / 5))
            for i in range(n):
                m = (i + 0.5) * line.length / n
                p = line.interpolate(m)
                v = tangent(line, m)
                bm, _ = b.match(p, v)
                um, _ = u.match(p, v)
                if not bm or not um:
                    continue
                bp, up = b.props[bm[0]], u.props[um[0]]
                scores = bna_scores(bp, "seg_stress", bm[1])
                if None in scores or not up.get("LTS_SCORE"):
                    continue
                # One vote per approximately 5 m of BNA edge even on overlapping school plans.
                idx = (bp["road_id"], int(b.lines[bm[0]].project(p) // 5))
                key = (
                    int(str(up["LTS_SCORE"])[0]),
                    str(up.get("Facility1") or ""),
                    max(scores) > 2,
                    str(bp["name"] or ("osm:" + str(bp["osm_id"]))).casefold(),
                )
                bins.setdefault(idx, set()).add(key)
    # Different matched Utah categories in one bin are unresolved.
    return [next(iter(values)) for values in bins.values() if len(values) == 1]


def native(score):
    return "calmer" if score <= 1 else "moderate" if score == 2 else "busier"


def counts(rows):
    corridors = defaultdict(Counter)
    for _, _, high, road in rows:
        corridors[road][high] += 1
    return corridors


def fit(rows):
    # Cap long corridors at 500 m; a single short fragment does not get the weight of a whole street.
    byroad = counts(rows)
    if len(rows) < 40 or len(byroad) < 5:
        return None
    high = sum(
        min(100, c.total()) * c[True] / c.total() for c in byroad.values()
    ) / sum(min(100, c.total()) for c in byroad.values())
    return "busier" if high >= 0.80 else "calmer" if high <= 0.20 else None


def loss(label, high):
    # Absolute distance on the 0, 0.5, 1 display scale to the binary BNA reference.
    return abs({"calmer": 0, "moderate": 0.5, "busier": 1}[label] - int(high))


def calibrate(routes, ways, utah):
    rows = samples(routes, ways, utah)
    groups = defaultdict(list)
    for r in rows:
        groups[(r[0], r[1])].append(r)
    table = {}
    for (score, facility), group in sorted(groups.items()):
        corridors = counts(group)
        byhold = defaultdict(list)
        for r in group:
            byhold[r[3]].append(r)
        cv = baseline = 0.0
        accepted = 0
        weight = sum(min(len(v), 100) for v in byhold.values())
        for road, held in byhold.items():
            predicted = fit([r for r in group if r[3] != road])
            accepted += int(predicted is not None)
            cv += (
                min(100, len(held))
                * sum(loss(predicted or native(score), r[2]) for r in held)
                / len(held)
            )
            baseline += (
                min(100, len(held))
                * sum(loss(native(score), r[2]) for r in held)
                / len(held)
            )
        n = len(corridors)
        default = native(score)
        pred = fit(group)
        # Learn an override only when most held-out roads had support and it improves error.
        validated = bool(
            pred
            and accepted / n >= 0.8
            and cv <= baseline
            and (pred == default or baseline - cv >= 0.05 * weight)
        )
        table[f"{score}|{facility}"] = dict(
            display=pred if validated else default,
            basis="calibrated-facility" if validated else "native-utah",
            sampleBins=len(group),
            corridors=n,
            bnaBusierBins=sum(r[2] for r in group),
            validatedFolds=accepted,
            baselineError=round(baseline / weight, 4),
            heldOutError=round(cv / weight, 4),
        )
    return dict(
        method="Five-meter BNA edge bins counted once across plans. Paired unambiguous Utah score and facility, both BNA directions assessed. Each named corridor or unnamed OSM way contributes up to 500 m of weight. Hold out whole corridors. A calibrated class needs at least 40 paired bins, five corridors, 80% corridor-balanced consensus, support in 80% of held-out folds, and at least 0.05 improvement in mean held-out ordinal error to override a native label. Unsupported groups retain the native band. BNA stays primary; crossings retain their own movement scores.",
        groups=table,
    )
