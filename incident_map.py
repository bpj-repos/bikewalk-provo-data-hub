"""Reproduce a reviewed incident-map package from checksummed private presentation inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from danger_zones.incident_summary import add_summaries
from danger_zones.validate_normalized import validate_snapshot

ROOT = Path(__file__).resolve().parent
NAME = 'provo-active-transportation-incident-map'
METHOD = '''This historical, reviewed map extract covers 2018-01 through 2026-09. It preserves the published November 2 selection, approximate points, source associations and prepared summaries. A feature is a mapped source-record group, not necessarily a unique crash. Unreconciled sources can describe the same event. Do not sum this layer as the official annual crash series; use annual-at-crash-aggregates for that purpose.

The private pipeline normalizes retained PD, UDOT and state portal observations using reviewed common and derived catalogs, then binds summaries to the exact existing source identifiers and snapshots. Four of 1,199 selected record groups lack accepted map positions; 1,195 are mapped. Coordinates are rounded to four decimals. PD dates are report dates, not established occurrence dates. Missing source values remain unavailable; unknown flags are not No. Crash severity and AT-person injuries are separate measures. Source conflicts and source coverage remain visible. No new source records, matches, coordinates or inferred times are introduced by this migration. This version predates later PD intake and reconciliation; it is not the current operational collection.

Updates: receive data privately through update_crashes.py, review source selection and public fields, normalize and derive using the hub catalogs, review any changed groupings separately, and prepare a new checksummed presentation receipt. Rebuild with incident_map.py. The existing source-snapshot guard rejects an accidental mix of old feature selection and new sources. Candidate generation never promotes a release or changes an app pin. A correction is a patch; compatible records are a minor release; changed record meaning or field semantics require a major release. Withdrawals follow OPERATIONS.md and apply to consumer copies too.
'''
DICTIONARY = {'schemaVersion':1, 'format':'GeoJSON FeatureCollection (RFC 7946)',
    'identity':'Source identifiers in properties.details qualify each record. Array position is not a longitudinal identity.',
    'fields':[
        {'name':'geometry','type':'Point','description':'Longitude, latitude; WGS84, rounded to four decimals. Approximate.'},
        {'name':'properties.mode','type':'string','description':'Reviewed reported travel category; source conflict remains in details and overview.'},
        {'name':'properties.month','type':'string','format':'YYYY-MM','description':'Historical display month. Inspect prepared dates for occurrence versus PD report date.'},
        {'name':'properties.source','type':'string','description':'Historical display label. Prepared filters.sources and details retain source-specific provenance.'},
        {'name':'properties.details','type':'object','description':'Approved source-prefixed scalar fields. Police, UDOT, Portal and Provenance namespaces. Missing/null is not a negative value; nested person/vehicle records are source-qualified text, not stable person identities.'},
        {'name':'properties.prepared.version','type':'integer','description':'Prepared-view schema version, currently 1.'},
        {'name':'properties.prepared.filters','type':'object','description':'Arrays: years, modeGroups, fineModes, crashSeverity, factors, lighting, sources. atSeverity is a string: serious-fatal, other, unknown. OR within a filter, AND across filters; an empty selected year/mode/source set matches nothing.'},
        {'name':'properties.prepared.overview','type':'object','description':'Source-qualified dates, location labels, injury/severity and circumstances arrays; boolean modeConflict; availability and timeNotes arrays. These are prepared shared interpretations, not app recalculations.'},
        {'name':'properties.summary','type':'array','description':'Sections {heading, entries:[{key,label,values:[{text,sources: string[]}]}]}. Only reviewed common concepts appear; full-precision location.point is excluded.'},
    ]}


def encoded(value):
    return (json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def checked(path, expected):
    raw=path.read_bytes()
    if sha(raw)!=expected:
        raise ValueError('Input checksum mismatch: '+path.name)
    return raw


def build(receipt_path, output):
    receipt=json.loads(receipt_path.read_bytes())
    if receipt.get('kind')!='reviewed-incident-map' or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)',receipt['version']):
        raise ValueError('Expected a reviewed receipt and numeric version')
    if output.exists() or not output.resolve().is_relative_to(ROOT/'private'):
        raise ValueError('Use a new private hub directory')
    def ref(key):
        item=receipt[key]
        path=(receipt_path.parent/item['path']).resolve()
        if not path.is_relative_to(ROOT/'private'):
            raise ValueError('Receipt escaped private inputs')
        return path,checked(path,item['sha256'])
    normalized,nraw=ref('normalized')
    derived,draw=ref('derived')
    base,braw=ref('base')
    legacy,lraw=ref('mapManifest')
    nmeta,dmeta,manifest=map(json.loads,(nraw,draw,lraw))
    definitions=receipt['definitions']
    if not re.fullmatch('[a-z0-9-]+',definitions):
        raise ValueError('Invalid definition identity')
    rules=ROOT/'incident-map-contracts'/definitions
    validate_snapshot(normalized.parent,rules/'common.yml',rules/'fields.yml',rules/'references')
    if (dmeta['normalizedManifestSha256']!=sha(nraw) or dmeta['rulesSha256']!=sha((rules/'derived.yml').read_bytes())
            or dmeta['kind']!='source-qualified-derived-incidents'):
        raise ValueError('Derived snapshot differs from reviewed definitions')
    rows=[json.loads(line) for line in (normalized.parent/'observations.jsonl').read_text().splitlines()]
    data=checked(derived.parent/'derived.jsonl',dmeta['sha256'])
    derived_rows=[json.loads(line) for line in data.decode().splitlines()]
    by_id={r['observationId']:r for r in derived_rows}
    if len(by_id)!=len(derived_rows) or any(r['issues'] for r in derived_rows):
        raise ValueError('Ambiguous/unreviewed derived values')
    for key,table in [('udot-crashes','udot.arcgis'),('utah-crash-portal','portal.crashes')]:
        if next(s for s in manifest['sourceCoverage'] if s['sourceKey']==key)['snapshotId']!=nmeta['sources'][table]['snapshotId']:
            raise ValueError('Source snapshot changed; review feature selection separately')
    layer=add_summaries(json.loads(braw),rows,by_id)
    raw=(json.dumps(layer,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode()
    if sha(raw)!=manifest['sha256'] or len(layer['features'])!=manifest['mappedCount']:
        raise ValueError('Rebuilt presentation differs from the approved map')
    files={'incidents.geojson':raw,'map-manifest.json':lraw,'dictionary.json':encoded(DICTIONARY),'method.txt':METHOD.encode()}
    version=receipt['version']
    package=dict(name=NAME,version=version,title='Reviewed active transportation incident map in Provo',
        records=len(layer['features']),coverage={'fromMonth':manifest['fromMonth'],'toMonth':manifest['toMonth'],
        'selected':manifest['recordCount'],'unmapped':manifest['omittedCount']},
        sourceRelease=manifest['releaseId'],sourceCoverage=manifest['sourceCoverage'],
        preparation='Reviewed historical normalized and derived snapshots; existing feature selection preserved.',
        attribution='Provo Police Department, UDOT and Utah Crash Data Portal. Prepared by BikeWalk Provo.',
        reuse='Existing source-specific publication permissions apply. This map extract does not grant rights beyond those source terms; it is not covered by the counts CC0 decision.',
        citation=f'BikeWalk Provo. Reviewed active transportation incident map in Provo, {version}. https://bikewalk-provo-data-hub.vercel.app/datasets/{NAME}/{version}/datapackage.json',
        resources=[dict(name=Path(k).stem,path=k,bytes=len(v),hash='sha256:'+sha(v)) for k,v in files.items()])
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        stage=Path(temp)/'package';stage.mkdir()
        for k,v in {**files,'datapackage.json':encoded(package)}.items():
            (stage/k).write_bytes(v)
        # Reuse the existing public-field, provenance and geographic validators.
        (stage/'incidents.json').write_bytes(raw)
        (stage/'manifest.json').write_bytes(lraw)
        validator=(ROOT/'tools/incident-map/police-demo-data.mjs').as_uri()
        subprocess.run(['node','--input-type=module','-e',f'import {{validateDemoRelease}} from {json.dumps(validator)};validateDemoRelease(process.argv[1]);',str(stage)],check=True)
        (stage/'incidents.json').unlink();(stage/'manifest.json').unlink()
        stage.rename(output)
    print(json.dumps(dict(version=version,sha256=sha(encoded(package)),records=package['records'],bytes=sum(len(v) for v in files.values()))))
    return package


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('receipt',type=Path)
    p.add_argument('output',type=Path)
    args=p.parse_args()
    build(args.receipt.resolve(),args.output.resolve())
