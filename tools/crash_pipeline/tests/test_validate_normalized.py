import copy
import unittest
from danger_zones.common_structure import read_contract
from danger_zones.validate_normalized import validate_records


class ValidateNormalizedTests(unittest.TestCase):
    def test_rejects_duplicates_bad_types_missing_provenance_and_unknown_states(self):
        contract=read_contract()
        row={'observationId':'source:snapshot:table:0','source':'source','snapshotId':'snapshot','table':'table',
             'sourceRecordId':'0001','sourceRow':{'row':2},'values':{'classification.speed_related':{'value':False,'state':'reported','columns':['speed']}}}
        self.assertEqual(validate_records([row],contract)['records'],1)
        with self.assertRaisesRegex(ValueError,'Repeated'):validate_records([row,row],contract)
        for prop,value in [('value','N'),('state','guess'),('columns',[])]:
            bad=copy.deepcopy(row);bad['values']['classification.speed_related'][prop]=value
            with self.assertRaises(ValueError):validate_records([bad],contract)
        bad=copy.deepcopy(row);bad['sourceRow']=None
        with self.assertRaises(ValueError):validate_records([bad],contract)
        bad=copy.deepcopy(row);bad['values']['classification.speed_related']['value']=None
        with self.assertRaises(ValueError):validate_records([bad],contract)

    def test_snapshot_rejects_catalog_drift_and_parquet_value_drift(self):
        import tempfile
        from pathlib import Path
        import pyarrow as pa
        import pyarrow.parquet as pq
        from danger_zones.common_structure import CONTRACT
        from danger_zones.field_inventory import CATALOG
        from danger_zones.util import sha256_file, write_json
        from danger_zones.validate_normalized import validate_snapshot
        row={'observationId':'source:snapshot:table:0','source':'source','snapshotId':'snapshot','table':'table','entity':'crash',
             'sourceRecordId':'0001','sourceRow':{'row':2},'values':{'classification.speed_related':{'value':False,'state':'reported','columns':['speed']}}}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            import json
            (p/'observations.jsonl').write_text(json.dumps(row)+'\n')
            pq.write_table(pa.Table.from_pylist([row]),p/'crash.parquet')
            manifest={'kind':'unmerged-normalized-incident-observations','schemaVersion':1,
                      'rules':{'contractSha256':sha256_file(CONTRACT),'catalogSha256':sha256_file(CATALOG)},
                      'files':{name:sha256_file(p/name) for name in ['observations.jsonl','crash.parquet']}}
            write_json(p/'manifest.json',manifest)
            write_json(p/'audit.json',{'issues':{},'records':1,'selectedRows':{'table':1},'crossSourceLinksCreated':0})
            self.assertTrue(validate_snapshot(p)['ok'])
            manifest['rules']['catalogSha256']='0'*64;write_json(p/'manifest.json',manifest)
            with self.assertRaisesRegex(ValueError,'catalog differs'):validate_snapshot(p)
            manifest['rules']['catalogSha256']=sha256_file(CATALOG)
            row['values']['classification.speed_related']['value']=True
            pq.write_table(pa.Table.from_pylist([row]),p/'crash.parquet')
            manifest['files']['crash.parquet']=sha256_file(p/'crash.parquet');write_json(p/'manifest.json',manifest)
            with self.assertRaisesRegex(ValueError,'value or source observation'):validate_snapshot(p)
