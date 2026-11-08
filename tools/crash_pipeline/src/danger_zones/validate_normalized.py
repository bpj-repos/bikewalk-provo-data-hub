"""Verify a staged normalized snapshot, checksums, types and source relationships offline."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .common_structure import CONTRACT, read_contract
from .config import PACKAGE_ROOT
from .field_inventory import CATALOG, REPO, read_catalog
from .util import read_json, sha256_file

STATES = {'reported','not-supplied','null','blank','unknown','not-provided','not-applicable','invalid-source-value','incomplete-coordinate'}


def validate_records(records, contract):
    seen=set(); tables=Counter(); nulls=Counter()
    types={v['target']:v['type'] for v in contract['concepts'].values() if v['disposition']=='keep'}
    types['location.point']='point'
    for row in records:
        identity=row['observationId']
        if identity in seen:
            raise ValueError('Repeated source observation ID')
        seen.add(identity);tables[row['table']]+=1
        if not row['sourceRecordId'] or not row['sourceRow']:
            raise ValueError('Missing source record/row provenance')
        if not identity.startswith(row['source']+':'+row['snapshotId']+':'+row['table']+':'):
            raise ValueError('Observation ID is not source/snapshot qualified')
        for key,cell in row['values'].items():
            if key not in types or cell['state'] not in STATES or not cell['columns']:
                raise ValueError('Unknown normalized target/state or missing source columns')
            value=cell['value'];nulls[cell['state']]+=1
            if value is None:
                if cell['state']=='reported':
                    raise ValueError('Reported value cannot be null')
                continue
            kind=types[key]
            if kind=='boolean' and type(value) is not bool or kind=='integer' and type(value) is not int or kind=='number' and type(value) not in {int,float}:
                raise ValueError('Incorrect normalized scalar type')
            if kind=='text' and not isinstance(value,str):
                raise ValueError('Incorrect normalized text type')
            if kind=='category' and (not isinstance(value,dict) or set(value)!={'code','label'} or any(v is not None and not isinstance(v,str) for v in value.values())):
                raise ValueError('Incorrect normalized category type')
            if kind=='temporal' and (not isinstance(value,dict) or set(value)!={'date','time','offset','precision','zone'}):
                raise ValueError('Incorrect normalized temporal type')
            if kind=='point' and (value.get('crs')!='EPSG:4326' or not -180<=value['longitude']<=180 or not -90<=value['latitude']<=90):
                raise ValueError('Incorrect normalized point')
    return {'records':len(seen),'tables':dict(tables),'states':dict(nulls)}


def validate_snapshot(path, contract_path=CONTRACT, catalog_path=CATALOG, reference_root=PACKAGE_ROOT):
    manifest=read_json(path/'manifest.json')
    contract=read_contract(contract_path, read_catalog(catalog_path, reference_root))
    if manifest.get('kind')!='unmerged-normalized-incident-observations' or manifest.get('schemaVersion')!=1:
        raise ValueError('Unknown normalized snapshot format')
    if manifest['rules']['contractSha256']!=sha256_file(contract_path):
        raise ValueError('Snapshot contract differs from current reviewed contract')
    if manifest['rules']['catalogSha256']!=sha256_file(catalog_path):
        raise ValueError('Snapshot source catalog differs from the current reviewed catalog')
    for name,expected in manifest['files'].items():
        if Path(name).name!=name or sha256_file(path/name)!=expected:
            raise ValueError('Snapshot file checksum/path mismatch')
    records=[json.loads(line) for line in (path/'observations.jsonl').read_text().splitlines()]
    result=validate_records(records,contract)
    audit=read_json(path/'audit.json')
    if audit['issues'] or result['records']!=audit['records']:
        raise ValueError('Audit is not clean or record counts differ')
    for table,count in result['tables'].items():
        if audit['selectedRows'].get(table)!=count:
            raise ValueError('Source selection count changed')
    for entity in {row['entity'] for row in records}:
        expected=[r for r in records if r['entity']==entity]
        table=pq.read_table(path/(entity+'.parquet'))
        if table.to_pylist()!=pa.Table.from_pylist(expected).to_pylist():
            raise ValueError('Parquet/JSONL value or source observation mismatch')
    return {'ok':True,**result,'crossSourceLinksCreated':audit['crossSourceLinksCreated']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot',type=Path)
    args=parser.parse_args()
    if args.snapshot.resolve().is_relative_to((REPO/'apps/maps').resolve()):
        parser.error('Normalized snapshots belong outside the public application')
    print(json.dumps(validate_snapshot(args.snapshot)))


if __name__=='__main__':main()
