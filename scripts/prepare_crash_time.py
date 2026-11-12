"""Release local occurrence weekday and minute for the pinned Streets Watch crash IDs."""
import argparse
from collections import Counter
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
import tempfile
from zoneinfo import ZoneInfo

from scripts.prepare_crash_streets import BASE, compact, digest, pinned_details

ZONE = ZoneInfo('America/Denver')
DATASET = 'provo-crash-occurrence-time'


def local_value(raw):
    if re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}', raw):
        return datetime.strptime(raw, '%m/%d/%Y').date(), None
    if re.fullmatch(r'\d{4}-\d\d-\d\d', raw):
        return date.fromisoformat(raw), None
    if re.fullmatch(r'\d+/\d+/\d{4} \d+:\d\d:\d\d [AP]M', raw):
        stamp = datetime.strptime(raw, '%m/%d/%Y %I:%M:%S %p')
    elif re.fullmatch(r'\d{4}-\d\d-\d\d[T ]\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[+-]\d\d:\d\d)?', raw):
        stamp = datetime.fromisoformat(re.sub(r'\.([0-9]+)', lambda m: '.' + m[1][:6].ljust(6, '0'), raw).replace('Z', '+00:00'))
    else:
        raise ValueError('Unexpected occurrence date precision or format')
    if stamp.tzinfo:
        stamp = stamp.astimezone(ZONE)
    elif stamp.replace(tzinfo=ZONE).astimezone(timezone.utc).astimezone(ZONE).replace(tzinfo=None) != stamp:
        return stamp.date(), None  # Nonexistent spring-forward clock reading.
    return stamp.date(), stamp.hour * 60 + stamp.minute


def derive(records):
    evidence, days, minutes = [], set(), set()
    for i, record in enumerate(records):
        source = record['source']
        if source not in ('UDOT', 'Utah Crash Data Portal'):
            continue
        fields = []
        if source == 'Utah Crash Data Portal':
            # The snapshot formatter can expand a date-only cell to synthetic midnight.
            fields.extend((f['label'], f['value']) for s in record['sections'] for f in s['fields']
                          if f['label'] in ('Crash date', 'Crash dateand time'))
        elif record['dateMeaning'] == 'crash date/time':
            fields.append(('date', record['date']))
        for field, raw in fields:
            if raw in (None, '', 'Unavailable'):
                continue
            day, minute = local_value(raw)
            days.add(day)
            if minute is not None:
                minutes.add(minute)
            evidence.append(dict(recordIndex=i, source=source, field=field,
                                 localWeekday=day.isoweekday(), localMinuteOfDay=minute))
    if len(days) > 1:
        status = 'date-conflict'
    elif len(minutes) > 1:
        status = 'minute-conflict'
    elif minutes:
        status = 'complete'
    else:
        status = 'date-only' if days else 'no-occurrence-evidence'
    return dict(localWeekday=next(iter(days)).isoweekday() if len(days) == 1 else None,
                localMinuteOfDay=next(iter(minutes)) if status == 'complete' else None,
                status=status, evidence=evidence)


def build(snapshot, output):
    details = pinned_details(snapshot)
    rows = {key: derive(value['records']) for key, value in sorted(details.items())}
    coverage = dict(crashes=len(rows), statuses=dict(Counter(row['status'] for row in rows.values())),
                    weekday=sum(r['localWeekday'] is not None for r in rows.values()),
                    minute=sum(r['localMinuteOfDay'] is not None for r in rows.values()))
    manifest = dict(name=DATASET, version='1.0.0', title='Provo crash local occurrence time',
                    crashDataset=BASE, timezone='America/Denver', weekdayConvention='ISO Monday=1 through Sunday=7',
                    attribution='BikeWalk Provo, Utah Crash Data Portal and UDOT.',
                    reuse='Credit the named sources when reusing these derived fields.', resources=[])
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError('Use a fresh package directory')
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp)/'package'
        stage.mkdir()
        for name, value in [('occurrence', rows), ('coverage', coverage)]:
            raw = compact(value) + b'\n'
            path = name + '.json'
            (stage/path).write_bytes(raw)
            manifest['resources'].append(dict(name=name, path=path, bytes=len(raw), hash='sha256:'+digest(raw)))
        (stage/'datapackage.json').write_bytes(compact(manifest)+b'\n')
        stage.rename(output)
    return coverage


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.snapshot, args.output), indent=2))
