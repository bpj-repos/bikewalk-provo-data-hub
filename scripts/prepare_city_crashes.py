"""Prepare one Utah city's annual active transportation crash package from one portal XLSX."""
import argparse
from datetime import date
from pathlib import Path
import re

from danger_zones.city_history import read_city_workbook
from danger_zones.research_reports import annual_report
from scripts.prepare_crash_releases import AT, write_package
from scripts.city_cli import run, package_result
from danger_zones.util import sha256_file


def prepare(workbook, digest, output, city, version, complete):
    observations, start, end, years, selection = read_city_workbook(workbook, digest, city)
    last_full_year = end.year if end == date(end.year, 12, 31) else end.year - 1
    if complete > last_full_year:
        raise ValueError('Complete-through exceeds the workbook’s last full year')
    report = annual_report(observations, complete, city, years)
    for row in report['annual']:
        year = row['year']
        row['complete'] = row['complete'] and start <= date(year, 1, 1) and date(year, 12, 31) <= end
    slug = re.sub(r'[^a-z]+', '-', city.lower())
    package = write_package(report, [selection], output, version, complete, city=city, dataset=f'{slug}-{AT}')

    return package_result(package, sha256_file(package / 'datapackage.json'),
                          inputs={"workbook": str(workbook.resolve()), "sha256": digest, "city": city},
                          coverage={"from": str(start), "to": str(end), "years": years,
                                    "completeThrough": complete,
                                    "crashes": sum(r['total'] for r in report['annual'])},
                          excluded={"outsidePopulation": len(observations) - sum(r['total'] for r in report['annual'])},
                          next_command=["python", "-m", "scripts.register_city_crashes", str(package),
                                        sha256_file(package / 'datapackage.json'), "--json"])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workbook', type=Path)
    parser.add_argument('sha256')
    parser.add_argument('output', type=Path)
    parser.add_argument('--city', required=True)
    parser.add_argument('--version', default='1.1.0')
    parser.add_argument('--complete-through', type=int, required=True, help='Last year reviewed as complete')
    run(parser, lambda args: prepare(args.workbook, args.sha256, args.output, args.city, args.version, args.complete_through))
