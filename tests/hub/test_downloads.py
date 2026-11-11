"""Complete downloads preserve approved bytes and follow catalog visibility."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import build_catalog, build_demo_counts


class DatasetDownloads(unittest.TestCase):
    def setUp(self):
        self.tree=build_demo_counts.expected(build_demo_counts.VERSIONS)
        self.dataset=json.loads(self.tree['catalog.json'])['datasets'][0]
        self.release=self.dataset['releases'][0]

    def test_complete_single_folder_with_unchanged_files_and_repeatable_bytes(self):
        archive=build_catalog.download_zip(self.tree,self.release)
        self.assertEqual(archive,build_catalog.download_zip(self.tree,self.release))
        prefix=self.release['manifest'].lstrip('/').rsplit('/',1)[0]+'/'
        manifest=json.loads(self.tree[prefix+'datapackage.json'])
        folder=manifest['name']+'-'+manifest['version']+'/'
        names=['datapackage.json']+[r['path'] for r in manifest['resources']]
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            self.assertIsNone(zipped.testzip())
            self.assertEqual(zipped.namelist(),[folder+name for name in sorted(names)])
            for name in names:
                self.assertEqual(zipped.read(folder+name),self.tree[prefix+name])

    def test_approved_update_automatically_includes_a_new_detail_file(self):
        version='1.1.0'
        name='new-source-notes.md'
        notes=b'# Source notes\nNew supporting detail for this update.\n'
        files=build_demo_counts.package(build_demo_counts.VERSIONS[0])
        manifest=json.loads(files['datapackage.json'])
        manifest.update(version=version,title='Test-only approved update')
        manifest.pop('synthetic',None)
        manifest['resources'].append(dict(name='source-notes',path=name,bytes=len(notes),hash='sha256:'+hashlib.sha256(notes).hexdigest()))
        files[name]=notes
        files['datapackage.json']=build_demo_counts.encoded(manifest)
        approval=dict(dataset=manifest['name'],version=version,sha256=hashlib.sha256(files['datapackage.json']).hexdigest())
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            package=root/'releases/datasets'/manifest['name']/version
            package.mkdir(parents=True)
            for filename,data in files.items():
                (package/filename).write_bytes(data)
            (package/'unlisted-private.txt').write_text('Not an approved resource')
            (root/'config').mkdir()
            (root/'config/vercel.json').write_bytes((build_catalog.ROOT/'config/vercel.json').read_bytes())
            output=root/'stage'
            with patch.object(build_catalog,'ROOT',root),patch.object(build_catalog.counts,'bundle',return_value=(copy.deepcopy(self.tree),[])):
                build_catalog.build(root,output,dict(approved=[approval],withdrawn=[]))
            dataset=json.loads((output/'public/catalog.json').read_bytes())['datasets'][0]
            self.assertEqual(dataset['current'],version)
            release=next(r for r in dataset['releases'] if r['version']==version)
            folder=manifest['name']+'-'+version+'/'
            with zipfile.ZipFile(output/'public'/release['download']['path'].lstrip('/')) as archive:
                self.assertEqual(archive.read(folder+name),notes)
                self.assertEqual(json.loads(archive.read(folder+'datapackage.json')),manifest)
                self.assertNotIn(folder+'unlisted-private.txt',archive.namelist())
            self.assertFalse((output/'public/datasets'/manifest['name']/version/'unlisted-private.txt').exists())

    def test_city_registration_only_hosts_selected_versions(self):
        ledger=json.loads((build_catalog.ROOT/'releases/release-ledger.json').read_bytes())
        versions=[r for r in ledger['approved'] if r['dataset']=='springville-annual-at-crash-aggregates']
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'stage'
            with patch.object(build_catalog.counts,'bundle',return_value=(copy.deepcopy(self.tree),[])):
                build_catalog.build(output,output,dict(approved=versions,withdrawn=[],
                    publicCityReleases=[dict(dataset=versions[0]['dataset'],version='1.1.0')]))
            city=json.loads((output/'public/catalog.json').read_bytes())['datasets'][-1]
            self.assertEqual([r['version'] for r in city['releases']],['1.1.0'])
            self.assertFalse((output/'public/datasets'/city['id']/'1.0.0').exists())
            self.assertFalse((output/'public/downloads'/city['id']/'1.0.0').exists())

    def test_reject_corruption_and_unsafe_resource_paths(self):
        prefix=self.release['manifest'].lstrip('/').rsplit('/',1)[0]+'/'
        corrupt=copy.deepcopy(self.tree)
        corrupt[prefix+'series.csv']+=b'changed'
        with self.assertRaisesRegex(ValueError,'Bad download resource'):
            build_catalog.download_zip(corrupt,self.release)
        for name in ('../private.csv','..\\private.csv','/private.csv','datapackage.json'):
            with self.subTest(name=name):
                manifest=json.loads(self.tree[prefix+'datapackage.json'])
                manifest['resources'][0]['path']=name
                tree={**self.tree,prefix+'datapackage.json':build_demo_counts.encoded(manifest)}
                with self.assertRaisesRegex(ValueError,'Bad download resource path'):
                    build_catalog.download_zip(tree,self.release)

    def test_catalog_checksum_and_withdrawal_and_retirement(self):
        for mode in ('available','withdrawn','retired'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temporary:
                output=Path(temporary)/'stage'
                ledger={'approved':[],'withdrawn':[],'retired':[]}
                if mode=='withdrawn':
                    ledger['withdrawn']=[dict(dataset=self.dataset['id'],version=self.release['version'],date='2026-11-11',notice='Test withdrawal')]
                elif mode=='retired':
                    ledger['retired']=[self.dataset['id']]
                with patch.object(build_catalog.counts,'bundle',return_value=(copy.deepcopy(self.tree),[])):
                    build_catalog.build(Path(temporary),output,ledger)
                catalog=json.loads((output/'public/catalog.json').read_bytes())
                if mode=='retired':
                    self.assertEqual(catalog['datasets'],[])
                    self.assertEqual(list((output/'public').glob('downloads/**/*.zip')),[])
                    continue
                for release in catalog['datasets'][0]['releases']:
                    if release.get('status')=='withdrawn':
                        self.assertNotIn('download',release)
                        expected=f"downloads/{self.dataset['id']}/{release['version']}"
                        self.assertFalse((output/'public'/expected).exists())
                    else:
                        download=release['download']
                        data=(output/'public'/download['path'].lstrip('/')).read_bytes()
                        self.assertEqual(len(data),download['bytes'])
                        self.assertEqual(hashlib.sha256(data).hexdigest(),download['sha256'])
