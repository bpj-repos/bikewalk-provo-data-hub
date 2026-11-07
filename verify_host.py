"""Compare every anonymous HTTPS response with the verified synthetic build."""
import argparse
import urllib.error
import urllib.request

from release import VERSIONS, expected

HOST = 'https://bikewalk-provo-data-hub.vercel.app'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--first', action='store_true')
args = parser.parse_args()
files = expected(VERSIONS[:1] if args.first else VERSIONS)
for path, data in files.items():
    request = urllib.request.Request(HOST + '/' + path, headers={'Origin': 'https://projects.bikewalkprovo.org'})
    with urllib.request.urlopen(request, timeout=30) as response:
        mime = response.headers.get_content_type()
        if path.endswith('.csv') and mime != 'text/csv' or path.endswith('.json') and mime != 'application/json':
            raise RuntimeError(f'{path}: unexpected MIME type {mime}')
        if response.headers.get('Access-Control-Allow-Origin') != '*' or response.read() != data:
            raise RuntimeError(f'{path}: CORS or byte mismatch')
print(f'{len(files)} public resources verified')
