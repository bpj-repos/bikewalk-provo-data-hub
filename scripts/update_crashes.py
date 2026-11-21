"""Update the active private crash workspace using verified historical path mappings."""
import json
import os
from pathlib import Path
import sys

HUB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HUB / 'pipelines/crashes/src'))
from danger_zones.update_incidents import main, parse_args


def run():
    if any(arg.split('=')[0] in {'--private-data-root', '--data-root', '--restore-path', '--restore-root'} for arg in sys.argv[1:]):
        sys.exit('Use danger_zones.update_incidents directly for an isolated recovery drill.')
    parsed = parse_args()
    os.umask(0o077)
    if '--rollback' not in sys.argv[1:] and '--offline' not in sys.argv[1:]:
        from scripts.crash_road_segments import capture_for_update
        capture_for_update()
    main(parsed)
    if '--rollback' not in sys.argv[1:]:
        from scripts.crash_summaries import pending_work
        result = pending_work()
        print(json.dumps({'summaryReview': result}, ensure_ascii=False, indent=2))
        if result['pending']:
            return 2
        from scripts.crash_road_segments import refresh
        print(json.dumps({'roadSegments': refresh(offline=True)}, indent=2))
        return 0


if __name__ == '__main__':
    sys.exit(run())
