"""Build BYU access geometry from the retained Provo street network and reviewed venue references."""
import argparse
import json
from pathlib import Path

import pyarrow.parquet as pq
from shapely import from_wkb
from shapely.geometry import Point, box, mapping

from danger_zones.util import sha256_file

CROSSINGS = [
    ('university-parkway-university-avenue', 'University Parkway / University Avenue', -111.65862, 40.25575),
    ('university-parkway-canyon-road', 'University Parkway / Canyon Road', -111.65611, 40.25578),
    ('stadium-avenue-canyon-road', 'Stadium Avenue / Canyon Road', -111.65608, 40.25879),
    ('university-parkway-450-east', 'University Parkway / 450 East', -111.65050, 40.25565),
    ('university-parkway-900-east', 'University Parkway / 900 East', -111.64326, 40.25670),
]
LOTS = [
    ('stadium-west', 'Stadium west parking', [-111.6583, 40.2560, -111.6563, 40.2585]),
    ('stadium-north', 'Stadium north parking', [-111.6559, 40.2590, -111.6514, 40.2608]),
    ('marriott-north', 'Marriott Center north parking', [-111.6505, 40.2548, -111.6470, 40.2558]),
    ('marriott-east', 'Marriott Center east parking', [-111.6470, 40.2534, -111.6453, 40.2554]),
    ('west-intramural', 'West intramural event parking', [-111.6615, 40.2561, -111.6590, 40.2585]),
]


def run(streets, output):
    digest = sha256_file(streets)
    athletics = ['byu_football', 'byu_mens_basketball']
    sources = ['https://byucougars.com/news/2015/09/10/byu-announces-improvements-to-football-game-day-experience',
               'https://byucougars.com/news/2002/08/26/parking-procedures-for-byu-football',
               'https://byucougars.com/marriott-center-policies']
    features = []
    def add(identifier, name, geometry, types, reviewed, series, **extra):
        features.append({'type': 'Feature', 'geometry': mapping(geometry), 'properties': {
            'id': identifier, 'name': name, 'match_types': types, 'series': series,
            'review_status': 'reviewed' if reviewed else 'candidate',
            'valid_from': '2026-01-01' if reviewed else '2010-01-01', 'valid_through': '2026-12-31',
            'sources': sources, 'network_sha256': digest, **extra}})
    for identifier, name, x, y in CROSSINGS:
        add(identifier, name, Point(x, y), ['crossing'], True, athletics, buffer_metres=45,
            basis='2026 city street junction with venue access references. Grade-separated walkway excluded.')
        add(identifier+'-historical-review', name, Point(x, y), ['crossing'], False, athletics + ['stadium_of_fire'],
            buffer_metres=45, basis='Historical event access and exact crossing footprint require dated verification.')
    envelope = box(-111.6618, 40.2505, -111.6430, 40.2635)
    for row in pq.read_table(streets).to_pylist():
        if row['full_name'] not in {'N UNIVERSITY AVE', 'N CANYON RD', 'E UNIVERSITY PKWY', 'E STADIUM AVE', 'E COUGAR BLVD', 'N 450 E', 'N 900 E'}:
            continue
        g = from_wkb(row['geometry']).intersection(envelope)
        if not g.is_empty:
            add('street-'+row['segment_id'], row['full_name'], g, ['parking'], True, athletics,
                buffer_metres=25, basis='2026 street frontage. Positive match still requires reported improper parking or parking maneuver.')
            add('historical-street-'+row['segment_id'], row['full_name'], g, ['parking'], False, athletics + ['stadium_of_fire'],
                buffer_metres=25, basis='Historical event access requires verification.')
    for identifier, name, bounds in LOTS:
        add(identifier, name, box(*bounds), ['parking'], False, athletics + ['stadium_of_fire'],
            basis='Approximate review envelope, not a surveyed lot or historical parking-use assertion.')
    # The 2026 organizer explicitly locates the pre-show and dance in the stadium west lot.
    add('stadium-of-fire-west-access', 'Stadium of Fire west-lot access', Point(-111.65610, 40.2572),
        ['crossing', 'parking'], True, ['stadium_of_fire'], buffer_metres=45,
        basis='Organizer 2026 west-lot program plus city Canyon Road geometry.',
        event_source='https://freedomfestival.org/stadium-of-fire/')
    output.write_text(json.dumps({'type':'FeatureCollection','features':features}, indent=2) + '\n')
    print(json.dumps({'features':len(features), 'network_sha256':digest}))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('streets',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.streets,a.output)
