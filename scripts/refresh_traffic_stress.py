"""Acquire citywide inputs, cache heavy processing and prepare a reviewed-release candidate."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sys

from pipelines.traffic_stress import refresh
from scripts.build_catalog import checked_package
from scripts.prepare_traffic_stress import prepare, DATASET

ROOT = Path(__file__).resolve().parents[1]


def baseline():
    ledger = json.loads((ROOT / 'releases/release-ledger.json').read_bytes())
    withdrawn = {(r['dataset'], r['version']) for r in ledger['withdrawn']}
    entry = next(e for e in reversed(ledger['approved']) if e['dataset'] == DATASET and
                 (e['dataset'], e['version']) not in withdrawn)
    files = checked_package(ROOT / 'releases/datasets' / DATASET / entry['version'], entry)
    return entry, files


def execute(previous_receipt, output, version, cache, resume=False, refresh_intersections=False):
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.with_name(output.name + '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        owns_run = resume or not output.exists()
        try:
            return _execute(previous_receipt, output, version, cache, resume, refresh_intersections)
        except Exception as error:
            if owns_run and output.is_dir():
                refresh.write(output / 'failure.json', dict(error=str(error),
                    acquisitionCheckpoint=(output / 'acquisition.json').exists(),
                    recovery='Use --resume after completed acquisition. For incomplete acquisition or changed tools, keep the failed run and use a new output directory.'))
            raise


def _execute(previous_receipt, output, version, cache, resume=False, refresh_intersections=False):
    if not re.fullmatch(r'1\.\d+\.\d+', version):
        raise ValueError('Expected compatible 1.x.y candidate version')
    entry, previous_files = baseline()
    if tuple(map(int, version.split('.'))) <= tuple(map(int, entry['version'].split('.'))):
        raise ValueError('Candidate must follow the current approved version')
    paths = [Path(__file__), *(ROOT / 'pipelines/traffic_stress').glob('*.py'),
             ROOT / 'data-definitions' / DATASET / 'method.md', ROOT / 'data-definitions' / DATASET / 'dictionary.json']
    paths += [ROOT / 'scripts' / name for name in ('model_bicycle_stress.py', 'capture_traffic_stress.py',
              'refresh_route_sources.py', 'prepare_traffic_stress.py', 'route_stress.py', 'build_demo_counts.py')]
    tools = {str(p.relative_to(ROOT)): refresh.sha(p) for p in sorted(paths)}
    inputs = output / 'inputs'
    state_path = output / 'acquisition.json'
    if resume:
        state = json.loads(state_path.read_bytes())
        if state['baseline'] != entry or state['tools'] != tools or state['version'] != version:
            raise ValueError('Baseline, tools or version changed; start a new run')
        record = state['receipt']
        for source in record['sources'].values():
            refresh.checked(inputs / source['path'], source['sha256'])
    else:
        output.mkdir(parents=True, exist_ok=False)
        inputs.mkdir()
        record = refresh.acquire(previous_receipt.resolve(), inputs.resolve(), refresh_intersections)
        refresh.write(state_path, dict(baseline=entry, tools=tools, version=version, receipt=record))
    record = refresh.process(record, inputs.resolve(), cache.resolve())
    processing = dict(record['provenance']['processing'])
    record['provenance']['processing'] = {k: v for k, v in processing.items() if k.endswith('Recipe')}
    record['provenance']['refreshTools'] = tools
    receipt_bytes = refresh.encoded(record)
    if (inputs / 'receipt.json').exists() and (inputs / 'receipt.json').read_bytes() != receipt_bytes:
        raise ValueError('Resume would change the frozen source receipt; start a new run')
    (inputs / 'receipt.json').write_bytes(receipt_bytes)
    package = output / 'package'
    if package.exists():
        manifest = json.loads((package / 'datapackage.json').read_bytes())
        candidate_pin = refresh.sha(package / 'datapackage.json')
        checked_package(package, dict(dataset=DATASET, version=version, sha256=candidate_pin))
        sources = json.loads((package / 'sources.json').read_bytes())
        # Cache-hit diagnostics differ on resume; input identities and processing recipes must agree.
        if sources['receiptSha256'] != refresh.sha(inputs / 'receipt.json'):
            raise ValueError('Candidate belongs to a different receipt')
        if sources['sources'] != {k: {a: b for a, b in v.items() if a != 'path'} for k, v in record['sources'].items()}:
            raise ValueError('Existing candidate uses different inputs; start a new run')
    else:
        prepare(inputs / 'receipt.json', package, version)
        candidate_pin = refresh.sha(package / 'datapackage.json')
    review = refresh.compare(previous_files, package)
    review.update(inputs=record['sources'], baseline=entry, version=version, manifestSha256=candidate_pin,
                  dependencyStatus=record['provenance']['acquisition'], processing=processing,
                  checks=dict(inputHashes=True, candidateHashes=True), blockers=[],
                  nextCommand=[sys.executable, '-B', '-m', 'scripts.prepare_traffic_stress',
                               str(inputs / 'receipt.json'), str(output / 'independent-rebuild'), '--version', version],
                  publication='Private candidate. Compare independent rebuild, review changes and use the existing release/adoption runbook.')
    refresh.write(output / 'review.json', review)
    return dict(version=version, manifestSha256=candidate_pin, review=str(output / 'review.json'),
                modelCacheReused=review['processing']['modelCacheReused'],
                networkCacheReused=review['processing']['networkCacheReused'], nextCommand=review['nextCommand'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--previous-receipt', required=True, type=Path)
    parser.add_argument('--version', required=True)
    parser.add_argument('--cache', type=Path, default=ROOT / 'private/cache/traffic-stress')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--refresh-intersections', action='store_true')
    args = parser.parse_args()
    print(json.dumps(execute(**vars(args)), indent=2))
