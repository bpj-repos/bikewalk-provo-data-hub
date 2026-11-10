"""Readable export projection. Never mutate retained source observations."""
from functools import lru_cache
import json
import re

from .common_structure import CONTRACT, read_contract
from .field_inventory import read_catalog


def field_label(key):
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', key).replace('_', ' ').strip().capitalize()


@lru_cache(maxsize=1)
def definitions():
    catalog = read_catalog()
    books = {k: v['codes'] for k, v in read_contract(catalog=catalog)['codebooks'].items()}
    extra = json.loads(CONTRACT.with_name('export-codes.json').read_text())
    if extra['schemaVersion'] != 1:
        raise ValueError('Unsupported export codebook')
    for concept, book in extra['codebooks'].items():
        if 'sameAs' not in book:
            if book['reference'] not in catalog['references']:
                raise ValueError('Unknown export codebook reference')
            books[concept] = book['codes']
    for concept, book in extra['codebooks'].items():
        if 'sameAs' in book:
            books[concept] = books[book['sameAs']]
    return catalog['tables'], books


def export_values(table, values):
    """Fold companion labels into their base fields, decoding code-only categories."""
    tables, books = definitions()
    fields = tables[table]['fields']
    companions = {}
    for key, binding in fields.items():
        if key.endswith('_label'):
            bases = [k for k, b in fields.items() if b['concept'] == binding['concept'] and b['representation'] == 'code']
            companions[key] = bases[0] if bases else key.removesuffix('_label')
    result = {}
    for key, value in values.items():
        if key in companions:
            continue
        binding = fields.get(key, {})
        if binding.get('representation') == 'code' and value is not None and value != '':
            code = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value).strip()
            book = books.get(binding['concept'], {})
            token = str(int(code)) if code.isascii() and code.isdecimal() else code
            value = book.get(code, book.get(token, 'Unmapped code: ' + code if token.isdecimal() else value))
        result[key] = value
    for companion, base in companions.items():
        if companion in values:
            supplied = values[companion]
            if supplied is not None and supplied != '' and supplied != 'Unavailable':
                result[base] = supplied
            elif base not in result:
                result[base] = supplied
    return result


def export_display_fields(table, fields):
    """Migrate the existing public label/value projection without raw private inputs."""
    tables, _ = definitions()
    keys = {field_label(k): k for k in tables[table]['fields']}
    seen = {}
    for field in fields:
        if field['label'] in seen and seen[field['label']] != field['value']:
            raise ValueError('Conflicting duplicate exported field: ' + field['label'])
        seen[field['label']] = field['value']
    values = {keys.get(f['label'], f['label']): f['value'] for f in fields}
    exported = export_values(table, values)
    return [{'label': field_label(k) if k in tables[table]['fields'] or k not in values else k, 'value': v}
            for k, v in exported.items()]
