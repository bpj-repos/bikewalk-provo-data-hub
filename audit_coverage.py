"""Audit UDOT coverage against Provo city limits and the state school roster (requires shapely)."""
from collections import Counter
from urllib.request import urlopen
from shapely.geometry import shape
import json

from safe_routes import LAYERS,endpoint,query

CITY='https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/UtahMunicipalBoundaries/FeatureServer/0/query'
DIRECTORY='https://cactus.schools.utah.gov/api/legacy/schools'


def main():
    city_response=query(CITY,dict(where="UPPER(NAME)='PROVO'",outFields='NAME',returnGeometry='true',outSR=4326,f='geojson'))
    if len(city_response['features'])!=1:
        raise ValueError('Cannot identify Provo municipal polygon')
    city=shape(city_response['features'][0]['geometry'])
    bbox=','.join(map(str,city.bounds))
    for key in LAYERS:
        url=endpoint(key)+'/query'
        ids=query(url,dict(where='1=1',geometry=bbox,geometryType='esriGeometryEnvelope',inSR=4326,spatialRel='esriSpatialRelIntersects',returnIdsOnly='true',f='json'))['objectIds']
        outside=Counter()
        for start in range(0,len(ids),100):
            batch=ids[start:start+100]
            results=query(url,dict(objectIds=','.join(map(str,batch)),outFields='NAME_SCHOOL,ID_SCHOOL,NAME_DISTRICT,APPROVED',returnGeometry='true',outSR=4326,f='geojson'))['features']
            if len(results)!=len(batch):
                raise ValueError('Incomplete spatial audit')
            for r in results:
                p=r['properties']
                if r.get('geometry') and city.intersects(shape(r['geometry'])) and (p['NAME_DISTRICT']!='Provo' or p['APPROVED']!='Yes'):
                    outside[(p['NAME_SCHOOL'],p['ID_SCHOOL'],p['NAME_DISTRICT'],p['APPROVED'])]+=1
        print(key,sorted(outside.items(),key=str))
    with urlopen(DIRECTORY,timeout=30) as response:
        roster=json.load(response)['schools']
    print('Open Provo campuses:',sorted(s['schoolName'] for s in roster if s['isOpenThisSchoolYear'] and (s.get('city') or '').strip().upper()=='PROVO'))

if __name__=='__main__':
    main()

