"""Deterministic, offline police/portal candidate review. Never merges or publishes."""
import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
import csv
import json
import math
import re
from openpyxl import load_workbook
from pyproj import Geod
from .config import DEFAULT_DATA_ROOT, DEFAULT_PRIVATE_DATA_ROOT, PACKAGE_ROOT
from .field_inventory import REPO, source_tables, read_catalog
from .incident_conversions import temporal
from .police_portal_candidates import month_boundary, mode_relation, point, portal_rows, road_tokens
from .util import read_json, sha256_file, write_json

POLICY = PACKAGE_ROOT / 'catalog/incident-metadata/matching.json'
TIERS = ['exact-clock-address', 'exact-clock', 'same-day-address-at', 'near-day-tight-at',
         'window-address-at', 'window-spatial-at', 'contradictory-evidence']


def validate_policy(p):
    if set(p) != {'schemaVersion', 'nearDays', 'months', 'delayedLookbackDays', 'tightMetres', 'wideMetres', 'minimumAddressTokens', 'tiers'} or p['schemaVersion'] != 2 or p['tiers'] != TIERS:
        raise ValueError('Unsupported matching policy')
    for k in ['nearDays', 'months', 'delayedLookbackDays', 'minimumAddressTokens']:
        if type(p[k]) is not int or p[k] < 0:
            raise ValueError('Invalid policy integer: ' + k)
    for k in ['tightMetres', 'wideMetres']:
        if type(p[k]) not in (int, float) or not math.isfinite(p[k]) or p[k] <= 0:
            raise ValueError('Invalid distance: ' + k)
    if p['tightMetres'] > p['wideMetres'] or p['minimumAddressTokens'] < 3:
        raise ValueError('Invalid policy bounds')


def location_flags(local):
    g = local['geocoding']
    flags = []
    if not local['address']:
        flags.append('missing-address')
    if local['coordinates'] is None:
        flags.append('missing-coordinates')
    if g.get('status') != 'matched':
        flags.append('unaccepted-geocode')
    selected = (g.get('providerCandidates') or [{}])[0]
    if selected.get('properties', {}).get('kind') in {'street', 'virtual_street'}:
        flags.append('street-only-geocode-possible-input-or-validation-error')
    return flags


def intersection(value):
    # The portal also separates intersection legs with repeated whitespace.
    legs = re.split(r'\s*(?:&|\bAND\b|\bAT\b|/)\s*|\s{2,}', (value or '').strip().upper())
    if len(legs) != 2:
        return None
    aliases = {'NORTH':'N','SOUTH':'S','EAST':'E','WEST':'W','AVENUE':'AVE','AV':'AVE',
               'BOULEVARD':'BLVD','PARKWAY':'PKWY','ROAD':'RD','STREET':'ST','LANE':'LN','DRIVE':'DR'}
    normalized = [tuple(aliases.get(t,t) for t in re.findall(r'[A-Z]+|\d+', leg)) for leg in legs]
    return sorted(normalized) if all(normalized) else None


def address_agrees(left, right, minimum_tokens):
    streets = intersection(left)
    if streets and streets == intersection(right):
        return True
    tokens = road_tokens(left)
    def grid_pairs(value):
        text = (value or '').upper()
        for word, short in [('NORTH','N'), ('SOUTH','S'), ('EAST','E'), ('WEST','W')]:
            text = re.sub(r'\b' + word + r'\b', short, text)
        return set(re.findall(r'(\d+)\s*([NSEW])\b', text))
    return (len(tokens) >= minimum_tokens and any(t.isdigit() for t in tokens)
            and tokens <= road_tokens(right) and grid_pairs(left) <= grid_pairs(right))


def state_signature(row):
    values = {k:v for k,v in row.items() if k not in {'scopes', 'sourceRow', 'sourceConflict'}}
    for key in ['people', 'vehicles']:
        values[key] = sorted(values.get(key, []), key=lambda v: json.dumps(v, sort_keys=True))
    return json.dumps(values, sort_keys=True)


def previous_year(value):
    day = date.fromisoformat(value)
    try:
        return day.replace(year=day.year - 1).isoformat()
    except ValueError:
        return day.replace(year=day.year - 1, day=28).isoformat()


def review(police, crashes, policy):
    validate_policy(policy)
    for rows in [police, crashes]:
        if len({r['id'] for r in rows}) != len(rows):
            raise ValueError('Duplicate review identifiers')
        for row in rows:
            date.fromisoformat(row['date'])
            point(row['coordinates'])
    ordered = sorted(crashes, key=lambda c: (c['date'], c['id']))
    dates = [c['date'] for c in ordered]
    geod = Geod(ellps='WGS84')
    results = []
    for local in sorted(police, key=lambda p: p['id']):
        day = date.fromisoformat(local['date'])
        start, end = month_boundary(day, -policy['months']), month_boundary(day, policy['months'])
        if 'DELAY' in (local['notes'] or '').upper():
            from datetime import timedelta
            start = min(start, day - timedelta(days=policy['delayedLookbackDays']))
        flags = location_flags(local)
        unreliable = any(f in flags for f in ['unaccepted-geocode', 'street-only-geocode-possible-input-or-validation-error'])
        found = []
        for c in ordered[bisect_left(dates, start.isoformat()):bisect_right(dates, end.isoformat())]:
            delta = (date.fromisoformat(c['date']) - day).days
            exact = (delta == 0 and bool(re.fullmatch(r'\d\d:\d\d:\d\d(?:\.\d+)?',local['time'] or ''))
                     and local['time'] == c['time'])
            address = address_agrees(local['address'], c['road'], policy['minimumAddressTokens'])
            distance = geod.inv(*local['coordinates'], *c['coordinates'])[2] if local['coordinates'] and c['coordinates'] else None
            near = distance is not None and distance <= policy['wideMetres'] and not unreliable
            mode = mode_relation(local['mode'], c['modes'])
            at = bool(c['modes'])
            compatible = mode != 'mode-mismatch-or-missing'
            # Long delayed windows are address-only, not expanded spatial searches.
            in_month = month_boundary(day, -policy['months']) <= date.fromisoformat(c['date']) <= end
            conditions = [exact and address, exact and at, delta == 0 and address and compatible,
                          abs(delta) <= policy['nearDays'] and near and distance <= policy['tightMetres'] and compatible,
                          address and compatible, in_month and near and compatible, exact or address or in_month and near]
            tier = next((i for i, condition in enumerate(conditions) if condition), None)
            if tier is None:
                continue
            conflicts = []
            if not at: conflicts.append('no-active-transportation-evidence')
            elif not compatible: conflicts.append('mode-classification-disagreement')
            if c.get('sourceConflict'): conflicts.append('state-export-version-conflict')
            if delta != 0: conflicts.append('different-source-calendar-date')
            if local['time'] and c['time'] and not exact: conflicts.append('different-source-clock')
            found.append({'stateId': c['id'], 'tier': TIERS[tier], 'rank': tier,
                          'exactDayAndClock': exact, 'addressTokenAgreement': address,
                          'offsetDays': delta, 'distanceMetres': round(distance, 1) if distance is not None else None,
                          'distanceUsed': not unreliable, 'modeRelationship': mode, 'conflicts': conflicts,
                          'source': c, 'competingPoliceIds': []})
        found.sort(key=lambda c: (c['rank'], abs(c['offsetDays']), c['distanceMetres'] if c['distanceMetres'] is not None else math.inf, c['stateId']))
        results.append({'police': local, 'validationFlags': flags, 'manualConfirmationRequired': bool(flags), 'candidates': found})
    owners = defaultdict(set)
    for row in results:
        if row['candidates']:
            top = row['candidates'][0]['rank']
            for c in row['candidates']:
                if c['rank'] == top:
                    owners[c['stateId']].add(row['police']['id'])
    for row in results:
        found = row['candidates']
        for c in found:
            c['competingPoliceIds'] = sorted(owners[c['stateId']] - {row['police']['id']})
        top = [c for c in found if c['rank'] == found[0]['rank']] if found else []
        if not top:
            status = 'unresolved'
        elif top[0]['rank'] == 6:
            status = 'contradictory-evidence-only'
        elif len(top) != 1 or top[0]['competingPoliceIds']:
            status = 'ambiguous'
        elif (top[0]['rank'] <= 1 and 'state-export-version-conflict' not in top[0]['conflicts']
              and (top[0]['addressTokenAgreement'] or not row['police']['address'] or not top[0]['source']['road'])):
            status = 'distinctive-circumstantial-lead'
        elif top[0]['rank'] < 6:
            status = 'candidate-only'
        else:
            status = 'contradictory-evidence-only'
        row['status'] = status
        row['documentaryIdentityConfirmed'] = False
    return results


def load_portal(tables, scope):
    raw = {str(r['Crash_ID']): r for r in tables['portal.crashes']['rows']}
    vehicles = defaultdict(list)
    for r in tables['portal.vehicles']['rows']:
        vehicles[str(r['Crash_ID'])].append(r)
    rows = portal_rows(tables)
    for c in rows:
        parsed = temporal(raw[c['id']]['crashDateandTime'])
        c.update(time=parsed['time'] if parsed['precision'] in {'second','microsecond'} else None, city=raw[c['id']]['City_Geo'],
                 vehicles=vehicles[c['id']], scopes=[scope], sourceConflict=False)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New directory outside public app')
    parser.add_argument('--policy', type=Path, default=POLICY)
    parser.add_argument('--broader-workbook', type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve().is_relative_to((REPO / 'apps/maps').resolve()):
        parser.error('Require new output outside public app')
    policy = read_json(args.policy); validate_policy(policy)
    tables = source_tables(DEFAULT_DATA_ROOT, DEFAULT_PRIVATE_DATA_ROOT, with_locators=True)
    catalog = read_catalog()
    for name, table in tables.items():
        if any(set(r) != set(catalog['tables'][name]['fields']) for r in table['rows']):
            raise ValueError('Source column drift: ' + name)
    pointer_path = DEFAULT_PRIVATE_DATA_ROOT / 'datastores/combined-incidents.json'
    pointer = read_json(pointer_path); snapshot_path = Path(pointer['path'])
    if sha256_file(snapshot_path) != pointer['sha256']:
        raise ValueError('Snapshot checksum mismatch')
    police = []
    for group in read_json(snapshot_path)['records']:
        for o in group['observations']:
            if o['sourceKey'] != 'provo-police-incidents': continue
            m = o['metadata']
            if not any(v['snapshotId'] == t['snapshotId'] and v['workbookSha256'] == t['sha256']
                       for v in m['sourceVersions'] for name, t in tables.items() if name.startswith('police.')):
                raise ValueError('Police source provenance differs')
            police.append({'id': o['sourceRecordId'], 'date': m['observedAt']['localDate'], 'time': m['observedAt']['localTime'],
                           'address': m['location']['addressPartRaw'], 'notes': m['location'].get('noteRaw'),
                           'mode': o['mode'], 'coordinates': o['coordinates'], 'geocoding': m['location']['geocoding'],
                           'sourceRows': [{k:v[k] for k in ['snapshotId','sourceSheet','sourceRow','workbookSha256']} for v in m['sourceVersions']]})
    crashes = {c['id']: c for c in load_portal(tables, 'retained-city')}
    broader_hash = None
    broader_filters = None
    version_conflicts = []
    if args.broader_workbook:
        broader_hash = sha256_file(args.broader_workbook)
        extra = {}
        workbook = load_workbook(args.broader_workbook, read_only=True, data_only=True)
        try:
            for sheet in ['Crashes', 'Persons', 'Vehicles', 'Rollups', 'Filters']:
                ws = workbook[sheet]; ws.reset_dimensions(); values = iter(ws.values); headers = next(values)
                key = 'portal.' + sheet.lower()
                if len(set(headers)) != len(headers) or set(headers) != set(catalog['tables'][key]['fields']):
                    raise ValueError('Broader workbook column drift: ' + sheet)
                extra[key] = {'rows': [dict(zip(headers, r)) for r in values]}
        finally: workbook.close()
        if sha256_file(args.broader_workbook) != broader_hash: raise ValueError('Workbook changed during inspection')
        broader_filters = extra['portal.filters']['rows']
        for c in load_portal(extra, 'retained-broader'):
            if c['id'] in crashes:
                prior = crashes[c['id']]
                if state_signature(prior) != state_signature(c):
                    prior['sourceConflict'] = True
                    version_conflicts.append({'stateId': c['id'], 'cityVersion': dict(prior), 'broaderVersion': c})
                prior['scopes'].extend(c['scopes'])
            else: crashes[c['id']] = c
    results = review(police, list(crashes.values()), policy)
    covered_years = {c['date'][:4] for c in crashes.values()}
    controls = [dict(p, date=previous_year(p['date'])) for p in police if previous_year(p['date'])[:4] in covered_years]
    control_results = review(controls, list(crashes.values()), policy)
    report = {'negativeControl': {'method': 'one calendar year earlier; February 29 clamps to February 28; clock and location unchanged',
                                  'limits': 'Year presence does not establish equal coverage or a calibrated false-match probability.',
                                  'statuses': dict(Counter(r['status'] for r in control_results)),
                                  'records': [{'policeId': r['police']['id'], 'controlDate': r['police']['date'], 'status': r['status'],
                                               'topStateIds': [c['stateId'] for c in r['candidates'] if c['rank'] == r['candidates'][0]['rank']]} for r in control_results]},
              'schemaVersion': 1, 'policy': policy, 'policySha256': sha256_file(args.policy),
              'scriptSha256': sha256_file(Path(__file__)), 'combinedSnapshotSha256': pointer['sha256'],
              'sourceHashes': {name:t['sha256'] for name,t in tables.items()}, 'broaderWorkbookSha256': broader_hash,
              'broaderFilters': broader_filters, 'stateExportConflicts': version_conflicts,
              'summary': {'policeRecords': len(police), 'stateRecords': len(crashes), 'statuses': dict(Counter(r['status'] for r in results)),
                          'recordsWithValidationFlags': sum(bool(r['validationFlags']) for r in results)}, 'records': results,
              'limits': ['Candidates only; no automatic identity confirmation, merges or publication.',
                         'Address tokens are evidence, not authoritative address equivalence.',
                         'No shared agency identifier is supplied by these police workbooks.',
                         'Geocode errors are possible input/validation errors requiring manual confirmation.',
                         'Source clocks are compared literally; no inferred timezone or report-date correction.']}
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / 'report.json', report)
    with (args.output / 'cases.csv').open('w', newline='') as f:
        writer = csv.writer(f); writer.writerow(['policeCase','status','topTier','topStateIds','validationFlags','manualConfirmationRequired'])
        for r in results:
            top = r['candidates'][0]['rank'] if r['candidates'] else None
            writer.writerow([r['police']['id'], r['status'], TIERS[top] if top is not None else '',
                             ';'.join(c['stateId'] for c in r['candidates'] if c['rank'] == top),
                             ';'.join(r['validationFlags']), r['manualConfirmationRequired']])
    print(json.dumps(report['summary']))


if __name__ == '__main__': main()
