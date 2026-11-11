"""Read-only structured queries returning complete merged incident entries as a JSON array."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
from .incidents import observation_day

from pyproj import Geod
from .config import DEFAULT_PRIVATE_DATA_ROOT

FIELDS = {
    'incident': {'year':'integer; state occurrence year, America/Denver', 'date':'YYYY-MM-DD; state occurrence date',
                 'report_year':'integer; police report year only', 'city':'state geographic city label; missing for many UDOT records',
                 'street':'source road text or police address', 'mode':'bicycle, electric-bicycle, pedestrian, other-conveyance',
                 'fatal':'boolean; any fatality in the crash, not necessarily the AT person', 'source':'source key', 'lighting':'reviewed lighting group', 'weekday':'source occurrence weekday', 'hour':'occurrence hour 0–23', 'weather':'recorded weather label', 'road_surface':'recorded surface label', 'driver_circumstance':'reported driver circumstance', 'reported_factor':'reported crash factor'},
    'vehicle': {'body_code':'source vehicle-body code string; passenger-car codes 1, 2, 3',
                'maneuver':'straight-ahead, backing, changing-lanes, right-turn, left-turn, u-turn, or source code',
                'vehicle_number':'source vehicle number string'},
    'person': {'mode':'bicycle, pedestrian, other-conveyance, driver, passenger',
               'setting':'crosswalk, on-street-bike-lane, separated-bike-lane, sidewalk, or source code',
               'injury':'fatal, serious, minor, possible, none, or source code', 'age_group':'under18, 18to64, 65plus'}}
for event_field in ('byu_football_event_context', 'byu_mens_basketball_event_context', 'stadium_of_fire_event_context'):
    FIELDS['incident'][event_field] = 'stored likely_match, no_match, or indeterminate; absent before event enrichment'

MANEUVERS={'1':'straight-ahead','2':'backing','3':'changing-lanes','5':'right-turn','6':'left-turn','7':'u-turn'}
SETTINGS={**{str(i):'crosswalk' for i in range(1,6)},'10':'sidewalk','12':'on-street-bike-lane','17':'separated-bike-lane'}
MODES={'1':'driver','2':'passenger','3':'pedestrian','4':'bicycle','5':'other-conveyance'}
INJURIES={'1':'none','2':'possible','3':'minor','4':'serious','5':'fatal'}
GEOD=Geod(ellps='WGS84')


def conjunction(values):
    return False if False in values else None if None in values else True


def disjunction(values):
    return True if True in values else None if None in values else False


def normalized(value):
    return ' '.join(re.findall(r'\w+',value.casefold())) if isinstance(value,str) else value


def validate(query, scope='incident'):
    if not isinstance(query,dict): raise ValueError('Each query node must be an object')
    if 'field' in query:
        if set(query) != {'field','op','value'} or query['field'] not in FIELDS[scope]:
            raise ValueError('Unknown field or predicate keys for '+scope)
        op,value=query['op'],query['value']
        if op not in {'eq','ne','in','between','gte','lte','contains','exists'}: raise ValueError('Unknown operator')
        if op=='in' and (not isinstance(value,list) or not value): raise ValueError('in requires nonempty list')
        if op=='between' and (not isinstance(value,list) or len(value)!=2): raise ValueError('between requires two inclusive bounds')
        if op=='exists':
            if type(value) is not bool: raise ValueError('exists requires boolean')
            return
        values=value if op in {'in','between'} else [value]
        field=query['field']
        for v in values:
            if field in {'year','report_year','hour'}:
                if type(v) is not int: raise ValueError('Year/hour requires integer')
                if field=='hour' and not 0<=v<=23: raise ValueError('Hour must be 0–23')
            elif field=='fatal':
                if type(v) is not bool: raise ValueError('fatal requires boolean')
            elif not isinstance(v,str) or not v.strip(): raise ValueError('Field requires nonempty string')
            if field=='date': datetime.strptime(v,'%Y-%m-%d')
        if op=='contains' and not isinstance(value,str): raise ValueError('contains requires text')
        if op=='between' and values[0]>values[1]: raise ValueError('Reversed bounds')
        return
    if len(query)!=1: raise ValueError('Use exactly one of all, any, not, vehicle, person, near, within')
    kind,value=next(iter(query.items()))
    if kind in {'all','any'}:
        if not isinstance(value,list) or kind=='any' and not value: raise ValueError('Boolean group requires list; any must be nonempty')
        for child in value: validate(child,scope)
    elif kind=='not': validate(value,scope)
    elif kind in {'vehicle','person'} and scope=='incident': validate(value,kind)
    elif kind=='near' and scope=='incident':
        if not isinstance(value,dict) or set(value)!={'longitude','latitude','metres'}: raise ValueError('near requires longitude, latitude, metres')
        for v in value.values():
            if type(v) not in {int,float} or not math.isfinite(v): raise ValueError('Require finite numeric geography')
        if not -180<=value['longitude']<=180 or not -90<=value['latitude']<=90 or value['metres']<=0:
            raise ValueError('Invalid longitude, latitude or radius')
    elif kind=='within' and scope=='incident':
        if not isinstance(value,str) or not value: raise ValueError('within requires GeoJSON path')
    else: raise ValueError('Unknown query node or invalid nesting: '+kind)


def views(group):
    for o in group['observations']:
        yield o
        if o.get('statePortal'): yield o['statePortal']


def facts(o, enrichment=None):
    meta=o.get('metadata',{}); source=o['sourceKey']; portal=source=='utah-crash-portal'
    raw=meta.get('crash',{}) if portal else meta
    people=meta.get('persons') if portal else None
    vehicles=meta.get('vehicles') if portal else None
    modes=set(o.get('modes',[]))
    if o.get('mode'): modes.add(o['mode'])
    if 'electric-bicycle' in modes: modes.add('bicycle')
    if 'other-micromobility' in modes: modes.add('other-conveyance')
    for p in people or []:
        mode=MODES.get(str(p.get('personType')))
        if mode in {'bicycle','pedestrian','other-conveyance'}: modes.add(mode)
    date=None
    if o.get('observedAt'):
        date=observation_day(o).isoformat()
    police=source=='provo-police-incidents'
    severity=str(raw.get('crashSeverity_label',raw.get('CRASH_SEVERITY_DESC',''))).casefold()
    fatal=None
    if not police:
        if raw.get('crashSeverity') is not None and str(raw['crashSeverity']) in {'1','2','3','4','5'}:
            fatal=str(raw['crashSeverity'])=='5'
        elif severity in {'fatal','fatalities','fatal injury'}: fatal=True
        elif severity in {'no injury','possible injury','suspected minor injury','suspected serious injury'}: fatal=False
        if any(str(p.get('injuryLevel'))=='5' for p in people or []): fatal=True
        if raw.get('NUMBER_FATALITIES') is not None and int(raw['NUMBER_FATALITIES'])>0: fatal=True
    point=o.get('coordinates')
    if police:
        g=meta.get('location',{}).get('geocoding',{})
        selected=(g.get('providerCandidates') or [{}])[0]
        if g.get('status')!='matched' or selected.get('properties',{}).get('kind') in {'street','virtual_street'}:
            point=None
    if point is not None and (len(point)!=2 or any(type(v) not in {int,float} or not math.isfinite(v) for v in point) or not -180<=point[0]<=180 or not -90<=point[1]<=90):
        raise ValueError('Invalid source coordinates')
    extra={};partial=set()
    if enrichment:
        f=enrichment['fields']
        for name,key in [('lighting','lighting'),('driver_circumstance','driverCircumstances'),('reported_factor','reportedFactors')]:
            extra[name]=f[key]['value'] if f[key]['availability']=='complete' or f[key]['value'] else None
            if f[key]['availability']!='complete':partial.add(name)
        t=f['time']['value']
        extra.update(weekday=t['weekday'] if t and t['basis']=='occurrence' else None,hour=t['hour'] if t and t['basis']=='occurrence' else None)
        for name in ['weather','road_surface']:
            c=f['conditions']['value'][name]
            extra[name]=c['value'].get('label') if c['availability']=='complete' and c['value'] else None
    from .derived_incidents import age_group
    from .incident_conversions import convert
    return {**extra,'_partialFields':partial,'source':source,'date':date if not police else None,'year':int(date[:4]) if date and not police else None,
            'report_year':int(date[:4]) if date and police else None,
            'city':raw.get('City_Geo') or raw.get('city_geo'),
            'street':raw.get('roadName') or raw.get('MAIN_ROAD_NAME') or meta.get('location',{}).get('addressPartRaw'),
            'mode':sorted(modes) if modes else None,'fatal':fatal,'_point':point,
            '_vehicles':None if vehicles is None else [{'body_code':str(v['vehicleBodyType']) if v.get('vehicleBodyType') is not None else None,
                         'maneuver':MANEUVERS.get(str(v.get('vehicleManeuver')),str(v['vehicleManeuver']) if v.get('vehicleManeuver') is not None else None),
                         'vehicle_number':str(v['vehicleNumber']) if v.get('vehicleNumber') is not None else None} for v in vehicles],
            '_people':None if people is None else [{'mode':MODES.get(str(p.get('personType'))),
                         'setting':SETTINGS.get(str(p.get('personNmLocation')),str(p['personNmLocation']) if p.get('personNmLocation') is not None and str(p['personNmLocation']) not in {'89','96','99'} else None),
                         'injury':INJURIES.get(str(p.get('injuryLevel'))), 'age_group':age_group(convert(p.get('ageCalculated'),'age')['value'])} for p in people]}


def evaluate(query, row, polygons):
    if 'field' in query:
        actual=row.get(query['field']);op=query['op'];wanted=query['value']
        if op=='exists': return (actual is not None)==wanted
        if actual is None: return None
        values=actual if isinstance(actual,list) else [actual]
        def compare(value):
            a=normalized(value);b=normalized(wanted)
            if op=='eq': return a==b
            if op=='ne': return a!=b
            if op=='in': return a in [normalized(v) for v in wanted]
            if op=='contains': return (' '+b+' ') in (' '+a+' ')
            if op=='between': return wanted[0]<=value<=wanted[1]
            if op=='gte': return value>=wanted
            if op=='lte': return value<=wanted
            raise ValueError('Unsupported operator')
        answer=all(compare(v) for v in values) if op=='ne' else any(compare(v) for v in values)
        if query['field'] in row.get('_partialFields',set()) and (answer if op=='ne' else not answer):return None
        return answer
    kind,value=next(iter(query.items()))
    if kind=='all': return conjunction([evaluate(q,row,polygons) for q in value])
    if kind=='any': return disjunction([evaluate(q,row,polygons) for q in value])
    if kind=='not':
        result=evaluate(value,row,polygons)
        return None if result is None else not result
    if kind in {'vehicle','person'}:
        related=row['_vehicles' if kind=='vehicle' else '_people']
        return None if related is None else disjunction([evaluate(value,r,polygons) for r in related])
    point=row['_point']
    if point is None: return None
    if kind=='near': return GEOD.inv(value['longitude'],value['latitude'],*point)[2]<=value['metres']
    from shapely.geometry import Point
    return polygons[value].covers(Point(*point))


def load_polygons(query):
    from shapely.geometry import shape
    from shapely.ops import unary_union
    result={}
    def visit(node):
        if 'within' in node:
            path=node['within'];data=json.loads(Path(path).read_text())
            if data.get('crs') and data['crs'].get('properties',{}).get('name') not in {'EPSG:4326','urn:ogc:def:crs:OGC:1.3:CRS84'}:
                raise ValueError('Boundary CRS must be WGS84 longitude/latitude')
            geometries=[f['geometry'] for f in data['features']] if data.get('type')=='FeatureCollection' else [data['geometry']] if data.get('type')=='Feature' else [data]
            shapes=[shape(g) for g in geometries]
            if not shapes or any(g.geom_type not in {'Polygon','MultiPolygon'} or g.is_empty or not g.is_valid or not (-180<=g.bounds[0]<=g.bounds[2]<=180 and -90<=g.bounds[1]<=g.bounds[3]<=90) for g in shapes):
                raise ValueError('within requires valid WGS84 polygons')
            result[path]=unary_union(shapes)
        for k,v in node.items():
            if k in {'all','any'}:
                for child in v:visit(child)
            elif k in {'not','vehicle','person'}:visit(v)
    visit(query)
    return result


def select(entries,query):
    validate(query);polygons=load_polygons(query);matched=[];counts=Counter({'matched':0,'notMatched':0,'unknown':0});evidence={}
    for group in entries:
        enrichments={o['observationId']:o for o in group.get('enrichment',{}).get('observations',[])}
        results=[]
        for o in views(group):
            row=facts(o,enrichments.get(o['id']))
            if 'coordinates' in group.get('resolvedCrash',{}):
                row['_point']=group['resolvedCrash']['coordinates']
            for key, value in group.get('eventContext', {}).get('fields', {}).items():
                row[key] = value['value']
            results.append((o['id'],evaluate(query,row,polygons)))
        status=disjunction([value for _,value in results]);counts['matched' if status is True else 'unknown' if status is None else 'notMatched']+=1
        if status is True:
            matched.append(group);evidence[group['id']]=[identifier for identifier,value in results if value is True]
    return matched,dict(counts),evidence


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=DEFAULT_PRIVATE_DATA_ROOT/'datastores/combined-incidents.json',help='Collection JSON, filtered JSON array, or checksummed collection pointer')
    parser.add_argument('--query',type=Path,help='Structured JSON query file; paths are relative to working directory')
    parser.add_argument('--output',type=Path,help='New JSON array file; default stdout')
    parser.add_argument('--report',type=Path,help='New provenance/evidence/unknown-count JSON file')
    parser.add_argument('--fields',action='store_true',help='Print supported fields and operators')
    args=parser.parse_args()
    if args.fields:
        print(json.dumps({'fields':FIELDS,'operators':['eq','ne','in','between','gte','lte','contains','exists']},indent=2));return
    try:
        if not args.query: parser.error('--query is required unless --fields')
        for path in [args.output,args.report]:
            if path and path.exists(): raise ValueError('Refusing to overwrite '+str(path))
            if path and path.resolve().is_relative_to((Path(__file__).resolve().parents[4]/'apps/maps').resolve()):
                raise ValueError('Query exports must remain outside the public maps app')
        if args.output and args.report and args.output.resolve()==args.report.resolve(): raise ValueError('Output and report paths must differ')
        started=time.perf_counter();source=args.input;payload=source.read_bytes();data=json.loads(payload)
        if isinstance(data,dict) and 'records' not in data and 'path' in data:
            source=Path(data['path']);payload=source.read_bytes()
            if hashlib.sha256(payload).hexdigest()!=data['sha256']: raise ValueError('Collection checksum mismatch')
            data=json.loads(payload)
        entries=data if isinstance(data,list) else data['records']
        if len({g['id'] for g in entries})!=len(entries): raise ValueError('Duplicate incident IDs')
        query=json.loads(args.query.read_text());matched,counts,evidence=select(entries,query)
        result=json.dumps(matched,indent=2,ensure_ascii=False)+'\n'
        report={'input':str(source.resolve()),'inputSha256':hashlib.sha256(payload).hexdigest(),
                'query':query,'querySha256':hashlib.sha256(args.query.read_bytes()).hexdigest(),
                'inputEntries':len(entries),'counts':counts,'matchingObservationIds':evidence,
                'elapsedSeconds':round(time.perf_counter()-started,4),
                'semantics':'A single observation must satisfy the query; spatial filters use the resolved crash location when present. Results preserve the complete entry.'}
        if args.output:
            with args.output.open('x') as f:f.write(result)
        else:sys.stdout.write(result)
        if args.report:
            with args.report.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
        print(json.dumps({'inputEntries':len(entries),**counts,'elapsedSeconds':report['elapsedSeconds']}),file=sys.stderr)
    except (ValueError,KeyError,TypeError,OSError) as exc: parser.error(str(exc))


if __name__=='__main__':main()
