"""Build a private candidate of fatal active-transportation crashes from a pinned hub release."""
import argparse
from datetime import datetime
import hashlib
import json
import math
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from danger_zones.incident_updates import flatten
from danger_zones.research_reports import crash_modes

NAME = 'provo-active-transportation-fatal-crashes'
ROOT = Path(__file__).resolve().parent
MODES = {'3': 'pedestrian', '4': 'bicycle', '5': 'other-conveyance'}
DICTIONARY = {
    'id': 'String. State crash identifier, one feature per crash.',
    'geometry': 'GeoJSON Point in longitude, latitude order (WGS84). Portal location rounded to four decimal places. Approximate.',
    'month': 'String YYYY-MM. State occurrence month in Mountain Time.',
    'mode': 'Category of the person or people recorded killed: pedestrian, bicycle, or other-conveyance. The last includes wheelchairs, skaters and personal conveyances. It does not identify a specific device.',
    'fatalities': 'Integer. Number of people recorded killed in this crash, including multiple deaths in one crash.',
}
METHOD = """One feature represents one reviewed fatal crash in the managed active-transportation series. The state portal must assign the crash to Provo and support active-transportation involvement. The hub uses portal person injury level 5 for deaths and checks any corresponding UDOT death count. Unassigned city records are outside coverage. A new or mixed category among the people killed requires review before publication. The geojson omits personal attributes, exact times and dates, police case numbers, news and narratives. The 2010–2017 archive has been examined separately and is outside this version. State records may be revised.
"""


def encoded(item):
    return (json.dumps(item, indent=2, ensure_ascii=False, allow_nan=False)+'\n').encode()


def checked(path, expected):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Checksum mismatch: ' + path.name)
    return json.loads(raw)


def feature(group):
    observations = list(flatten({'records': [group]}).values())
    portals = [o for o in observations if o['sourceKey'] == 'utah-crash-portal']
    udot = [o for o in observations if o['sourceKey'] == 'udot-crashes']
    if not portals:
        return None
    if len(portals) != 1:
        raise ValueError('Ambiguous state crash identity')
    source = portals[0]
    crash = source['metadata']['crash']
    if crash.get('City_Geo') != 'Provo' or not crash_modes(source):
        return None
    dead = [p for p in source['metadata']['persons'] if str(p.get('injuryLevel')) == '5']
    counts = {int(o['metadata']['NUMBER_FATALITIES']) for o in udot if o['metadata'].get('NUMBER_FATALITIES') is not None}
    if not (dead or str(crash.get('crashSeverity')) == '5' or any(counts)
            or any(str(o['metadata'].get('CRASH_SEVERITY_DESC')).lower() == 'fatal' for o in udot)):
        return None
    identifier = source['sourceRecordId']
    if not identifier.isascii() or not identifier.isdecimal() or any(o['sourceRecordId'] != identifier for o in udot):
        raise ValueError('Review state identifier: ' + identifier)
    if not dead or counts - {len(dead)}:
        raise ValueError('Review missing or conflicting death count: ' + identifier)
    modes = {MODES.get(str(p.get('personType'))) for p in dead}
    if None in modes or len(modes) != 1:
        raise ValueError('Review category of people killed: ' + identifier)
    lon, lat = source['coordinates']
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError('Invalid portal point: ' + identifier)
    stamp = datetime.fromisoformat(source['observedAt'])
    if stamp.tzinfo is None:
        raise ValueError('Missing time offset: ' + identifier)
    if stamp.astimezone(ZoneInfo('America/Denver')).year < 2018:
        return None
    return {'type': 'Feature', 'id': identifier, 'geometry': {'type': 'Point', 'coordinates': [round(lon,4), round(lat,4)]},
            'properties': {'month': stamp.astimezone(ZoneInfo('America/Denver')).strftime('%Y-%m'),
                           'mode': modes.pop(), 'fatalities': len(dead)}}


def build(manifest_file, pin, output, version):
    if not re.fullmatch(r'(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)', version):
        raise ValueError('Expected a numeric release version')
    if not output.resolve().is_relative_to(ROOT / 'private') or output.exists():
        raise ValueError('Use a new directory under private/')
    manifest = checked(manifest_file, pin)
    data = checked(manifest_file.parent / 'collection.json', manifest['files']['collection.json'])
    if data['snapshotId'] != manifest['releaseId']:
        raise ValueError('Release identity mismatch')
    features = sorted((f for group in data['records'] if (f := feature(group))), key=lambda f: f['id'])
    if not features or len(features) != len({f['id'] for f in features}):
        raise ValueError('Empty layer or duplicate state crash ID')
    files = {'fatal-crashes.geojson': encoded({'type': 'FeatureCollection', 'features': features}),
             'dictionary.json': encoded(DICTIONARY), 'method.txt': METHOD.encode()}
    resources = [{'name': Path(k).stem,'path':k,'bytes':len(v),'hash':'sha256:'+hashlib.sha256(v).hexdigest()} for k,v in files.items()]
    package = dict(name=NAME, version=version, title='Fatal active transportation crashes in Provo',
                   source='https://utaps.shinyapps.io/DataPortalAWS/', attribution='Utah Crash Data Portal and UDOT. Prepared by BikeWalk Provo.',
                   reuse='Credit the Utah Crash Data Portal, UDOT, and BikeWalk Provo when reusing this geographic dataset.',
                   coverage='State portal Provo city assignments, starting in 2018. Recent records are provisional.',
                   citySourceSelections=[i['filters']['Date Selection'] for i in manifest['inputs'] if i.get('kind')=='portal' and i.get('scope')=='collection'],
                   observedMonths=sorted({f['properties']['month'] for f in features}),
                   records=len(features), fatalities=sum(f['properties']['fatalities'] for f in features),
                   citation=f'BikeWalk Provo. Fatal active transportation crashes in Provo, {version}. https://bikewalk-provo-data-hub.vercel.app/datasets/{NAME}/{version}/datapackage.json',
                   sourceRelease=manifest['releaseId'], resources=resources)
    output.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temp:
        stage = Path(temp)/'package'
        stage.mkdir(mode=0o700)
        for k,v in {**files, 'datapackage.json':encoded(package)}.items():
            (stage/k).write_bytes(v)
        stage.rename(output)
    print(hashlib.sha256(encoded(package)).hexdigest())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    parser.add_argument('sha256')
    parser.add_argument('output',type=Path)
    parser.add_argument('--version', default='1.0.0')
    args = parser.parse_args()
    build(args.manifest, args.sha256, args.output, args.version)
