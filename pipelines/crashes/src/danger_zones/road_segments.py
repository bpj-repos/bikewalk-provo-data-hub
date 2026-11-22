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
from scripts.prepare_crash_streets import normalize

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


DIRECTION = r'(?:NORTH|SOUTH|EAST|WEST)'
SUFFIX = r'(?:STREET|AVENUE|ROAD|BOULEVARD|DRIVE|LANE|PARKWAY|PLACE|COURT|CIRCLE|HIGHWAY)'


def road_text(value, rules):
    value=re.sub(r'(?<=\d)(?=[NSEW]\b)', ' ', value.upper())
    value=re.sub(r'\b(?:INTERSTATE|I)[ -]?(\d+)\b', r'INTERSTATE \1', value)
    value=normalize(re.sub(r'[^A-Z0-9 ]', ' ', value))
    for old,new in rules['roadTokenCorrections'].items():
        value=re.sub(r'\b'+re.escape(old)+r'\b',new,value)
    return re.sub(r'(\d+ '+DIRECTION+r') STREET\b',r'\1',value)


def road_key(value, rules):
    return re.sub(r'^'+DIRECTION+r' ', '', road_text(value,rules))


def name_patterns(segments, rules):
    lookup=defaultdict(set)
    for segment in segments:
        for name in segment['properties']['derived']['names']:
            key=road_key(name,rules)
            if not key or re.fullmatch(DIRECTION+'|'+SUFFIX+r'|\d+',key):continue
            lookup[key].add(key)
            shortened=re.sub(r' '+SUFFIX+r'$', '',key)
            if shortened!=key and not re.fullmatch(DIRECTION+'|'+SUFFIX+r'|\d+',shortened):lookup[shortened].add(key)
    for alias,target in rules['reviewedRoadAliases'].items():
        lookup[road_text(alias,rules)].add(road_key(target,rules))
    return [(re.compile(r'(?<!\w)'+re.escape(name)+r'(?!\w)'),values)
            for name,values in sorted(lookup.items(),key=lambda item:(-len(item[0]),item[0]))]


def recorded_names(roads, patterns, rules):
    evidence=[]
    for road in roads:
        # Keep the primary description: secondary clauses can contain dispatch notes.
        text=road_text(road['value'].split(';')[0].split(', PROVO')[0],rules)
        spans=[]
        for pattern,values in patterns:
            for found in pattern.finditer(text):
                if any(a<=found.start() and b>=found.end() for a,b in spans):continue
                spans.append(found.span())
                address=re.match(r'^\d+ '+DIRECTION+r' (?=.+)',text)
                evidence.append({'source':road['source'],'text':found.group(),'names':sorted(values),
                    'role':'address-grid' if address and found.end()<=address.end() else 'road'})
    return sorted({name for e in evidence if e['role']=='road' for name in e['names']}), evidence


def intersections(segments, geometries, nodes, rules, city):
    by_id={s['id']:i for i,s in enumerate(segments)}
    positions={}
    for segment,line in zip(segments,geometries):
        parts=[line] if line.geom_type=='LineString' else list(line.geoms)
        endpoints=[Point(c) for part in parts for c in (part.coords[0],part.coords[-1])]
        for node,point in zip(segment['properties']['derived']['endpointIds'],endpoints):positions[node]=point
    tree=STRtree(geometries);result=[];seen=set()
    for node,ids in nodes.items():
        point=positions[node]
        if not city.covers(point):continue
        grade=segments[by_id[ids[0]]]['properties']['derived']['grade']
        members=set(ids)
        # An endpoint can meet a line interior (a T); two crossing interiors never create a node.
        for i in tree.query(point.buffer(rules['endpointJoinMeters'])):
            d=segments[i]['properties']['derived']
            if d['grade']==grade and geometries[i].distance(point)<=rules['endpointJoinMeters']:members.add(segments[i]['id'])
        members=sorted(i for i in members if segments[by_id[i]]['properties']['derived']['eligible'])
        physical={segments[by_id[i]]['properties']['derived']['physicalGeometryId'] for i in members}
        primary={road_key(segments[by_id[i]]['properties']['source'].get('FULLNAME') or segments[by_id[i]]['properties']['source'].get('LABEL') or segments[by_id[i]]['properties']['source'].get('NAME') or '',rules) for i in members}-{''}
        arms=0;counted=set()
        for member in members:
            i=by_id[member];key=segments[i]['properties']['derived']['physicalGeometryId']
            if key in counted:continue
            counted.add(key)
            line=geometries[i]
            for part in ([line] if line.geom_type=='LineString' else line.geoms):
                if part.distance(point)<=rules['endpointJoinMeters']:
                    arms+=1 if min(point.distance(Point(part.coords[0])),point.distance(Point(part.coords[-1])))<=rules['endpointJoinMeters'] else 2
        if len(physical)<2 or arms<3:continue
        signature=tuple(members)
        if signature in seen:continue
        seen.add(signature)
        names=sorted({road_key(n,rules) for i in members for n in segments[by_id[i]]['properties']['derived']['names']})
        result.append({'type':'Feature','id':node.replace('city-endpoint:','provo-city-intersection:'),
            'geometry':mapping(transform(TO_WGS84,point)), 'properties':{'segmentIds':members,'names':names,
            'name':' / '.join(sorted(primary)),'grade':grade,'basis':'city-street-endpoint-junction',
            'sourceVersion':segments[by_id[members[0]]]['properties']['derived']['sourceVersion']}})
    crossing_nodes={}
    endpoints=STRtree([transform(TO_METERS,shape(f['geometry'])) for f in result])
    for i,line in enumerate(geometries):
        a=segments[i]['properties']['derived']
        if not a['eligible']:continue
        for j in tree.query(line,predicate='crosses'):
            if j<=i:continue
            b=segments[j]['properties']['derived']
            if not b['eligible'] or (a['grade'] is not None and b['grade'] is not None and a['grade']!=b['grade']):continue
            crossing=line.intersection(geometries[j])
            points=[crossing] if crossing.geom_type=='Point' else list(crossing.geoms) if crossing.geom_type=='MultiPoint' else []
            for point in points:
                if not city.covers(point) or len(endpoints.query(point.buffer(rules['endpointJoinMeters']))):continue
                key=(round(point.x,1),round(point.y,1))
                crossing_nodes.setdefault(key,set()).update([i,int(j)])
    for coordinate,indices in sorted(crossing_nodes.items()):
        members=[segments[i] for i in sorted(indices)]
        names=sorted({road_key(n,rules) for f in members for n in f['properties']['derived']['names']})
        primary=sorted({road_key(f['properties']['source'].get('FULLNAME') or f['properties']['source'].get('NAME') or '',rules) for f in members})
        result.append({'type':'Feature','id':'provo-city-crossing:'+digest(coordinate)[:24],
            'geometry':mapping(transform(TO_WGS84,Point(*coordinate))), 'properties':{
                'segmentIds':[f['id'] for f in members],'names':names,'name':' / '.join(primary),
                'grade':None,'basis':'interior-crossing-needs-crash-junction-evidence','sourceVersion':members[0]['properties']['derived']['sourceVersion']}})
    # Short connecting pieces can represent the two sides of one named intersection.
    merged=[]
    for feature in sorted(result,key=lambda f:f['id']):
        prop=feature['properties'];point=transform(TO_METERS,shape(feature['geometry']))
        group=next((g for g in merged if g[0]['properties']['name']==prop['name']
            and g[0]['properties']['basis']==prop['basis'] and prop['basis']=='city-street-endpoint-junction'
            and 'ACCESS ROAD' not in prop['name'] and ' / ' in prop['name']
            and any(set(f['properties']['segmentIds']).intersection(prop['segmentIds']) for f in g)
            and all(point.distance(transform(TO_METERS,shape(f['geometry'])))<=rules['intersectionMergeMeters'] for f in g)),None)
        if group is None:merged.append([feature])
        else:group.append(feature)
    result=[]
    for group in merged:
        feature=group[0];prop=feature['properties']
        prop['componentIntersectionIds']=[f['id'] for f in group]
        if len(group)>1:
            points=[transform(TO_METERS,shape(f['geometry'])) for f in group]
            feature['id']='provo-city-intersection:'+digest(prop['componentIntersectionIds'])[:24]
            feature['geometry']=mapping(transform(TO_WGS84,Point(sum(p.x for p in points)/len(points),sum(p.y for p in points)/len(points))))
            prop['segmentIds']=sorted({i for f in group for i in f['properties']['segmentIds']})
            prop['names']=sorted({n for f in group for n in f['properties']['names']})
            prop['basis']='connected-city-junction-components'
        result.append(feature)
    result.sort(key=lambda f:f['id'])
    return result,[transform(TO_METERS,shape(f['geometry'])) for f in result]


def attach_official_sites(junctions, points, sites, segments, geometries, patterns, rules, city):
    tree=STRtree(geometries)
    for site in sorted(sites,key=lambda f:f['id']):
        prop=site['properties'];point=transform(TO_METERS,shape(site['geometry']))
        if not city.covers(point) or 'METER' in (prop.get('primary','')+' '+prop.get('secondary','')).upper():continue
        groups=[set(recorded_names([{'source':'UDOT ATSPM','value':prop.get(k,'').split('(')[0]}],patterns,rules)[0]) for k in ('primary','secondary')]
        if not all(groups) or groups[0]==groups[1]:continue
        nearby=[int(i) for i in tree.query(point.buffer(rules['officialSiteLinkMeters']))
            if geometries[i].distance(point)<=rules['officialSiteLinkMeters'] and segments[i]['properties']['derived']['eligible']]
        members=[i for i in nearby if set(road_key(n,rules) for n in segments[i]['properties']['derived']['names']).intersection(set.union(*groups))]
        names={road_key(n,rules) for i in members for n in segments[i]['properties']['derived']['names']}
        if not all(g.intersection(names) for g in groups):continue
        linked=[i for i,f in enumerate(junctions) if points[i].distance(point)<=rules['officialSiteLinkMeters'] and all(g.intersection(f['properties']['names']) for g in groups)]
        # Prefer the provider identity for the same fully named junction, retaining City components.
        geometry=junctions[min(linked,key=lambda i:points[i].distance(point))]['geometry'] if linked else site['geometry']
        feature={'type':'Feature','id':site['id'],'geometry':geometry,'properties':{
            'name':prop['primary']+' / '+prop['secondary'],'names':sorted(names|{n for i in linked for n in junctions[i]['properties']['names']}),
            'segmentIds':sorted({segments[i]['id'] for i in members}|{s for i in linked for s in junctions[i]['properties']['segmentIds']}),
            'componentIntersectionIds':sorted({c for i in linked for c in junctions[i]['properties']['componentIntersectionIds']}),
            'grade':None,'basis':'udot-atspm-roster-and-city-streets','sourceVersion':segments[members[0]]['properties']['derived']['sourceVersion'],
            'providerSiteId':prop['siteId'],'providerCoordinates':site['geometry']['coordinates']}}
        for i in sorted(linked,reverse=True):junctions.pop(i);points.pop(i)
        junctions.append(feature);points.append(transform(TO_METERS,shape(geometry)))
    ordered=sorted(zip(junctions,points),key=lambda pair:pair[0]['id'])
    return [f for f,p in ordered],[p for f,p in ordered]


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


def assign(collection, features, boundary, rules, source_pin, sites=()):
    segments, geometries, nodes, city = inventory(features,boundary,rules,source_pin)
    tree = STRtree(geometries)
    patterns=name_patterns(segments,rules)
    segment_names=[{road_key(n,rules) for n in s['properties']['derived']['names']} for s in segments]
    road_indices=defaultdict(set)
    for i,names in enumerate(segment_names):
        if segments[i]['properties']['derived']['eligible']:
            for name in names:road_indices[name].add(i)
    junctions,junction_points=intersections(segments,geometries,nodes,rules,city)
    junctions,junction_points=attach_official_sites(junctions,junction_points,sites,segments,geometries,patterns,rules,city)
    junction_tree=STRtree(junction_points)
    state_groups=defaultdict(set)
    for group in collection['records']:
        for reference in crash_evidence(group)[2]:state_groups[reference['recordId']].add(group['id'])
    if len({g['id'] for g in collection['records']})!=len(collection['records']):raise ValueError('Duplicate managed group ID')
    rows = []; review_points={}
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
               'assignmentType':None,'matchEvidence':None,'nameEvidence':[],'exceptionCategory':None,'intersectionId':None,'relatedSegmentIds':[], 'intersectionCandidates':[], 'scope':'unknown',
               'ruleVersion':rules['version'],'distanceMeters':None,'junctionReported':None,'reasons':[],'roadEvidence':roads,'candidates':[],
               'junctionEvidence':sorted(junction_evidence,key=lambda e:(e['source'],e['value'])),
               'locationSource':locations[0][0] if locations else None,
               'coordinates':[round(v,4) for v in locations[0][2]] if locations else None}
        rows.append(row)
        if not locations:
            row['reasons']=['no-valid-recorded-location']; continue
        point=locations[0][1];review_points[row['crashId']]=point
        if not city.covers(point):
            row.update(status='out-of-scope',scope='outside-provo',reasons=['outside-road-boundary']); continue
        row['scope']='inside-provo'
        private_roads=[{'source':o['sourceKey'],'value':o['metadata']['location']['normalizedAddress']} for o in group['observations']
            if o['sourceKey']=='provo-police-incidents' and o['metadata'].get('location',{}).get('normalizedAddress')
            and o['metadata']['location'].get('geocoding',{}).get('mapEligible') and not o['metadata'].get('hasSourceConflict')] if locations[0][0]=='provo-police-incidents' else []
        recorded,name_evidence=recorded_names(roads+private_roads,patterns,rules)
        recorded=set(recorded);row['nameEvidence']=[{k:v for k,v in e.items() if k!='text' or e['source']!='provo-police-incidents'} for e in name_evidence]
        junction_reported=classified_junction or any(re.search(r'&|@|\bAND\b|\bAT\b',r['value'].upper().split(';')[0]) for r in roads)
        spaced_junction=any(len(parts:=re.split(r'\s{2,}',r['value'].split(';')[0].strip()))>1 and all(recorded_names([{'source':r['source'],'value':part}],patterns,rules)[0] for part in parts) for r in roads)
        junction_reported |= spaced_junction
        intersection_names=recorded|{n for e in name_evidence for n in e['names']}
        row['junctionReported']=junction_reported
        nearby=tree.query(point.buffer(rules['maximumDistanceMeters']))
        for index in nearby:
            segment=segments[index];derived=segment['properties']['derived'];line=geometries[index]
            distance=point.distance(line)
            if distance > rules['maximumDistanceMeters']:continue
            endpoint_distance=min(point.distance(Point(c)) for part in ([line] if line.geom_type=='LineString' else line.geoms) for c in [part.coords[0],part.coords[-1]])
            row['candidates'].append({'segmentId':segment['id'],'physicalGeometryId':derived['physicalGeometryId'],
                'distanceMeters':round(distance,3),'endpointDistanceMeters':round(endpoint_distance,3),
                'nameAgreement':sorted(recorded.intersection(segment_names[index])),'eligible':derived['eligible'],
                'endpointIds':derived['endpointIds'],'grade':derived['grade']})
        row['candidates'].sort(key=lambda c:(c['distanceMeters'],c['segmentId']))
        conflict=any(loc[1].distance(point)>rules['coordinateDisagreementMeters'] for loc in locations if loc[0]!='provo-police-incidents')
        blockers=(['conflicting-source-locations'] if conflict else [])+(['unresolved-state-identity'] if ambiguous_identity else [])+(['police-location-needs-review'] if locations[0][0]=='provo-police-incidents' and not private_roads else [])
        for index in junction_tree.query(point.buffer(rules['intersectionSearchMeters'])):
            feature=junctions[index];distance=point.distance(junction_points[index])
            if distance>rules['intersectionSearchMeters']:continue
            agreement=sorted(intersection_names.intersection(feature['properties']['names']))
            primary_agreement=sorted(recorded.intersection(feature['properties']['names']))
            row['intersectionCandidates'].append({'intersectionId':feature['id'],'basis':feature['properties']['basis'],'distanceMeters':round(distance,3),
                'nameAgreement':agreement,'primaryNameAgreement':primary_agreement,'segmentIds':feature['properties']['segmentIds']})
        row['intersectionCandidates'].sort(key=lambda c:(-len(c['nameAgreement']),c['distanceMeters'],c['intersectionId']))
        location_only=not recorded and locations[0][0]!='provo-police-incidents' and all(re.fullmatch(r'\d+(?: '+DIRECTION+r')?',road_text(e['value'].split(';')[0],rules)) for e in roads)
        required_names=[set(e['names']) for e in name_evidence if e['role']=='road']
        junction_supported=[c for c in row['intersectionCandidates'] if (c['primaryNameAgreement'] or (location_only and classified_junction and c['distanceMeters']<=rules['spatialIntersectionMeters']))
            and all(names.intersection(c['nameAgreement']) for names in required_names)
            and (len(c['nameAgreement'])>=2 or c['distanceMeters']<=rules['singleRoadIntersectionMeters'])
            and (c['basis']!='interior-crossing-needs-crash-junction-evidence' or (junction_reported and (len(c['primaryNameAgreement'])>=2 or (classified_junction and c['distanceMeters']<=rules['spatialIntersectionMeters']))))]
        # Two named roads or a source junction classification justify an intersection search.
        if junction_reported or (junction_supported and (junction_supported[0]['distanceMeters']<=rules['junctionRadiusMeters'] or (len(junction_supported[0]['nameAgreement'])>=2 and junction_supported[0]['distanceMeters']<=rules['spatialIntersectionMeters']))):
            if junction_supported:
                first=junction_supported[0]
                alternatives=[c for c in junction_supported[1:] if len(c['nameAgreement'])>=len(first['nameAgreement']) and c['distanceMeters']<=first['distanceMeters']+rules['intersectionSeparationMeters']]
                if not alternatives and not blockers:
                    row.update(status='matched',assignmentType='intersection',intersectionId=first['intersectionId'],relatedSegmentIds=first['segmentIds'],distanceMeters=first['distanceMeters'],reasons=['recorded-junction-and-city-streets' if junction_reported else 'near-city-junction-with-road-agreement'])
                    continue
            row.update(status='ambiguous',reasons=blockers+['recorded-junction','unresolved-intersection']);continue
        eligible=[c for c in row['candidates'] if c['eligible']]
        supported=[c for c in eligible if c['nameAgreement']]
        if not supported and location_only:
            supported=[c for c in eligible if c['distanceMeters']<=rules['unlabeledPointSnapMeters']]
        if not supported:
            row.update(status='unmatched',reasons=blockers+['no-corroborated-road-name' if eligible else 'no-eligible-segment-within-tolerance']);continue
        first=supported[0]
        alternatives=[c for c in row['candidates'] if c['physicalGeometryId']!=first['physicalGeometryId'] and
                      (c['distanceMeters']<=first['distanceMeters']+rules['separationMeters'] or
                       (first['endpointDistanceMeters']<=rules['junctionRadiusMeters'] and c['endpointDistanceMeters']<=rules['junctionRadiusMeters']))]
        if alternatives or blockers:
            row.update(status='ambiguous',reasons=blockers+(['junction-or-parallel-candidates'] if alternatives else []))
        else:
            row.update(status='matched',assignmentType='segment',segmentId=first['segmentId'],relatedSegmentIds=[first['segmentId']],physicalGeometryId=first['physicalGeometryId'],
                       distanceMeters=first['distanceMeters'],reasons=['recorded-road-and-location'])
    exceptions=[]
    for row in rows:
        if row['status']=='matched':
            row['matchEvidence']='road-and-location' if any(e['role']=='road' for e in row.get('nameEvidence',[])) else 'recorded-location-only'
            continue
        if row['status']=='out-of-scope':continue
        recorded={n for e in row.get('nameEvidence',[]) if e['role']=='road' for n in e['names']}
        point=review_points.get(row['crashId'])
        named=[]
        if point and recorded:
            for i in set().union(*(road_indices[n] for n in recorded)):
                named.append((round(point.distance(geometries[i]),1),segments[i]['id']))
        nearest=min(named) if named else None
        if row['status']=='missing-location':category='missing-location'
        elif 'unresolved-state-identity' in row['reasons']:category='unresolved-source-identity'
        elif row['locationSource']=='provo-police-incidents':category='private-police-location-review'
        elif any(re.search(r'PRIVATE PROPERTY|\bLOT\s+\d|PARKING LOT',e['value'],re.I) for e in row['roadEvidence']):category='off-road-or-parking-location'
        elif nearest and nearest[0]>rules['intersectionSearchMeters']:category='road-name-location-disagreement'
        elif not recorded:category='unrecognized-road-description'
        elif row['junctionReported']:category='intersection-evidence-unresolved'
        elif nearest and nearest[0]>rules['maximumDistanceMeters']:category='position-offset-from-named-road'
        else:category='competing-road-geometries'
        row['exceptionCategory']=category
        exceptions.append({'crashId':row['crashId'],'status':row['status'],'category':category,'reasons':row['reasons'],
            'nearestNamedSegment':{'segmentId':nearest[1],'distanceMeters':nearest[0]} if nearest else None})
    physical={}
    for segment in segments:
        d=segment['properties']['derived']
        if d['eligible']:
            physical.setdefault(d['physicalGeometryId'],d['withinBoundaryLengthMeters'])
    distances=sorted(r['distanceMeters'] for r in rows if r['status']=='matched')
    report={'crashes':len(rows),'statuses':dict(sorted(Counter(r['status'] for r in rows).items())),
            'inProvoStatuses':dict(sorted(Counter(r['status'] for r in rows if r['scope']=='inside-provo').items())),
            'assignmentTypes':dict(Counter(r['assignmentType'] for r in rows if r['status']=='matched')),
            'exceptionCategories':dict(sorted(Counter(e['category'] for e in exceptions).items())),
            'locatedInProvo':sum(r['scope']=='inside-provo' for r in rows),'outsideProvo':sum(r['scope']=='outside-provo' for r in rows),
            'intersectionCount':len(junctions),'sourceSegments':len(segments),'eligibleSegments':sum(s['properties']['derived']['eligible'] for s in segments),
            'physicalGeometryCount':len(physical),'physicalLengthMeters':round(sum(physical.values()),3),
            'matchedDistanceMeters':{str(p):distances[min(len(distances)-1,int((len(distances)-1)*p/100))] if distances else None for p in [0,50,90,95,100]},
            'potentialEndpointClusters':len(nodes),'confirmedConnectivity':False}
    return {'segments.geojson':{'type':'FeatureCollection','features':segments},'assignments.json':rows,
            'endpoints.json':nodes,'intersections.geojson':{'type':'FeatureCollection','features':junctions},'coverage.json':report,
            'exceptions.json':exceptions}


def crash_records(result):
    """Materialize the shared road join once, with no raw private crash fields."""
    segments = {f['id']: f['properties'] for f in result['segments.geojson']['features']}
    intersections_by_id = {f['id']: f for f in result['intersections.geojson']['features']}
    records = []
    for row in result['assignments.json']:
        location = {key: row[key] for key in (
            'status', 'scope', 'identityStatus', 'assignmentType', 'intersectionId',
            'segmentId', 'physicalGeometryId', 'relatedSegmentIds', 'matchEvidence',
            'exceptionCategory', 'reasons', 'ruleVersion', 'distanceMeters', 'locationSource')}
        location.update(intersection=None, segment=None)
        if row['intersectionId']:
            feature = intersections_by_id[row['intersectionId']]
            location['intersection'] = {**feature['properties'], 'coordinates': feature['geometry']['coordinates']}
        if row['segmentId']:
            props = segments[row['segmentId']]
            location['segment'] = {**props['derived'], 'label': props['source'].get('LABEL') or props['source'].get('FULLNAME'),
                                   'attributes': props['source']}
        records.append({'crashId': row['crashId'], 'sourceRecords': row['sourceRecords'], 'roadLocation': location})
    return records


def enrich_collection(collection, records, package_pin):
    """Return a private derived view; never rewrite the reconciled source release."""
    from copy import deepcopy
    by_id = {r['crashId']: r['roadLocation'] for r in records}
    ids = ['crash:'+hashlib.sha256(g['id'].encode()).hexdigest()[:24] for g in collection['records']]
    if len(by_id) != len(records) or len(set(ids)) != len(ids) or set(ids) != set(by_id):
        raise ValueError('Road enrichment and collection membership differ')
    enriched = deepcopy(collection)
    enriched['roadLocationPackage'] = package_pin
    for group, identifier in zip(enriched['records'], ids):
        group.setdefault('enrichment', {})['roadLocation'] = deepcopy(by_id[identifier])
    return enriched


def changes(previous, current):
    old={r['crashId']:r for r in previous.get('assignments.json',[])}
    new={r['crashId']:r for r in current['assignments.json']}
    a={s['id']:s for s in previous.get('segments.geojson',{}).get('features',[])}
    b={s['id']:s for s in current['segments.geojson']['features']}
    old_intersections={f['id']:f for f in previous.get('intersections.geojson',{}).get('features',[])}
    new_intersections={f['id']:f for f in current.get('intersections.geojson',{}).get('features',[])}
    # Explicit reassignment replaces guesses of stable IDs across provider edits.
    return {'addedIntersectionIds':sorted(new_intersections.keys()-old_intersections.keys()),
            'removedIntersectionIds':sorted(old_intersections.keys()-new_intersections.keys()),
            'changedIntersectionIds':sorted(k for k in old_intersections.keys()&new_intersections.keys() if old_intersections[k]!=new_intersections[k]),
            'addedCrashes':sorted(new.keys()-old.keys()),'removedCrashes':sorted(old.keys()-new.keys()),
            'changedAssignments':[{'crashId':k,'before':{f:old[k].get(f) for f in ('status','assignmentType','segmentId','intersectionId','physicalGeometryId')},
                                   'after':{f:new[k].get(f) for f in ('status','assignmentType','segmentId','intersectionId','physicalGeometryId')}}
                                  for k in sorted(new.keys()&old.keys()) if any(old[k].get(f)!=new[k].get(f) for f in ('status','assignmentType','segmentId','intersectionId','physicalGeometryId'))],
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
