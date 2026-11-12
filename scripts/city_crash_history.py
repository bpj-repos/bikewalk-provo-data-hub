"""Report city crash history from verified source captures and update the annual crash guide."""
import argparse
import json
from pathlib import Path

from scripts.city_cli import run
from danger_zones.city_history import portal_report, udot_summary
from scripts.register_city_crashes import ROOT, COVERAGE, GUIDE, encoded, city_guide, city_write_lock, replace_text

def report(args):
    udot = udot_summary(args.udot, args.cities)
    portal = {city: portal_report(args.portal, city) for city in args.cities}
    with city_write_lock(ROOT):
        previous = json.loads((ROOT / COVERAGE).read_bytes()) if (ROOT / COVERAGE).exists() else []
        rows = {row['city']: row for row in previous}
        for city in args.cities:
            stats = portal[city]
            values = {k: stats[k] for k in ('count', 'years', 'latest')}
            old = rows.get(city, {})
            if old.get('dataset') and old.get('portal') != values:
                raise ValueError('Register the updated city package before refreshing its coverage')
            rows[city] = {**old, 'city': city, 'portal': values,
                          'udot': dict(zip(('count', 'years', 'latest'), udot[city]))}
            rows[city]['udot']['latest'] = str(udot[city][2]) if udot[city][2] else None
        rows = list(rows.values())
        if args.write:
            markdown = city_guide(rows, ROOT)
            replace_text(ROOT / COVERAGE, encoded(rows))
            replace_text(ROOT / GUIDE, markdown)
        else:
            print(encoded(rows), end='')
        return dict(inputs=dict(portal=str(args.portal.resolve()), udot=str(args.udot.resolve()),
                                cities=args.cities),
                    outputs=dict(coverage=str((ROOT / COVERAGE).resolve()) if args.write else None,
                                 guide=str((ROOT / GUIDE).resolve()) if args.write else None),
                    coverage=dict(cities=[row for row in rows if row['city'] in args.cities]),
                    excluded={}, nextCommand=None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('portal', type=Path)
    parser.add_argument('udot', type=Path)
    parser.add_argument('cities', nargs='+')
    parser.add_argument('--write', action='store_true', help='Update tracked city coverage and annual crash guide')
    run(parser, report)
