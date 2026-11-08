import csv, json, hashlib, re, subprocess, sys
from pathlib import Path
from datetime import date
import xlrd
root=Path(sys.argv[1]).resolve()
output=Path(sys.argv[2])
output.mkdir(parents=True,exist_ok=False)
commit='5f46d516876cd7d71a7a87f819e7b3eddf3c9135'
def git(*args):
 return subprocess.check_output(['git','-C',str(root),*args])
def blob(p):
 return git('show',f'{commit}:{p}')
inventory=[]
def record(p,year,role):
 raw=blob(p)
 inventory.append(dict(path=p,year=year,role=role,sha256=hashlib.sha256(raw).hexdigest(),snapshot_commit_date=git('log','-1','--format=%cs',commit,'--',p).decode().strip(),inventory_date='2026-11-07'))
 return raw
cross={}
for year in (2019,2021,2022,2023,2024,2025,2026):
 p=f'apps/maps/public/data/active-transportation-counts/{year}'
 origin='2026 hosted station layer' if year==2026 else ('historical ArcGIS view' if year<=2022 else 'historical ArcGIS base')
 raw=record(p+'.csv',year,origin);record(p+'.json',year,origin)
 cols=next(csv.reader(raw.decode().splitlines()))
 m={}
 for key in cols:
  if key in ('OBJECTID','FID','StreetName','x','y'):
   m[key]=dict(role='station metadata',decision='retain ID and name; omit coordinates');continue
  name=key.lower().replace('bicyle','bicycle')
  mt=re.fullmatch(r'[yf](?:\d\d)?(bicycle|ped|scoot|other|total)([fm]?)(?:_(t|sat))?',name)
  if not mt:raise ValueError(key)
  mode,part,period=mt.groups()
  m[key]=dict(role='measure',mode=dict(bicycle='bicycle',ped='walking',scoot='scooter',other='other',total='all')[mode],breakdown=part.upper() or 'total',slot={'t':'session_1','sat':'session_2',None:'combined'}[period],decision='source count mapped directly; cross-year protocol equivalence unverified')
 cross[str(year)]=m
files=sorted(root / p for p in git('ls-tree','-r','--name-only',commit).decode().splitlines() if '/assets/count-' in p and p.endswith(('.xls','.pptx')))
for p in files:
 if p.suffix in ('.xls','.pptx'):
  raw=record(str(p.relative_to(root)),2019,'protocol and station evidence')
  if p.suffix=='.xls':sheet=xlrd.open_workbook(file_contents=raw).sheet_by_name('NBPD Data Sheet')
for p in ['docs/active-transportation-counts-rollout.md','docs/active-transportation-counts-2026-inventory.md']:
 record(p,None,'protocol evidence')
historical=json.loads(blob('apps/maps/public/data/active-transportation-counts/2019.json'))
audit=[]
for col in range(1,14):
 r=next(r for r in historical if r['OBJECTID']==col)
 for slot,suffix,date_row,time_row,first in [(1,'T',45,46,48),(2,'Sat',55,56,58)]:
  def cell(row):
   return sheet.cell_value(row-1,col)
  diffs={}
  for ix,mode in enumerate(['Bicycle','Ped','Other','BicycleF']):
   key=f'Y19{mode}_{suffix}'
   v=cell(first+ix);v=None if v=='' else v
   if v!=r[key]:diffs[key]=[v,r[key]]
  audit.append(dict(id=col,workbook_station=cell(27),export_station=r['StreetName'],slot=slot,date=cell(date_row),window=cell(time_row),has_count=any(cell(first+i)!='' for i in range(3)),differences=diffs))
def save(p,v):(output / p).write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
save('sources.json',dict(repository='bpj-repos/bikewalk-provo',commit=commit,inputs=inventory));save('crosswalk.json',cross);save('workbook-review.json',audit)
print('Discrepancies:',[(r['id'],r['slot'],r['differences']) for r in audit if r['differences']]);print(sum(r['has_count'] for r in audit),'observed workbook sessions')
