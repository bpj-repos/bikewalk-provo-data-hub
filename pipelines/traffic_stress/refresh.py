"""Private citywide source acquisition, content-keyed processing and release comparison."""
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

from shapely.geometry import shape
from shapely.ops import transform

from scripts import refresh_route_sources as upstream
from scripts.capture_traffic_stress import capture_layer, LAYERS
from scripts.route_stress import PROJECT, UNPROJECT
from scripts.build_demo_counts import encoded

ROOT = Path(__file__).resolve().parents[2]
STUDIES = {
    'crosswalks': 'https://gispublicweb.provo.gov/ArcGIS/rest/services/Public_Works/Crosswalks/MapServer/1',
    'signalized': 'https://maps.udot.utah.gov/central/rest/services/TrafficAndSafety/AT_Intersection_Safety_Data/MapServer/1',
    'nonsignalized': 'https://maps.udot.utah.gov/central/rest/services/TrafficAndSafety/AT_Intersection_Safety_Data/MapServer/2',
}
NETWORK_FILES = ('network.json',)
MODEL_FILES = ('neighborhood_ways.geojson', 'neighborhood_ways_intersections.geojson')


def sha(path):
    return upstream.digest(path)


def write(path, obj):
    path.write_bytes(encoded(obj))


def checked(path, expected):
    if sha(path) != expected:
        raise ValueError('Changed retained input: ' + str(path))
    return path


def read_receipt(path):
    value = json.loads(path.read_bytes())
    for source in value['sources'].values():
        checked(path.parent / source['path'], source['sha256'])
    return value


def descriptor(path, origin, version, date, **extra):
    return dict(path=path.name, sha256=sha(path), origin=origin, version=version, date=date, **extra)


def cached(directory, recipe, filenames, produce):
    """Serialize one expensive recipe and reject altered cached output."""
    key = hashlib.sha256(encoded(recipe)).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / key
    with (directory / (key + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if target.exists():
            receipt = json.loads((target / 'receipt.json').read_bytes())
            if receipt['recipe'] != recipe or set(receipt['outputs']) != set(filenames):
                raise ValueError('Cache recipe mismatch')
            for name, digest in receipt['outputs'].items():
                checked(target / name, digest)
            return target, True
        with tempfile.TemporaryDirectory(dir=directory) as temp:
            stage = Path(temp) / 'entry'
            stage.mkdir()
            produce(stage)
            receipts = {name: sha(stage / name) for name in filenames}
            write(stage / 'receipt.json', dict(recipe=recipe, outputs=receipts))
            stage.rename(target)
    return target, False


def parse_osm(stream):
    """Retain street tags and shared OSM nodes, without geometric intersection inference."""
    coords, ways = {}, []
    events = ET.iterparse(stream, events=('start', 'end'))
    _, root = next(events)
    for event, element in events:
        if event != 'end' or element.tag not in ('node', 'way', 'relation'):
            continue
        if element.tag == 'node':
            coords[int(element.attrib['id'])] = [float(element.attrib['lon']), float(element.attrib['lat'])]
        elif element.tag == 'way':
            tags = {child.attrib['k']: child.attrib['v'] for child in element.findall('tag')}
            nodes = [int(child.attrib['ref']) for child in element.findall('nd')]
            if 'highway' in tags and len(nodes) >= 2:
                if any(node not in coords for node in nodes):
                    raise ValueError('Incomplete OSM way nodes')
                ways.append([int(element.attrib['id']), nodes, tags])
        root.clear()
    used = {node for _, nodes, _ in ways for node in nodes}
    if not ways:
        raise ValueError('Empty reference street network')
    return dict(coords={str(node): coords[node] for node in sorted(used)}, ways=sorted(ways))


def extract_network(inputs, image, output):
    boundary = shape(json.loads((inputs / 'boundary.json').read_bytes())['features'][0]['geometry'])
    area = transform(UNPROJECT, transform(PROJECT, boundary).buffer(3000)).bounds
    mount = ['-v', f'{inputs}:/tmp/inputs:ro', '-v', f'{output}:/tmp/outputs']
    upstream.run('docker', 'run', '--rm', '--user', f'{os.getuid()}:{os.getgid()}', *mount, '--entrypoint', 'osmium', image,
                 'extract', '-b', ','.join(map(str, area)), '-s', 'complete_ways',
                 '/tmp/inputs/utah.osm.pbf', '-o', '/tmp/outputs/reference.osm.pbf')
    xml = output / 'reference.osm'
    with xml.open('wb') as stream:
        upstream.run('docker', 'run', '--rm', '-v', f'{output}:/tmp/outputs:ro', '--entrypoint',
                     'osmium', image, 'cat', '/tmp/outputs/reference.osm.pbf', '-f', 'osm', stdout=stream)
    with xml.open('rb') as stream:
        network = parse_osm(stream)
    (output / 'network.json').write_text(json.dumps(network, separators=(',', ':'), allow_nan=False))
    # Only these identified, reproducible intermediates belong to this cache build.
    xml.unlink()
    (output / 'reference.osm.pbf').unlink()


def acquire(previous_path, output, refresh_intersections=False):
    previous = read_receipt(previous_path)
    sources, status = {}, {}
    now = datetime.now(timezone.utc).isoformat()
    boundary = upstream.api(upstream.BOUNDARY + '/query', where="UPPER(NAME)='PROVO'", outFields='NAME',
                            returnGeometry='true', outSR=4326, f='geojson')
    if len(boundary['features']) != 1 or boundary['features'][0]['properties']['NAME'].lower() != 'provo':
        raise ValueError('Unexpected municipal boundary')
    city = shape(boundary['features'][0]['geometry'])
    if city.geom_type not in ('Polygon', 'MultiPolygon') or not city.is_valid:
        raise ValueError('Invalid municipal geometry')
    write(output / 'boundary.json', boundary)
    sources['boundary'] = descriptor(output / 'boundary.json', upstream.BOUNDARY, now, now[:10])
    rating = upstream.api(upstream.CITY)
    if (rating['city']['name'], rating['city']['state']) != ('Provo', 'Utah'):
        raise ValueError('Unexpected BNA city')
    version = rating['ratings'][0]['version']
    if not re.fullmatch(r'\d{2}\.\d{2}', version):
        raise ValueError('Unexpected BNA version')
    speed = rating['ratings'][0].get('residential_speed_limit_override') or rating['city']['residential_speed_limit']
    if type(speed) is not int or not 5 <= speed <= 55:
        raise ValueError('Invalid residential default')
    published_url = f'https://files.storage.bna.peopleforbikes.org/united%20states/utah/provo/{version}/neighborhood_ways.geojson'
    upstream.fetch(published_url, output / 'published.geojson')
    published = json.loads((output / 'published.geojson').read_bytes())['features']
    fields = ('ft_seg_stress', 'tf_seg_stress', 'ft_int_stress', 'tf_int_stress')
    if not published or len({f['properties']['road_id'] for f in published}) != len(published):
        raise ValueError('Incomplete published BNA network')
    if any(f['properties'][key] not in (None, 1, 2, 3, 4) for f in published for key in fields):
        raise ValueError('Unsupported published BNA rating')
    sources['published'] = descriptor(output / 'published.geojson', published_url, version, version)
    prior_model = previous['provenance']['modelReceipt']
    model = {key: prior_model[key] for key in ('method', 'analyzer', 'analyzerVersion', 'database')}
    image = model['analyzer']
    if not re.fullmatch(r'ghcr.io/peopleforbikes/brokenspoke-analyzer@sha256:[a-f0-9]{64}', image):
        raise ValueError('Expected approved analyzer image digest')
    latest = upstream.api(upstream.ANALYZER)['tag_name'].lstrip('v')
    model['method'] = f"BikeWalk local Brokenspoke Analyzer {model['analyzerVersion']}"
    model['speed'] = speed
    # Refresh data using the reviewed model; report new algorithm releases for deliberate adoption.
    upstream.run('docker', 'pull', image)
    expected = upstream.fetch(upstream.PBF + '.md5').decode().split()[0]
    if not re.fullmatch('[a-f0-9]{32}', expected):
        raise ValueError('Invalid PBF checksum delivery')
    prior_acquisition = previous.get('provenance', {}).get('acquisition', {})
    prior_pbf = prior_acquisition.get('osm', {})
    prior_path = previous_path.parent / prior_pbf.get('path', 'recovery/utah.osm.pbf')
    pbf = output / 'utah.osm.pbf'
    reused = False
    if prior_path.exists():
        expected_sha = prior_pbf.get('sha256') or previous['provenance'].get('originalOsmPbfSha256')
        if not expected_sha:
            raise ValueError('Retained PBF has no recorded SHA-256')
        checked(prior_path, expected_sha)
        if upstream.digest(prior_path, 'md5') == expected:
            shutil.copyfile(prior_path, pbf)
            reused = True
    if not reused:
        upstream.fetch(upstream.PBF, pbf)
    if upstream.digest(pbf, 'md5') != expected or upstream.fetch(upstream.PBF + '.md5').decode().split()[0] != expected:
        raise ValueError('PBF changed during acquisition; use a fresh run')
    timestamp = upstream.run('docker', 'run', '--rm', '-v', f'{pbf}:/utah.osm.pbf:ro', '--entrypoint',
                             'osmium', image, 'fileinfo', '-g', 'header.option.osmosis_replication_timestamp',
                             '/utah.osm.pbf', capture_output=True, text=True).stdout.strip()
    datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    osm = dict(path=pbf.name, sha256=sha(pbf), md5=expected, snapshot=timestamp, origin=upstream.PBF, reused=reused)
    urls = dict(LAYERS, utah=upstream.BIKES)
    if refresh_intersections:
        urls.update(STUDIES)
    bounds = city.bounds
    for key, url in urls.items():
        old = previous['sources'].get(key, {})
        meta = upstream.api(url, f='json')
        stamp = meta.get('editingInfo', {}).get('lastEditDate')
        old_bounds = old.get('query', {}).get('geometry')
        reuse = bool(stamp and stamp == old.get('editingInfo', {}).get('lastEditDate') and old.get('origin') == url
                     and old_bounds and tuple(map(float, old_bounds.split(','))) == bounds)
        target = output / (key + '.geojson')
        if reuse:
            shutil.copyfile(previous_path.parent / old['path'], target)
            source = dict(old, path=target.name)
        else:
            source = capture_layer(url, bounds, target)
            if key in ('city-streets', 'sgid-streets', 'utah') and not json.loads(target.read_bytes())['features']:
                raise ValueError('Empty primary source: ' + key)
            stamp = (source.get('editingInfo') or {}).get('lastEditDate')
            source.update(path=target.name, sha256=sha(target), version=str(stamp or now),
                          date=upstream.date_ms(stamp) if stamp else now[:10])
        source['checkedAt'] = now
        sources[key] = source
        status[key] = 'reused_verified_edit_stamp' if reuse else 'captured'
    if not refresh_intersections:
        for key in STUDIES:
            old = previous['sources'].get(key)
            if old:
                target = output / (key + Path(old['path']).suffix)
                shutil.copyfile(previous_path.parent / old['path'], target)
                sources[key] = dict(old, path=target.name)
                status[key] = 'retained_dated_snapshot'
    model.update(publishedComparison=published_url, publishedVersion=version, comparisonSha256=sources['published']['sha256'], utahBikeways=sources['utah'])
    model.update(modelInputs={'utah.osm.pbf': osm, 'boundary.json': sources['boundary']})
    return dict(sources=sources, evidence=previous.get('evidence', []),
                provenance=dict(modelReceipt=model, acquisition=dict(osm=osm, sourceStatus=status,
                    availableAnalyzerVersion=latest, approvedAnalyzerVersion=model['analyzerVersion'])))


def process(record, inputs, cache):
    osm = record['provenance']['acquisition']['osm']
    checked(inputs / osm['path'], osm['sha256'])
    model = record['provenance']['modelReceipt']
    image = model['analyzer']
    common = dict(osm=osm['sha256'], boundary=record['sources']['boundary']['sha256'], analyzer=image)
    network_recipe = dict(common, extractor=sha(Path(__file__)), bufferMeters=3000)
    network, network_reused = cached(cache / 'network', network_recipe, NETWORK_FILES,
        lambda output: extract_network(inputs, image, output))
    recipe = dict(common, database=model['database'], speed=model['speed'], runner=sha(Path(upstream.__file__)),
                  modelScript=sha(ROOT / 'scripts/model_bicycle_stress.py'))
    def produce(output):
        upstream.model(inputs, model)
        for name in MODEL_FILES:
            rows = json.loads((inputs / name).read_bytes())['features']
            if not rows:
                raise ValueError('Empty model output')
            shutil.copyfile(inputs / name, output / name)
    modeled, model_reused = cached(cache / 'model', recipe, MODEL_FILES, produce)
    for key, folder, name, version in [('network', network, 'network.json', osm['snapshot']),
            ('local', modeled, MODEL_FILES[0], model['analyzerVersion']), ('local-nodes', modeled, MODEL_FILES[1], model['analyzerVersion'])]:
        target = inputs / name
        shutil.copyfile(folder / name, target)
        record['sources'][key] = descriptor(target, 'BikeWalk processing of pinned OSM input', version, osm['snapshot'][:10])
    model['pinnedResources'] = {record['sources'][key]['path']: record['sources'][key]['sha256'] for key in ('local', 'local-nodes', 'utah')}
    record['provenance']['processing'] = dict(networkRecipe=network_recipe, modelRecipe=recipe,
                                             networkCacheReused=network_reused, modelCacheReused=model_reused)
    return record


def compare(previous_files, package):
    """Review native selection changes by feature identity, retaining geometry churn separately."""
    report = {}
    for resource in ('segments', 'approaches'):
        old = {f['id']: f for f in json.loads(previous_files[resource + '.geojson'])['features']}
        new = {f['id']: f for f in json.loads((package / (resource + '.geojson')).read_bytes())['features']}
        shared = old.keys() & new.keys()
        report[resource] = dict(added=len(new.keys()-old.keys()), removed=len(old.keys()-new.keys()),
            sourceChanged=sum(old[k]['properties']['source'] != new[k]['properties']['source'] for k in shared),
            bandChanged=sum(old[k]['properties']['band'] != new[k]['properties']['band'] for k in shared),
            geometryChanged=sum(old[k]['geometry'] != new[k]['geometry'] for k in shared))
    report['previousCoverage'] = json.loads(previous_files['coverage.json'])
    report['candidateCoverage'] = json.loads((package / 'coverage.json').read_bytes())
    report['interpretation'] = 'Added/removed IDs can reflect segmentation and source geometry changes. Reference coverage excludes overlapping publisher-only extras.'
    return report
