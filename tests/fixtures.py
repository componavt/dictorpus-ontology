"""Shared synthetic RuWordNet fixtures for tests."""
import os


def write_rwn(root, synsets, relations, senses=None):
    """Create a minimal RuWordNet dump in `root`.

    synsets:  list of (id, ruthes_name, definition, part_of_speech)
    relations: list of (name, child_id, parent_id)
    senses:   list of (id, name, synset_id)
    """
    os.makedirs(root, exist_ok=True)
    by_pos = {}
    for sid, name, definition, pos in synsets:
        suffix = {'N': 'N', 'Adj': 'A', 'V': 'V'}[pos]
        by_pos.setdefault(suffix, []).append((sid, name, definition, pos))
    for suffix, items in by_pos.items():
        with open(os.path.join(root, 'synsets.%s.xml' % suffix), 'w',
                  encoding='utf-8') as fh:
            fh.write('<synsets>\n')
            for sid, name, definition, _pos in items:
                fh.write('  <synset id="%s" ruthes_name="%s" definition="%s" '
                         'part_of_speech="%s"><sense id="%s-s"/></synset>\n'
                         % (_esc(sid), _esc(name), _esc(definition),
                            _esc(_pos_of(sid, items)), _esc(sid + '-s')))
            fh.write('</synsets>\n')
    with open(os.path.join(root, 'synset_relations.N.xml'), 'w',
              encoding='utf-8') as fh:
        fh.write('<relations>\n')
        for name, child, parent in relations:
            fh.write('  <relation name="%s" child_id="%s" parent_id="%s"/>\n'
                     % (_esc(name), _esc(child), _esc(parent)))
        fh.write('</relations>\n')
    for suffix in ('A', 'V'):
        path = os.path.join(root, 'synset_relations.%s.xml' % suffix)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('<relations/>\n')
    if senses is None:
        senses = []
    for suffix in ('N', 'A', 'V'):
        with open(os.path.join(root, 'senses.%s.xml' % suffix), 'w',
                  encoding='utf-8') as fh:
            fh.write('<senses>\n')
            for sid, name, synset_id in senses:
                fh.write('  <sense id="%s" name="%s" lemma="%s" '
                         'synset_id="%s" part_of_speech="N"/>\n'
                         % (_esc(sid), _esc(name), _esc(name),
                            _esc(synset_id)))
            fh.write('</senses>\n')
    return root


def _pos_of(sid, items):
    for i_sid, _n, _d, pos in items:
        if i_sid == sid:
            return pos
    return 'N'


def _esc(s):
    return (s.replace('&', '&amp;').replace('<', '&lt;')
             .replace('>', '&gt;').replace('"', '&quot;'))
