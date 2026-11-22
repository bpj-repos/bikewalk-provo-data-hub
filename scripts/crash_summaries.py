"""Prepare isolated crash-summary assignments and apply reviewed results with the Hub updater."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from danger_zones.config import DEFAULT_PRIVATE_DATA_ROOT, HUB_ROOT
from danger_zones.crash_labels import definitions, export_values
from danger_zones.incident_updates import flatten
from danger_zones.update_incidents import validate_summary, summary_basis, summary_groups, summary_keys
from danger_zones.util import read_json, sha256_file, sha256_json, write_json


def snapshot():
    pointer = read_json(DEFAULT_PRIVATE_DATA_ROOT / 'datastores/combined-incidents.json')
    path = Path(pointer['path'])
    if sha256_file(path) != pointer['sha256']:
        raise ValueError('Active collection checksum mismatch')
    collection = read_json(path)
    ids = {key for group in collection['records'] for key in summary_keys(group)}
    groups = summary_groups(collection, ids)
    # Ambiguous state IDs remain unresolved; review each existing group independently.
    ids.update('group:' + g['id'] for g in collection['records']
               if any(groups.get(key) is None for key in summary_keys(g)))
    return pointer, summary_groups(collection, ids)


def resolve(identifier, groups):
    key = identifier.removeprefix('utah-crash-portal:').removeprefix('udot-crashes:')
    if key in groups and groups[key]:
        return key
    case = key.removeprefix('provo-police-incidents:')
    matches = [k for k, g in groups.items() if g and any(
        o['id'] == 'provo-police-incidents:' + case for o in g['observations'])]
    if len(matches) != 1:
        raise ValueError('Unknown or ambiguous crash: ' + identifier)
    return matches[0]


def evidence(group):
    # Limit each assignment to structured reporting fields. Raw PD rows and notes stay private.
    tables, _ = definitions()
    result = []
    for o in flatten({'records': [group]}).values():
        src, meta = o['sourceKey'], o['metadata']
        record = {k:o.get(k) for k in ('id','observedAt','timePrecision','dateMeaning','mode','modes')}
        result.append(record)
        if src == 'provo-police-incidents':
            record['reportedLocation'] = meta.get('location', {}).get('normalizedAddress')
            continue
        sections = [('udot.arcgis',[meta])] if src == 'udot-crashes' else [
            ('portal.crashes',[meta['crash']]), *[('portal.' + k, meta.get(k, [])) for k in ('persons','vehicles','rollups')]]
        for table, rows in sections:
            fields = tables[table]['fields']
            projected = []
            for row in rows:
                values = {}
                for column, value in export_values(table, row).items():
                    concept = fields.get(column, {}).get('concept','')
                    if concept == 'person.age':
                        try:
                            age = int(value)
                        except (ValueError, TypeError):
                            continue
                        if 0 <= age <= 120:
                            values['ageGroup'] = 'under 18' if age < 18 else '18–64' if age < 65 else '65+'
                    elif (concept.startswith(('event.','road.','condition.','count.','classification.','injury.','vehicle.','person.'))
                          or concept in ('location.road_name','location.description','location.geographic_city','identity.vehicle_number')):
                        if value is not None and value != '':
                            values[column] = value
                projected.append(values)
            record[table] = projected
    link = group.get('reviewedLink') or {}
    return {'observations':result, 'linkBasis':{k:link[k] for k in ('evidenceType','confidence','documentaryIdentityConfirmed') if k in link}}


def prepare(work, groups, keys, pin):
    work.mkdir(mode=0o700, parents=True, exist_ok=False)
    jobs = {}
    for key in keys:
        if not re.fullmatch(r'(?:[0-9]+|provo-police-incidents:[A-Za-z0-9_-]+|group:[A-Za-z0-9_:-]+)', key):
            raise ValueError('Unexpected crash identifier')
        g = groups[key]
        jobs[key] = {'basis':summary_basis(g), 'prior':sha256_json(g['enrichment'].get('reviewedSummary'))}
        write_json(work / (key + '.input.json'), evidence(g))
    write_json(work/'jobs.json', {'collectionSHA256':pin,'jobs':jobs})


def collect(work, groups, pin):
    jobs = read_json(work/'jobs.json')['jobs']
    results = {}
    for key, job in jobs.items():
        g = groups.get(key)
        if not g or summary_basis(g) != job['basis']:
            raise ValueError('Reporting changed. Prepare again: ' + key)
        summary = read_json(work/(key+'.summary.json'))
        validate_summary(key, summary)
        previous = g['enrichment'].get('reviewedSummary')
        if previous == summary:
            continue
        if sha256_json(previous) != job['prior']:
            raise ValueError('Concurrent summary edit. Prepare again: ' + key)
        results[key] = summary
    return {'collectionSHA256':pin, 'summaries':results}


def pending_work():
    """Prepare resumable review work; ingestion alone does not complete an update."""
    pointer, groups = snapshot()
    keys = sorted(k for k, group in groups.items()
                  if group and 'reviewedSummary' not in group['enrichment'])
    result = {'releaseId': pointer['snapshotId'], 'collectionSHA256': pointer['sha256'],
              'status': 'needs-summary-review' if keys else 'ready',
              'pending': keys, 'ambiguousIds': sorted(k for k, group in groups.items() if group is None)}
    if keys:
        work = DEFAULT_PRIVATE_DATA_ROOT / 'incident-updates/summary-work' / pointer['snapshotId']
        if work.exists():
            jobs = read_json(work / 'jobs.json')
            if jobs['collectionSHA256'] != pointer['sha256'] or set(jobs['jobs']) != set(keys):
                raise ValueError('Summary work does not match the active collection')
        else:
            prepare(work, groups, keys, pointer['sha256'])
        result['work'] = str(work)
        result['nextCommand'] = [sys.executable, '-m', 'scripts.crash_summaries', 'apply', str(work)]
        result['instructions'] = ('Draft and review each .input.json into its .summary.json using the nine-field '
                                  'summary workflow before applying. Do not adopt consumers until status is ready.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('show').add_argument('id')
    sub.add_parser('status', help='Prepare pending summary work; exit 2 until reviewed summaries are applied')
    prep = sub.add_parser('prepare')
    prep.add_argument('work',type=Path)
    choice = prep.add_mutually_exclusive_group(required=True)
    choice.add_argument('--id', action='append')
    choice.add_argument('--pending', action='store_true')
    prep.add_argument('--limit',type=int)
    sub.add_parser('apply').add_argument('work',type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    if args.command == 'status':
        result = pending_work()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result['pending'] else 0
    pointer, groups = snapshot()
    if args.command == 'show':
        key = resolve(args.id, groups)
        print(json.dumps({'id':key,'releaseId':pointer['snapshotId'],
                          'summary':groups[key]['enrichment'].get('reviewedSummary')},ensure_ascii=False,indent=2))
    elif args.command == 'prepare':
        if args.limit is not None and (args.limit < 1 or not args.pending):
            parser.error('--limit requires --pending and must be positive')
        if args.pending:
            keys = sorted(k for k,g in groups.items() if g and 'reviewedSummary' not in g['enrichment'])
        else:
            keys = list(dict.fromkeys(resolve(request,groups) for request in args.id))
        keys = keys[:args.limit]
        prepare(args.work, groups, keys, pointer['sha256'])
        print(f'{len(keys)} assignments in {args.work}. Ambiguous IDs excluded: {sum(g is None for g in groups.values())}.')
    else:
        packet = collect(args.work, groups, pointer['sha256'])
        if packet['summaries']:
            receipt = args.work / 'reviewed-packet.json'
            write_json(receipt,packet)
            completed = subprocess.run([sys.executable,'-m','scripts.update_crashes','--offline','--reviewed-summaries',str(receipt.resolve())],
                           cwd=HUB_ROOT)
            if completed.returncode not in (0, 2):
                completed.check_returncode()
            return completed.returncode
        else:
            print('No changes.')


if __name__ == '__main__':
    sys.exit(main())
