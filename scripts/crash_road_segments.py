"""Rebuild the complete managed crash/City road association and prepare an immutable package."""
import argparse
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import tempfile
from datetime import datetime, timezone

from danger_zones.config import HUB_ROOT, DEFAULT_PRIVATE_DATA_ROOT
from danger_zones.road_segments import assign, changes, encoded, digest
from scripts.build_catalog import checked_package, download_zip
from scripts.capture_traffic_stress import capture_layer

DATASET='provo-crash-road-segments'
RULES=HUB_ROOT/'data-definitions/crashes/road-segments-v1.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def atomic(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
        f.write(encoded(value)); temporary=f.name
    os.replace(temporary,path)


def archive_bytes(files, version):
    prefix=f'datasets/{DATASET}/{version}/'
    return download_zip({prefix+k:v for k,v in files.items()}, {'manifest':'/'+prefix+'datapackage.json'})


def verify_archive(directory, files, version):
    path=Path(directory)/f'{DATASET}-{version}.zip'
    expected=archive_bytes(files, version)
    if path.read_bytes()!=expected:raise ValueError('Candidate ZIP differs from manifest resources')
    return {'zip':str(path),'zipSha256':hashlib.sha256(expected).hexdigest()}


def latest_boundary():
    ledger=read(HUB_ROOT/'releases/release-ledger.json')
    withdrawn={(r['dataset'],r['version']) for r in ledger['withdrawn']}
    entry=next(e for e in reversed(ledger['approved']) if e['dataset']=='provo-bicycle-traffic-stress' and (e['dataset'],e['version']) not in withdrawn)
    directory=HUB_ROOT/'releases/datasets'/entry['dataset']/entry['version']
    files=checked_package(directory,entry)
    return directory/'boundary.geojson', entry


def capture(root,boundary,rules):
    from shapely.geometry import shape
    directory=root/'captures'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    directory.mkdir(parents=True)
    road=directory/'city-streets.geojson'
    info=capture_layer(rules['source'],shape(read(boundary)['features'][0]['geometry']).bounds,road)
    metadata=road.with_suffix('.metadata.json')
    receipt={'road':{'path':str(road),'sha256':sha(road)},'metadata':{'path':str(metadata),'sha256':sha(metadata)},
             'source':info,'capturedAt':datetime.now(timezone.utc).isoformat()}
    atomic(directory/'receipt.json',receipt)
    return receipt


def prepare(pointer, receipt, boundary, output, version, previous=None):
    pointer=Path(pointer); boundary=Path(boundary); output=Path(output)
    if not re.fullmatch(r"[1-9][0-9]*\.[0-9]+\.[0-9]+",version):raise ValueError("Invalid package version")
    before=pointer.read_bytes(); pin=json.loads(before)
    if sha(pin['path'])!=pin['sha256']:raise ValueError('Crash collection checksum mismatch')
    for item in (receipt['road'],receipt['metadata']):
        if sha(item['path'])!=item['sha256']:raise ValueError('City source checksum mismatch')
    rules=read(RULES); metadata=read(receipt['metadata']['path']); roads=read(receipt['road']['path'])
    if len(roads['features'])<rules['minimumSourceSegments']:raise ValueError('Unexpectedly small City inventory; retain last good release and review capture')
    fields={f['name'] for f in metadata['fields']}
    actual=set().union(*(set(f['properties']) for f in roads['features']))
    if fields!=set(rules['reviewedSourceFields']) or actual-fields:
        raise ValueError('City source schema changed; review all new/removed fields before export')
    collection=read(pin['path'])
    if any('reviewedSummary' not in g.get('enrichment',{}) for g in collection['records']):
        raise ValueError('Finish crash summary review before road-segment export')
    tools=[HUB_ROOT/'pipelines/crashes/src/danger_zones/road_segments.py',Path(__file__),HUB_ROOT/'scripts/prepare_crash_streets.py',HUB_ROOT/'pipelines/crashes/pyproject.toml',HUB_ROOT/'docs/datasets/crash-road-segments.md',HUB_ROOT/'scripts/capture_traffic_stress.py']
    dependencies={'crashCollection':pin['sha256'],'road':receipt['road']['sha256'],'metadata':receipt['metadata']['sha256'],
                  'boundary':sha(boundary),'rules':sha(RULES),'tools':{str(p.relative_to(HUB_ROOT)):sha(p) for p in tools}}
    guarded={Path(pin['path']):pin['sha256'],Path(receipt['road']['path']):receipt['road']['sha256'],
             Path(receipt['metadata']['path']):receipt['metadata']['sha256'],boundary:dependencies['boundary'],RULES:dependencies['rules'],
             **{HUB_ROOT/k:v for k,v in dependencies['tools'].items()}}
    def check_inputs():
        if pointer.read_bytes()!=before or any(sha(p)!=h for p,h in guarded.items()):
            raise ValueError('Dependency changed during segment rebuild')
    recipe=digest(dependencies)
    previous_files={}; comparison=None
    if previous:
        old=read(Path(previous)/'datapackage.json')
        comparison={'version':old['version'],'sha256':sha(Path(previous)/'datapackage.json')}
        verified=checked_package(Path(previous),{'dataset':DATASET,'version':old['version'],'sha256':sha(Path(previous)/'datapackage.json')})
        previous_files={k:json.loads(v) for k,v in verified.items() if k in ('assignments.json','segments.geojson')}
        archive=verify_archive(previous,verified,old['version'])
        if old['dependencyFingerprint']==recipe:
            check_inputs()
            return {'status':'unchanged','path':str(previous),'sha256':sha(Path(previous)/'datapackage.json'),'dependencyFingerprint':recipe,'version':old['version'],**archive}
    result=assign(collection,roads['features'],read(boundary)['features'][0]['geometry'],rules,receipt['road']['sha256'])
    result['review.json']=changes(previous_files,result)
    result['boundary.geojson']=read(boundary)
    result['rules.json']=rules
    result['dictionary.json']={'sourceFields':[f for f in metadata['fields'] if f['name'] not in rules['excludedSourceFields']],
        'sourceSpatialReference':metadata.get('sourceSpatialReference',metadata.get('extent',{}).get('spatialReference')),
        'excludedSourceFields':rules['excludedSourceFields'],
        'derived':{'lengthMeters':'EPSG:26912 planar line length, metres; full source geometry.',
          'withinBoundaryLengthMeters':'EPSG:26912 length clipped to boundary, metres; count physicalGeometryId once.',
          'physicalGeometryId':'Normalized complete line geometry and recorded grade; exact forward/reverse duplicates share a key.',
          'endpointIds':'0.1-metre coordinate/recorded-grade clusters, potential connectivity only; never interior crossings.',
          'segmentId':'Provo City OBJECTID qualified by source; valid only with this package version.',
          'status':'matched, ambiguous, unmatched or missing-location; only matched contributes a single segment count.',
          'sourceRecords':'State-source IDs for joining. Police case numbers and private wording excluded.',
          'coordinates':'Preferred recorded crash position rounded to four decimal degrees; matching uses retained precision.',
          'crashId':'Stable opaque hash of the managed reconciled group ID; one row per managed group.',
          'identityStatus':'managed-group or ambiguous-state-id; ambiguous IDs never receive a confirmed segment count.',
          'ruleVersion':'Version of the explicit matching policy in rules.json.',
          'reasons':'Recorded decision codes explaining selection or non-selection.',
          'roadEvidence':'Original state-source road descriptions used for name matching.',
          'locationSource':'Source of the preferred retained position; null when no valid location.',
          'junctionReported':'Source-classified intersection/roundabout, explicit separator or two recognized spaced road names.',
          'junctionEvidence':'Original state-source junction classifications, including unknown and non-junction labels.',
          'candidates':'All lines within tolerance, with segment/physical IDs, metric distance, endpoint distance, name agreement, eligibility, endpoint IDs and recorded grade.',
          'distanceMeters':'Point-to-source-line planar distance in EPSG:26912, rounded to 0.001 m for reproducibility, not an accuracy claim.',
          'sourceVersion':'SHA-256 of the complete captured City GeoJSON, also bound by sources.json and manifest dependencies.',
          'eligible':'Positive within-boundary road length, excluding Planned and Walkway; zero-crash segments retained.',
          'publicOwner':'OWNER is explicitly Provo, State, Orem or Other; original owner remains available for stricter filters.',
          'names':'Normalized original City primary and alias name components; no invented historical aliases.',
          'grade':'Unchanged VERT_LEVEL, including null; no inferred bridge/tunnel level.',
          'connectivityStatus':'unknown-grade or endpoint-and-recorded-level; neither is field-verified traversability.',
          'source':'All reviewed City properties except disclosed exclusions, unchanged including nulls. Native units and domains retained; undocumented units unresolved.'}}
    result['sources.json']={'city':{'url':rules['source'],'dataSha256':receipt['road']['sha256'],'metadataSha256':receipt['metadata']['sha256'],
                                   'copyrightText':metadata.get('copyrightText'), 'sourceSpatialReference':result['dictionary.json']['sourceSpatialReference']},
                            'crashes':{'releaseId':pin['snapshotId'],'collectionSha256':pin['sha256']},
                            'dependencies':dependencies,'attributeTimeMeaning':'City attributes describe the retained road snapshot, not conditions at each historical crash date.'}
    files={k:encoded(v) for k,v in result.items()}
    files['method.md']=(HUB_ROOT/'docs/datasets/crash-road-segments.md').read_bytes()
    manifest={'name':DATASET,'version':version,'title':'Provo crash associations with City street segments',
              'attribution':'Provo City GIS; Utah Crash Data Portal; UDOT; BikeWalk Provo processing.',
              'reuse':'Retain Provo City and Utah source attribution and informational-use limitations. No independent accuracy warranty. Staff editor identifiers and private police details excluded.',
              'dependencyFingerprint':recipe,'dependencies':dependencies,'crashRelease':pin['snapshotId'],'comparisonBaseline':comparison,
              'resources':[{'name':Path(k).stem,'path':k,'bytes':len(v),'hash':'sha256:'+hashlib.sha256(v).hexdigest()} for k,v in sorted(files.items())]}
    files['datapackage.json']=encoded(manifest)
    archive=archive_bytes(files,version)
    zip_name=f'{DATASET}-{version}.zip'
    expected={'dataset':DATASET,'version':version,'sha256':hashlib.sha256(files['datapackage.json']).hexdigest()}
    check_inputs()
    if output.exists():
        existing=checked_package(output,expected)
        if existing!=files:raise ValueError('Existing candidate differs')
        verify_archive(output,existing,version)
    else:
        output.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output.parent) as temp:
            stage=Path(temp)/'package';stage.mkdir()
            for name,raw in files.items():(stage/name).write_bytes(raw)
            (stage/zip_name).write_bytes(archive)
            checked_package(stage,expected)
            verify_archive(stage,files,version)
            check_inputs()
            stage.rename(output)
    return {'status':'prepared','path':str(output),'sha256':expected['sha256'],'dependencyFingerprint':recipe,'version':version,'coverage':result['coverage.json'], 'zip':str(output/zip_name),'zipSha256':hashlib.sha256(archive).hexdigest()}


def capture_for_update():
    """Capture road dependencies before intake; summary completion later reuses these verified bytes."""
    root=DEFAULT_PRIVATE_DATA_ROOT.parent/'road-segments';root.mkdir(parents=True,exist_ok=True)
    with (root/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        receipt=capture(root,latest_boundary()[0],read(RULES))
        atomic(root/'source.json',receipt)


def refresh(*,offline=False,source_receipt=None,version=None,root=None,pointer=None,boundary=None):
    root=Path(root or DEFAULT_PRIVATE_DATA_ROOT.parent/'road-segments');root.mkdir(parents=True,exist_ok=True)
    pointer=Path(pointer or DEFAULT_PRIVATE_DATA_ROOT/'datastores/combined-incidents.json')
    boundary=Path(boundary or latest_boundary()[0])
    with (root/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        prior=read(root/'candidate.json') if (root/'candidate.json').exists() else None
        if prior:
            checked_package(Path(prior['path']),{'dataset':DATASET,'version':prior['version'],'sha256':prior['sha256']})
        if source_receipt:receipt=read(source_receipt)
        elif offline:
            if not (root/'source.json').exists():raise ValueError('No retained City capture; run scripts.crash_road_segments online or provide --source-receipt')
            receipt=read(root/'source.json')
        else:receipt=capture(root,boundary,read(RULES))
        # Never reuse a capture queried for a different municipal envelope.
        from shapely.geometry import shape
        bounds=','.join(map(str,shape(read(boundary)['features'][0]['geometry']).bounds))
        if receipt['source']['query']['geometry']!=bounds:
            raise ValueError('Boundary changed; recapture City streets online')
        if version is None:
            versions=[e['version'] for e in read(HUB_ROOT/'releases/release-ledger.json')['approved'] if e['dataset']==DATASET]
            version='1.0.0' if not versions else '.'.join(map(str,[1,int(versions[-1].split('.')[1])+1,0]))
        # Content-addressed run directory allows safe repeat and interrupted-build recovery.
        run=digest({'collection':read(pointer)['sha256'],'road':receipt['road']['sha256'],'metadata':receipt['metadata']['sha256'],
                    'boundary':sha(boundary),'rules':sha(RULES),'version':version,'producer':sha(Path(__file__)),
                    'matcher':sha(HUB_ROOT/'pipelines/crashes/src/danger_zones/road_segments.py'),
                    'method':sha(HUB_ROOT/'docs/datasets/crash-road-segments.md'),
                    'names':sha(HUB_ROOT/'scripts/prepare_crash_streets.py'),
                    'capture':sha(HUB_ROOT/'scripts/capture_traffic_stress.py'),
                    'environment':sha(HUB_ROOT/'pipelines/crashes/pyproject.toml'),'comparisonBaseline':prior['sha256'] if prior else None})
        result=prepare(pointer,receipt,boundary,root/'candidates'/run/version,version,prior['path'] if prior else None)
        # Preparation and verification must succeed before either operational pointer advances.
        atomic(root/'source.json',receipt);atomic(root/'candidate.json',result)
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline',action='store_true');parser.add_argument('--source-receipt',type=Path)
    parser.add_argument('--version');parser.add_argument('--root',type=Path);parser.add_argument('--pointer',type=Path);parser.add_argument('--boundary',type=Path)
    print(json.dumps(refresh(**vars(parser.parse_args())),indent=2))
