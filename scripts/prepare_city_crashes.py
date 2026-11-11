"""Prepare one Utah city's annual active transportation crash package from one portal XLSX."""
import argparse
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
import re

from danger_zones.crash_portal import ZONE, portal_tables, portal_time
from danger_zones.research_reports import annual_report
from scripts.prepare_crash_releases import AT, write_package
from scripts.restore_crash_collections import verified


def prepare(workbook, digest, output, city, version, complete):
    if city.lower() == 'all' or not re.fullmatch(r"[A-Za-z]+(?:[. '-]+[A-Za-z]+)*", city):
        raise ValueError('Use the exact city name shown in the Utah portal')
    tables, related, filters = portal_tables(BytesIO(verified(workbook, digest)), city=city,
                                             allow_county=False, validate=True)
    required = {'Age Range': 'All Ages Included', 'Agency': 'All', 'Counties': 'All',
                'Days': 'Mon, Tue, Wed, Thu, Fri, Sat, Sun', 'Hours': '12:00 AM to 11:59 PM',
                'Months': 'All Months', 'Number of Vehicles': 'All Vehicle Counts Included'}
    if (len(filters) != len(tables['Filters'])
            or set(filters) != required.keys() | {'City', 'Date Selection', 'Vehicle Types', 'Crash Severity'}
            or any(filters[k] != v for k, v in required.items())):
        raise ValueError('Use an unrestricted city export with all days, hours, agencies and vehicles')
    selection = filters['Date Selection']
    match = re.fullmatch(r'(.+?) to (.+?) for (\d{4}(?:, \d{4})*)', selection)
    if not match:
        raise ValueError('Unrecognized portal date selection')
    start, end = (datetime.strptime(day, '%b %d, %Y').date() for day in match.groups()[:2])
    years = [int(y) for y in match[3].split(', ')]
    if start > end or any(not start.year <= year <= end.year for year in years):
        raise ValueError('Inconsistent portal date range and selected years')
    last_full_year = end.year if end == date(end.year, 12, 31) else end.year - 1
    if complete > last_full_year:
        raise ValueError('Complete-through exceeds the workbook’s last full year')
    observations = []
    seen = set()
    for crash in tables['Crashes']:
        identifier = str(crash['Crash_ID'])
        if not identifier.isdecimal() or identifier in seen:
            raise ValueError('Expected distinct numeric state crash identifiers')
        seen.add(identifier)
        observed = portal_time(crash['crashDateandTime']).astimezone(ZONE)
        if not start <= observed.date() <= end or observed.year not in years:
            raise ValueError('Crash outside selected dates')
        observations.append({
            'sourceKey': 'utah-crash-portal', 'sourceRecordId': identifier,
            'observedAt': observed.isoformat(),
            'metadata': {'crash': crash, 'persons': related['Persons'][identifier],
                         'rollups': related['Rollups'][identifier]},
        })
    report = annual_report(observations, complete, city, years)
    for row in report['annual']:
        year = row['year']
        row['complete'] = row['complete'] and start <= date(year, 1, 1) and date(year, 12, 31) <= end
    slug = re.sub(r'[^a-z]+', '-', city.lower())
    write_package(report, [selection], output, version, complete, city=city, dataset=f'{slug}-{AT}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workbook', type=Path)
    parser.add_argument('sha256')
    parser.add_argument('output', type=Path)
    parser.add_argument('--city', required=True)
    parser.add_argument('--version', default='1.0.0')
    parser.add_argument('--complete-through', type=int, required=True, help='Last year reviewed as complete')
    args = parser.parse_args()
    prepare(args.workbook, args.sha256, args.output, args.city, args.version, args.complete_through)
