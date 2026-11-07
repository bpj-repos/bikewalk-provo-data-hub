"""Audit or stage source-qualified normalized observations. Never links incidents or publishes."""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import Geod, Transformer

from .common_structure import CONTRACT, read_contract
from .config import DEFAULT_DATA_ROOT, DEFAULT_PRIVATE_DATA_ROOT
from .field_inventory import CATALOG, REPO, read_catalog, source_tables
from .incident_conversions import category, convert, missing
from .util import isoformat, sha256_file, utc_now, write_json


def selected_indices(tables):
    """Selection uses only explicit involvement evidence and exact keys inside one workbook."""
    included = set()
    for name in ('portal.crashes', 'portal.rollups'):
        for row in tables[name]['rows']:
            if any(row.get(key) == 'Y' for key in ('pedestrian_involved', 'cyclist_involved')):
                included.add(str(row['Crash_ID']))
    for row in tables['portal.persons']['rows']:
        if str(row.get('personType')) in {'3', '4', '5'}:
            included.add(str(row['Crash_ID']))
    selected = {}
    for table, data in tables.items():
        if table == 'udot.arcgis':
            selected[table] = [i for i,r in enumerate(data['rows']) if r.get('PEDESTRIAN_INVOLVED') == 'Y' or r.get('BICYCLIST_INVOLVED') == 'Y']
        elif table.startswith('portal.') and table != 'portal.filters':
            selected[table] = [i for i,r in enumerate(data['rows']) if str(r.get('Crash_ID')) in included]
        else:
            selected[table] = list(range(len(data['rows'])))
    return selected


def normalize_row(table, row, catalog, contract):
    """Combine code/label facets or equal aliases within this row, never across source records."""
    grouped = defaultdict(list)
    for column, binding in catalog['tables'][table]['fields'].items():
        concept = binding['concept']
        policy = contract['concepts'][concept]
        if policy['disposition'] in {'exclude', 'manifest', 'provenance', 'query'}:
            continue
        rule = contract['bindings'][table + '.' + column]['rule']
        try:
            cell = convert(row.get(column), rule, column in row)
        except ValueError as exc:
            cell = {'value': None, 'state': 'conversion-error', 'error': str(exc)}
        grouped[concept].append((column, rule, cell))
    values = {}
    errors = []
    for concept, parts in grouped.items():
        policy = contract['concepts'][concept]
        cells = [cell for _, _, cell in parts]
        errors.extend({'concept': concept, 'error': cell['error']} for cell in cells if 'error' in cell)
        populated = [c['value'] for c in cells if c['value'] is not None]
        state = next((c['state'] for c in cells if c['state'] == 'conversion-error'), cells[0]['state'])
        if policy['type'] == 'category':
            codes = list(dict.fromkeys(cell['value'] for _,rule,cell in parts if rule == 'category-code' and cell['value'] is not None))
            labels = list(dict.fromkeys(cell['value'] for _,rule,cell in parts if rule == 'category-label' and cell['value'] is not None))
            book = contract['codebooks'].get(concept)
            if book:
                labels = list(dict.fromkeys(book['labelAliases'].get(s,s) for s in labels))
                for code in codes:
                    decoded = book['codes'].get(code)
                    if decoded is None:
                        errors.append({'concept':concept, 'error':'unrecognized-code'})
                    elif decoded not in labels:
                        labels.append(decoded)
            if len(codes) > 1 or len(labels) > 1:
                cell = {'value': None, 'state': 'conflict'}
                errors.append({'concept':concept, 'error':'conflicting-alias-or-code-label'})
            else:
                cell = category(codes[0] if codes else None, labels[0] if labels else None, state)
        elif len({json.dumps(v, sort_keys=True) for v in populated}) > 1:
            cell = {'value':None, 'state':'conflict'}
            errors.append({'concept':concept, 'error':'conflicting-alias'})
        else:
            cell = {'value': populated[0] if populated else None, 'state':'reported' if populated else state}
        cell['columns'] = [column for column,_,_ in parts]
        values[policy['target'] if policy['disposition'] != 'component' else concept] = cell
    if table == 'portal.crashes':
        lat, lng = values.pop('location.latitude'), values.pop('location.longitude')
        if lat['value'] is not None and lng['value'] is not None:
            point = {'value': {'longitude': lng['value'], 'latitude':lat['value'], 'crs':'EPSG:4326'}, 'state':'reported'}
        else:
            point = {'value':None, 'state':'incomplete-coordinate' if lat['value'] is not None or lng['value'] is not None else lat['state']}
        point['columns'] = lng['columns'] + lat['columns']
        values['location.point'] = point
        helper = row.get('crash_date')
        occurred = values.get('time.occurred_at', {}).get('value')
        if helper and occurred:
            try:
                if convert(helper,'date')['value'] != occurred['date']:
                    errors.append({'concept':'time.occurrence_date','error':'date-helper-disagreement'})
            except ValueError:
                errors.append({'concept':'time.occurrence_date','error':'invalid-date-helper'})
    return values, errors


def build_candidate(catalog, contract, tables):
    selected = selected_indices(tables)
    records = []
    issues = Counter()
    states = Counter()
    transform = Transformer.from_crs(3857,4326,always_xy=True)
    geod = Geod(ellps='WGS84')
    coordinate_checks = 0
    for table, indices in selected.items():
        if table == 'portal.filters':
            continue
        definition = catalog['tables'][table]
        for i in indices:
            row = tables[table]['rows'][i]
            values, errors = normalize_row(table,row,catalog,contract)
            issues.update(table + ':' + e['concept'] + ':' + e['error'] for e in errors)
            states.update(cell['state'] for cell in values.values())
            identifier = row.get('CRASH_ID',row.get('Crash_ID',row.get('column_1',row.get('Case Number:'))))
            if missing(identifier):
                issues[table + ':missing-record-key'] += 1
            snapshot = tables[table]['snapshotId']
            locator = tables[table].get('locators', [])[i] if tables[table].get('locators') else {'rowOrdinal':i}
            record = {'observationId':f"{definition['source']}:{snapshot}:{table}:{i}", 'entity':definition['entity'],
                      'source':definition['source'],'snapshotId':snapshot,'table':table,
                      'sourceRecordId':str(identifier) if identifier is not None else None,
                      'sourceRow':locator, 'values': values,
                      'provenance':{column:convert(row.get(column),contract['bindings'][table + '.' + column]['rule'],column in row)
                                    for column,b in definition['fields'].items() if contract['concepts'][b['concept']]['disposition']=='provenance'} or None}
            if table in {'portal.persons','portal.vehicles'}:
                record['vehicleNumber'] = convert(row.get('vehicleNumber'),'identifier')['value']
            if table.startswith('police.'):
                record['values']['time.reported_at']['value']['zone']='America/Denver'
            modes=set()
            for concept,mode in [('classification.bicycle_involved','bicycle'),('classification.pedestrian_involved','pedestrian')]:
                if values.get(concept,{}).get('value') is True:modes.add(mode)
            person=values.get('person.type',{}).get('value')
            if person and person.get('code') in {'3','4','5'}:
                modes.add({'3':'pedestrian','4':'bicycle','5':'other-conveyance'}[person['code']])
            local_mode=values.get('travel.police_mode',{}).get('value')
            if local_mode:
                mapped=contract['policeModes'].get(' '.join(local_mode.lower().split()))
                if mapped is None:issues[table+':unrecognized-police-mode']+=1
                else:modes.update(mapped)
            record['modes']=sorted(modes)
            records.append(record)
            if table == 'udot.arcgis' and row.get('LONG_UTM_X') is not None and row.get('LAT_UTM_Y') is not None:
                try:
                    lng,lat = transform.transform(float(row['LONG_UTM_X']),float(row['LAT_UTM_Y']))
                    point = values['location.point']['value']
                    distance = geod.inv(lng,lat,point['longitude'],point['latitude'])[2]
                    if not math.isfinite(distance) or distance > 2:
                        issues['udot.arcgis:utm-point-disagreement-over-2m'] += 1
                    coordinate_checks += 1
                except (ValueError,TypeError):
                    issues['udot.arcgis:invalid-utm-comparison'] += 1
    # Exact source foreign keys only; these checks do not establish cross-source incident identity.
    crashes = {str(r['Crash_ID']) for r in tables['portal.crashes']['rows']}
    if len(crashes)!=len(tables['portal.crashes']['rows']):
        issues['portal.crashes:duplicate-source-crash-id']+=1
    vehicles = {(str(r['Crash_ID']),str(r['vehicleNumber'])) for r in tables['portal.vehicles']['rows']}
    relationship_counts = Counter()
    if len(vehicles)!=len(tables['portal.vehicles']['rows']):
        issues['portal.vehicles:duplicate-source-compound-key']+=1
    crash_rows={str(r['Crash_ID']):r for r in tables['portal.crashes']['rows']}
    for i in selected['portal.rollups']:
        row=tables['portal.rollups']['rows'][i]
        other=crash_rows.get(str(row['Crash_ID']),{})
        for concept in contract['concepts']:
            if not concept.startswith('classification.') or contract['concepts'][concept]['disposition']=='exclude':
                continue
            left=[other.get(k) for k,b in catalog['tables']['portal.crashes']['fields'].items() if b['concept']==concept]
            right=[row.get(k) for k,b in catalog['tables']['portal.rollups']['fields'].items() if b['concept']==concept]
            for a in left:
                for b in right:
                    if missing(a) is None and missing(b) is None and convert(a,'boolean')['value']!=convert(b,'boolean')['value']:
                        relationship_counts['crashRollupDisagreements']+=1
    for table in ['portal.persons','portal.vehicles','portal.rollups']:
        for i in selected[table]:
            row = tables[table]['rows'][i]
            if str(row['Crash_ID']) not in crashes:
                issues[table + ':orphan-crash-reference'] += 1
            if table=='portal.persons':
                vehicle = row.get('vehicleNumber')
                if missing(vehicle):
                    relationship_counts['nullPersonVehicleReference'] += 1
                elif (str(row['Crash_ID']),str(vehicle)) not in vehicles:
                    relationship_counts['unmatchedPersonVehicleReference'] += 1
    audit = {'schemaVersion':1, 'selectedRows':{k:len(v) for k,v in selected.items()},
             'inputRows':{k:len(v['rows']) for k,v in tables.items()}, 'valueStates':dict(sorted(states.items())),
             'issues':dict(sorted(issues.items())), 'relationshipWarnings':dict(relationship_counts),
             'coordinateComparisons':coordinate_checks, 'records':len(records), 'crossSourceLinksCreated':0}
    return records,audit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract',type=Path,default=CONTRACT)
    parser.add_argument('--data-root',type=Path,default=DEFAULT_DATA_ROOT)
    parser.add_argument('--private-data-root',type=Path,default=DEFAULT_PRIVATE_DATA_ROOT)
    parser.add_argument('--output',type=Path,required=True,help='New private candidate directory')
    parser.add_argument('--audit-only',action='store_true',help='Write aggregate audit only, without normalized records')
    args=parser.parse_args()
    if not args.output.resolve().is_relative_to(DEFAULT_PRIVATE_DATA_ROOT.resolve()):
        parser.error('Normalized candidates must stay in tools/.danger-zone-private/')
    if args.output.exists():
        parser.error('Output directory must be new')
    catalog=read_catalog(); contract=read_contract(args.contract,catalog)
    if contract['status']!='approved' and not args.audit_only:
        parser.error('Owner field-exclusion approval is required before staging normalized records')
    tables=source_tables(args.data_root,args.private_data_root,with_locators=True)
    # Use the maintained inventory validator to stop for physical column drift.
    from .field_inventory import inventory
    inventory(catalog,tables)
    records,audit=build_candidate(catalog,contract,tables)
    audit.update({'contractSha256':sha256_file(args.contract),'catalogSha256':sha256_file(CATALOG),
                  'scriptSha256':sha256_file(Path(__file__)), 'conversionScriptSha256':sha256_file(Path(__file__).with_name('incident_conversions.py'))})
    args.output.mkdir(parents=True,exist_ok=False)
    write_json(args.output/'audit.json',audit)
    if not args.audit_only and not audit['issues']:
        with (args.output/'observations.jsonl').open('w') as handle:
            for row in records:
                handle.write(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n')
        for entity in ('crash','police_report','person','vehicle'):
            entity_rows=[r for r in records if r['entity']==entity]
            if entity_rows:
                pq.write_table(pa.Table.from_pylist(entity_rows),args.output/(entity+'.parquet'))
        manifest={'schemaVersion':1,'kind':'unmerged-normalized-incident-observations','status':'candidate',
                  'createdAt':isoformat(utc_now()),'sources':{k:{name:value for name,value in table.items() if name not in {'rows','years','locators'}} for k,table in tables.items()},
                  'exportFilters':tables['portal.filters']['rows'], 'fieldAvailability':{k:sorted({b['concept'] for b in v['fields'].values() if contract['concepts'][b['concept']]['disposition'] not in {'exclude','query','manifest'}}) for k,v in catalog['tables'].items()},
                  'files':{p.name:sha256_file(p) for p in args.output.iterdir() if p.suffix in {'.jsonl','.parquet'}},
                  'rules':{k:audit[k] for k in ['contractSha256','catalogSha256','scriptSha256','conversionScriptSha256']},
                  'recordMerging':'paused; no cross-source grouping created'}
        write_json(args.output/'manifest.json',manifest)
    print(json.dumps({'output':str(args.output),**audit}))
    return 1 if audit['issues'] else 0


if __name__=='__main__':
    raise SystemExit(main())
