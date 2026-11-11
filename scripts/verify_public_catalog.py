"""Compare every restored file against production or an explicitly selected staging host."""
import argparse
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

HOST='https://bikewalk-provo-data-hub.vercel.app'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('public',type=Path)
p.add_argument('--stage')
a=p.parse_args()
base=(a.stage or HOST).rstrip('/')
headers={'Origin':'https://projects.bikewalkprovo.org'}
if a.stage:
    if not re.fullmatch(r'https://bikewalk-provo-data-[a-z0-9]+-brycepjs-projects\.vercel\.app',base):
        raise ValueError('Unexpected staging host')
    result=subprocess.run(['vercel','curl','/?x-vercel-set-bypass-cookie=true','--deployment',base,'--scope=brycepjs-projects','--','--head'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,text=True)
    cookies=re.findall(r'^set-cookie:\s*([^=;\s]+=[^;\r\n]*)',result.stdout,re.I|re.M)
    if cookies:
        headers['Cookie']='; '.join(cookies)
if not (a.public/'catalog.json').is_file():
    raise ValueError('Missing local catalog')


def verify(path):
    url=base+'/'+path.relative_to(a.public).as_posix()
    with urlopen(Request(url,headers=headers),timeout=60) as response:
        if urlparse(response.geturl()).hostname!=urlparse(url).hostname or response.read()!=path.read_bytes() or response.headers.get('Access-Control-Allow-Origin')!='*':
            raise ValueError('Public release mismatch: '+url)
        mime={'.csv':'text/csv','.json':'application/json','.geojson':'application/geo+json','.zip':'application/zip'}.get(path.suffix)
        if mime and response.headers.get_content_type()!=mime:
            raise ValueError('Unexpected MIME type: '+url)
        if path.suffix=='.zip' and response.headers.get('Content-Disposition','').split(';')[0].strip().lower()!='attachment':
            raise ValueError('ZIP must download as an attachment: '+url)

paths=sorted(path for path in a.public.rglob('*') if path.is_file())
with ThreadPoolExecutor(5) as pool:
    list(pool.map(verify,paths))
print(f'Checked {len(paths)} files on {base}')

