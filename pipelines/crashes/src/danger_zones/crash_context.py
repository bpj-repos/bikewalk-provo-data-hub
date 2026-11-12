"""Persist source-reported darkness and dated school arrival/dismissal context."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
import math

from pyproj import Geod

from .config import HUB_ROOT
from .util import read_json, sha256_file

REGISTER = HUB_ROOT / 'data-definitions/crashes/school-context-v1.json'
GEOD = Geod(ellps='WGS84')
DARKNESS = {'dark-lighted': 'dark', 'dark-unlighted': 'dark',
            'dark-lighting-unknown': 'dark', 'daylight': 'daylight', 'dawn-dusk': 'dawn/dusk'}


def load_register(path=REGISTER):
    data = read_json(path)
    if data['schemaVersion'] != 1 or data['radiusMetres'] != 402 or data['windowMinutes'] != 30:
        raise ValueError('Unsupported school context policy')
    ids = [s['id'] for s in data['schools']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate school identity')
    calendars = data['calendars']
    for school in data['schools']:
        date.fromisoformat(school['opened'])
        if school.get('closed'):
            date.fromisoformat(school['closed'])
        for location in school['locations']:
            date.fromisoformat(location['from'])
            date.fromisoformat(location['through'])
            lon, lat = location['point']
            if not (-180 <= lon <= 180 and -90 <= lat <= 90) or not all(map(math.isfinite, [lon, lat])):
                raise ValueError('Invalid campus point')
            if location['from'] > location['through'] or not location['sources']:
                raise ValueError('Invalid campus effective dates or evidence')
        for schedule in school['schedules']:
            date.fromisoformat(schedule['from'])
            date.fromisoformat(schedule['through'])
            if schedule['calendar'] not in calendars or not schedule['sources']:
                raise ValueError('Missing schedule calendar or evidence')
            if schedule['from'] > schedule['through']:
                raise ValueError('Reversed bell schedule dates')
            if set(schedule['weekdays']) - {'0', '1', '2', '3', '4'}:
                raise ValueError('Unsupported school weekday')
            for day in schedule.get('overrides', {}):
                date.fromisoformat(day)
            for sessions in [*schedule['weekdays'].values(), *schedule.get('overrides', {}).values()]:
                if sessions is not None:
                    for session in sessions:
                        if len(session) != 2:
                            raise ValueError('Require start and dismissal pair')
                        for clock in session:
                            datetime.strptime(clock, '%H:%M')
                        if session[0] >= session[1]:
                            raise ValueError('Reversed school session')
    for calendar in calendars.values():
        for key in ['from', 'through']:
            date.fromisoformat(calendar[key])
        for start, end in calendar['closedRanges']:
            if date.fromisoformat(start) > date.fromisoformat(end):
                raise ValueError('Reversed calendar closure')
        for day in calendar.get('uncertainDates', []):
            date.fromisoformat(day)
    for school in data['schools']:
        for item in [school, *school['locations'], *school['schedules']]:
            if any(source not in data['sources'] for source in item['sources']):
                raise ValueError('Unknown school evidence reference')
    return data


def reported_darkness(observations):
    evidence = [{'observationId': o['observationId'], 'lighting': o['fields']['lighting']['value']}
                for o in observations if o['fields']['lighting']['value'] in DARKNESS]
    categories = {DARKNESS[e['lighting']] for e in evidence}
    return {'value': next(iter(categories)) if len(categories) == 1 else 'unknown',
            'reason': 'source-conflict' if len(categories) > 1 else None if categories else 'lighting-unavailable',
            'lighting': sorted({e['lighting'] for e in evidence}), 'evidence': evidence}


def school_at(point, occurred, register, radius):
    day = occurred.date().isoformat()
    matches, nearby, reasons = [], [], set()
    for school in register['schools']:
        if day < school['opened'] or school.get('closed') and not school.get('closureUncertain') and day > school['closed']:
            continue
        locations = [loc for loc in school['locations'] if loc['from'] <= day <= loc['through']]
        # Retain possible geography for historical diagnostics without dating a modern point backward.
        candidates = locations or school['locations']
        distances = [(GEOD.inv(*point, *loc['point'])[2], loc) for loc in candidates]
        if not distances:
            reasons.add('campus-location-unavailable')
            continue
        distance, location = min(distances, key=lambda v: v[0])
        if distance > radius + 1e-7:
            continue
        nearby.append({'schoolId': school['id'], 'distanceMetres': round(distance, 3),
                       'locationVerifiedForDate': bool(locations)})
        if not locations:
            reasons.add('campus-history-unavailable')
            continue
        schedules = [s for s in school['schedules'] if s['from'] <= day <= s['through']]
        if not schedules:
            reasons.add('bell-schedule-unavailable')
            continue
        schedule_matches = []
        for schedule in schedules:
            calendar = register['calendars'][schedule['calendar']]
            if not calendar['from'] <= day <= calendar['through']:
                reasons.add('instructional-calendar-unavailable')
                continue
            if occurred.weekday() >= 5 or any(start <= day <= end for start, end in calendar['closedRanges']):
                schedule_matches.append([])
                continue
            sessions = schedule.get('overrides', {}).get(day, schedule['weekdays'].get(str(occurred.weekday())))
            if day in calendar.get('uncertainDates', []) and day not in schedule.get('overrides', {}):
                sessions = None
            if sessions is None:
                reasons.add('exception-schedule-unavailable')
                continue
            phases = []
            for start, end in sessions:
                begin = datetime.fromisoformat(day + 'T' + start)
                finish = datetime.fromisoformat(day + 'T' + end)
                for phase, lower, upper in [('drop-off', begin - timedelta(minutes=30), begin),
                                             ('pickup', finish, finish + timedelta(minutes=30))]:
                    if lower <= occurred <= upper:
                        phases.append({'schoolId': school['id'], 'phase': phase,
                                       'distanceMetres': round(distance, 3), 'locationId': location['id'],
                                       'scheduleId': schedule['id'], 'windowStart': lower.isoformat(),
                                       'windowEnd': upper.isoformat()})
            schedule_matches.append(phases)
        phase_sets = {tuple(sorted(m['phase'] for m in items)) for items in schedule_matches}
        if len(phase_sets) > 1:
            reasons.add('bell-schedule-conflict')
        else:
            for items in schedule_matches:
                matches.extend(items)
    if not any(start <= day <= end for start, end in register['inventoryCoverage']):
        reasons.add('historical-inventory-incomplete')
    phases = {m['phase'] for m in matches}
    value = 'both' if len(phases) == 2 else next(iter(phases)) if phases else 'unknown' if reasons else 'no match'
    if 'bell-schedule-conflict' in reasons:
        value = 'unknown'
    return {'value': value, 'matches': matches, 'nearby': nearby, 'reasons': sorted(reasons)}


def school_context(group, observations, source_observations, register, radius=402):
    candidates, incomplete, missing = [], [], set()
    for observation in observations:
        t = observation['fields']['time']['value']
        if not t or t['basis'] != 'occurrence':
            continue
        original = source_observations[observation['observationId']]
        point = group.get('resolvedCrash', {}).get('coordinates') or original.get('coordinates')
        if not point:
            missing.add('crash-location-unavailable')
            continue
        if len(point) != 2 or not all(type(v) in {int, float} and math.isfinite(v) for v in point) or not (-180 <= point[0] <= 180 and -90 <= point[1] <= 90):
            raise ValueError('Invalid crash coordinates')
        if not t.get('clock') or t['precision'] not in {'second', 'minute', 'millisecond'}:
            missing.add('occurrence-clock-unavailable')
            outcome = school_at(point, datetime.fromisoformat(t['date']), register, radius)
            outcome.update(value='unknown', matches=[], reasons=['occurrence-clock-unavailable'],
                           observationId=observation['observationId'])
            incomplete.append(outcome)
            continue
        occurred = datetime.fromisoformat(t['date'] + 'T' + t['clock'])
        outcome = school_at(point, occurred, register, radius)
        outcome['observationId'] = observation['observationId']
        candidates.append(outcome)
    if not candidates and incomplete:
        candidates = incomplete
    if not candidates:
        return {'value': 'unknown', 'matches': [], 'nearby': [],
                'reasons': sorted(missing or {'occurrence-time-unavailable'}), 'evidence': []}
    values = {c['value'] for c in candidates}
    reasons = {r for c in candidates for r in c['reasons']}
    if len(values) > 1:
        reasons.add('crash-source-conflict')
    return {'value': next(iter(values)) if len(values) == 1 else 'unknown',
            'matches': [dict(m, observationId=c['observationId']) for c in candidates for m in c['matches']],
            'nearby': [dict(n, observationId=c['observationId']) for c in candidates for n in c['nearby']],
            'reasons': sorted(reasons), 'evidence': [c['observationId'] for c in candidates]}


def add_context(group, source_observations, register):
    observations = group['enrichment']['observations']
    group['enrichment']['context'] = {
        'schemaVersion': 1, 'registerVersion': register['version'], 'registerSha256': sha256_file(REGISTER),
        'darkness': reported_darkness(observations),
        'school': school_context(group, observations, source_observations, register)}


def coverage(collection, register):
    years = defaultdict(lambda: {'groups': 0, 'darkness': Counter(), 'school': Counter(),
                                 'unknownReasons': Counter(), 'darknessUnknownReasons': Counter(), 'spatialCandidates': 0,
                                 'possibleHistoricalSpatialCandidates': 0, 'radius201Metres': Counter()})
    from .incident_updates import flatten
    for group in collection['records']:
        observations = group['enrichment']['observations']
        occurrence_years = {o['fields']['time']['value']['year'] for o in observations
                            if o['fields']['time']['value'] and o['fields']['time']['value']['basis'] == 'occurrence'}
        year = str(next(iter(occurrence_years))) if len(occurrence_years) == 1 else 'unknown'
        row = years[year]
        context = group['enrichment']['context']
        row['groups'] += 1
        row['darkness'][context['darkness']['value']] += 1
        if context['darkness']['reason']:
            row['darknessUnknownReasons'][context['darkness']['reason']] += 1
        school = context['school']
        row['school'][school['value']] += 1
        if school['value'] == 'unknown':
            row['unknownReasons'].update(school['reasons'])
        row['spatialCandidates'] += any(n['locationVerifiedForDate'] for n in school['nearby'])
        row['possibleHistoricalSpatialCandidates'] += bool(school['nearby'])
        small = school_context(group, observations, flatten({'records': [group]}), register, 201)
        row['radius201Metres'][small['value']] += 1
        row['spatialCandidates201Metres'] = row.get('spatialCandidates201Metres', 0) + any(n['locationVerifiedForDate'] for n in small['nearby'])
        row['possibleHistoricalSpatialCandidates201Metres'] = row.get('possibleHistoricalSpatialCandidates201Metres', 0) + bool(small['nearby'])
    return {'denominator': 'distinct managed incident groups; occurrence year, with unknown when unavailable or conflicting',
            'registerVersion': register['version'], 'registerSha256': sha256_file(REGISTER),
            'years': dict(sorted(years.items()))}
