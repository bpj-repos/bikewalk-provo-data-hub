"""Run the hub's maintained private updater against the operational Provo collection."""
from pathlib import Path
import sys

HUB = Path(__file__).resolve().parent
sys.path.insert(0, str(HUB / 'tools/crash_pipeline/src'))
from danger_zones.update_incidents import main


if __name__ == '__main__':
    original = Path('/Users/test/dev/bwp-data-hub/private/crashes')
    batch = original / 'pd-forwards-20261107'
    operations = HUB / 'private/crashes/operational-20261107'
    if any(arg.split('=')[0] in {'--private-data-root', '--data-root', '--restore-path'} for arg in sys.argv[1:]):
        sys.exit('Use the pipeline module directly for an isolated recovery drill.')
    origins = [Path('/Users/test/Documents/ChatGPT/bikewalk-provo'), batch / 'verified-hub-intake',
               batch / 'address-geocoding-shadow', original / operations.name]
    for origin in origins:
        if origin.resolve() == operations.resolve():
            continue
        sys.argv.extend(['--restore-path', str(origin), str(operations)])
    main()
