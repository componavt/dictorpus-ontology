"""Readers for the dictorpus-data export (stdlib only).

Conventions of the export (per README):
- meanings_*/examples_*/lemmas_* are CSV compressed with Zstandard;
- semantics tables are uncompressed TSV;
- an empty cell is an empty string, a literal "\\N" cell is SQL NULL.
Both are treated as "no value" downstream, but tracked separately.
"""
import csv
import hashlib
import io
import os
from compression import zstd

LANGS = ('vep', 'krl', 'olo', 'lud')
NULL_TOKEN = r'\N'


def norm_value(value):
    """Map an export cell to (text, was_null). NULL and '' -> ('', flag)."""
    if value is None:
        return '', False
    value = value.strip('\r\n')
    if value == NULL_TOKEN:
        return '', True
    return value, False


def read_zst_csv(path):
    """Decompress a .csv.zst export and return list of dict rows."""
    with open(path, 'rb') as fh:
        raw = zstd.decompress(fh.read())
    text = raw.decode('utf-8-sig')
    return list(csv.DictReader(io.StringIO(text)))


def read_tsv(path):
    """Read an uncompressed TSV table into list of dict rows."""
    with open(path, encoding='utf-8-sig', newline='') as fh:
        return list(csv.DictReader(fh, delimiter='\t'))


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def input_inventory(data_dir):
    """All files used by the inventory, with size and sha256."""
    rels = []
    for lang in LANGS:
        rels.append('dict/meanings_%s.csv.zst' % lang)
        rels.append('dict/examples_%s.csv.zst' % lang)
        rels.append('dict/morphology/lemmas_%s.csv.zst' % lang)
    rels.append('semantics/concepts.csv')
    rels.append('semantics/concept_categories_wdh.tsv')
    files = []
    for rel in rels:
        path = os.path.join(data_dir, rel)
        files.append({'name': rel, 'size_bytes': os.path.getsize(path),
                      'sha256': sha256_of(path)})
    return files
