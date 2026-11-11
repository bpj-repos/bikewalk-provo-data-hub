"""Prepare one Utah city's annual active transportation crash package from one portal XLSX."""
import argparse
from datetime import date
from io import BytesIO
from pathlib import Path
import re

from danger_zones.city_history import city_coverage
from danger_zones.crash_portal import ZONE, portal_tables, portal_time
from danger_zones.research_reports import annual_report
from scripts.prepare_crash_releases import AT, write_package
from scripts.restore_crash_collections import verified


def prepare(workbook, digest, output, city, version, complete):
    if city.lower() == 'all' or not re.fullmatch(r"[A-Za-z]+(?:[. '-]+[A-Za-z]+)*", city):
        raise ValueError('Use the exact city name shown in the Utah portal')
    tables, related, filters = portal_tables(BytesIO(verified(workbook, digest)), city=city,
                                             allow_county=False, validate=True)
    start, end, years = city_coverage(tables['Filters'], city)
    selection = filters['Date Selection']
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
    parser.add_argument('--version', default='1.1.0')
    parser.add_argument('--complete-through', type=int, required=True, help='Last year reviewed as complete')
    args = parser.parse_args()
    prepare(args.workbook, args.sha256, args.output, args.city, args.version, args.complete_through)
