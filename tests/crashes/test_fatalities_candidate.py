import unittest
from scripts.prepare_fatalities_release import feature


class FatalitiesTest(unittest.TestCase):
    def group(self):
        observation = dict(id='utah-crash-portal:123', sourceKey='utah-crash-portal',sourceRecordId='123',
                           observedAt='2026-09-01T01:00:00Z',coordinates=[-111.666661,40.233333],
                           metadata=dict(crash={'crashSeverity':'5','City_Geo':'Provo'},rollups=[],
                                         persons=[{'personType':'5','injuryLevel':'5','ageCalculated':17}]))
        return {'observations':[observation]}

    def test_minimized_fields_and_local_month(self):
        f=feature(self.group())
        self.assertEqual(f['properties'],dict(month='2026-08',mode='other-conveyance',fatalities=1))
        self.assertEqual(f['geometry']['coordinates'],[-111.6667,40.2333])
        grp=self.group()
        grp['observations'][0]['metadata']['crash']['City_Geo']=''
        self.assertIsNone(feature(grp))

    def test_conflicting_and_mixed_deaths_hold(self):
        grp=self.group()
        grp['observations'].append(dict(id='udot-crashes:123',sourceKey='udot-crashes',sourceRecordId='123',metadata={'NUMBER_FATALITIES':2}))
        with self.assertRaisesRegex(ValueError,'death count'):
            feature(grp)
        grp['observations'][0]['metadata']['persons'].append({'personType':'3','injuryLevel':'5'})
        with self.assertRaisesRegex(ValueError,'category'):
            feature(grp)
