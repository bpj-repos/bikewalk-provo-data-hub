"""Export reviewed summaries and police references for state crashes eligible for concern display."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from .crash_enrichment import export_release
from .update_incidents import SUMMARY_FIELDS


def public_summary(summary, identifier):
    if (not isinstance(summary, dict) or set(summary) != set(SUMMARY_FIELDS)
            or not all(isinstance(v, str) and len(v.encode('utf-16-le')) <= 4000
                       and (not v or v.strip()) and not re.search(r'[\x00-\x1f\x7f-\x9f\u2028\u2029]', v)
                       for v in summary.values())
            or not 1 <= len(summary['brief'].split()) <= 12):
        raise ValueError('Invalid public reviewed summary for state ID ' + identifier)
    return summary


def reviewed_report(group):
    link = group.get('reviewedLink')
    if not link:
        return None
    by_id = {o['id']: o for o in group['observations']}
    police = by_id[link['policeId']]
    state = by_id[link['udotId']]
    if police['sourceKey'] != 'provo-police-incidents' or state['sourceKey'] not in {'utah-crash-portal', 'udot-crashes'}:
        raise ValueError('Reviewed link has inconsistent sources')
    case = police['sourceRecordId']
    if not re.fullmatch(r'[0-9]{2}PRW?[0-9]{4,6}', case):
        raise ValueError('Unexpected police case number')
    evidence = link['evidenceType']
    if evidence == 'owner-authorized-circumstantial':
        basis = 'exact-clock-address'
    elif evidence == 'manual-case-review' and link.get('confidence') in {'strong', 'probable'}:
        basis = link['confidence']
    elif evidence in {'shared-identifier', 'agency-crosswalk', 'documentary-confirmation'}:
        basis = 'documented'
    else:
        raise ValueError('Unsupported reviewed link basis')
    return state['sourceRecordId'], {'caseNumber': case, 'basis': basis}


def export_concern_details(release, manifest_hash):
    export = export_release(release, manifest_hash)
    raw = (release / 'collection.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != export['collectionSha256']:
        raise ValueError('Collection checksum mismatch')
    export['schemaVersion'] = 3
    for details in export['crashes'].values():
        details['schemaVersion'] = 3
    for group in json.loads(raw)['records']:
        summary = group['enrichment'].get('reviewedSummary')
        if summary is not None:
            ids = {o['sourceRecordId'] for o in group['observations']
                   if o['sourceKey'] in {'utah-crash-portal', 'udot-crashes'}}
            if len(ids) == 1 and (identifier := next(iter(ids))) in export['crashes']:
                export['crashes'][identifier]['reviewedSummary'] = public_summary(summary, identifier)
        reference = reviewed_report(group)
        if reference:
            identifier, report = reference
            if identifier not in export['ambiguousCrashIds']:
                export['crashes'][identifier]['policeReport'] = report
    return export


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export = export_concern_details(args.release, args.manifest_sha256)
    with args.output.open('x') as output:
        json.dump(export, output, sort_keys=True, separators=(',', ':'), allow_nan=False)
        output.write('\n')


if __name__ == '__main__':
    main()
