"""Streaming readers for RuWordNet XML dumps (stdlib only).

All functions are generators over top-level records; element trees are freed
as soon as a record is consumed, so full XML documents are never held in
memory. External entities/DTD are not fetched (expat default in iterparse);
no file in this delivery declares a DTD, so no parse workaround is applied.
"""
import hashlib
import os
from xml.etree import ElementTree as ET

SYNSET_FILES = ('synsets.N.xml', 'synsets.A.xml', 'synsets.V.xml')
RELATION_FILES = ('synset_relations.N.xml', 'synset_relations.A.xml',
                  'synset_relations.V.xml')
SENSE_FILES = ('senses.N.xml', 'senses.A.xml', 'senses.V.xml')
INPUT_FILES = SYNSET_FILES + RELATION_FILES + SENSE_FILES


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def iter_synsets(path):
    """Yield dicts: {id, ruthes_name, definition, part_of_speech, sense_ids}."""
    depth = 0
    record = None
    for event, el in ET.iterparse(path, events=('start', 'end')):
        if event == 'start':
            depth += 1
            if depth == 2 and el.tag == 'synset':
                record = {
                    'id': el.get('id'),
                    'ruthes_name': el.get('ruthes_name'),
                    'definition': el.get('definition') or '',
                    'part_of_speech': el.get('part_of_speech'),
                    'sense_ids': [],
                }
        else:
            depth -= 1
            if depth == 2 and el.tag == 'sense' and record is not None:
                record['sense_ids'].append(el.get('id'))
            elif depth == 1 and el.tag == 'synset':
                yield record
                record = None
            if depth <= 1:
                el.clear()


def iter_relations(path):
    """Yield dicts: {name, child_id, parent_id, source_file}."""
    base = os.path.basename(path)
    for event, el in ET.iterparse(path, events=('end',)):
        if el.tag == 'relation':
            yield {
                'name': el.get('name'),
                'child_id': el.get('child_id'),
                'parent_id': el.get('parent_id'),
                'source_file': base,
            }
            el.clear()


def iter_senses(path):
    """Yield dicts: {id, name, lemma, synset_id} (fields needed for lemmas)."""
    for event, el in ET.iterparse(path, events=('end',)):
        if el.tag == 'sense':
            yield {
                'id': el.get('id'),
                'name': el.get('name'),
                'lemma': el.get('lemma'),
                'synset_id': el.get('synset_id'),
            }
            el.clear()


def read_synsets(rwn_dir):
    """Read all synsets.*.xml; return (registry, diagnostics).

    registry: id -> synset dict; diagnostics records duplicate ids and
    conflicts (same id with differing name/pos/definition).
    """
    registry = {}
    diag = {'synset_rows': 0, 'duplicate_synset_ids': 0,
            'synset_id_conflicts': []}
    for fname in SYNSET_FILES:
        path = os.path.join(rwn_dir, fname)
        for rec in iter_synsets(path):
            diag['synset_rows'] += 1
            sid = rec['id']
            if sid in registry:
                diag['duplicate_synset_ids'] += 1
                old = registry[sid]
                if (old['ruthes_name'], old['part_of_speech'],
                        old['definition']) != (
                        rec['ruthes_name'], rec['part_of_speech'],
                        rec['definition']):
                    diag['synset_id_conflicts'].append(sid)
            else:
                registry[sid] = rec
    return registry, diag


def read_relations(rwn_dir):
    """Read all synset_relations.*.xml; return (rows, xml_counts)."""
    rows = []
    xml_counts = {}
    for fname in RELATION_FILES:
        path = os.path.join(rwn_dir, fname)
        for rec in iter_relations(path):
            rows.append(rec)
            key = (fname, rec['name'])
            xml_counts[key] = xml_counts.get(key, 0) + 1
    return rows, xml_counts


def read_lemmas_for(rwn_dir, synset_ids):
    """Read senses.*.xml and return {synset_id: [lemma, ...]} for given ids."""
    want = set(synset_ids)
    lemmas = {}
    for fname in SENSE_FILES:
        path = os.path.join(rwn_dir, fname)
        for rec in iter_senses(path):
            sid = rec['synset_id']
            if sid in want:
                value = rec['lemma'] or rec['name']
                if value:
                    lemmas.setdefault(sid, [])
                    if value not in lemmas[sid]:
                        lemmas[sid].append(value)
    return lemmas
