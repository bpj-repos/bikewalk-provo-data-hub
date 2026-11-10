"""Source-only pilot, explicitly retaining missing movement inputs."""
from shapely.geometry import Point, shape
from shapely.ops import transform
from scripts.route_stress import PROJECT


def pilot(inputs, segments, approaches):
    def chosen(predicate):
        return next((f for f in segments if predicate(f['properties'])), None)
    picks = {
        'asymmetric-facility': chosen(lambda p: any(o.get('secondaryFacility') and o.get('facility') != o.get('secondaryFacility') for o in p['observations'])),
        'trail': chosen(lambda p: p['roadClass'] in ('path', 'cycleway')),
        'bridge': chosen(lambda p: p.get('bridge') not in (None, 'no')),
        'service': chosen(lambda p: p['roadClass'] == 'service'),
    }
    # The study signal is a source identity. Proximity below is reported as proximity only.
    study = inputs.get('signalized', {}).get('features', [])
    row = next((f for f in study if any(str(v) == '6444' for v in f['properties'].values())), None)
    if row:
        center = transform(PROJECT, shape(row['geometry'])).centroid
        nearby = [f for f in approaches if transform(PROJECT, shape(f['geometry'])).distance(center) <= 40]
    else:
        nearby = []
    cases = [dict(case=key, featureId=f['id'] if f else None,
                  observations=f['properties']['observations'] if f else [], status='source_only') for key, f in picks.items()]
    cases.append(dict(case='800-north-500-west-signal-6444', studyFound=row is not None,
                      approaches=[dict(id=f['id'], observations=f['properties']['observations']) for f in nearby],
                      status='source_only', missingForFurth=['movement-specific crossed lanes', 'verified refuge-island status', 'control applicability']))
    cases.append(dict(case='nonsignalized-study', sourceRecords=len(inputs.get('nonsignalized', {}).get('features', [])),
                      status='source_only', missingForFurth=['movement identity', 'verified refuge-island status']))
    cases.append(dict(case='divided-road', status='requires_movement_side_verification'))
    return dict(cases=cases, independentFieldValidation=False, localAttributesInjected=False,
                interpretation='Native source comparison. Existing Brokenspoke output fills gaps. Furth Table 6 evaluator is tested against the published table; no city rating is inferred where movement inputs are incomplete.')
