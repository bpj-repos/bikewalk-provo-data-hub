"""Update the active private crash workspace using verified historical path mappings."""
from pathlib import Path
import sys

HUB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HUB / 'pipelines/crashes/src'))
from danger_zones.update_incidents import main


def run():
    if any(arg.split('=')[0] in {'--private-data-root', '--data-root', '--restore-path', '--restore-root'} for arg in sys.argv[1:]):
        sys.exit('Use danger_zones.update_incidents directly for an isolated recovery drill.')
    main()


if __name__ == '__main__':
    run()
