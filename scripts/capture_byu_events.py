"""Capture or replay BYU season schedules into a source-qualified event register."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import date, datetime, timedelta
import hashlib
from html import unescape
import json
from pathlib import Path
import re
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests

ZONE = ZoneInfo('America/Denver')
COLUMNS = ['event_id', 'series', 'season', 'event_date', 'name', 'venue', 'status',
           'start_local', 'start_basis', 'end_local', 'end_basis', 'arrival_start',
           'arrival_end', 'departure_start', 'departure_end', 'source_url', 'source_sha256',
           'detail_url', 'notes']


def text(html):
    return ' '.join(unescape(re.sub('<[^>]+>', ' ', html)).split())


def parse_schedule(html, series, season, url, digest, through):
    blocks = re.split(r'<div class="schedule-event-item(?: [^\"]*)?"[^>]*>', html)[1:]
    if not blocks:
        raise ValueError('No schedule items: ' + url)
    rows = []
    for block in blocks:
        # Stop before the next item rather than mixing venue/time/link evidence.
        block = block.split('scheduleAfterScheduledEvent', 1)[0]
        def field(name):
            match = re.search(r'class="' + name + r'[^\"]*"[^>]*>(.*?)</(?:span|strong|div|time)>', block, re.S)
            return text(match[1]) if match else ''
        venue = field('schedule-event-location schedule-event-item__location-venue')
        place = field('schedule-event-location schedule-event-item__location-place')
        expected = 'LaVell Edwards Stadium' if series == 'byu_football' else 'Marriott Center'
        if expected.casefold() not in venue.casefold() and not (expected.casefold() in place.casefold()):
            continue
        times = re.findall(r'<time datetime="([^\"]+)"', block)
        if not times:
            raise ValueError('Home event missing date: ' + url)
        start = datetime.fromisoformat(times[0]).astimezone(ZONE)
        day = start.date()
        if not date(2010, 1, 1) <= day <= through:
            continue
        clock = field('schedule-event-date__clock')
        known_time = bool(re.search(r'\d+:\d+\s*[AP]M', clock))
        name = field('schedule-event-item__opponent-name')
        if not name:
            raise ValueError('Home event missing opponent: ' + url)
        result_match = re.search(r'class="schedule-event-item-result__label"[^>]*>(.*?)</div>', block, re.S)
        result = text(result_match[1]) if result_match else ''
        canceled = bool(re.search(r'cancel|postpon', text(block), re.I))
        status = 'canceled' if canceled else 'held' if re.search(r'\d+\s*-\s*\d+', result) else 'unverified'
        detail = re.search(r'href="([^\"]+)"[^>]*aria-label="[^\"]*Box Score', block)
        rows.append(dict(zip(COLUMNS, [''] * len(COLUMNS))) | {
            'event_id': f'{series}-{day.isoformat()}', 'series': series, 'season': season,
            'event_date': day.isoformat(), 'name': 'BYU vs. ' + name, 'venue': expected,
            'status': status, 'start_local': start.isoformat() if known_time else '',
            'start_basis': 'published-schedule' if known_time else 'unresolved',
            'arrival_start': (start - timedelta(minutes=120 if series == 'byu_football' else 60)).isoformat() if known_time and status == 'held' else '',
            'arrival_end': (start + timedelta(minutes=15 if series == 'byu_football' else 10)).isoformat() if known_time and status == 'held' else '',
            'end_basis': 'unresolved', 'source_url': url, 'source_sha256': digest,
            'detail_url': urljoin(url, detail[1]) if detail else '',
            'notes': 'Departure requires documented end or actual start plus elapsed duration.'})
    return rows, len(blocks)


def run(captures, output, through, offline=False):
    captures.mkdir(parents=True, exist_ok=True)
    tasks = [('byu_football', str(y), 'football') for y in range(2010, through.year + 1)]
    tasks += [('byu_mens_basketball', f'{y}-{y+1}', 'mens-basketball') for y in range(2009, through.year + 1)]
    def capture(task):
        series, season, sport = task
        url = f'https://byucougars.com/sports/{sport}/schedule/season/{season}'
        path = captures / f'{series}-{season}.html'
        receipt = path.with_suffix('.json')
        if path.exists():
            raw = path.read_bytes()
            if not receipt.exists() or json.loads(receipt.read_text())['sha256'] != hashlib.sha256(raw).hexdigest():
                raise ValueError('Capture checksum mismatch: ' + str(path))
        elif offline:
            raise ValueError('Missing offline capture: ' + str(path))
        else:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            raw = response.content
            path.write_bytes(raw)
            receipt.write_text(json.dumps({'url': url, 'sha256': hashlib.sha256(raw).hexdigest(),
                                          'retrieved_at': datetime.now(ZONE).isoformat()}, indent=2) + '\n')
        digest = hashlib.sha256(raw).hexdigest()
        rows, total = parse_schedule(raw.decode('utf-8'), series, season, url, digest, through)
        return rows, {'series': series, 'season': season, 'url': url, 'sha256': digest,
                      'schedule_items': total, 'home_events': len(rows),
                      'coverage': 'schedule-captured', 'through': through.isoformat()}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(capture, tasks))
    rows = sorted([row for result, _ in results for row in result], key=lambda r: (r['event_date'], r['series']))
    if len({r['event_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate event identity needs review')
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'athletics.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader(); writer.writerows(rows)
    (output / 'coverage.json').write_text(json.dumps([c for _, c in results], indent=2) + '\n')
    print(json.dumps({'events': len(rows), 'season_captures': len(results), 'through': str(through)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('captures', type=Path, help='Private immutable HTML capture directory')
    parser.add_argument('output', type=Path, help='Structured definition directory')
    parser.add_argument('--through', type=date.fromisoformat, required=True)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    run(args.captures, args.output, args.through, args.offline)


if __name__ == '__main__':
    main()
