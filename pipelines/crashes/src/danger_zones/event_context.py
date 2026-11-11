"""Reproducible event travel context over source-qualified crash evidence."""
import csv
from datetime import date, datetime, timedelta
import json
from io import StringIO
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform

from .config import DEFINITIONS_ROOT
from .derived_incidents import cell, code
from .util import sha256_file, sha256_json

ROOT = DEFINITIONS_ROOT / 'events'
ZONE = ZoneInfo('America/Denver')
FILES = ('policy.json', 'coverage.json', 'locations.geojson')


def provenance(root=ROOT):
    registers = json.loads((root / 'policy.json').read_text())['registers']
    if not registers or any(Path(n).name != n or not n.endswith('.csv') for n in registers):
        raise ValueError('Register names must be CSV basenames')
    return {name: sha256_file(root / name) for name in (*FILES, *registers)}


def local_time(value):
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError('Event interval requires an explicit offset')
    return stamp.astimezone(ZONE)


class EventMatcher:
    def __init__(self, root=ROOT):
        self.inputs = provenance(root)
        self.policy = json.loads((root / 'policy.json').read_text())
        self.series = self.policy['series']
        self.version = sha256_json(self.inputs)
        self.project = Transformer.from_crs(4326, 26912, always_xy=True).transform
        self.events = {s: [] for s in self.series}
        identifiers = set()
        for filename in self.policy['registers']:
            for row in csv.DictReader(StringIO((root / filename).read_text())):
                if row['series'] not in self.series or row['event_id'] in identifiers:
                    raise ValueError('Unknown series or duplicate event ID')
                identifiers.add(row['event_id'])
                date.fromisoformat(row['event_date'])
                if row['status'] not in {'held', 'canceled', 'unverified'} or not row['source_url']:
                    raise ValueError('Invalid event status or missing source')
                for phase in ('arrival', 'departure'):
                    a, b = row[phase + '_start'], row[phase + '_end']
                    if bool(a) != bool(b):
                        raise ValueError('Incomplete event interval')
                    if a and local_time(a) > local_time(b):
                        raise ValueError('Reversed event interval')
                    if phase == 'departure' and a and local_time(b) - local_time(a) != timedelta(minutes=self.series[row['series']]['departure_minutes']):
                        raise ValueError('Departure window disagrees with policy')
                self.events[row['series']].append(row)
        self.features = []
        for f in json.loads((root / 'locations.geojson').read_text())['features']:
            p = f['properties']
            if not p['sources'] or not set(p['series']) <= self.series.keys():
                raise ValueError('Invalid location evidence')
            g = transform(self.project, shape(f['geometry']))
            if g.is_empty or not g.is_valid:
                raise ValueError('Invalid event geometry')
            self.features.append((p, g.buffer(p.get('buffer_metres', 0))))
        self.coverage = json.loads((root / 'coverage.json').read_text())

    def mechanism(self, rows):
        evidence = []
        for row in rows:
            if code(row, 'person.type') in {'3', '4', '5'} and code(row, 'person.nonmotorist_location') in self.policy['crossing_location_codes']:
                evidence.append({'kind': 'crossing', 'observation_id': row['observationId'],
                                 'fields': ['person.type', 'person.nonmotorist_location']})
            if code(row, 'person.type') == '1':
                for key in ('person.driver_contributing_first', 'person.driver_contributing_second'):
                    if code(row, key) == '14':
                        evidence.append({'kind': 'parking', 'observation_id': row['observationId'], 'fields': [key]})
            if code(row, 'vehicle.maneuver') in self.policy['parking_maneuver_codes']:
                evidence.append({'kind': 'parking', 'observation_id': row['observationId'], 'fields': ['vehicle.maneuver']})
        return evidence

    def observation(self, observation, rows):
        occurred = cell(rows[0], 'time.occurred_at')['value']
        point = observation.get('coordinates')
        if point is not None and (len(point) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in point)
                                  or not -180 <= point[0] <= 180 or not -90 <= point[1] <= 90):
            raise ValueError('Invalid crash coordinates')
        # Report-only and approximate police geocodes cannot establish event occurrence.
        if observation['sourceKey'] == 'provo-police-incidents':
            point = None
        projected = transform(self.project, Point(point)) if point is not None else None
        stamp = None
        day = None
        if occurred:
            day = date.fromisoformat(occurred['date'])
            if occurred['time']:
                raw = datetime.fromisoformat(occurred['date'] + 'T' + occurred['time'] + (occurred['offset'] or ''))
                stamp = raw.replace(tzinfo=ZONE) if raw.tzinfo is None else raw.astimezone(ZONE)
                day = stamp.date()
        if day is None:
            return {settings['field']: {'value': 'indeterminate', 'matches': [],
                    'reasons': ['missing-occurrence-date', 'missing-occurrence-clock'] +
                               (['missing-usable-location'] if projected is None else [])}
                    for settings in self.series.values()}
        mechanism = self.mechanism(rows)
        results = {}
        for series, settings in self.series.items():
            matches, uncertain, reasons = [], [], set()
            applicable = [(p, g) for p, g in self.features if series in p['series']]
            nearby = [(p, g) for p, g in applicable if projected is None or g.distance(projected) <= self.policy['coordinate_margin_metres']]
            if projected is not None and not nearby:
                results[settings['field']] = {'value': 'no_match', 'matches': [], 'reasons': ['outside-reviewed-access-area']}
                continue
            calendar_known = day is not None and self.policy['from'] <= day.isoformat() <= self.policy['through']
            candidates = [e for e in self.events[series] if day is None or -1 <= (day - date.fromisoformat(e['event_date'])).days <= 1]
            for event in candidates:
                if event['status'] == 'canceled':
                    continue
                phases = [phase for phase in ('arrival', 'departure') if stamp and event[phase + '_start'] and
                          local_time(event[phase + '_start']) <= stamp <= local_time(event[phase + '_end'])]
                event_day = date.fromisoformat(event['event_date'])
                if day and not stamp and day < event_day:
                    continue
                unresolved = not stamp or event['status'] != 'held'
                if stamp and not phases:
                    start = local_time(event['start_local']) if event['start_local'] else None
                    # Missing phases remain candidates only on the event day and following morning.
                    unresolved |= (not event['arrival_start'] and day == event_day and (start is None or stamp <= start))
                    unresolved |= (not event['departure_start'] and (start is None or stamp >= start) and
                                   (day == event_day or day == event_day + timedelta(days=1) and stamp.hour < 12))
                    if not unresolved:
                        continue
                if projected is None: reasons.add('missing-usable-location')
                if not stamp: reasons.add('missing-occurrence-clock')
                if unresolved: reasons.add('unresolved-event-window')
                if not mechanism: reasons.add('missing-crossing-or-parking-evidence')
                for p, geometry in nearby:
                    if day and not p['valid_from'] <= day.isoformat() <= p['valid_through']:
                        reasons.add('location-period-unverified'); continue
                    basis = [m for m in mechanism if m['kind'] in p['match_types']]
                    entry = {'event_id': event['event_id'], 'phases': phases, 'feature_id': p['id'], 'evidence': basis,
                             'source_observation_id': observation['id'], 'direct_corroboration': False}
                    interior = projected is not None and geometry.covers(projected.buffer(self.policy['coordinate_margin_metres']))
                    if phases and event['status'] == 'held' and basis and interior and p['review_status'] == 'reviewed':
                        matches.append(entry)
                    else:
                        if projected is not None and not interior: reasons.add('location-boundary-uncertain')
                        if p['review_status'] != 'reviewed': reasons.add('location-use-unverified')
                        uncertain.append(entry)
                if not nearby or not any(p['valid_from'] <= (day.isoformat() if day else '') <= p['valid_through'] for p, _ in nearby):
                    uncertain.append({'event_id': event['event_id'], 'source_observation_id': observation['id']})
            if not calendar_known: reasons.add('calendar-coverage-unknown')
            value = 'likely_match' if matches else 'indeterminate' if uncertain or not calendar_known else 'no_match'
            results[settings['field']] = {'value': value, 'matches': matches, 'candidates': uncertain, 'reasons': sorted(reasons)}
        return results

    def group(self, observations):
        output = {}
        for settings in self.series.values():
            key = settings['field']
            cells = [o['fields'][key] for o in observations]
            values = {c['value'] for c in cells}
            # Conflicting positive/negative observations need review rather than cross-source composition.
            value = ('indeterminate' if {'likely_match', 'no_match'} <= values else 'likely_match' if 'likely_match' in values
                     else 'no_match' if values == {'no_match'} else 'indeterminate')
            output[key] = {'value': value, 'matches': [m for c in cells for m in c['matches']],
                           'reasons': sorted({r for c in cells for r in c['reasons']} |
                                             ({'source-disagreement'} if {'likely_match', 'no_match'} <= values else set()))}
        return {'rules_version': self.policy['version'], 'inputs_sha256': self.version, 'inputs': self.inputs, 'fields': output}
