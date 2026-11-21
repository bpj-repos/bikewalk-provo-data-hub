"""Versioned City street associations; geometry never establishes a grade-separated junction."""
from collections import Counter, defaultdict
import hashlib
import json
import math
import re

from pyproj import Transformer
from shapely.geometry import Point, shape, mapping
from shapely.ops import transform
from shapely import STRtree, normalize as normalize_geometry
from scripts.prepare_crash_streets import normalize, match

TO_METERS = Transformer.from_crs(4326, 26912, always_xy=True).transform
TO_WGS84 = Transformer.from_crs(26912, 4326, always_xy=True).transform


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)+'\n').encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def aliases(properties):
    values = [properties.get(k) for k in ('FULLNAME', 'LABEL')]
    for prefix in ('', 'A1_', 'A2_'):
        values.append(' '.join(str(properties.get(prefix+k) or '') for k in ('PREDIR','NAME','POSTTYPE','POSTDIR')))
    values.append(' '.join(str(properties.get(k) or '') for k in ('AN_NAME','AN_POSTDIR')))
    return sorted({normalize(v.strip()) for v in values if v and v.strip()})


def inventory(features, boundary, rules, source_pin):
    city = transform(TO_METERS, shape(boundary))
    segments, geometries, nodes, seen = [], [], defaultdict(list), set()
    for feature in sorted(features, key=lambda f: str(f['properties']['OBJECTID'])):
        p = feature['properties']; key = str(p['OBJECTID'])
        if key in seen:
            raise ValueError('Repeated City OBJECTID: '+key)
        seen.add(key)
        geom = shape(feature['geometry'])
        if geom.is_empty or not geom.is_valid or geom.geom_type not in ('LineString','MultiLineString'):
            raise ValueError('Invalid City segment geometry: '+key)
        metric = transform(TO_METERS, geom)
        clipped = metric.intersection(city)
        parts = [metric] if metric.geom_type == 'LineString' else list(metric.geoms)
        endpoints = [Point(c) for part in parts for c in (part.coords[0], part.coords[-1])]
        # Coordinate clusters are potential connections only; unknown grade stays unknown.
        precision=rules['endpointPrecisionMeters']
        endpoint_ids = ['city-endpoint:'+digest([round(pt.x/precision),round(pt.y/precision),p.get('VERT_LEVEL')])[:24] for pt in endpoints]
        identifier = 'provo-city:'+key
        for node in endpoint_ids:
            nodes[node].append(identifier)
        eligible = clipped.length > 0 and p.get('STATUS') not in rules['excludedStatuses'] and p.get('CLASSIFICATION') not in rules['excludedClasses']
        physical = 'city-geometry:'+digest([normalize_geometry(geom).wkb_hex,p.get('VERT_LEVEL')])[:24]
        segments.append({'type':'Feature','id':identifier,'geometry':feature['geometry'], 'properties':{
            'source':{k:v for k,v in p.items() if k not in rules['excludedSourceFields']},
            'derived':{'sourceVersion':source_pin,'eligible':eligible,'publicOwner':p.get('OWNER') in rules['eligibleOwners'],
                'names':aliases(p),'physicalGeometryId':physical,'lengthMeters':round(metric.length,3),
                'withinBoundaryLengthMeters':round(clipped.length,3),'endpointIds':endpoint_ids,
                'connectivityStatus':'unknown-grade' if p.get('VERT_LEVEL') is None else 'endpoint-and-recorded-level',
                'grade':p.get('VERT_LEVEL')}}})
        geometries.append(metric)
    return segments, geometries, {k:sorted(set(v)) for k,v in sorted(nodes.items())}, city


def crash_evidence(group):
    observations = [r for o in group['observations'] for r in [o,*([o['statePortal']] if o.get('statePortal') else [])]]
    priority = {'utah-crash-portal':0,'udot-crashes':1,'provo-police-incidents':2}
    observations.sort(key=lambda o:(priority[o['sourceKey']],o['id']))
    locations, roads, references = [], [], []
    for o in observations:
        src = o['sourceKey']; xy = o.get('coordinates')
        if xy and len(xy)==2 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in xy) and -180<=xy[0]<=180 and -90<=xy[1]<=90:
            locations.append((src,Point(*TO_METERS(*xy)),xy))
        if src == 'utah-crash-portal':
            road = o['metadata']['crash'].get('roadName')
        elif src == 'udot-crashes':
            road = o['metadata'].get('MAIN_ROAD_NAME')
        else:
            road = None
        if road:
            roads.append({'source':src,'value':str(road)})
        if src != 'provo-police-incidents':
            references.append({'source':src,'recordId':str(o['sourceRecordId'])})
    return locations, roads, sorted(references,key=lambda r:(r['source'],r['recordId']))


def assign(collection, features, boundary, rules, source_pin):
    segments, geometries, nodes, city = inventory(features,boundary,rules,source_pin)
    tree = STRtree(geometries)
    names = {n:n for s in segments for n in s['properties']['derived']['names']}
    state_groups=defaultdict(set)
    for group in collection['records']:
        for reference in crash_evidence(group)[2]:state_groups[reference['recordId']].add(group['id'])
    if len({g['id'] for g in collection['records']})!=len(collection['records']):raise ValueError('Duplicate managed group ID')
    rows = []
    for group in sorted(collection['records'],key=lambda g:g['id']):
        locations, roads, references = crash_evidence(group)
        junction_evidence=[]
        for observation in group['observations']:
            for o in [observation,*([observation['statePortal']] if observation.get('statePortal') else [])]:
                if o['sourceKey']=='provo-police-incidents':continue
                label=o['metadata'].get('ROADWAY_JUNCT_FEATURE_DESC') or o['metadata'].get('crash',{}).get('roadwayJunction_label')
                if label:junction_evidence.append({'source':o['sourceKey'],'value':label})
        classified_junction=any(e['value'].casefold() in {v.casefold() for v in rules['intersectionClassifications']} for e in junction_evidence)
        ambiguous_identity=any(len(state_groups[r['recordId']])>1 for r in references)
        row = {'identityStatus':'ambiguous-state-id' if ambiguous_identity else 'managed-group', 'crashId':'crash:'+hashlib.sha256(group['id'].encode()).hexdigest()[:24],
               'sourceRecords':references,'status':'missing-location','segmentId':None,'physicalGeometryId':None,
               'ruleVersion':rules['version'],'distanceMeters':None,'junctionReported':None,'reasons':[],'roadEvidence':roads,'candidates':[],
               'junctionEvidence':sorted(junction_evidence,key=lambda e:(e['source'],e['value'])),
               'locationSource':locations[0][0] if locations else None,
               'coordinates':[round(v,4) for v in locations[0][2]] if locations else None}
        rows.append(row)
        if not locations:
            row['reasons']=['no-valid-recorded-location']; continue
        point=locations[0][1]
        if not city.covers(point):
            row.update(status='unmatched',reasons=['outside-road-boundary']); continue
        recorded=set(); junction_reported=classified_junction
        for road in roads:
            parts=re.split(r'\s*(?:&|@|/|\bAND\b|\bAT\b)\s*',road['value'].upper().split(';')[0])
            if len(parts)==1:
                spaced=re.split(r'\s{2,}',parts[0].strip())
                if len(spaced)>1 and all(match(p,names)[0] for p in spaced):parts=spaced
            junction_reported |= len([p for p in parts if p.strip()])>1
            for part in parts:
                found,_=match(part,names)
                if found:recorded.add(found)
        row['junctionReported']=junction_reported
        nearby=tree.query(point.buffer(rules['maximumDistanceMeters']))
        for index in nearby:
            segment=segments[index];derived=segment['properties']['derived'];line=geometries[index]
            distance=point.distance(line)
            if distance > rules['maximumDistanceMeters']:continue
            endpoint_distance=min(point.distance(Point(c)) for part in ([line] if line.geom_type=='LineString' else line.geoms) for c in [part.coords[0],part.coords[-1]])
            row['candidates'].append({'segmentId':segment['id'],'physicalGeometryId':derived['physicalGeometryId'],
                'distanceMeters':round(distance,3),'endpointDistanceMeters':round(endpoint_distance,3),
                'nameAgreement':sorted(recorded.intersection(derived['names'])),'eligible':derived['eligible'],
                'endpointIds':derived['endpointIds'],'grade':derived['grade']})
        row['candidates'].sort(key=lambda c:(c['distanceMeters'],c['segmentId']))
        row['status']='unmatched'
        eligible=[c for c in row['candidates'] if c['eligible']]
        supported=[c for c in eligible if c['nameAgreement']]
        if not supported:
            row['reasons']=['no-corroborated-road-name' if eligible else 'no-eligible-segment-within-tolerance'];continue
        first=supported[0]
        alternatives=[c for c in row['candidates'] if c['physicalGeometryId']!=first['physicalGeometryId'] and
                      (c['distanceMeters']<=first['distanceMeters']+rules['separationMeters'] or
                       (first['endpointDistanceMeters']<=rules['junctionRadiusMeters'] and c['endpointDistanceMeters']<=rules['junctionRadiusMeters']))]
        conflict=any(loc[1].distance(point)>rules['coordinateDisagreementMeters'] for loc in locations if loc[0]!='provo-police-incidents')
        if alternatives or conflict or ambiguous_identity or junction_reported or locations[0][0]=='provo-police-incidents':
            row.update(status='ambiguous',reasons=(['conflicting-source-locations'] if conflict else [])+
                       (['unresolved-state-identity'] if ambiguous_identity else [])+
                       (['recorded-junction'] if junction_reported else [])+
                       (['junction-or-parallel-candidates'] if alternatives else [])+
                       (['police-location-needs-review'] if locations[0][0]=='provo-police-incidents' else []))
        else:
            row.update(status='matched',segmentId=first['segmentId'],physicalGeometryId=first['physicalGeometryId'],
                       distanceMeters=first['distanceMeters'],reasons=['recorded-road-and-location'])
    physical={}
    for segment in segments:
        d=segment['properties']['derived']
        if d['eligible']:
            physical.setdefault(d['physicalGeometryId'],d['withinBoundaryLengthMeters'])
    distances=sorted(r['distanceMeters'] for r in rows if r['status']=='matched')
    report={'crashes':len(rows),'statuses':dict(sorted(Counter(r['status'] for r in rows).items())),
            'sourceSegments':len(segments),'eligibleSegments':sum(s['properties']['derived']['eligible'] for s in segments),
            'physicalGeometryCount':len(physical),'physicalLengthMeters':round(sum(physical.values()),3),
            'matchedDistanceMeters':{str(p):distances[min(len(distances)-1,int((len(distances)-1)*p/100))] if distances else None for p in [0,50,90,95,100]},
            'potentialEndpointClusters':len(nodes),'confirmedConnectivity':False}
    return {'segments.geojson':{'type':'FeatureCollection','features':segments},'assignments.json':rows,
            'endpoints.json':nodes,'coverage.json':report}


def changes(previous, current):
    old={r['crashId']:r for r in previous.get('assignments.json',[])}
    new={r['crashId']:r for r in current['assignments.json']}
    a={s['id']:s for s in previous.get('segments.geojson',{}).get('features',[])}
    b={s['id']:s for s in current['segments.geojson']['features']}
    # Explicit reassignment replaces guesses of stable IDs across provider edits.
    return {'addedCrashes':sorted(new.keys()-old.keys()),'removedCrashes':sorted(old.keys()-new.keys()),
            'changedAssignments':[{'crashId':k,'before':{f:old[k].get(f) for f in ('status','segmentId','physicalGeometryId')},
                                   'after':{f:new[k].get(f) for f in ('status','segmentId','physicalGeometryId')}}
                                  for k in sorted(new.keys()&old.keys()) if any(old[k].get(f)!=new[k].get(f) for f in ('status','segmentId','physicalGeometryId'))],
            'changedAssignmentEvidence':[k for k in sorted(new.keys()&old.keys()) if old[k]!=new[k]],
            'addedSegmentIds':sorted(b.keys()-a.keys()),'removedSegmentIds':sorted(a.keys()-b.keys()),
            'changedSegments':[{'segmentId':k,'oldLengthMeters':a[k]['properties']['derived']['lengthMeters'],
                                'newLengthMeters':b[k]['properties']['derived']['lengthMeters'],
                                'oldWithinBoundaryLengthMeters':a[k]['properties']['derived']['withinBoundaryLengthMeters'],
                                'newWithinBoundaryLengthMeters':b[k]['properties']['derived']['withinBoundaryLengthMeters'],
                                'geometryChanged':a[k]['geometry']!=b[k]['geometry'],
                                'attributesChanged':a[k]['properties']['source']!=b[k]['properties']['source']}
                               for k in sorted(a.keys()&b.keys()) if a[k]['geometry']!=b[k]['geometry'] or a[k]['properties']['source']!=b[k]['properties']['source'] or a[k]['properties']['derived']['withinBoundaryLengthMeters']!=b[k]['properties']['derived']['withinBoundaryLengthMeters']],
            'lineagePolicy':'Provider IDs are version-scoped. Splits, merges and renumbering require full reassignment; no automatic identity inheritance.'}
