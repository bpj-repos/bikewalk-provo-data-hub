"""Check every file in a rebuilt release against the public HTTPS alias."""
import argparse
import urllib.request
from pathlib import Path

HOST='https://bikewalk-provo-data-hub.vercel.app/'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('public',type=Path)
root=p.parse_args().public
paths=sorted(p for p in root.rglob('*') if p.is_file())
if not (root/'catalog.json').is_file():
    raise ValueError('Missing local catalog')
for path in paths:
    url=HOST+path.relative_to(root).as_posix()
    with urllib.request.urlopen(urllib.request.Request(url,headers={'Origin':'https://projects.bikewalkprovo.org'}),timeout=30) as r:
        if r.read()!=path.read_bytes() or r.headers.get('Access-Control-Allow-Origin')!='*':
            raise ValueError(f'Public release mismatch: {url}')
        mime={'.csv':'text/csv','.json':'application/json'}.get(path.suffix)
        if mime and r.headers.get_content_type()!=mime:
            raise ValueError(f'Unexpected MIME type: {url}')
print(f'Anonymous checks passed for {len(paths)} public files')
