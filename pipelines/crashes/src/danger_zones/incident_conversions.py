"""Small explicit conversions; source absence, null, blank and coded unknowns stay distinct."""
from __future__ import annotations

import math
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo


def missing(value, present=True):
    if not present:
        return 'not-supplied'
    if value is None:
        return 'null'
    if isinstance(value, str) and not value.strip():
        return 'blank'
    return None


def text(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError('invalid-text')
    return str(value).strip()


def number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError('invalid-number')
    try:
        result = float(value)
    except (ValueError, OverflowError):
        raise ValueError('invalid-number') from None
    if not math.isfinite(result):
        raise ValueError('nonfinite-number')
    return result


def integer(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError('invalid-integer')
    try:
        parsed = Decimal(str(value).strip())
        if not parsed.is_finite() or parsed != parsed.to_integral_value() or parsed < 0 or parsed > 2**63 - 1:
            raise ValueError('invalid-integer')
        return int(parsed)
    except InvalidOperation:
        raise ValueError('invalid-integer') from None


def temporal(value, epoch=False):
    if epoch:
        ms = number(value)
        try:
            dt = datetime.fromtimestamp(ms / 1000, timezone.utc)
        except (ValueError, OverflowError, OSError):
            raise ValueError('invalid-epoch') from None
        precision = 'millisecond'
    elif isinstance(value, datetime):
        dt = value
        precision = 'microsecond' if value.microsecond else 'second'
    elif isinstance(value, date):
        return {'date': value.isoformat(), 'time': None, 'offset': None, 'precision': 'date', 'zone': None}
    elif isinstance(value, str):
        s = value.strip()
        for fmt in ('%Y-%m-%d', '%m/%d/%Y'):
            try:
                d = datetime.strptime(s, fmt).date()
                return {'date': d.isoformat(), 'time': None, 'offset': None, 'precision': 'date', 'zone': None}
            except ValueError:
                pass
        dt = None
        # fromisoformat also accepts dates and abbreviated times; only allow explicit clocks here.
        if re.match(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}', s) and not s.endswith(('AM', 'PM')):
            try:
                dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
            except ValueError:
                pass
        if dt is None:
            for fmt in ('%m/%d/%Y %I:%M:%S %p', '%Y-%m-%d %I:%M:%S %p', '%m/%d/%Y %I:%M %p'):
                try:
                    dt = datetime.strptime(s, fmt)
                    break
                except ValueError:
                    pass
        if dt is None:
            raise ValueError('invalid-temporal')
        precision = 'microsecond' if dt.microsecond else ('second' if re.search(r':\d{2}:\d{2}',s) else 'minute')
    else:
        raise ValueError('invalid-temporal')
    offset = dt.strftime('%z') if dt.utcoffset() is not None else None
    return {'date': dt.date().isoformat(), 'time': dt.time().isoformat(),
            'offset': offset[:3] + ':' + offset[3:] if offset else None,
            'precision': precision, 'zone': 'UTC' if epoch else None}


def convert(value, rule, present=True):
    state = missing(value, present)
    if state:
        return {'value': None, 'state': state}
    if rule in {'identifier', 'text', 'category-code', 'category-label'}:
        result = text(value)
    elif rule == 'boolean':
        token = text(value)
        if token not in {'Y', 'N', 'TRUE', 'FALSE'}:
            raise ValueError('invalid-boolean')
        result = token in {'Y', 'TRUE'}
    elif rule == 'age':
        if str(value).strip() == '-99':
            return {'value': None, 'state': 'invalid-source-value'}
        result = integer(value)
        if result > 200:
            raise ValueError('age-range')
    elif rule == 'integer':
        result = integer(value)
    elif rule in {'number', 'latitude', 'longitude'}:
        result = number(value)
        if rule == 'latitude' and not -90 <= result <= 90 or rule == 'longitude' and not -180 <= result <= 180:
            raise ValueError('coordinate-range')
    elif rule in {'temporal', 'epoch-ms', 'date'}:
        result = temporal(value, rule == 'epoch-ms')
        if rule == 'date':
            if result['time'] is not None:
                raise ValueError('unexpected-clock')
            result = result['date']
    elif rule == 'point':
        if not isinstance(value, dict) or value.get('type') != 'Point' or len(value.get('coordinates', [])) != 2:
            raise ValueError('invalid-point')
        lng, lat = value['coordinates']
        result = {'longitude': convert(lng, 'longitude')['value'], 'latitude': convert(lat, 'latitude')['value'], 'crs': 'EPSG:4326'}
        if result['longitude'] is None or result['latitude'] is None:
            raise ValueError('incomplete-point')
    else:
        raise ValueError('unknown-rule')
    return {'value': result, 'state': 'reported'}


def category(code=None, label=None, state='reported'):
    if code is None and label is None:
        return {'value': None, 'state': state}
    # No global numeric sentinels: 89 is only Not Provided where its field-specific label says so.
    label_states = {'unknown': 'unknown', 'not provided': 'not-provided', 'invalid': 'invalid-source-value',
                    'not applicable': 'not-applicable', 'not applicable (legacy code)': 'not-applicable'}
    state = label_states.get((label or '').strip().lower(), 'reported')
    return {'value': {'code': code, 'label': label}, 'state': state}


def _date(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Observation timestamps must include a time zone")
    return result.astimezone(ZoneInfo("America/Denver"))


