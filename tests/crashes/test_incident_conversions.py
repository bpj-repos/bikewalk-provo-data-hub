import unittest
from datetime import datetime
from danger_zones.incident_conversions import convert, category


class IncidentConversionTests(unittest.TestCase):
    def test_missing_is_not_zero_or_false(self):
        self.assertEqual(convert(None,'number',False)['state'],'not-supplied')
        self.assertEqual(convert(None,'number')['state'],'null')
        self.assertEqual(convert(' ','number')['state'],'blank')
        self.assertEqual(convert('0','integer')['value'],0)
        self.assertIs(convert('N','boolean')['value'],False)
        self.assertEqual(category('99','Unknown')['state'],'unknown')
        self.assertEqual(category('89','Not Provided')['state'],'not-provided')
        self.assertEqual(category('96','Not Applicable (Legacy code)')['state'],'not-applicable')
        self.assertEqual(convert('89','identifier')['value'],'89')
        self.assertEqual(convert('-99','age'),{'state':'invalid-source-value','value':None})

    def test_numbers_and_identifiers_fail_without_lossy_coercion(self):
        self.assertEqual(convert('00089','identifier')['value'],'00089')
        self.assertEqual(convert('2.0','integer')['value'],2)
        for v in ('2.1','-1','NaN','Infinity',True):
            with self.assertRaises(ValueError): convert(v,'integer')
        for v in ('NaN','Infinity',False):
            with self.assertRaises(ValueError): convert(v,'number')
        with self.assertRaises(ValueError): convert(1.0,'identifier')
        with self.assertRaises(ValueError): convert('yes','boolean')
        with self.assertRaises(ValueError): convert(91,'latitude')
        with self.assertRaises(ValueError): convert(201,'age')

    def test_precision_and_zone_are_not_fabricated(self):
        for s in ('1/17/2020','2020-01-17'):
            c=convert(s,'temporal')['value']
            self.assertEqual(c['precision'],'date'); self.assertIsNone(c['time']); self.assertIsNone(c['zone'])
        for s in ('1/17/2020 7:30:00 PM','2020-01-17 07:30:00 PM','2020-01-17 19:30:00'):
            c=convert(s,'temporal')['value'];self.assertEqual(c['time'],'19:30:00');self.assertIsNone(c['offset'])
        self.assertEqual(convert('2020-01-17 19:30','temporal')['value']['precision'],'minute')
        self.assertEqual(convert('2020-01-17T19:30:00-07:00','temporal')['value']['offset'],'-07:00')
        self.assertEqual(convert(0,'epoch-ms')['value']['zone'],'UTC')
        self.assertEqual(convert(datetime(2020,1,17,0,0),'temporal')['value']['precision'],'second')
        for v in ('invalid','2020-13-01','2020-01-17T99:30:00'):
            with self.assertRaises(ValueError): convert(v,'temporal')

    def test_point_requires_finite_wgs84_coordinates(self):
        self.assertEqual(convert({'type':'Point','coordinates':[-111.65,40.25]},'point')['value']['crs'],'EPSG:4326')
        for value in ({'type':'LineString','coordinates':[]},{'type':'Point','coordinates':[None,40.25]},{'type':'Point','coordinates':[-111.65,400]}):
            with self.assertRaises(ValueError):convert(value,'point')
