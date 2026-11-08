"""Parse source rows from the two retained Provo PD forwarded table formats."""
from datetime import datetime
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
import re


class Rows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        elif tag in ('th','td') and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def read_forward_rows(path):
    msg = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    html = msg.get_body(preferencelist=('html',))
    if html is None:
        raise ValueError('Missing HTML report table')
    parser = Rows()
    parser.feed(html.get_content())
    rows = parser.rows
    title_row = bool(rows and rows[0] == ['BikeWalk ProvoTraffic Accidents Data'])
    if title_row:
        rows = rows[1:]
    timed = ['Case Number:', 'Date of Report:', 'Address:', 'Type:']
    dated = ['number','dtrepor','agency','street']
    if not rows or rows[0] not in (timed, dated+['desc'], dated+['Type']):
        raise ValueError('Unrecognized PD table header')
    out = []
    for n,r in enumerate(rows[1:],start=2+int(title_row)):
        if len(r)!=len(rows[0]) or not re.fullmatch(r'\d{2}PR[A-Z]?\d+',r[0]):
            raise ValueError('Unexpected police row')
        if rows[0]==timed:
            key,raw,address,mode=r
            when=datetime.strptime(raw,'%m/%d/%Y %I:%M:%S %p')
        else:
            key,raw,agency,address,mode=r
            if agency!='PRPD':
                raise ValueError('Unexpected agency')
            when=datetime.strptime(raw,'%m/%d/%Y').date()
        if not mode:
            raise ValueError('Missing police travel mode')
        out.append(dict(incident_id=key,observed_at=when,location_raw=address,mode_raw=mode,
                        source_row=n,source_sheet='Forwarded message',source_table='PD report table',
                        source_headers=rows[0],source_cells=r))
    if not out:
        raise ValueError('Empty PD delivery')
    return out
