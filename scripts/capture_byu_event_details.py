"""Retain official game recaps and resolve explicitly reported football start/end times."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from scripts.capture_byu_events import COLUMNS, text


def run(captures, register, offline=False):
    rows = list(csv.DictReader(register.open()))
    def resolve(row):
        if row['status'] != 'held':
            return row
        schedule = (captures / f"{row['series']}-{row['season']}.html").read_text()
        day = row['event_date']
        # Locate the item by its dated time element, retaining the exact item's links.
        blocks = re.split(r'<div class="schedule-event-item(?: [^\"]*)?"[^>]*>', schedule)[1:]
        block = next(b for b in blocks if f'datetime="{day}' in b)
        recap = re.search(r'href="([^\"]+)"[^>]*aria-label="[^\"]*Recap', block)
        if not recap:
            return row
        url = urljoin(row['source_url'], recap[1])
        path = captures / f"{row['event_id']}-recap.html"
        receipt = path.with_suffix('.json')
        if path.exists():
            raw = path.read_bytes()
            if json.loads(receipt.read_text())['sha256'] != hashlib.sha256(raw).hexdigest():
                raise ValueError('Changed recap capture: ' + str(path))
        elif offline:
            raise ValueError('Missing recap: ' + str(path))
        else:
            response = requests.get(url, timeout=60); response.raise_for_status()
            raw = response.content; path.write_bytes(raw)
            receipt.write_text(json.dumps({'url': url, 'sha256': hashlib.sha256(raw).hexdigest()}, indent=2) + '\n')
        # HTML body only, excluding the serialized site-wide data and related stories.
        body = re.sub(r'<script\b[^>]*>.*?</script>', '', raw.decode('utf-8'), flags=re.S)
        plain = text(body)
        match = re.search(r'Kickoff time:\s*(\d{1,2}:\d{2}\s*[ap]\.?m\.?).{0,100}?End of Game:\s*(\d{1,2}:\d{2}\s*[ap]\.?m\.?)', plain, re.I)
        row['detail_url'] = url
        if match and row['series'] == 'byu_football':
            def clock(value):
                value = re.sub('[. ]', '', value).upper()
                return datetime.strptime(day + ' ' + value, '%Y-%m-%d %I:%M%p').replace(tzinfo=ZoneInfo('America/Denver'))
            start, end = map(clock, match.groups())
            if end < start: end += timedelta(days=1)
            if not timedelta(hours=1) < end - start < timedelta(hours=8):
                raise ValueError('Implausible game duration: ' + url)
            row.update(start_local=start.isoformat(), start_basis='actual-recap', end_local=end.isoformat(),
                       end_basis='actual-recap', arrival_start=(start-timedelta(minutes=120)).isoformat(),
                       arrival_end=(start+timedelta(minutes=15)).isoformat(), departure_start=end.isoformat(),
                       departure_end=(end+timedelta(minutes=90)).isoformat(),
                       notes='Official recap reports kickoff and end. Detail capture SHA-256 ' + hashlib.sha256(raw).hexdigest())
        return row
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(resolve, rows))
    with register.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS); writer.writeheader(); writer.writerows(rows)
    print(json.dumps({'events': len(rows), 'documented_departures': sum(bool(r['end_local']) for r in rows)}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('captures', type=Path); p.add_argument('register', type=Path); p.add_argument('--offline', action='store_true')
    a = p.parse_args(); run(a.captures, a.register, a.offline)
