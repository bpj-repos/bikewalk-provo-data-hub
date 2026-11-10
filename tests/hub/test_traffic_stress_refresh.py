import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

try:
    from pipelines.traffic_stress import refresh
    from scripts.capture_traffic_stress import capture_layer
except ImportError:
    refresh = None


@unittest.skipIf(refresh is None, 'Requires GIS dependencies')
class RefreshTests(unittest.TestCase):
    def test_expensive_cache_reuses_only_identical_verified_recipes(self):
        with TemporaryDirectory() as directory:
            calls = []
            def produce(out):
                calls.append(out)
                (out/'result.json').write_text('{}')
            folder = Path(directory)
            first, reused = refresh.cached(folder, dict(pbf='one', image='pin'), ['result.json'], produce)
            self.assertFalse(reused)
            same, reused = refresh.cached(folder, dict(pbf='one', image='pin'), ['result.json'], produce)
            self.assertTrue(reused)
            self.assertEqual(first, same)
            self.assertEqual(len(calls), 1)
            refresh.cached(folder, dict(pbf='two', image='pin'), ['result.json'], produce)
            self.assertEqual(len(calls), 2)
            (first/'result.json').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'Changed retained input'):
                refresh.cached(folder, dict(pbf='one', image='pin'), ['result.json'], produce)

    def test_failed_processing_never_becomes_a_cache_hit(self):
        with TemporaryDirectory() as directory:
            def fail(out):
                (out/'result.json').write_text('partial')
                raise RuntimeError('interrupted')
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                refresh.cached(Path(directory), dict(input='one'), ['result.json'], fail)
            self.assertEqual(list(Path(directory).glob('*/receipt.json')), [])

    def test_reference_extraction_keeps_shared_node_identity_and_tags(self):
        xml = b'''<osm><node id="1" lon="-111.6" lat="40.2"/><node id="2" lon="-111.5" lat="40.3"/>
          <node id="3" lon="-111.6" lat="40.3"/><node id="4" lon="-111.5" lat="40.2"/>
          <way id="11"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/><tag k="oneway:bicycle" v="no"/></way>
          <way id="12"><nd ref="3"/><nd ref="4"/><tag k="highway" v="residential"/><tag k="bridge" v="yes"/></way></osm>'''
        result = refresh.parse_osm(io.BytesIO(xml))
        self.assertEqual(len(result['ways']), 2)
        self.assertEqual(len(result['coords']), 4)
        self.assertEqual(result['ways'][0][2]['oneway:bicycle'], 'no')
        self.assertEqual(result['ways'][1][2]['bridge'], 'yes')
        self.assertFalse(set(result['ways'][0][1]) & set(result['ways'][1][1]))
        with self.assertRaisesRegex(ValueError, 'Incomplete OSM'):
            refresh.parse_osm(io.BytesIO(b'<osm><node id="1" lon="0" lat="0"/><way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="path"/></way></osm>'))

    def test_arcgis_paging_completeness_and_changed_membership(self):
        query_count = []
        def fetch(url, params):
            if not url.endswith('/query'):
                return dict(maxRecordCount=2, editingInfo=dict(lastEditDate=5))
            if params.get('returnIdsOnly'):
                return dict(objectIds=[1,2,3], objectIdFieldName='OBJECTID')
            if params.get('returnCountOnly'):
                return dict(count=3)
            ids = list(map(int, params['objectIds'].split(',')))
            query_count.append(ids)
            return dict(features=[dict(properties=dict(OBJECTID=i), geometry=dict(type='Point', coordinates=[0,0])) for i in ids])
        with TemporaryDirectory() as directory, patch('scripts.capture_traffic_stress.fetch', side_effect=fetch):
            p = Path(directory)/'out.geojson'
            self.assertEqual(capture_layer('https://source', (0,0,1,1), p)['count'], 3)
            self.assertEqual(query_count, [[1,2],[3]])
        def incomplete(url, params):
            result = fetch(url, params)
            if params.get('objectIds'):
                result['features'].pop()
            return result
        with TemporaryDirectory() as directory, patch('scripts.capture_traffic_stress.fetch', side_effect=incomplete):
            with self.assertRaisesRegex(ValueError, 'membership mismatch'):
                capture_layer('https://source', (0,0,1,1), Path(directory)/'out.geojson')

    def test_review_distinguishes_ratings_from_geometry_churn(self):
        def feature(id, source, band, coords):
            return dict(id=id, properties=dict(source=source, band=band), geometry=dict(type='Point', coordinates=coords))
        old = [feature('same', 'bna', 'lower', [0,0]), feature('removed', 'bna', 'lower', [0,0])]
        new = [feature('same', 'utah', 'higher', [1,0]), feature('added', 'bna', 'lower', [0,0])]
        with TemporaryDirectory() as directory:
            path = Path(directory)
            previous = {'coverage.json': b'{}'}
            for resource in ('segments', 'approaches'):
                previous[resource+'.geojson'] = json.dumps(dict(features=old)).encode()
                (path/(resource+'.geojson')).write_text(json.dumps(dict(features=new)))
            (path/'coverage.json').write_text('{}')
            result = refresh.compare(previous, path)
            self.assertEqual(result['segments'], dict(added=1,removed=1,sourceChanged=1,bandChanged=1,geometryChanged=1))

    def test_large_arcgis_pages_use_post_to_avoid_url_limits(self):
        from scripts.capture_traffic_stress import fetch
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value = io.BytesIO(b'{"features":[]}')
        with patch('scripts.capture_traffic_stress.urlopen', return_value=response) as open_url:
            fetch('https://source/query', dict(objectIds=','.join(map(str,range(500))),f='geojson'))
        request = open_url.call_args.args[0]
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(request.full_url, 'https://source/query')
        self.assertIn(b'objectIds=', request.data)

    def test_refusing_existing_run_does_not_write_failure_into_it(self):
        from scripts import refresh_traffic_stress as command
        with TemporaryDirectory() as directory:
            out = Path(directory)/'existing'
            out.mkdir()
            (out/'review.json').write_text('preserved')
            with patch.object(command, 'baseline', return_value=(dict(version='1.0.0'), {})):
                with self.assertRaises(FileExistsError):
                    command.execute(Path(directory)/'old.json', out, '1.1.0', Path(directory)/'cache')
            self.assertFalse((out/'failure.json').exists())
            self.assertEqual((out/'review.json').read_text(), 'preserved')

    def test_resume_rejects_changed_tools_before_processing(self):
        from scripts import refresh_traffic_stress as command
        entry = dict(dataset='provo-bicycle-traffic-stress', version='1.0.0', sha256='pin')
        with TemporaryDirectory() as directory:
            out = Path(directory)/'run';out.mkdir()
            (out/'acquisition.json').write_text(json.dumps(dict(baseline=entry, version='1.1.0', tools={}, receipt={})))
            with patch.object(command, 'baseline', return_value=(entry, {})), patch.object(refresh, 'process') as process:
                with self.assertRaisesRegex(ValueError, 'tools or version changed'):
                    command.execute(Path(directory)/'old.json',out,'1.1.0',Path(directory)/'cache',resume=True)
                process.assert_not_called()
            self.assertTrue((out/'acquisition.json').exists())

    def test_processed_provenance_replaces_old_output_pins(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);inputs=root/'inputs';inputs.mkdir();net=root/'net';net.mkdir();model=root/'model';model.mkdir()
            (inputs/'utah.osm.pbf').write_bytes(b'input')
            (net/'network.json').write_text('{"coords":{},"ways":[]}')
            for file in refresh.MODEL_FILES:(model/file).write_text('{"features":[{}]}')
            record=dict(sources={'boundary':dict(sha256='boundary'), 'utah':dict(path='utah.geojson',sha256='fresh-utah')},
                provenance=dict(acquisition=dict(osm=dict(path='utah.osm.pbf',sha256=refresh.sha(inputs/'utah.osm.pbf'),snapshot='2026-11-10T00:00:00Z')),
                    modelReceipt=dict(analyzer='image',analyzerVersion='3.3.0',database='db',speed=25,pinnedResources={'stale':'old'})))
            with patch.object(refresh,'cached',side_effect=[(net,True),(model,True)]):
                result=refresh.process(record,inputs,root/'cache')
            pins=result['provenance']['modelReceipt']['pinnedResources']
            self.assertNotIn('stale',pins)
            self.assertEqual(pins['utah.geojson'],'fresh-utah')
            self.assertEqual(pins['neighborhood_ways.geojson'],refresh.sha(inputs/'neighborhood_ways.geojson'))

    def test_acquisition_records_each_sources_own_origin_and_captured_vintage(self):
        from types import SimpleNamespace
        image = 'ghcr.io/peopleforbikes/brokenspoke-analyzer@sha256:' + 'a'*64
        boundary = dict(features=[dict(properties=dict(NAME='Provo'), geometry=dict(type='Polygon',
            coordinates=[[[-112,40],[-111,40],[-111,41],[-112,40]]]))])
        def api(url, **params):
            if url == refresh.upstream.BOUNDARY + '/query': return boundary
            if url == refresh.upstream.CITY:
                return dict(city=dict(name='Provo',state='Utah',residential_speed_limit=25), ratings=[dict(version='26.11')])
            if url == refresh.upstream.ANALYZER: return dict(tag_name='v3.4.0')
            return dict(editingInfo=dict(lastEditDate=5))
        def fetch(url, output=None):
            if output is None: return md5.encode()
            output.write_text(json.dumps(dict(features=[dict(properties=dict(road_id=1,
                ft_seg_stress=1,tf_seg_stress=3,ft_int_stress=None,tf_int_stress=None))])))
        def capture(url, bounds, output):
            output.write_text('{"features":[{}]}')
            return dict(origin=url,editingInfo=dict(lastEditDate=6),count=1)
        with TemporaryDirectory() as directory:
            root=Path(directory);old=root/'old';old.mkdir();out=root/'new';out.mkdir()
            pbf=old/'utah.osm.pbf';pbf.write_bytes(b'original')
            md5=refresh.upstream.digest(pbf,'md5')
            previous=dict(sources={},provenance=dict(modelReceipt=dict(method='old',analyzer=image,
                analyzerVersion='3.3.0',database='db',pinnedResources={'stale':'old'}),
                acquisition=dict(osm=dict(path=pbf.name,sha256=refresh.sha(pbf)))))
            for key in refresh.STUDIES:
                path=old/(key+'.json');path.write_text('{"features":[]}')
                previous['sources'][key]=refresh.descriptor(path,key,'old','2026-01-01')
            receipt=old/'receipt.json';refresh.write(receipt,previous)
            with patch.object(refresh.upstream,'api',side_effect=api), patch.object(refresh.upstream,'fetch',side_effect=fetch), \
                 patch.object(refresh.upstream,'run',return_value=SimpleNamespace(stdout='2026-11-08T21:21:00Z')), \
                 patch.object(refresh,'capture_layer',side_effect=capture):
                result=refresh.acquire(receipt,out)
            model=result['provenance']['modelReceipt']
            self.assertEqual(model['publishedComparison'],result['sources']['published']['origin'])
            self.assertIn('/provo/26.11/',model['publishedComparison'])
            self.assertEqual(result['sources']['utah']['version'],'6')
            self.assertTrue(result['provenance']['acquisition']['osm']['reused'])
            self.assertNotIn('pinnedResources',model)
            self.assertEqual(result['provenance']['acquisition']['sourceStatus']['crosswalks'],'retained_dated_snapshot')
