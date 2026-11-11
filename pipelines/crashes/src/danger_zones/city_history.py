"""Aggregate checksummed city crash captures using the shared annual population."""
from collections import Counter
from io import BytesIO
from datetime import datetime, timezone
import json
import hashlib
import re
from urllib.parse import quote

from openpyxl import load_workbook

from .crash_portal import portal_time, ZONE
from .research_reports import annual_report
from .util import sha256_file



def city_coverage(rows, city):
    filters = {row['Filter']: row['Value'] for row in rows}
    required = {'Age Range': 'All Ages Included', 'Agency': 'All', 'Counties': 'All',
                'Days': 'Mon, Tue, Wed, Thu, Fri, Sat, Sun', 'Hours': '12:00 AM to 11:59 PM',
                'Months': 'All Months', 'Number of Vehicles': 'All Vehicle Counts Included'}
    if (len(filters) != len(rows)
            or set(filters) != required.keys() | {'City', 'Date Selection', 'Vehicle Types', 'Crash Severity'}
            or any(filters[k] != v for k, v in required.items())):
        raise ValueError('Use an unrestricted city export with all days, hours, agencies and vehicles')
    if (filters['City'] != city or filters['Vehicle Types'] != 'All'
            or {s.strip() for s in filters['Crash Severity'].split(',')} != {'1','2','3','4','5'}):
        raise ValueError('Unexpected portal city, vehicle or severity selection')
    selection = filters['Date Selection']
    match = re.fullmatch(r'(.+?) to (.+?) for (\d{4}(?:, \d{4})*)', selection)
    if not match:
        raise ValueError('Unrecognized portal date selection')
    start, end = (datetime.strptime(day, '%b %d, %Y').date() for day in match.groups()[:2])
    years = [int(y) for y in match[3].split(', ')]
    if start > end or any(not start.year <= year <= end.year for year in years):
        raise ValueError('Inconsistent portal date range and selected years')
    return start, end, years



def columns(workbook, name, *fields):
    sheet = workbook[name]
    sheet.reset_dimensions()
    rows = iter(sheet.values)
    header = next(rows)
    if len(set(header)) != len(header):
        raise ValueError(f'Duplicate {name} column')
    indices = [header.index(field) for field in fields]
    for row in rows:
        yield tuple(row[i] if i < len(row) else None for i in indices)


def portal_report(directory, city):
    path = directory / (quote(city, safe="~()*!.'-") + '.xlsx')
    receipt = json.loads(path.with_suffix('.xlsx.json').read_bytes())
    if receipt['city'] != city or receipt['file'] != path.name or sha256_file(path) != receipt['sha256']:
        raise ValueError(f'Portal receipt mismatch for {city}')
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        filters = [dict(Filter=k, Value=v) for k, v in columns(workbook, 'Filters', 'Filter', 'Value')]
        start, end, years = city_coverage(filters, city)
        if ([start, end] != [datetime.strptime(d, '%m/%d/%Y').date() for d in receipt['dates']]
                or years != list(range(start.year, end.year + 1)) or years != list(map(int, receipt['years']))):
            raise ValueError(f'Incomplete portal year selection for {city}')
        seen, eligible = set(), {}
        for key, location, vehicles, timestamp, bike, ped in columns(
                workbook, 'Crashes', 'Crash_ID', 'City_Geo', 'numberOfVehicles', 'crashDateandTime',
                'cyclist_involved', 'pedestrian_involved'):
            key = str(key)
            if not key.isdecimal() or key in seen:
                raise ValueError('Invalid or duplicate portal crash ID')
            seen.add(key)
            day = portal_time(timestamp).astimezone(ZONE).date()
            if not start <= day <= end:
                raise ValueError('Portal crash outside selected dates')
            if city == location and float(vehicles or 0) >= 1:
                eligible[key] = {
                    'sourceKey': 'utah-crash-portal', 'sourceRecordId': key,
                    'observedAt': portal_time(timestamp).isoformat(),
                    'metadata': {
                        'crash': {'City_Geo': city, 'numberOfVehicles': vehicles,
                                  'cyclist_involved': bike, 'pedestrian_involved': ped},
                        'persons': [], 'rollups': [],
                    },
                }
        if len(seen) != receipt['expectedCrashes']:
            raise ValueError('Workbook count differs from applied dashboard filters')
        for key, kind in columns(workbook, 'Persons', 'Crash_ID', 'personType'):
            key = str(key)
            if key not in seen:
                raise ValueError('Orphan portal person')
            if key in eligible and str(kind) in {'3', '4', '5'}:
                eligible[key]['metadata']['persons'].append({'personType': str(kind)})
        for key, bike, ped in columns(workbook, 'Rollups', 'crash_id', 'cyclist_involved', 'pedestrian_involved'):
            key = str(key)
            if key not in seen:
                raise ValueError('Orphan portal rollup')
            if key in eligible and 'Y' in (bike, ped):
                eligible[key]['metadata']['rollups'].append({'cyclist_involved': bike, 'pedestrian_involved': ped})
        report = annual_report(eligible.values(), end.year - 1, city, years)
        return dict(city=city, count=sum(r['total'] for r in report['annual']),
                    years=f'{start.year}–{end.year}', latest=report['coverageEnd'],
                    sourceSelection=next(r['Value'] for r in filters if r['Filter'] == 'Date Selection'),
                    sourceSha256=receipt['sha256'], report=report)
    finally:
        workbook.close()


def udot_summary(directory, requested):
    from shapely import STRtree
    from shapely.geometry import shape

    receipt = json.loads((directory / 'receipt.json').read_bytes())
    def read(name):
        raw = (directory / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != receipt['files'][name]:
            raise ValueError('UDOT capture checksum mismatch: ' + name)
        return json.loads(raw)
    cities = read('cities.json')
    names = [f['properties']['NAME'] for f in cities]
    if set(requested) - set(names):
        raise ValueError('A requested municipality is missing from the boundary source')
    tree = STRtree([shape(f['geometry']) for f in cities])
    counts, latest, seen = Counter(), {}, {}
    years = sorted(map(int, receipt['layers']))
    if not years or years != list(range(years[0], years[-1] + 1)):
        raise ValueError('UDOT year coverage is discontinuous')
    for year in years:
        for row in read(f'{year}.json'):
            props = {k.lower(): v for k, v in row['properties'].items()}
            key = str(props['crash_id'])
            evidence = (row['geometry'], props['number_vehicles_involved'], props['crash_datetime'])
            if not key.isdecimal() or (key in seen and seen[key] != evidence):
                raise ValueError('Invalid or conflicting UDOT crash ID')
            if key in seen:
                continue
            seen[key] = evidence
            if not row['geometry'] or float(props['number_vehicles_involved'] or 0) < 1:
                continue
            matches = {names[i] for i in tree.query(shape(row['geometry']), predicate='intersects')}
            if len(matches) != 1 or matches.isdisjoint(requested):
                continue
            city = matches.pop()
            stamp = props['crash_datetime']
            time = datetime.fromtimestamp(stamp / 1000, timezone.utc) if isinstance(stamp, (int, float)) else datetime.fromisoformat(stamp)
            if time.tzinfo is None:
                raise ValueError('Missing UDOT timestamp offset')
            day = time.astimezone(ZONE).date()
            counts[city] += 1
            latest[city] = max(latest.get(city, day), day)
    return {c: (counts[c], f'{years[0]}–{years[-1]}', latest.get(c)) for c in requested}




def read_city_workbook(workbook, digest, city):
    """Validate the same source population for annual statistics and map exports."""
    from .crash_portal import portal_tables

    if city.lower() == 'all' or not re.fullmatch(r"[A-Za-z]+(?:[. '-]+[A-Za-z]+)*", city):
        raise ValueError('Use the exact city name shown in the Utah portal')
    raw = workbook.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('Checksum mismatch: ' + workbook.name)
    tables, related, filters = portal_tables(BytesIO(raw), city=city, allow_county=False, validate=True)
    start, end, years = city_coverage(tables['Filters'], city)
    observations = []
    for crash in tables['Crashes']:
        identifier = str(crash['Crash_ID'])
        if not identifier.isdecimal():
            raise ValueError('Expected distinct numeric state crash identifiers')
        observed = portal_time(crash['crashDateandTime']).astimezone(ZONE)
        if not start <= observed.date() <= end or observed.year not in years:
            raise ValueError('Crash outside selected dates')
        observations.append({
            'sourceKey': 'utah-crash-portal', 'sourceRecordId': identifier,
            'observedAt': observed.isoformat(),
            'metadata': {'crash': crash, 'persons': related['Persons'][identifier],
                         'rollups': related['Rollups'][identifier]},
        })
    return observations, start, end, years, filters['Date Selection']
