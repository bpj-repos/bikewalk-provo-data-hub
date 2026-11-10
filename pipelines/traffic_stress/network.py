"""Reconcile source ratings without changing their scoring criteria."""
import hashlib
import json
import math
from collections import Counter, defaultdict

from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import substring, transform
from shapely.strtree import STRtree

from scripts.route_stress import PROJECT, UNPROJECT, load, tangent, dot

PUBLISHED = 'peopleforbikes'
LOCAL = 'bikewalk-brokenspoke'
UTAH = 'utah-bikeways'
PATHS = {'path', 'cycleway', 'footway', 'pedestrian', 'bridleway'}
ROADS = {'primary', 'secondary', 'tertiary', 'residential', 'unclassified', 'living_street', 'service',
         'primary_link', 'secondary_link', 'tertiary_link', 'trunk', 'trunk_link', 'road', 'track'}


def band(score):
    if score is None:
        return None
    if score not in (0, 1, 2, 3, 4):
        raise ValueError('Unsupported native stress score')
    return 'lower' if score <= 2 else 'higher'


def select(observations):
    """Choose one applicable observation, independent of source input order."""
    candidates = [o for o in observations if o['score'] is not None and o['applicable']]
    if not candidates:
        return dict(band=None, score=None, source=None, selectedVersion=None, selectionReason='no_applicable_rating', disagreement=False)
    for o in candidates:
        band(o['score'])
    precedence = {PUBLISHED: 0, UTAH: 1, LOCAL: 2, 'bikewalk-furth': 3}
    published = [o for o in candidates if o['source'] in (PUBLISHED, UTAH)]
    pool = published or candidates
    supported = [o for o in pool if o.get('betterEvidence')]
    # Mixed evidence uses the same directional tie-break as equal evidence.
    winner = min(supported if len(supported) == 1 else pool,
                 key=lambda o: (precedence[o['source']], str(o['recordId'])))
    reason = 'sole_applicable_source'
    if len(pool) > 1:
        reason = 'documented_input_evidence' if len(supported) == 1 else 'published_directional_tiebreak'
    if not published:
        reason = 'published_method_gap_fill'
    return dict(band=band(winner['score']), score=winner['score'], source=winner['source'], selectedVersion=winner.get('version'),
                selectionReason=reason, disagreement=len({band(o['score']) for o in candidates}) > 1)


def eligibility(tags):
    h = tags['highway']
    access = tags.get('bicycle', tags.get('access', 'yes'))
    if access in ('no', 'private', 'customers', 'customers_only') or tags.get('area') == 'yes':
        return 'ineligible'
    if h in ('construction', 'proposed', 'motorway', 'motorway_link', 'steps', 'raceway', 'busway', 'platform'):
        return 'ineligible'
    if h in ('trunk', 'trunk_link') and tags.get('bicycle') not in ('yes', 'designated', 'permissive'):
        return 'access_unknown'
    if h in ('footway', 'pedestrian', 'bridleway') and tags.get('bicycle') not in ('yes', 'designated', 'permissive'):
        return 'access_unknown'
    if h == 'service' and (tags.get('service') in ('parking_aisle', 'driveway', 'drive-through') or
                           not tags.get('name') and tags.get('service') != 'alley'):
        return 'service_access'
    if access in ('destination', 'delivery') or tags.get('bicycle:conditional') or tags.get('access:conditional'):
        return 'access_unknown'
    return 'eligible' if h in ROADS | PATHS else 'out_of_scope'


def directions(tags):
    value = tags.get('oneway:bicycle', tags.get('oneway', 'yes' if tags.get('junction') == 'roundabout' else 'no'))
    if 'oneway:bicycle' not in tags and any('opposite' in tags.get(k, '') for k in ('cycleway', 'cycleway:left', 'cycleway:right')):
        value = 'no'
    if value in ('yes', '1', 'true'):
        return ['forward']
    if value == '-1':
        return ['reverse']
    return ['forward', 'reverse']


def parts(geometry):
    if geometry.geom_type == 'LineString':
        yield geometry
    elif hasattr(geometry, 'geoms'):
        for g in geometry.geoms:
            yield from parts(g)


class Ratings:
    def __init__(self, rows, source, version, city):
        rows = sorted(rows, key=lambda f: str(f['properties'].get('road_id', f['properties'].get('OBJECTID'))))
        self.lines, self.props = [], []
        self.source, self.version = source, version
        for f in rows:
            g = shape(f['geometry'])
            if g.intersects(city) and g.geom_type == 'LineString':
                self.lines.append(transform(PROJECT, g))
                self.props.append(f['properties'])
        self.tree = STRtree(self.lines)

    def match(self, point, direction, tags, osm_id=None):
        candidates = []
        if self.source == UTAH and (tags.get('bridge', 'no') != 'no' or tags.get('tunnel', 'no') != 'no' or tags.get('layer', '0') != '0'):
            return None, 'grade_not_documented'
        for index in self.tree.query(point, predicate='dwithin', distance=8):
            index = int(index)
            p, line = self.props[index], self.lines[index]
            if self.source != UTAH:
                if osm_id is None or str(p['osm_id']) != str(osm_id):
                    continue
            elif (tags['highway'] in PATHS) != (p['SOURCE'] == 'Trails Pathways'):
                continue
            m = line.project(point)
            alignment = dot(direction, tangent(line, m))
            if abs(alignment) < .87 or not .01 < m < line.length - .01:
                continue
            candidates.append((line.distance(point) + 6 * (1 - abs(alignment)), index, alignment > 0))
        candidates.sort()
        if not candidates:
            return None, 'unmatched_geometry'
        if len(candidates) > 1 and candidates[1][0] - candidates[0][0] < 3:
            return None, 'ambiguous_geometry'
        return candidates[0][1:], 'matched'

    def observation(self, match, direction, point=None):
        index, aligned = match
        p = self.props[index]
        if self.source == UTAH:
            score = int(p['LTS_SCORE'][0]) if p.get('LTS_SCORE') else None
            same = p.get('Facility1') == p.get('Facility2') or p['SOURCE'] == 'Trails Pathways'
            side = p.get('Facility1_Side')
            # Utah publishes one best-facility score. Apply asymmetric records only at whole-line scope.
            applicable = direction == 'unspecified' or same or side in ('Both', 'Both Sides')
            return dict(source=UTAH, version=self.version, recordId=str(p['OBJECTID']), score=score,
                        nativeLabel=p.get('LTS_SCORE'), directionScope='unspecified', applicable=applicable,
                        facility=p.get('Facility1'), facilitySide=side, secondaryFacility=p.get('Facility2'),
                        secondarySide=p.get('Facility2_Side'), inputBasis='publisher_inputs_not_exported')
        d = 'ft' if (direction == 'forward') == aligned else 'tf'
        score = p.get(d + '_seg_stress')
        applicable = p.get('one_way') not in ('ft', 'tf') or p['one_way'] == d
        return dict(source=self.source, version=self.version, recordId=str(p['road_id']), score=score,
                    nativeLabel=None, directionScope=d, applicable=applicable, osmId=p['osm_id'],
                    speedMph=p.get('speed_limit'), lanes=p.get(d + '_lanes'),
                    inputBasis='explicit_and_model_defaults', speedBasis='source_field' if p.get('speed_limit') is not None else 'model_default_or_unavailable')


def feature(identifier, geometry, properties):
    g = transform(UNPROJECT, geometry)
    return dict(type='Feature', id=identifier, geometry=mapping(g), properties=properties)


def furth_crossing(speed, lanes, island):
    """Original 2012 Table 6, crossed street width, not incoming street width."""
    if speed is None or lanes is None or type(island) is not bool:
        return None
    if speed <= 0 or lanes < 1 or int(lanes) != lanes:
        raise ValueError('Invalid crossing inputs')
    if 25 < speed < 30 or 30 < speed < 35 or 35 < speed < 40:
        return None
    row = 0 if speed <= 25 else 1 if speed <= 30 else 2 if speed <= 35 else 3
    col = 0 if lanes <= 3 else 1 if lanes <= 5 else 2
    table = ((1, 1, 2), (1, 2, 3), (2, 3, 4), (3, 4, 4)) if island else ((1, 2, 4), (1, 2, 4), (2, 3, 4), (3, 4, 4))
    return table[row][col]


def build(inputs, metadata, evidence):
    city = shape(inputs['boundary']['features'][0]['geometry'])
    network = inputs['network']
    coords = {int(k): v for k, v in network['coords'].items()}
    ways = sorted(network['ways'], key=lambda w: w[0])
    nets = [Ratings(inputs[key]['features'], source, metadata[key]['version'], city)
            for key, source in [('published', PUBLISHED), ('utah', UTAH), ('local', LOCAL)]]
    reference = {str(wid): (ns, tags) for wid, ns, tags in ways}

    def currently_allowed(p, direction, source_line):
        item = reference.get(str(p['osm_id']))
        if item is None:
            return True
        ns, tags = item
        if eligibility(tags) == 'ineligible':
            return False
        current = transform(PROJECT, LineString([coords[n] for n in ns]))
        middle = source_line.interpolate(source_line.length / 2)
        aligned = dot(tangent(source_line, source_line.length / 2), tangent(current, current.project(middle))) >= 0
        travel = 'forward' if (direction == 'ft') == aligned else 'reverse'
        return travel in directions(tags)

    uses = Counter(n for _, ns, t in ways if eligibility(t) == 'eligible' for n in set(ns))
    neighbors = defaultdict(set)
    segments, approaches, supplemental = [], [], []
    metrics = defaultdict(Counter)
    eligible_lines = []
    bna_endpoint = defaultdict(list)
    for net in (nets[0], nets[2]):
        for index, (line, p) in enumerate(zip(net.lines, net.props)):
            for d, endpoint in [('ft', -1), ('tf', 0)]:
                if p.get('one_way') in ('ft', 'tf') and p['one_way'] != d:
                    continue
                bna_endpoint[str(p['osm_id'])].append((net, index, d, Point(line.coords[endpoint])))
    evidence_by_key = {}
    used_evidence = set()
    for e in evidence:
        required = ('featureId', 'source', 'recordId', 'attribute', 'observedDate', 'reference', 'competingBasis')
        if any(not e.get(k) for k in required) or e['competingBasis'] not in ('default', 'older_observation'):
            raise ValueError('Incomplete decisive evidence')
        from datetime import date
        date.fromisoformat(e['observedDate'])
        if e['attribute'] not in ('speed', 'lanes', 'facility', 'facility_side', 'width', 'control', 'volume', 'refuge'):
            raise ValueError('Evidence attribute is outside the published methods')
        key = e['featureId'], e['source'], str(e['recordId'])
        if key in evidence_by_key:
            raise ValueError('Duplicate evidence identity')
        evidence_by_key[key] = e

    def add_segment(base, line, tags, direction, observations, match_reasons):
        identifier = base + ':' + direction
        for o in observations:
            e = evidence_by_key.get((identifier, o['source'], o['recordId']))
            if e:
                o['betterEvidence'] = e
                used_evidence.add((identifier, o['source'], o['recordId']))
        props = dict(featureId=base, direction=direction, eligibility=eligibility(tags),
                     roadClass=tags['highway'], name=tags.get('name'), bridge=tags.get('bridge'),
                     tunnel=tags.get('tunnel'), lengthMeters=round(line.length, 3), observations=observations,
                     matchReasons=match_reasons, **select(observations))
        winner = next((o for o in observations if o['source'] == props['source'] and o['applicable'] and o['score'] == props['score']), {})
        props.update(speedMph=winner.get('speedMph'), lanes=winner.get('lanes'),
                     speedBasis=winner.get('speedBasis', 'unavailable'), laneBasis='source_field' if winner.get('lanes') is not None else 'unavailable')
        segments.append(feature(identifier, line, props))
        c = metrics[props['roadClass']]
        if direction in ('forward', 'reverse'):
            c['eligibleDirectionMeters'] += line.length
            c['ratedDirectionMeters' if props['band'] else 'unratedDirectionMeters'] += line.length
            c['selected:' + str(props['source'])] += line.length
            published = any(o['source'] == PUBLISHED and o['applicable'] and o['score'] is not None for o in observations)
            utah = any(o['source'] == UTAH and o['applicable'] and o['score'] is not None for o in observations)
            c['overlap' if published and utah else 'publishedOnly' if published else 'utahOnly' if utah else 'neitherPublished'] += line.length
            c['disagreementDirectionMeters'] += line.length * props['disagreement']
        return props

    for wid, ns, tags in ways:
        state = eligibility(tags)
        raw = LineString([coords[n] for n in ns])
        if not raw.intersects(city):
            continue
        if state != 'eligible':
            metrics['excluded'][state + 'Meters'] += sum(transform(PROJECT, p).length for p in parts(raw.intersection(city)))
            continue
        for a, b in zip(ns, ns[1:]):
            if a != b:
                neighbors[a].add(b)
                neighbors[b].add(a)
        cuts = [0] + [i for i in range(1, len(ns)-1) if uses[ns[i]] > 1] + [len(ns)-1]
        for start, end in zip(cuts, cuts[1:]):
            full = transform(PROJECT, LineString([coords[n] for n in ns[start:end+1]]))
            for part_index, clipped in enumerate(parts(transform(UNPROJECT, full).intersection(city))):
                line = transform(PROJECT, clipped)
                if line.length < .01:
                    continue
                eligible_lines.append(line)
                metrics[tags['highway']]['physicalMeters'] += line.length
                n = max(1, math.ceil(line.length / 5))
                runs = []
                for k in range(n):
                    m = (k + .5) * line.length / n
                    point, vector = line.interpolate(m), tangent(line, m)
                    matches = [net.match(point, vector, tags, wid) for net in nets]
                    signature = tuple((match, reason) for match, reason in matches)
                    if runs and runs[-1][2] == signature:
                        runs[-1][1] = (k + 1) * line.length / n
                    else:
                        runs.append([k * line.length / n, (k+1) * line.length / n, signature])
                for run, (lo, hi, matches) in enumerate(runs):
                    sub = substring(line, lo, hi)
                    base = f'osm:{wid}:{ns[start]}:{ns[end]}:{part_index}:{run}'
                    any_rated = False
                    for direction in directions(tags):
                        observations = [net.observation(match, direction) for net, (match, _) in zip(nets, matches) if match]
                        props = add_segment(base, sub, tags, direction, observations, [r for _, r in matches])
                        props.update(osmId=wid, fromNode=str(ns[start]) if lo == 0 and Point(coords[ns[start]]).distance(clipped.boundary) < 1e-8 else None,
                                     toNode=str(ns[end]) if hi == line.length and Point(coords[ns[end]]).distance(clipped.boundary) < 1e-8 else None)
                        any_rated |= props['band'] is not None
                    utah_match = matches[1][0]
                    if utah_match:
                        o = nets[1].observation(utah_match, 'unspecified')
                        if o['score'] is not None and not all(nets[1].observation(utah_match, d)['applicable'] for d in directions(tags)):
                            add_segment(base, sub, tags, 'unspecified', [o], ['whole_line_only'])
                            any_rated = True
                    metrics[tags['highway']]['ratedPhysicalMeters' if any_rated else 'unratedPhysicalMeters'] += sub.length
                assert abs(sum(hi-lo for lo, hi, _ in runs) - line.length) < .001
        for a, b, direction in [(ns[0], ns[1], 'reverse'), (ns[-1], ns[-2], 'forward')] + [
            item for i in range(1, len(ns)-1) if uses[ns[i]] > 1
            for item in [(ns[i], ns[i-1], 'forward'), (ns[i], ns[i+1], 'reverse')]]:
            if direction not in directions(tags) or not city.covers(Point(coords[a])):
                continue
            # Final junction degree is evaluated after every eligible way has contributed.
            observations = []
            point = transform(PROJECT, Point(coords[a]))
            incoming = transform(PROJECT, LineString([coords[b], coords[a]]))
            for net, index, d, end in bna_endpoint[str(wid)]:
                if point.distance(end) > 2:
                    continue
                line = net.lines[index]
                model_vector = tangent(line, line.length if d == 'ft' else 0)
                if d == 'tf':
                    model_vector = (-model_vector[0], -model_vector[1])
                if dot(tangent(incoming, incoming.length), model_vector) < .87:
                    continue
                p = net.props[index]
                observations.append(dict(source=net.source, version=net.version, recordId=str(p['road_id']) + ':' + d,
                                         score=p.get(d + '_int_stress'), directionScope=d, applicable=True,
                                         inputBasis='explicit_and_model_defaults'))
            approach_id = f'approach:{a}:{b}:{wid}'
            for o in observations:
                e = evidence_by_key.get((approach_id, o['source'], o['recordId']))
                if e:
                    o['betterEvidence'] = e
                    used_evidence.add((approach_id, o['source'], o['recordId']))
            approaches.append(feature(approach_id, point, dict(junctionId=str(a), incomingNode=str(b),
                                      osmId=wid, direction=direction, eligibility='eligible', roadClass=tags['highway'],
                                      observations=observations, **select(observations))))
    approaches = [f for f in approaches if len(neighbors[int(f['properties']['junctionId'])]) >= 3]
    approaches = list({f['id']: f for f in approaches}.values())
    for f in approaches:
        f['properties']['legs'] = len(neighbors[int(f['properties']['junctionId'])])
    # Preserve published movements where the reference topology has no corresponding approach.
    existing_points = STRtree([shape(f['geometry']) for f in approaches])
    source_arms = defaultdict(list)
    for index, p in enumerate(nets[0].props):
        source_arms[p['intersection_from']].append(index)
        source_arms[p['intersection_to']].append(index)
    for node, indices in sorted(source_arms.items()):
        if len(set(indices)) < 3:
            continue
        for index in sorted(set(indices)):
            p, line = nets[0].props[index], nets[0].lines[index]
            d = 'ft' if p['intersection_to'] == node else 'tf'
            if p.get('one_way') in ('ft', 'tf') and p['one_way'] != d:
                continue
            if not currently_allowed(p, d, line):
                continue
            point = Point(line.coords[-1 if d == 'ft' else 0])
            geographic = transform(UNPROJECT, point)
            if not city.covers(geographic):
                continue
            context = [dict(source=PUBLISHED, recordId=str(nets[0].props[j]['road_id']),
                            speedMph=nets[0].props[j].get('speed_limit'), lanes=nets[0].props[j].get(dd + '_lanes'))
                       for j in sorted(set(indices)) for dd in ('ft', 'tf')
                       if nets[0].props[j].get(dd + '_seg_stress') is not None]
            nearby = [approaches[int(j)] for j in existing_points.query(geographic.buffer(.000025))
                      if point.distance(transform(PROJECT, shape(approaches[int(j)]['geometry']))) <= 2]
            for f in nearby:
                f['properties']['connectingRoads'] = context
            if any(any(o['source'] == PUBLISHED and o['recordId'] == str(p['road_id']) + ':' + d for o in f['properties']['observations']) for f in nearby):
                continue
            junction_id = nearby[0]['properties']['junctionId'] if nearby else 'pfb:' + str(node)
            o = dict(source=PUBLISHED, version=metadata['published']['version'], recordId=str(p['road_id']) + ':' + d,
                     score=p.get(d + '_int_stress'), directionScope=d, applicable=True, inputBasis='explicit_and_model_defaults')
            approaches.append(feature(f'published-approach:{node}:{p["road_id"]}:{d}', point,
                dict(junctionId=junction_id, incomingNode=None, osmId=p['osm_id'], direction=d,
                     eligibility='source_network', roadClass=p.get('functional_class'), legs=len(set(indices)),
                     observations=[o], connectingRoads=context, incomingSourceSegment=str(p['road_id']),
                     **select([o]))))
    inventory_tree = STRtree(eligible_lines)
    for key in ('city-streets', 'sgid-streets', 'utah', 'published'):
        rows = inputs[key]['features']
        for row in rows:
            raw = shape(row['geometry'])
            for piece_index, piece in enumerate(parts(raw.intersection(city))):
                line = transform(PROJECT, piece)
                if line.length < .01:
                    continue
                n = max(1, math.ceil(line.length / 5))
                unmatched = []
                for k in range(n):
                    point = line.interpolate((k+.5)*line.length/n)
                    vector = tangent(line, (k+.5)*line.length/n)
                    found = any(abs(dot(vector, tangent(eligible_lines[int(j)], eligible_lines[int(j)].project(point)))) >= .87
                                for j in inventory_tree.query(point, predicate='dwithin', distance=12))
                    if not found:
                        if unmatched and unmatched[-1][1] == k:
                            unmatched[-1][1] = k+1
                        else:
                            unmatched.append([k, k+1])
                p = row['properties']
                for k, (lo, hi) in enumerate(unmatched):
                    sub = substring(line, lo*line.length/n, hi*line.length/n)
                    identifier = f'{key}:{p.get("road_id", p.get("OBJECTID", p.get("OBJECTID_1", p.get("FID"))))}:{piece_index}:{k}'
                    public_city = key == 'city-streets' and p.get('OWNER') in ('Provo', 'State', 'County') and not p.get('ACCESSCODE') and p.get('STATUS') not in ('Proposed', 'Closed')
                    if key == 'published':
                        for d, direction in [('ft', 'forward'), ('tf', 'reverse')]:
                            if p.get('one_way') in ('ft', 'tf') and p['one_way'] != d:
                                continue
                            if not currently_allowed(p, d, line):
                                continue
                            o = dict(source=PUBLISHED, version=metadata['published']['version'], recordId=str(p['road_id']),
                                     score=p.get(d + '_seg_stress'), directionScope=d, applicable=True,
                                     inputBasis='explicit_and_model_defaults', speedMph=p.get('speed_limit'), lanes=p.get(d + '_lanes'))
                            segments.append(feature(identifier + ':' + direction, sub,
                                dict(featureId=identifier, direction=direction, eligibility='source_network',
                                     roadClass=p.get('functional_class'), name=p.get('name'), lengthMeters=round(sub.length, 3),
                                     observations=[o], osmId=p['osm_id'], speedMph=o['speedMph'], lanes=o['lanes'],
                                     speedBasis='source_field' if o['speedMph'] is not None else 'unavailable',
                                     laneBasis='source_field' if o['lanes'] is not None else 'unavailable',
                                     **select([o]))))
                    elif public_city:
                        tags = dict(highway='local-inventory', name=p.get('FULLNAME'))
                        match, reason = nets[1].match(sub.interpolate(sub.length/2), tangent(sub, sub.length/2), tags)
                        observations = [nets[1].observation(match, 'unspecified')] if match else []
                        props = add_segment(identifier, sub, tags, 'unspecified', observations, [reason])
                        props.update(eligibility='eligible', geometrySource=key, sourceRecordId=p['OBJECTID'],
                                     speedMph=p.get('SPEED_LMT') or None, speedBasis='city_source_field', lanes=None, laneBasis='total_lanes_only')
                        metrics['local-inventory']['physicalMeters'] += sub.length
                        metrics['local-inventory']['ratedPhysicalMeters' if props['band'] else 'unratedPhysicalMeters'] += sub.length
                    else:
                        supplemental.append(feature(identifier, sub, dict(source=key, sourceRecordId=p.get('OBJECTID', p.get('FID')),
                            lengthMeters=round(sub.length, 3), owner=p.get('OWNER'), name=p.get('NAME', p.get('FULLNAME')),
                            eligibility='inventory_only', selectionReason='additional_geometry_requires_access_and_identity',
                            band=None, score=None)))
    endpoints = defaultdict(list)
    for f in segments:
        p = f['properties']
        node = p.get('toNode') if p['direction'] == 'forward' else p.get('fromNode') if p['direction'] == 'reverse' else None
        if node:
            endpoints[node, p['osmId'], p['direction']].append(f['id'])
    for f in approaches:
        p = f['properties']
        p['incomingSegments'] = sorted(endpoints[p['junctionId'], p['osmId'], p['direction']])
    junctions = defaultdict(list)
    for f in approaches:
        if f['properties']['eligibility'] == 'source_network':
            continue
        junctions[f['properties']['junctionId']].append(f['properties']['band'] is not None)
    coverage = dict(byRoadClass={k: {label: round(value, 3) for label, value in sorted(v.items())} for k, v in sorted(metrics.items())},
                    approaches=dict(total=sum(f['properties']['eligibility'] == 'eligible' for f in approaches), rated=sum(f['properties']['band'] is not None and f['properties']['eligibility'] == 'eligible' for f in approaches),
                                    sourceNetworkAdditional=sum(f['properties']['eligibility'] == 'source_network' for f in approaches),
                                    junctions=len(junctions), fullyRated=sum(all(v) for v in junctions.values()),
                                    partiallyRated=sum(any(v) and not all(v) for v in junctions.values()), unrated=sum(not any(v) for v in junctions.values())),
                    sourceNetworkSegmentDirectionMeters=round(sum(f['properties']['lengthMeters'] for f in segments if f['properties']['eligibility'] == 'source_network'), 3),
                    supplemental=dict(records=len(supplemental), meters=sum(f['properties']['lengthMeters'] for f in supplemental)),
                    method='OSM eligible physical way length once; directional length per allowed direction; Utah unspecified counts only in physical coverage. Five-meter midpoint matching, 8m rating tolerance, 12m supplemental inventory screen. Supplemental sources overlap each other and are excluded from the eligible denominator.')
    if used_evidence != set(evidence_by_key):
        raise ValueError('Evidence references absent feature/source records')
    return segments, approaches, supplemental, coverage
