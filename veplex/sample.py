"""B1: stratified deterministic sample of толкования for the GLM review.

Three strata per the agreed plan: random per language, shortest
one-word-ish translations (ambiguity risk), longest descriptive
definitions. A dictionary example is attached to short толкования where
available (context hint). No rubric list is used at sampling time.
"""
import csv
import os
import random

LANG_ORDER = {'vep': 0, 'krl': 1, 'olo': 2, 'lud': 3}
EXAMPLE_TRIGGER_LEN = 15
EXAMPLE_MAX_CHARS = 100


def load_sememes(out_dir):
    path = os.path.join(out_dir, 'sememes.tsv')
    with open(path, encoding='utf-8', newline='') as fh:
        rows = list(csv.DictReader(fh, delimiter='\t'))
    examples = {}
    ex_path = os.path.join(out_dir, 'sememe_examples.tsv')
    if os.path.exists(ex_path):
        with open(ex_path, encoding='utf-8', newline='') as fh:
            for row in csv.DictReader(fh, delimiter='\t'):
                key = (row['lang'], row['meaning_id'])
                examples.setdefault(key, row['example'])
    return rows, examples


def build_sample(out_dir, per_lang=60, n_short=25, n_long=25, seed=42):
    rows, examples = load_sememes(out_dir)
    with_ru = [r for r in rows if r['meaning_ru']]
    picked = {}   # (lang, meaning_id) -> sample_kind

    rng = random.Random(seed)
    for lang in sorted({r['lang'] for r in with_ru},
                       key=lambda l: LANG_ORDER.get(l, 9)):
        pool = sorted((r for r in with_ru if r['lang'] == lang),
                      key=lambda r: int(r['meaning_id'])
                      if r['meaning_id'].isdigit() else 0)
        take = min(per_lang, len(pool))
        for r in rng.sample(pool, take):
            picked[(r['lang'], r['meaning_id'])] = 'random'

    by_len = sorted(with_ru, key=lambda r: (len(r['meaning_ru']),
                                            LANG_ORDER.get(r['lang'], 9),
                                            r['meaning_id']))
    for r in by_len[:n_short]:
        picked.setdefault((r['lang'], r['meaning_id']), 'short')
    for r in by_len[-n_long:]:
        picked.setdefault((r['lang'], r['meaning_id']), 'long')

    by_key = {(r['lang'], r['meaning_id']): r for r in rows}
    ordered = sorted(picked, key=lambda k: (
        LANG_ORDER.get(k[0], 9), k[1].zfill(12)))
    out_rows = []
    for i, key in enumerate(ordered, 1):
        r = by_key[key]
        ru = r['meaning_ru']
        hint = ''
        if len(ru) <= EXAMPLE_TRIGGER_LEN:
            hint = examples.get(key, '')[:EXAMPLE_MAX_CHARS]
        out_rows.append([i, picked[key], r['lang'], r['meaning_id'],
                         r['lemma'], r['pos'], ru, hint])
    return out_rows


def write_sample(out_dir, rows):
    path = os.path.join(out_dir, 'b1_sample.tsv')
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.writer(fh, delimiter='\t', lineterminator='\n')
        writer.writerow(['n', 'stratum', 'lang', 'meaning_id', 'lemma',
                         'pos', 'meaning_ru', 'example_hint'])
        writer.writerows(rows)
    return path
