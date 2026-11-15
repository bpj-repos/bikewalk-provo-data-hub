"""Screen private AT reports and apply reviewed bike-lane parking findings."""
from collections import defaultdict
from pathlib import Path
import re
import subprocess

from .util import sha256_file

FIELD = 'bikeLaneParkingContribution'
RULE = 'bike-lane-parking-v1'
VALUES = ('documented', 'possible', 'ruled_out', 'unknown')
FACILITY = re.compile(r'\b(?:(?:bi(?:ke|cycle)|cycling|cycle)[ -]?(?:lane|track|way)|protected lane)s?\b', re.I)
PARKING = re.compile(r'\b(?:park(?:ed|ing)|standing|stopped|(?:un)?loading|double.parked|block(?:ed|ing)|obstruct(?:ed|ing))\b', re.I)
SEQUENCE = re.compile(r'\b(?:swerv\w*|avoid\w*|forc\w*|merg\w*|struck|hit|collid\w*|crash\w*|fell|fell over|obscur\w*|obstruct\w*|could not see)\b', re.I)
CAUTION = re.compile(r"\b(?:no|not|never|denied|unrelated|disputed|conflict\w*|after the (?:crash|collision)|parking (?:bay|stall)|red light|traffic (?:queue|signal)|door(?:ed|ing)?)\b", re.I)


def screen(path):
    if path.suffix.lower() == '.pdf':
        extraction = subprocess.run(['pdftotext', '-layout', str(path.resolve()), '-'], capture_output=True)
        if extraction.returncode:
            return {'proposal': 'unknown', 'passages': [], 'reason': 'PDF extraction failed; inspect original pages'}
        text = extraction.stdout.decode('utf-8')
    elif path.suffix.lower() == '.txt':
        text = path.read_text(encoding='utf-8-sig')
    else:
        raise ValueError('Expected a report PDF or UTF-8 text')
    passages = []
    candidate = False
    for page, body in enumerate(text.split('\f'), 1):
        sentences = re.split(r'(?<=[.!?])\s+|\n\s*\n', body.strip())
        for i, sentence in enumerate(sentences):
            if not PARKING.search(sentence):
                continue
            window = ' '.join(sentences[max(0, i-1):i+3])
            signals = [key for key, pattern in [('facility', FACILITY), ('sequence', SEQUENCE),
                       ('qualification or conflicting context', CAUTION)] if pattern.search(window)]
            passages.append({'page': page, 'text': window, 'signals': signals})
            if ('facility' in signals or 'sequence' in signals) and not CAUTION.search(window):
                candidate = True
    return {'proposal': 'possible' if candidate else 'unknown', 'passages': passages,
            'reason': 'Parking near lane or crash-sequence language' if candidate else
                      'Insufficient or qualified language; inspect the original and diagram'}


def case_keys(group):
    keys = set()
    for item in group['observations']:
        for o in (item, item.get('statePortal')):
            if not o:
                continue
            source = o['sourceKey']
            if source in ('udot-crashes', 'utah-crash-portal'):
                keys.add('state:' + str(o['sourceRecordId']))
            elif source == 'provo-police-incidents':
                keys.add('police:' + str(o['sourceRecordId']))
    return sorted(keys)


def case_index(records):
    index = defaultdict(list)
    for group in records:
        for key in case_keys(group):
            index[key].append(group)
    return index


def import_reviews(path, state, root, old, retain, read):
    """Import a complete assessment for one group, replacing any prior assessment."""
    packet = read(path)
    if packet['rule'] != RULE or packet['value'] not in VALUES:
        raise ValueError('Unknown rule or category')
    matches = case_index(old['records'])[packet['case']]
    if len(matches) != 1 or packet['group'] != matches[0]['id'] or packet['links'] != case_keys(matches[0]):
        raise ValueError('Case link changed or ambiguous; reassess the report')
    if not all(isinstance(packet.get(k), str) and packet[k].strip() for k in ('reviewer', 'rationale')):
        raise ValueError('Missing reviewer or evidence rationale')
    if not packet['reports']:
        raise ValueError('Review requires an original report')
    for report in packet['reports']:
        original = Path(report['path'])
        if sha256_file(original) != report['sha256']:
            raise ValueError('Original report changed; reassessment required')
        ref = retain(original, root, 'parking-report')
        if ref['sha256'] != report['sha256']:
            raise ValueError('Report changed during import')
        if not any(r['kind'] == ref['kind'] and r['sha256'] == ref['sha256'] for r in state['inputs']):
            state['inputs'].append(ref)
    receipt = retain(path, root, 'parking-review')
    if read(Path(receipt['path'])) != packet:
        raise ValueError('Assessment changed during import')
    if not any(r['kind'] == receipt['kind'] and r['sha256'] == receipt['sha256'] for r in state['inputs']):
        state['inputs'].append(receipt)
    hashes = sorted({r['sha256'] for r in packet['reports']})
    reviews = state.setdefault('parkingReviews', {})
    # A corrected report-to-case link supersedes its former assignment.
    for group_id, prior in list(reviews.items()):
        if group_id != packet['group'] and set(hashes).intersection(prior['originals']):
            del reviews[group_id]
    reviews[packet['group']] = {
        k: packet[k] for k in ('case', 'group', 'links', 'rule', 'value')}
    reviews[packet['group']].update(receipt=receipt['sha256'], originals=hashes)


def apply_reviews(records, reviews):
    index = case_index(records)
    for group in records:
        entry = reviews.get(group['id'])
        valid = bool(entry and entry['rule'] == RULE and entry['links'] == case_keys(group)
                     and len(index[entry['case']]) == 1)
        group['enrichment'][FIELD] = entry['value'] if valid else 'unknown'
        group['enrichment'].pop('parkingReview', None)
        if valid:
            group['enrichment']['parkingReview'] = {'case': entry['case'], 'receipt': entry['receipt']}
