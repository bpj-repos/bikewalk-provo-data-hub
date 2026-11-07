import json
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from danger_zones.crash_enrichment import enrich_collection, export_release, public_details
from danger_zones.derived_incidents import age_group
from danger_zones.incident_updates import flatten
from danger_zones.query_incidents import select
from danger_zones.util import write_json, sha256_file


def fixture():
    identifier = '123'
    portal = {'id': 'utah-crash-portal:123', 'sourceKey': 'utah-crash-portal', 'sourceRecordId': identifier,
              'sourceSnapshotId': 'retained', 'observedAt': '2025-03-04T16:20:00-07:00',
              'coordinates': [-111.66, 40.23], 'modes': ['bicycle'],
              'metadata': {'crash': {'Crash_ID': identifier, 'crashDateandTime': '2025-03-04 16:20:00',
                                     'crashSeverity': '5', 'lightCondition': '1', 'weatherCondition': '1',
                                     'roadwaySurfaceCondition': '1'},
                           'persons': [{'Crash_ID': identifier, 'personType': '4', 'injuryLevel': '1', 'ageCalculated': '17'},
                                       {'Crash_ID': identifier, 'personType': '1', 'injuryLevel': '5', 'ageCalculated': '65',
                                        'personDriverContribCircumstances1': '3', 'personDriverContribCircumstances2': '0'}],
                           'vehicles': [], 'rollups': []}}
    return {'snapshotId': 'release-test', 'records': [{'id': portal['id'], 'observations': [portal]}]}


class EnrichmentTests(unittest.TestCase):
    def test_all_groups_source_preservation_and_person_attribution(self):
        collection = fixture()
        police = {'id': 'provo-police-incidents:P1', 'sourceKey': 'provo-police-incidents',
                  'sourceRecordId': 'P1', 'observedAt': '2025-03-04T10:00:00Z', 'mode': 'pedestrian', 'metadata': {}}
        collection['records'].append({'id': police['id'], 'observations': [police]})
        before = deepcopy(flatten(collection))
        audit = enrich_collection(collection)
        self.assertEqual(flatten(collection), before)
        self.assertEqual(audit['incidentGroups'], 2)
        first = public_details(collection['records'][0], collection['snapshotId'])
        self.assertEqual(len(first['fields']), 7)
        fields = {f['key']: f for f in first['fields']}
        self.assertIn('No injury (1)', fields['injuries']['values'][0]['text'])
        self.assertNotIn('Fatal', fields['injuries']['values'][0]['text'])
        self.assertIn('Under 18 (1)', fields['ageGroups']['values'][0]['text'])
        self.assertNotIn('65+', fields['ageGroups']['values'][0]['text'])
        self.assertIn('4:20 PM', fields['time']['values'][0]['text'])
        second = public_details(collection['records'][1], collection['snapshotId'])
        self.assertTrue(all(f['availability'] == 'unavailable' for f in second['fields']))
        again = deepcopy(collection)
        enrich_collection(again)
        self.assertEqual(collection, again)

    def test_age_boundaries_unknown_and_same_person_query(self):
        self.assertEqual([age_group(a) for a in [None, 0, 17, 18, 64, 65]],
                         [None, 'under18', 'under18', '18to64', '18to64', '65plus'])
        collection = fixture()
        enrich_collection(collection)
        person_query = {'person': {'all': [{'field': 'mode', 'op': 'eq', 'value': 'bicycle'},
                                         {'field': 'age_group', 'op': 'eq', 'value': '65plus'}]}}
        self.assertEqual(select(collection['records'], person_query)[0], [])
        person_query['person']['all'][1]['value'] = 'under18'
        self.assertEqual(len(select(collection['records'], person_query)[0]), 1)
        collection['records'][0]['observations'][0]['metadata']['persons'][0]['ageCalculated'] = '-99'
        enrich_collection(collection)
        ages = public_details(collection['records'][0], 'x')['fields'][-1]
        self.assertEqual(ages['availability'], 'partial')
        self.assertIn('Unknown age (1)', ages['values'][0]['text'])

    def test_source_conflicts_and_date_only(self):
        collection = fixture()
        state = {'id': 'udot-crashes:123', 'sourceKey': 'udot-crashes', 'sourceRecordId': '123',
                 'observedAt': '2025-03-04T23:20:00Z', 'modes': ['bicycle'],
                 'metadata': {'LIGHT_CONDITION_DESC': 'Dark - Not Lighted'}}
        collection['records'][0]['observations'].append(state)
        collection['records'][0]['observations'][0]['metadata']['crash']['crashDateandTime'] = '2025-03-04'
        enrich_collection(collection)
        fields = {f['key']: f for f in public_details(collection['records'][0], 'x')['fields']}
        self.assertEqual(fields['lighting']['availability'], 'conflicting')
        self.assertEqual(len(fields['lighting']['values']), 2)
        self.assertIn('time not recorded', fields['time']['values'][0]['text'])
        query = {'all': [{'field': 'lighting', 'op': 'eq', 'value': 'dark-unlighted'},
                         {'field': 'driver_circumstance', 'op': 'eq', 'value': 'failure-to-yield'}]}
        self.assertEqual(select(collection['records'], query)[0], [])

    def test_unmapped_and_invalid_inputs_stop_enrichment(self):
        collection = fixture()
        collection['records'][0]['observations'][0]['metadata']['persons'][1]['personDriverContribCircumstances1'] = 'NEW'
        with self.assertRaisesRegex(ValueError, 'Unreviewed enrichment mapping'):
            enrich_collection(collection)


    def test_partial_circumstances_do_not_establish_negative(self):
        collection=fixture()
        collection['records'][0]['observations'][0]['metadata']['persons'][1]['personDriverContribCircumstances2']='89'
        enrich_collection(collection)
        query={'not':{'field':'driver_circumstance','op':'eq','value':'improper-turn'}}
        selected,counts,_=select(collection['records'],query)
        self.assertEqual(selected,[])
        self.assertEqual(counts['unknown'],1)

    def test_verified_export_public_allowlist_and_ambiguous_id(self):
        collection = fixture()
        collection['records'][0]['observations'][0]['metadata']['persons'][0]['private_note'] = 'DO NOT EXPORT'
        enrich_collection(collection)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / 'collection.json', collection)
            write_json(root / 'manifest.json', {'releaseId': 'release-test', 'files': {'collection.json': sha256_file(root / 'collection.json')}})
            exported = export_release(root, sha256_file(root / 'manifest.json'))
            text = json.dumps(exported)
            for private in ['DO NOT EXPORT', 'ageCalculated', 'observationId', 'sourceSnapshotId', 'metadata', 'support']:
                self.assertNotIn(private, text)
            self.assertEqual(set(exported['crashes']), {'123'})
            collection['records'].append(deepcopy(collection['records'][0]))
            write_json(root / 'collection.json', collection)
            manifest = {'releaseId': 'release-test', 'files': {'collection.json': sha256_file(root / 'collection.json')}}
            write_json(root / 'manifest.json', manifest)
            ambiguous=export_release(root, sha256_file(root / 'manifest.json'))
            self.assertEqual(ambiguous['ambiguousCrashIds'],['123'])
            self.assertEqual(ambiguous['crashes'],{})
            (root / 'collection.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                export_release(root, sha256_file(root / 'manifest.json'))
