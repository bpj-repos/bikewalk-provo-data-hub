"""Receive UDOT records privately and prepare the Provo Safe Routes package."""
import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from release import encoded

DATASET='safe-routes-to-school'
BASE='https://services.arcgis.com/pA2nEVnB6tquxgOW/arcgis/rest/services/'
SCHOOL_EVIDENCE='https://timpanogos.provo.edu/january-12-2026-community-council-agenda-minutes/'
WHERE="APPROVED = 'Yes' AND (NAME_DISTRICT = 'Provo' OR (NAME_DISTRICT = 'CHARTER' AND ID_SCHOOL = 773 AND NAME_SCHOOL = 'Treeside Charter School'))"
LAYERS={
    'safe-routes-schools':('Schools',3,'OBJECTID','schools'),
    'safe-school-routes':('Routes',2,'OBJECTID_12_13_14','routes'),
    'safe-route-plan-features':('Features',1,'OBJECTID_1','features')}
ARCHIVE_DATE='2026-07-21T02:01:23.184589Z'
ARCHIVE_ID='udot-safe-routes-to-school-785cfb00279ee95b'
NAMES={226:'Franklin Elementary',257:'Timpanogos'}
HOST='https://bikewalk-provo-data-hub.vercel.app'
NOTICE='UDOT supplies these data for informational use and requires field verification before project use. Source accuracy, completeness and usefulness are not warranted. These layers contain no legal school-zone speed limits or operating schedules.'
FIELDS={'schoolId':'Nullable provider school identifier. Missing IDs are preserved.','schoolName':'Provider school label.','approved':'Approval at the source snapshot date.','approvalDate':'Provider plan approval timestamp.','featureType':'Provider category for a mapped plan point.','sourceStatus':'current-udot, archived-udot-approved, or archived-udot-school-confirmed.','sourceRetrievedAt':'UTC retrieval time of the geometry source.','evidence':'Geometry source URL; the manifest identifies the checksummed receipt.','schoolApprovalEvidenceUrl':'Optional independent evidence of school plan approval.','schoolApprovalEvidenceAt':'Date of independent school approval.','id':'GeoJSON feature ID, UDOT layer plus GlobalID or its layer object ID.'}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def endpoint(key):
    view,layer,_,_=LAYERS[key]
    return BASE+f'SR2S_{view}_Public_View/FeatureServer/{layer}'


def query(url, params):
    with urlopen(url+'?'+urlencode(params),timeout=60) as response:
        result=json.load(response)
    if 'error' in result:
        raise ValueError(result['error'])
    return result


def fetch(key, request=query):
    url=endpoint(key)+'/query'
    oid=LAYERS[key][2]
    def ids():
        values=request(url,dict(where=WHERE,returnIdsOnly='true',f='json'))['objectIds']
        if not values or len(set(values))!=len(values):
            raise ValueError('Missing or duplicate provider IDs')
        return sorted(values)
    expected=ids()
    rows=[]
    fields=[oid,'GlobalID','ID_SCHOOL','NAME_SCHOOL','NAME_DISTRICT','APPROVED','APPROVAL_DATE']
    if key=='safe-route-plan-features':
        fields.append('FEATURE_TYPE')
    for start in range(0,len(expected),100):
        batch=expected[start:start+100]
        page=request(url,dict(where=WHERE,objectIds=','.join(map(str,batch)),outFields=','.join(fields),outSR='4326',returnGeometry='true',f='geojson'))
        found=[f['properties'][oid] for f in page['features']]
        if page.get('exceededTransferLimit') or sorted(found)!=batch:
            raise ValueError('Incomplete or duplicate page for '+key)
        rows.extend(page['features'])
    if ids()!=expected:
        raise ValueError('Provider membership changed during acquisition')
    return sorted(rows,key=lambda f:f['properties'][oid])


def receive(output,archive):
    output.mkdir(parents=True,exist_ok=False)
    now=datetime.now(timezone.utc).isoformat()
    sources={}
    def save(filename,raw,url,date):
        (output/filename).write_bytes(raw)
        sources[filename]=dict(url=url,retrievedAt=date,sha256=sha(raw))
    for key,(_,_,_,folder) in LAYERS.items():
        save(key+'.json',encoded(fetch(key)),endpoint(key),now)
        directory=archive/folder/'pages'
        pages=sorted(directory.glob('*.geojson'))
        if archive.name!=ARCHIVE_ID or not pages:
            raise ValueError('Missing required July archive: '+folder)
        rows=[]
        for p in pages:
            rows.extend(json.loads(p.read_bytes())['features'])
        selected=[f for f in rows if f['properties'].get('ID_SCHOOL') in NAMES]
        save('archive-'+key+'.json',encoded(selected),endpoint(key),ARCHIVE_DATE)
    # Retain the reviewed school decision as evidence; it is independent of monthly geometry.
    evidence=encoded(dict(schoolId=257,date='2026-01-12',decision='School community council approved the Safe Routes Plan.',url=SCHOOL_EVIDENCE))
    save('school-approval.json',evidence,SCHOOL_EVIDENCE,'2026-11-07')
    (output/'receipt.json').write_bytes(encoded(sources))


def validate_geometry(g,key):
    if not g:
        return False
    t=g.get('type')
    if t not in (('LineString','MultiLineString') if key=='safe-school-routes' else ('Point',)):
        raise ValueError('Unexpected geometry '+str(t))
    coords=g['coordinates']
    lines=[coords] if t=='LineString' else coords if t=='MultiLineString' else []
    if t!='Point' and (not lines or any(len(line)<2 for line in lines)):
        raise ValueError('Malformed line')
    points=[coords] if t=='Point' else [p for line in lines for p in line]
    for p in points:
        if len(p) not in (2,3) or not all(type(v) in (int,float) and math.isfinite(v) for v in p) or not (-112<=p[0]<=-111 and 40<=p[1]<=41):
            raise ValueError('Invalid Provo coordinate')
    return True


def features(key, current, archives, sources):
    oid=LAYERS[key][2]
    present={f['properties'].get('ID_SCHOOL') for f in current}
    result={}
    rejected=[]
    for archived,records in ((False,current),(True,archives)):
        for f in records:
            p=f['properties']
            school=p.get('ID_SCHOOL')
            if archived and (school not in NAMES or school in present):
                continue
            provo = p['NAME_DISTRICT']=='Provo' or (p['NAME_DISTRICT']=='CHARTER' and school==773 and p['NAME_SCHOOL']=='Treeside Charter School')
            if p['APPROVED']!='Yes' or not provo or not p['NAME_SCHOOL']:
                raise ValueError('Unexpected scope or missing school name')
            source_id=p.get('GlobalID') or p.get(oid)
            if source_id is None:
                raise ValueError('Missing provider identity')
            fid=f'udot:{key}:{str(source_id).lower()}'
            if not validate_geometry(f.get('geometry'),key):
                rejected.append(fid)
                continue
            if key=='safe-routes-schools' and school is None:
                raise ValueError('Missing school ID for school point')
            when=datetime.fromtimestamp(p['APPROVAL_DATE']/1000,timezone.utc).isoformat()
            source=sources[('archive-' if archived else '')+key+'.json']
            status='current-udot' if not archived else ('archived-udot-school-confirmed' if school==257 else 'archived-udot-approved')
            props=dict(schoolId=school,schoolName=p['NAME_SCHOOL'],approved=True,approvalDate=when,sourceStatus=status,sourceRetrievedAt=source['retrievedAt'],evidence=source['url'])
            if key=='safe-route-plan-features':
                if not p.get('FEATURE_TYPE'):
                    raise ValueError('Missing feature type')
                props['featureType']=p['FEATURE_TYPE']
            if archived and school==257:
                props.update(schoolApprovalEvidenceUrl=SCHOOL_EVIDENCE,schoolApprovalEvidenceAt='2026-01-12')
            if fid in result:
                raise ValueError('Conflicting source identity '+fid)
            result[fid]=dict(type='Feature',id=fid,properties=props,geometry=f['geometry'])
    return [result[k] for k in sorted(result)],sorted(rejected)


PLANNED_CAMPUS = dict(campusStatus='planned', campusAddress='235 E 1600 S',
                      currentCampusAddress='34 E 1700 S',
                      campusEvidence='https://ucsfa.utah.gov/wp-content/uploads/08-11-2026-UCSFA-Meeting-Materials.pdf#page=13')
CAMPUS_FIELDS = {
    'campusStatus':'planned identifies geometry intended for a future campus.',
    'campusAddress':'Address served by the planned routes.',
    'currentCampusAddress':'Operating school address at the time of review. These routes do not give directions there.',
    'campusEvidence':'Source that connects the plan address to the future campus.'
}


def reviewed_treeside(key, records, version):
    if version=='1.0.0' or key=='safe-route-plan-features':
        return []
    # Only the geometry and attributes reviewed for this campus may inherit its designation.
    baseline=json.loads(Path(__file__).with_name('treeside-baseline.json').read_bytes())['features']
    expected={k:v for k,v in baseline.items() if k.startswith(key+':')}
    actual={key+':'+f['properties']['GlobalID']:sha(json.dumps(f,sort_keys=True,separators=(',',':')).encode()) for f in records}
    if actual!=expected or len(actual)!=len(records):
        raise ValueError('Treeside provider records changed; review campus attribution before release')
    return records


def prepare(receipt,output,version):
    sources=json.loads((receipt/'receipt.json').read_bytes())
    def read(name):
        raw=(receipt/name).read_bytes()
        if sha(raw)!=sources[name]['sha256']:
            raise ValueError('Source receipt mismatch: '+name)
        return raw
    read('school-approval.json')
    files={}
    audit={}
    approval_dates=[]
    for key in LAYERS:
        current=json.loads(read(key+'.json'))
        # The Treeside plan's mapped address differs from the verified current campus.
        held=[r for r in current if r['properties']['NAME_DISTRICT']=='CHARTER' and r['properties'].get('ID_SCHOOL')==773]
        included=reviewed_treeside(key,held,version)
        current=[r for r in current if r not in held or r in included]
        held=[r for r in held if r not in included]
        rows,rejected=features(key,current,json.loads(read('archive-'+key+'.json')),sources)
        for row in rows:
            if row['properties']['schoolId']==773 and included:
                row['properties'].update(PLANNED_CAMPUS)
        files[key+'.geojson']=encoded(dict(type='FeatureCollection',features=rows))
        approval_dates.extend(r['properties']['approvalDate'] for r in rows)
        audit[key]=dict(features=len(rows),campusReview=[r['properties']['GlobalID'] for r in held],rejected=rejected,missingSchoolId=sum(r['properties']['schoolId'] is None for r in rows),supplements=sum(r['properties']['sourceStatus']!='current-udot' for r in rows))
    files['coverage.md']=Path(__file__).with_name('coverage.md' if version=='1.0.0' else 'coverage-planned.md').read_bytes()
    files['dictionary.json']=encoded(FIELDS if version=='1.0.0' else {**FIELDS,**CAMPUS_FIELDS})
    files['sources.json']=encoded(dict(receipts=sources,filter=WHERE,archivedSnapshot=ARCHIVE_ID,review=audit))
    files['protocol.md']=('Provo approved school travel plans. '+NOTICE+'\nCurrent records take precedence within each school and layer. Reviewed archived Franklin and Timpanogos features can fill missing school layers. Timpanogos council minutes document school approval; coordinates are from the UDOT archive. Sort order is by layer-qualified provider ID.\n').encode()
    if version!='1.0.0':
        files['changes.md']=b"Adds seven Treeside routes and their school point for the planned campus at 235 E 1600 S. The operating campus is at 34 E 1700 S. The fourteen plan features remain under review. All other geographic records are unchanged from 1.0.0.\n"
    manifest=dict(name=DATASET,version=version,title='Provo Safe Routes to School',attribution='Utah Department of Transportation; Provo school plan evidence compiled by BikeWalk Provo.',reuse='BikeWalk has confirmed source-specific approval to redistribute these layers. Retain UDOT attribution and use notice.',notice=NOTICE,sourceRetrievedAt=sources['safe-routes-schools.json']['retrievedAt'],providerApprovalDate=max(approval_dates),citation=f'BikeWalk Provo. Provo Safe Routes to School, {version}. {HOST}/datasets/{DATASET}/{version}/datapackage.json',resources=[dict(name=Path(k).stem,path=k,bytes=len(b),hash='sha256:'+sha(b)) for k,b in sorted(files.items())])
    files['datapackage.json']=encoded(manifest)
    output.mkdir(parents=True,exist_ok=False)
    for k,b in files.items():
        (output/k).write_bytes(b)
    print(json.dumps(audit))
    print('Manifest SHA-256:',sha(files['datapackage.json']))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    commands=p.add_subparsers(dest='command',required=True)
    a=commands.add_parser('receive')
    a.add_argument('output',type=Path)
    a.add_argument('archive',type=Path)
    a=commands.add_parser('prepare')
    a.add_argument('receipt',type=Path)
    a.add_argument('output',type=Path)
    a.add_argument('--version',default='1.0.0')
    args=p.parse_args()
    if args.command=='receive':
        receive(args.output,args.archive)
    else:
        prepare(args.receipt,args.output,args.version)

