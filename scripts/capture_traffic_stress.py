"""Capture complete local street layers and pin retained model/network inputs privately."""
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from scripts.build_demo_counts import encoded

LAYERS = {
    'city-streets': 'https://gispublicweb.provo.gov/arcgis/rest/services/Parcel/FeatureServer/0',
    'sgid-streets': 'https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/UtahRoads/FeatureServer/0',
}


def fetch(url, params):
    with urlopen(url + '?' + urlencode(params), timeout=120) as response:
        value = json.load(response)
    if 'error' in value:
        raise ValueError(value['error'])
    return value


def capture_layer(url, bounds, output):
    metadata = fetch(url, {'f': 'json'})
    query = dict(f='json', where='1=1', geometry=','.join(map(str, bounds)),
                 geometryType='esriGeometryEnvelope', inSR=4326, spatialRel='esriSpatialRelIntersects')
    ids = fetch(url + '/query', dict(query, returnIdsOnly='true'))
    identifiers = sorted(ids['objectIds'])
    features = []
    for start in range(0, len(identifiers), 100):
        page = fetch(url + '/query', dict(f='geojson', objectIds=','.join(map(str, identifiers[start:start+100])),
                                          outFields='*', outSR=4326))
        if page.get('exceededTransferLimit'):
            raise ValueError('Incomplete ArcGIS page')
        features.extend(page['features'])
    key = ids['objectIdFieldName']
    if sorted(f['properties'][key] for f in features) != identifiers:
        raise ValueError('ArcGIS membership mismatch')
    count = fetch(url + '/query', dict(query, returnCountOnly='true'))['count']
    final_ids = sorted(fetch(url + '/query', dict(query, returnIdsOnly='true'))['objectIds'])
    if count != len(identifiers) or final_ids != identifiers:
        raise ValueError('ArcGIS membership changed during capture')
    after = fetch(url, {'f': 'json'})
    if metadata.get('editingInfo') != after.get('editingInfo'):
        raise ValueError('Source changed during capture')
    output.write_bytes(encoded(dict(type='FeatureCollection', features=features)))
    output.with_suffix('.metadata.json').write_bytes(encoded(metadata))
    return dict(origin=url, count=len(features), editingInfo=metadata.get('editingInfo'), query=query)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('holdings', type=Path, help='JSON mapping source names to path, origin, version and date')
    p.add_argument('output', type=Path)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    sources = json.loads(args.holdings.read_bytes())
    for key, source in sources.items():
        path = Path(source.pop('path'))
        target = args.output / (key + ''.join(path.suffixes))
        shutil.copyfile(path, target)
        source.update(path=target.name, sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    boundary = json.loads((args.output / sources['boundary']['path']).read_bytes())
    from shapely.geometry import shape
    bounds = shape(boundary['features'][0]['geometry']).bounds
    for key, url in LAYERS.items():
        target = args.output / (key + '.geojson')
        sources[key] = capture_layer(url, bounds, target)
        captured = datetime.now(timezone.utc).isoformat()
        sources[key].update(path=target.name, sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                            version=captured, date=captured[:10])
    (args.output / 'receipt.json').write_bytes(encoded(dict(sources=sources, evidence=[])))


if __name__ == '__main__':
    main()
