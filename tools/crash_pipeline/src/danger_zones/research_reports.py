"""Annual active transportation crash series from a pinned private collection."""
from .incidents import _date
from .incident_updates import flatten

MODE_KEYS=['bike','ped','other']


def crash_modes(observation):
    m=observation['metadata'];types={str(p.get('personType')) for p in m['persons']}
    modes={name for code,name in [('4','bike'),('3','ped'),('5','other')] if code in types}
    if not modes:
        flags=[m['crash'],*m['rollups']]
        if any(r.get('cyclist_involved')=='Y' for r in flags):modes.add('bike')
        if any(r.get('pedestrian_involved')=='Y' for r in flags):modes.add('ped')
    return modes


def crash_report(snapshot,complete_through):
    selected={}
    for o in flatten(snapshot).values():
        if o['sourceKey']!='utah-crash-portal':continue
        c=o['metadata']['crash']
        if c['City_Geo']!='Provo' or float(c.get('numberOfVehicles') or 0)<1:continue
        modes=crash_modes(o)
        if modes:selected[o['sourceRecordId']]=(o,modes)
    years=sorted({_date(o['observedAt']).year for o,_ in selected.values()})
    output=[]
    for year in years:
        annual={'year':year,'total':0,**{k:0 for k in MODE_KEYS},'months':[0]*12,
                'hours':[[0]*7 for _ in range(24)],'unknownTime':0,
                'severity':{k:0 for k in ['Fatal','Serious','Minor','Possible','No injury','Unknown']},'complete':year<=complete_through}
        for o,modes in selected.values():
            d=_date(o['observedAt'])
            if d.year!=year:continue
            annual['total']+=1
            for mode in modes:annual[mode]+=1
            annual['months'][d.month-1]+=1
            if o.get('timePrecision') in {'second','microsecond','minute'}:annual['hours'][d.hour][d.weekday()]+=1
            else:annual['unknownTime']+=1
            severity={'1':'No injury','2':'Possible','3':'Minor','4':'Serious','5':'Fatal'}.get(str(o['metadata']['crash'].get('crashSeverity')),'Unknown')
            annual['severity'][severity]+=1
        assert sum(annual['months'])==annual['total']==sum(annual['severity'].values())
        assert sum(sum(row) for row in annual['hours'])+annual['unknownTime']==annual['total']
        output.append(annual)
    return {'annual':output,'coverageEnd':max((_date(o['observedAt']).date().isoformat() for o,_ in selected.values()),default=None),
            'completeThrough':complete_through,'sourceUrl':'https://utaps.shinyapps.io/DataPortalAWS/',
            'scope':'State portal crashes classified as Provo, with at least one reported motor vehicle.',
            'modeMethod':'Person type 4 = bicycle, 3 = pedestrian, 5 = other conveyance. Involvement flags are used only when these person types are absent. A crash involving multiple modes appears in multiple mode lines; total counts it once.'}
