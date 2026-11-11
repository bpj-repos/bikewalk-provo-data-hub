"""Capture UDOT annual pedestrian/bicycle crash points and Utah city boundaries for offline review."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from datetime import datetime, timezone

from danger_zones.arcgis import session
from scripts.prepare_crash_releases import ROOT

ARCHIVE = 'https://maps.udot.utah.gov/central/rest/services/TrafficAndSafety/Crash_Locations/MapServer'
HOSTED = 'https://services.arcgis.com/pA2nEVnB6tquxgOW/ArcGIS/rest/services/Utah_Crash_Locations/FeatureServer'
BOUNDARIES = 'https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/UtahMunicipalBoundaries/FeatureServer/0'


def query(client, url, **params):
    data = {'f': 'json', **params}
    if 'objectIds' in params and url.startswith(HOSTED + '/'):
        response = client.post(url, data=data, timeout=(10, 60))
    else:
        response = client.get(url, params=data, timeout=(10, 60))
    response.raise_for_status()
    data = response.json()
    if 'error' in data or data.get('exceededTransferLimit'):
        raise ValueError(f'Incomplete ArcGIS query: {url}: {data.get("error")}')
    return data


def annual(client, url, hosted):
    ids = set()
    for field in ('pedestrian_involved', 'bicyclist_involved'):
        ids.update(query(client, url + '/query', where=f"{field} = 'Y'", returnIdsOnly='true')['objectIds'])
    fields = 'crash_id,crash_datetime,number_vehicles_involved'
    fields = 'OBJECTID,' + (fields if hosted else fields.upper())
    ordered = sorted(ids)
    features = []
    for offset in range(0, len(ordered), 500):
        page = ordered[offset:offset + 500]
        rows = query(client, url + '/query', objectIds=','.join(map(str, page)), outFields=fields,
                     outSR=4326, f='geojson')['features']
        if sorted(row['properties']['OBJECTID'] for row in rows) != page:
            raise ValueError(f'Incomplete UDOT feature page: {url}')
        features.extend(rows)
    return features


def capture(output):
    if not output.resolve().is_relative_to(ROOT / 'private'):
        raise ValueError('Use a new private directory')
    output.mkdir(mode=0o700)
    files = {}
    def save(name, value):
        raw = json.dumps(value, separators=(',', ':')).encode()
        (output / name).write_bytes(raw)
        files[name] = hashlib.sha256(raw).hexdigest()
    with session() as client:
        layers = {}
        for service in (ARCHIVE, HOSTED):
            for layer in query(client, service)['layers']:
                year = re.search(r'\b(20\d{2})\b', layer['name'])
                if year:
                    layers[int(year[1])] = f"{service}/{layer['id']}"
        years = sorted(layers)
        if not years or years != list(range(min(years), max(years) + 1)):
            raise ValueError('Expected continuous UDOT year layers')
        cities = query(client, BOUNDARIES + '/query', where='1=1', outFields='NAME', outSR=4326, f='geojson')['features']
        if len(cities) != query(client, BOUNDARIES + '/query', where='1=1', returnCountOnly='true')['count']:
            raise ValueError('Incomplete municipal boundary inventory')
        save('cities.json', cities)
        for year in years:
            rows = annual(client, layers[year], layers[year].startswith(HOSTED + '/'))
            save(f'{year}.json', rows)
            print(year, len(rows), flush=True)
    save('receipt.json', dict(layers=layers, boundaries=BOUNDARIES, files=files,
                              retrievedAt=datetime.now(timezone.utc).isoformat()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    capture(parser.parse_args().output)
