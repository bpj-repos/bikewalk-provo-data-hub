"""Replay the retained second Provo delivery in a temporary recovery tree."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from scripts.restore_crash_collections import ORIGINAL, PRIVATE, RELEASES, PINS, restore, verified
from danger_zones.update_incidents import RestorePaths, run_update, rollback
from danger_zones.motor_vehicle_candidate import build
from danger_zones.research_reports import crash_report
from danger_zones.util import sha256_file

def annual(folder, dest):
    f=folder/'manifest.json'
    m=json.loads(f.read_bytes())
    report=crash_report(json.loads(verified(folder/'collection.json',m['files']['collection.json'])),2025)
    at={r['year']:[r[k] for k in ('total','bike','ped','other')] for r in report['annual']}
    build(f,sha256_file(f),dest/PRIVATE/'incident-inputs',dest/f"motor-{folder.name}",2025)
    rev=json.loads((dest/f"motor-{folder.name}"/'private-review.json').read_bytes())
    return {int(y):[*at[int(y)],c['included'],c['unresolved'],c['excluded']] for y,c in rev['byYear'].items()}

def run():
    with TemporaryDirectory() as tmp:
        dest=Path(tmp).resolve()
        restore(ORIGINAL,ORIGINAL,dest)
        report='incidents-484f3b69f31351340636'
        historical=json.loads(verified(dest/RELEASES/report/'manifest.json',PINS[report]))
        previous=historical['predecessor']['pointer']
        active=dest/PRIVATE/'datastores/combined-incidents.json'
        active.parent.mkdir()
        active.write_text(json.dumps(previous))
        root=dest/PRIVATE
        mappings=RestorePaths([(ORIGINAL,dest)])
        workbook=next(root/'incident-inputs'/x['sha256']/'records.xlsx' for x in historical['inputs'] if x.get('kind')=='portal' and x.get('scope')=='collection' and x['sha256'].startswith('3405efb3'))
        before=annual(dest/RELEASES/previous['snapshotId'],dest)
        def update():
            return run_update(root,dest/'tools/.danger-zone-data',restore=mappings,portal_workbooks=[workbook],offline=True)
        updated=update()
        assert updated['status']=='accepted',updated['status']
        after=annual(Path(updated['bundle']),dest)
        reference=annual(dest/RELEASES/next(iter(PINS)),dest)
        assert after==reference
        old=active.read_bytes()
        assert update()['status']=='unchanged' and active.read_bytes()==old
        assert rollback(root,restore=mappings)['releaseId']==previous['snapshotId']
        print('year [AT, bicycle, pedestrian, other, motor-only, held, excluded] before -> after')
        for y in sorted(after):
            print(y,before.get(y),after[y])
        print('receipt replay, repeat, rollback verified')
if __name__=='__main__':run()
