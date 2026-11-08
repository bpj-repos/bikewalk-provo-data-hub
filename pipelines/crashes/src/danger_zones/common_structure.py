"""Validate the draft common structure and generate an exhaustive field decision report."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import yaml

from .field_inventory import CATALOG, REPO, read_catalog
from .util import sha256_file, write_json

CONTRACT = CATALOG.with_name('common.yml')
RULES = {'identifier', 'text', 'category-label', 'category-code', 'boolean', 'number',
         'integer', 'age', 'temporal', 'epoch-ms', 'date', 'point', 'latitude', 'longitude'}
DISPOSITIONS = {'keep', 'component', 'query', 'provenance', 'manifest', 'exclude'}
TYPES = {'text', 'category', 'boolean', 'integer', 'number', 'temporal', 'date', 'point'}


def read_contract(path=CONTRACT, catalog=None):
    catalog = catalog or read_catalog()
    contract = yaml.safe_load(Path(path).read_text())
    if set(contract) != {'version', 'status', 'inventoryCatalogVersion', 'scope', 'concepts', 'bindings', 'codebooks', 'policeModes'}:
        raise ValueError('Unsupported common structure keys')
    if contract['version'] != 1 or contract['status'] not in {'draft-awaiting-owner-exclusions', 'approved'}:
        raise ValueError('Unsupported common structure version/status')
    if contract['inventoryCatalogVersion'] != catalog['version']:
        raise ValueError('Inventory catalog version changed; review the common structure')
    if set(contract['concepts']) != set(catalog['concepts']):
        raise ValueError('Every inventoried concept needs exactly one common-structure decision')
    fields = {table + '.' + column for table, definition in catalog['tables'].items() for column in definition['fields']}
    if set(contract['bindings']) != fields:
        raise ValueError('Every inventoried field needs exactly one conversion binding')
    targets = {}
    for key, entry in contract['concepts'].items():
        if set(entry) - {'disposition', 'target', 'type', 'reason', 'group'}:
            raise ValueError('Unsupported concept decision keys')
        if entry['disposition'] not in DISPOSITIONS or (entry['disposition']!='keep' and not entry.get('reason')):
            raise ValueError('Each decision needs an allowed disposition and a reason')
        if entry['disposition'] == 'exclude':
            if not entry.get('group') or 'target' in entry or 'type' in entry:
                raise ValueError('Proposed exclusions need a group, not an active target')
        else:
            if entry.get('type') not in TYPES or not isinstance(entry.get('target'), str) or not entry['target']:
                raise ValueError('Retained concepts need a typed target')
            if entry['disposition'] == 'keep':
                if entry['target'] in targets:
                    raise ValueError('Redundant normalized target: ' + entry['target'])
                targets[entry['target']] = key
    for key, book in contract['codebooks'].items():
        if key not in contract['concepts'] or contract['concepts'][key].get('type') != 'category':
            raise ValueError('Codebook needs a categorical concept')
        if set(book) != {'reference', 'section', 'codes', 'labelAliases'} or book['reference'] not in catalog['references']:
            raise ValueError('Codebook requires a known reference and explicit mappings')
        if any(not isinstance(k, str) or not isinstance(v, str) for mapping in [book['codes'], book['labelAliases']] for k,v in mapping.items()):
            raise ValueError('Codebook codes and labels must be text')
    for entry in contract['bindings'].values():
        if set(entry) != {'rule'} or entry['rule'] not in RULES:
            raise ValueError('Unknown conversion rule')
    if any(not isinstance(k,str) or not isinstance(v,list) or not v or any(not isinstance(m,str) for m in v) for k,v in contract['policeModes'].items()):
        raise ValueError('Police mode mappings must be explicit nonempty arrays')
    compatible = {'category':{'category-code','category-label'},'text':{'text','identifier'},'boolean':{'boolean'},
                  'integer':{'integer','age'},'number':{'number','latitude','longitude'},
                  'temporal':{'temporal','epoch-ms'},'date':{'date'},'point':{'point'}}
    for table, definition in catalog['tables'].items():
        for column, binding in definition['fields'].items():
            policy=contract['concepts'][binding['concept']]
            if policy['disposition']!='exclude' and contract['bindings'][table+'.'+column]['rule'] not in compatible[policy['type']]:
                raise ValueError('Conversion rule and common target type disagree: '+table+'.'+column)
    return contract


def decision_report(contract, catalog):
    rows = []
    for table, definition in catalog['tables'].items():
        for column, binding in definition['fields'].items():
            key = table + '.' + column
            concept = binding['concept']
            decision = contract['concepts'][concept]
            rows.append({'field': key, 'source': definition['source'], 'entity': definition['entity'],
                         'concept': concept, **decision, 'rule': contract['bindings'][key]['rule']})
    return {'schemaVersion': 1, 'status': contract['status'], 'decisions': rows,
            'summary': {'fields': len(rows), 'concepts': len(contract['concepts']),
                        'conceptDispositions': dict(sorted(Counter(x['disposition'] for x in contract['concepts'].values()).items())),
                        'fieldDispositions': dict(sorted(Counter(x['disposition'] for x in rows).items()))}}


def write_report(report, output):
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'decisions.json', report)
    columns = ['field', 'source', 'entity', 'concept', 'disposition', 'target', 'type', 'rule', 'group', 'reason']
    with (output / 'decisions.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(report['decisions'])
    lines = ['# Common incident structure: field review', '', 'Owner approved the 20 omissions on November 2, 2026. Original data remains unchanged.', '',
             'Every source field has one decision and one explicit conversion rule. This does not approve a release or resume record merging.', '',
             '## Approved analytical exclusions', '', '| Concept | Source columns | Reason |', '| --- | ---: | --- |']
    grouped = {}
    for row in report['decisions']:
        grouped.setdefault(row['concept'], []).append(row)
    for key, rows in grouped.items():
        if rows[0]['disposition'] == 'exclude':
            lines.append(f"| {key} | {len(rows)} | {rows[0]['reason']} |")
    lines += ['', 'These are omissions from the proposed analytical structure only. Retained source files and the full source inventory are not deleted.', '',
              '## Retained targets', '', '| Concept | Destination | Type | Treatment |', '| --- | --- | --- | --- |']
    for key, rows in grouped.items():
        row = rows[0]
        if row['disposition'] != 'exclude':
            lines.append(f"| {key} | {row['target']} | {row['type']} | {row['disposition']} |")
    lines += ['', 'See decisions.csv for all source bindings and conversion rules, including redundant aliases and code/label components.']
    (output / 'decisions.md').write_text('\n'.join(lines) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', type=Path, default=CONTRACT)
    parser.add_argument('--output', type=Path, help='New report directory outside apps/maps')
    args = parser.parse_args()
    if args.output and args.output.resolve().is_relative_to((REPO / 'apps/maps').resolve()):
        parser.error('Reports belong outside the public application')
    catalog = read_catalog()
    contract = read_contract(args.contract, catalog)
    report = decision_report(contract, catalog)
    report['contractSha256'] = sha256_file(args.contract)
    report['catalogSha256'] = sha256_file(CATALOG)
    if args.output:
        write_report(report, args.output)
    print(json.dumps({'ok': True, 'status': contract['status'], **report['summary']}))


if __name__ == '__main__':
    main()
