"""Export reviewed summaries and police references for state crashes eligible for concern display."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from .crash_enrichment import export_release, public_details
from .incident_updates import flatten
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


# The November 15 Portal workbook omitted whole rollup rows previously supplied for these records.
INCOMPLETE_PORTAL_SNAPSHOT = 'd4cac55f1f2c64fe46996513bf2ef95773ab4993b46c3a95cfa58f5a381e176f'
FACTOR_RELEASE = {'releaseId': 'incidents-0a9d1f50cdb09a1af145',
                  'manifestSha256': '35afa67391c278b8d6f8ef284a98b95721a5a0f808e890c22c72963a42bb6b48'}


def retained_portal_factors(release):
    manifest_bytes = (release / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    if (hashlib.sha256(manifest_bytes).hexdigest() != FACTOR_RELEASE['manifestSha256']
            or manifest['releaseId'] != FACTOR_RELEASE['releaseId']):
        raise ValueError('Retained factor manifest pin mismatch')
    raw = (release / 'collection.json').read_bytes()
    collection = json.loads(raw)
    if (hashlib.sha256(raw).hexdigest() != manifest['files']['collection.json']
            or collection['snapshotId'] != manifest['releaseId']):
        raise ValueError('Retained factor collection pin mismatch')
    readings = {}
    for group in collection['records']:
        observations = flatten({'records': [group]})
        for reading in group['enrichment']['observations']:
            obs = observations[reading['observationId']]
            if obs['sourceKey'] == 'utah-crash-portal' and obs['metadata']['rollups']:
                readings[(group['id'], obs['id'])] = (group['enrichment']['rulesSha256'], reading['fields']['reportedFactors'])
    return readings


def restore_omitted_factors(export, groups, retained_release):
    history = None
    for group in groups:
        observations = flatten({'records': [group]})
        for reading in group['enrichment']['observations']:
            obs = observations[reading['observationId']]
            state_id = obs['sourceRecordId']
            if (obs['sourceKey'] != 'utah-crash-portal' or obs.get('sourceSnapshotId') != INCOMPLETE_PORTAL_SNAPSHOT
                    or obs['metadata'].get('rollups') != [] or state_id not in export['crashes']
                    or reading['fields']['reportedFactors']['availability'] != 'unavailable'):
                continue
            if history is None:
                history = retained_portal_factors(retained_release)
            prior = history.get((group['id'], obs['id']))
            if prior is None or (not prior[1]['value'] and prior[1]['availability'] != 'complete'):
                continue
            if prior[0] != group['enrichment']['rulesSha256']:
                raise ValueError('Retained factor rules differ from the adopted release')
            # Recombine just this earlier Portal reading with current readings from other sources.
            reading['fields']['reportedFactors'] = prior[1]
            field = next(f for f in public_details(group, export['releaseId'])['fields'] if f['key'] == 'reportedFactors')
            field['retainedPortalFactors'] = FACTOR_RELEASE
            fields = export['crashes'][state_id]['fields']
            current = next(f for f in fields if f['key'] == 'reportedFactors')
            current.update(field)


def add_recorded_road_names(crashes, group):
    observations = flatten({'records': [group]}).values()
    # The Portal's base crash record takes precedence over the UDOT main road for that ID.
    for source in ('udot-crashes', 'utah-crash-portal'):
        for obs in observations:
            state_id = obs['sourceRecordId']
            if obs['sourceKey'] != source or state_id not in crashes:
                continue
            meta = obs['metadata']
            road = meta['crash'].get('roadName') if source == 'utah-crash-portal' else meta.get('MAIN_ROAD_NAME')
            if road is None or (isinstance(road, str) and not road.strip()):
                continue
            if not isinstance(road, str) or not road.isprintable() or len(road.encode('utf-16-le')) > 400:
                raise ValueError('Invalid recorded road name for state ID ' + state_id)
            crashes[state_id]['recordedRoadName'] = road.strip()


def export_concern_details(release, manifest_hash, retained_factors_release=None):
    export = export_release(release, manifest_hash)
    raw = (release / 'collection.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != export['collectionSha256']:
        raise ValueError('Collection checksum mismatch')
    export['schemaVersion'] = 3
    for details in export['crashes'].values():
        details['schemaVersion'] = 3
    groups = json.loads(raw)['records']
    restore_omitted_factors(export, groups, retained_factors_release or release.parent / FACTOR_RELEASE['releaseId'])
    for group in groups:
        add_recorded_road_names(export['crashes'], group)
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
    parser.add_argument('--retained-factors-release', type=Path, help='Verified prior factor release when stored outside the release directory')
    args = parser.parse_args()
    export = export_concern_details(args.release, args.manifest_sha256, args.retained_factors_release)
    with args.output.open('x') as output:
        json.dump(export, output, sort_keys=True, separators=(',', ':'), allow_nan=False)
        output.write('\n')


if __name__ == '__main__':
    main()
