"""Register a reviewed city annual package, generate its ZIP and refresh the annual crash guide table."""
import argparse
from contextlib import contextmanager
import csv
import io
import hashlib
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from scripts.city_cli import run, package_result
from scripts.build_catalog import checked_package, download_zip
from scripts.prepare_crash_releases import ROOT, AT, city_has_recent_csv, recent_csv

COVERAGE = Path('data-definitions/crashes/city-coverage.json')
GUIDE = Path('docs/datasets/annual-at-crash-aggregates.md')
START = '<!-- city-crash-data:start -->'
END = '<!-- city-crash-data:end -->'


def encoded(data):
    return json.dumps(data, indent=2, ensure_ascii=False) + '\n'


def city_guide(rows, root=ROOT):
    ledger = json.loads((root / 'releases/release-ledger.json').read_bytes())
    withdrawn = {(entry['dataset'], entry['version']) for entry in ledger['withdrawn']}
    available = {(entry['dataset'], entry['version']) for entry in ledger.get('publicCityReleases', [])} - withdrawn
    # Provo's original public product predates the city-prefixed package IDs.
    provo = next((entry for entry in reversed(ledger['approved'])
                  if entry['dataset'] == AT and (AT, entry['version']) not in withdrawn
                  and AT not in ledger.get('retired', [])), None)
    lines = [
        START,
        '| City | Portal crashes | Portal years | Latest portal crash | UDOT crashes | UDOT years | Latest UDOT crash | Dataset |',
        '|---|---:|---|---|---:|---|---|---|',
    ]
    for row in sorted(rows, key=lambda r: (-r.get('portal', {}).get('count', 0), r['city'])):
        cells = [row['city']]
        for source in ('portal', 'udot'):
            values = row.get(source, {})
            cells.extend(f'{values[k]:,}' if k == 'count' and values.get(k) is not None
                         else str(values.get(k) or '—') for k in ('count', 'years', 'latest'))
        dataset = row.get('dataset')
        if row['city'] == 'Provo' and provo:
            version = provo['version']
            link = f'https://bikewalk-provo-data-hub.vercel.app/downloads/{AT}/{version}/{AT}-{version}.zip'
        else:
            link = f"../../{dataset['zip']}" if dataset and (dataset['id'], dataset['version']) in available else None
        cells.append(f'[Generated ZIP]({link})' if link else 'Not yet available')
        lines.append('| ' + ' | '.join(cells) + ' |')
    lines.append(END)
    path = root / GUIDE
    text = path.read_text()
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError('Expected one annual crash guide city table')
    before, rest = text.split(START)
    _, after = rest.split(END)
    return before + '\n'.join(lines) + after


@contextmanager
def city_write_lock(root=ROOT):
    lock = root / 'private/city-release.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError:
        raise ValueError('Another city update holds private/city-release.lock') from None
    try:
        yield
    finally:
        lock.rmdir()


def replace_text(path, text):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(text)
    temporary.replace(path)


def register(directory, digest, root=ROOT):
    with city_write_lock(root):
        return register_locked(directory, digest, root)


def register_locked(directory, digest, root=ROOT):
    manifest = json.loads((directory / 'datapackage.json').read_bytes())
    dataset, version = manifest['name'], manifest['version']
    if (not re.fullmatch(r'[a-z]+(?:-[a-z]+)*-' + AT, dataset)
            or not re.fullmatch(r'\d+\.\d+\.\d+', version)):
        raise ValueError('Expected a city annual crash package')
    city = manifest['title'].removesuffix(' active transportation crashes by year')
    expected = re.sub(r'[^a-z]+', '-', city.lower()) + '-' + AT
    if expected != dataset:
        raise ValueError('City title and dataset identity differ')
    entry = dict(dataset=dataset, version=version, sha256=digest)
    files = checked_package(directory, entry)
    reader = csv.DictReader(io.StringIO(files['annual.csv'].decode()))
    if reader.fieldnames != ['year', 'total', 'bike', 'ped', 'other', 'complete_year']:
        raise ValueError('Unexpected public annual fields')
    annual = list(reader)
    years = [int(r['year']) for r in annual]
    if not years or sorted(set(years)) != years:
        raise ValueError('Expected distinct ascending annual rows')
    expected_files = {'datapackage.json', 'annual.csv', 'dictionary.json', 'method.txt'}
    if city_has_recent_csv(version, years):
        expected_files.add('annual-from-2018.csv')
        if files.get('annual-from-2018.csv') != recent_csv(files['annual.csv']):
            raise ValueError('Expected exact 2018-onward slice of annual.csv')
    if set(files) != expected_files:
        raise ValueError('Unexpected city package resources')
    for row in annual:
        modes = [int(row[k]) for k in ('bike', 'ped', 'other')]
        total = int(row['total'])
        if min(modes) < 0 or not max(modes) <= total <= sum(modes) or row['complete_year'] not in ('True', 'False'):
            raise ValueError('Invalid annual crash values')
    relative = Path('releases/datasets') / dataset / version
    zip_path = relative / f'{dataset}-{version}.zip'
    prefix = f'datasets/{dataset}/{version}/'
    archive = download_zip({prefix + name: data for name, data in files.items()},
                           {'manifest': '/' + prefix + 'datapackage.json'})
    target = root / relative
    if target.exists():
        if checked_package(target, entry) != files:
            raise ValueError('Published city package differs')
        if (root / zip_path).exists() and (root / zip_path).read_bytes() != archive:
            raise ValueError('Published city ZIP differs')
    ledger_path = root / 'releases/release-ledger.json'
    ledger = json.loads(ledger_path.read_bytes())
    if any(e['dataset'] == dataset and e['version'] == version for e in ledger['withdrawn']):
        raise ValueError('City package has been withdrawn')
    existing = [e for e in ledger['approved'] if (e['dataset'], e['version']) == (dataset, version)]
    current = [e for e in ledger['approved'] if e['dataset'] == dataset]
    if existing and current[-1] != entry:
        raise ValueError('An older package cannot replace current city coverage')
    if existing and existing != [entry]:
        raise ValueError('Cannot replace an approved pin')
    if not existing:
        ledger['approved'].append(entry)
    rows = json.loads((root / COVERAGE).read_bytes())
    row = next((r for r in rows if r['city'] == city), None)
    if row is None:
        row = {'city': city}
        rows.append(row)
    count = sum(int(r['total']) for r in annual)
    portal = dict(count=count, years=f'{years[0]}–{years[-1]}', latest=manifest['latestEvent'])
    row.update(portal=portal, dataset=dict(id=dataset, version=version, sha256=digest, zip=str(zip_path)))
    updated_guide = city_guide(rows, root)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        with TemporaryDirectory(dir=target.parent) as tmp:
            stage = Path(tmp) / 'package'
            stage.mkdir()
            for name, data in files.items():
                (stage / name).write_bytes(data)
            (stage / zip_path.name).write_bytes(archive)
            stage.rename(target)
    else:
        (root / zip_path).write_bytes(archive)
    replace_text(ledger_path, encoded(ledger))
    replace_text(root / COVERAGE, encoded(rows))
    replace_text(root / GUIDE, updated_guide)
    print(f'Registered {city} {version}; ZIP {zip_path}')
    result = package_result(target, digest,
                            inputs=dict(package=str(directory.resolve()), sha256=digest),
                            coverage=dict(city=city, years=years, crashes=count))
    result['outputs'].update(zip=str((root / zip_path).resolve()),
                              zipSha256=hashlib.sha256(archive).hexdigest())
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('manifest_sha256')
    run(parser, lambda args: register(args.package, args.manifest_sha256))
