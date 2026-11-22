"""Update the active private crash workspace using verified historical path mappings."""
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import subprocess
import sys

HUB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HUB / 'pipelines/crashes/src'))
from danger_zones.update_incidents import main, parse_args
from danger_zones.util import read_json, sha256_file


def producer_preflight(private_root):
    pointer = read_json(private_root/'datastores/combined-incidents.json')
    path = Path(pointer['path'])
    if sha256_file(path) != pointer['sha256']:
        raise ValueError('Active snapshot checksum mismatch')
    producer = read_json(path).get('producerCommit')
    if producer and subprocess.run(['git', 'merge-base', '--is-ancestor', producer, 'HEAD'],
                                   cwd=HUB, capture_output=True).returncode:
        raise ValueError('This checkout predates or diverges from the active crash producer. Use updated main; use danger_zones.update_incidents for isolated recovery.')


def run():
    if any(arg.split('=')[0] in {'--private-data-root', '--data-root', '--restore-path', '--restore-root'} for arg in sys.argv[1:]):
        sys.exit('Use danger_zones.update_incidents directly for an isolated recovery drill.')
    parsed = parse_args()
    os.umask(0o077)
    result = {'schemaVersion': 1, 'status': 'failed', 'stages': {}}
    stage = 'preflight'
    try:
        with redirect_stdout(sys.stderr):
            producer_preflight(parsed[1])
            result['stages'][stage] = {'status': 'passed'}
            if not parsed[0].rollback and not parsed[0].offline:
                stage = 'roadCapture'
                from scripts.crash_road_segments import capture_for_update
                capture_for_update()
                result['stages'][stage] = {'status': 'captured'}
            stage = 'intake'
            intake = main(parsed, emit=False)
            result['stages'][stage] = intake
            result['releaseId'] = intake['releaseId']
            pointer = read_json(parsed[1]/'datastores/combined-incidents.json')
            result['collection'] = pointer
            if parsed[0].rollback:
                result['status'] = 'rolled-back'
            else:
                from scripts.crash_summaries import pending_work
                stage = 'summaryReview'
                summaries = pending_work()
                result['stages'][stage] = summaries
                if summaries['pending']:
                    result.update(status='needs-summary-review', nextCommand=summaries.get('nextCommand'))
                else:
                    from scripts.crash_road_segments import refresh
                    stage = 'roadSegments'
                    result['stages'][stage] = refresh(offline=True)
                    result['status'] = 'ready-for-consumer-preparation'
    except Exception as exc:
        result['stages'][stage] = {'status': 'failed', 'error': str(exc)}
        result['status'] = 'partially-complete' if 'intake' in result['stages'] and result['stages']['intake'].get('releaseId') else 'failed'
        result['blockedStage'] = stage
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] in {'ready-for-consumer-preparation', 'rolled-back'} else 2 if result['status'] == 'needs-summary-review' else 1


if __name__ == '__main__':
    sys.exit(run())
