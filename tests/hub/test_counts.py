import csv
import io
import json
import os
import unittest
from unittest.mock import patch
from collections import Counter
from pathlib import Path
from scripts import build_counts_releases as counts
from scripts.build_demo_counts import VERSIONS, check_version, expected


@unittest.skipUnless(os.environ.get('BWP_SOURCE_REPO'), 'requires pinned BikeWalk source repository')
class RealCounts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(os.environ['BWP_SOURCE_REPO'])
        cls.years = counts.load('coverage.json')
        cls.tree, cls.issues = counts.bundle(cls.repo,cls.years)
        cls.files = {k.removeprefix(counts.PREFIX): v for k,v in cls.tree.items() if k.startswith(counts.PREFIX)}

    def rows(self,path):
        return list(csv.DictReader(io.StringIO(self.files[path].decode())))

    def test_parity(self):
        rows=self.rows('series.csv')
        self.assertEqual(rows,[r for y in self.years for r in self.rows(f'{y}.csv')])
        self.assertEqual(len(rows),len({(r['year'],r['station_id'],r['source_field']) for r in rows}))
        self.assertEqual(Counter(r['status'] for r in rows),{'observed':1938,'missing':281,'unresolved':35})
        self.assertTrue(any(r['value']=='0' and r['status']=='observed' for r in rows))
        self.assertTrue(all(bool(r['value'])==(r['status']=='observed') for r in rows))
        self.assertEqual(set(r['year'] for r in rows),set(map(str,self.years)))

    def test_known_results(self):
        rows=self.rows('2026.csv')
        def total(k):return sum(int(r['value']) for r in rows if r['source_field']==k)
        self.assertEqual(len({r['station_id'] for r in rows}),14)
        self.assertEqual((total('y26Total'),total('y26Scoot'),total('y26Scoot_T')+total('y26Scoot_Sat')),(6186,236,283))
        old=self.rows('2019.csv')
        station={r['source_field']:r for r in old if r['station_id']=='1'}
        self.assertEqual([station['Y19Total_T'][k] for k in ('value','date','duration_minutes')],['103','2019-09-12','120'])
        self.assertEqual(station['Y19Total_Sat']['value'],'186')
        self.assertTrue(all(r['status']=='unresolved' for r in old if r['station_id']=='10' and r['source_field'] in ('Y19Ped_T','Y19Other_T','Y19Total_T','Y19Total')))

    def test_rebuild_and_restore(self):
        self.assertEqual(counts.bundle(self.repo,self.years),(self.tree,self.issues))
        previous=expected(VERSIONS)
        for path,data in previous.items():
            if path!='catalog.json': self.assertEqual(self.tree[path],data)
        manifest=json.loads(self.files['datapackage.json'])
        for resource in manifest['resources']:
            data=self.files[resource['path']]
            self.assertEqual(len(data),resource['bytes'])
            self.assertEqual('sha256:'+counts.hashlib.sha256(data).hexdigest(),resource['hash'])
        for kind,version in [('compatible','1.1.0'),('correction','1.0.1'),('breaking','2.0.0')]:
            check_version('1.0.0',version,kind)
            with self.assertRaises(ValueError): check_version('1.0.0','1.0.0',kind)

    def test_changed_measure_cannot_replace_pin(self):
        original = counts.prepare
        def corrected(repo, years):
            rows, issues = original(repo, years)
            observed = next(r for r in rows if r['status'] == 'observed')
            observed['value'] += 1
            return rows, issues
        with patch.object(counts, 'prepare', corrected), self.assertRaisesRegex(ValueError,'approved'):
            counts.bundle(self.repo, self.years)

    def test_changed_definition_cannot_replace_pin(self):
        with patch.dict(counts.FIELDS, {'unit': 'Observations per hour'}):
            with self.assertRaisesRegex(ValueError, 'approved'):
                counts.bundle(self.repo,self.years)

    def test_coverage_change_cannot_replace_pin(self):
        with self.assertRaisesRegex(ValueError, 'approved'):
            counts.bundle(self.repo,self.years[:-1])

    def test_official_scooter_patch(self):
        tree,_ = counts.bundle(self.repo,self.years,corrected=True)
        for path,data in self.tree.items():
            if path!='catalog.json':
                self.assertEqual(tree[path],data)
        path=f'datasets/{counts.DATASET}/1.0.1/'
        patched=list(csv.DictReader(io.StringIO(tree[path+'series.csv'].decode())))
        expected=self.rows('series.csv')
        self.assertEqual(len(expected), len(patched))
        corrected=[]
        for old,new in zip(expected,patched):
            if old['year']=='2026' and old['source_field']=='y26Scoot':
                self.assertEqual({**old,'value':new['value']},new)
                corrected.append(int(new['value']))
            else:
                self.assertEqual(old,new)
        self.assertEqual(len(corrected),14)
        self.assertEqual(sum(corrected),283)
        annual=list(csv.DictReader(io.StringIO(tree[path+'2026.csv'].decode())))
        self.assertEqual(annual,[r for r in patched if r['year']=='2026'])

    def test_scooter_zero_and_missing(self):
        def total(value,status):
            rows=[dict(year=2026,station_id=1,source_field=field,value=v,status=s)
                for field,v,s in [('y26Scoot_T',0,'observed'),('y26Scoot_Sat',value,status),
                                  ('y26Scoot',10,'observed')]]
            counts.correct_scooters(rows)
            return rows[-1]['value'],rows[-1]['status']
        self.assertEqual(total(0,'observed'),(0,'observed'))
        self.assertEqual(total(None,'missing'),(None,'unresolved'))
        self.assertEqual(total(None,'unresolved'),(None,'unresolved'))
