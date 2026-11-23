"""Stage A (task 006): sememe registry, counts, WDH overview, outputs.

Registry unit: one dictionary meaning = (lang, meaning_id). A repeated
meaning_id that differs only in id/concept_id/category_id is one sememe
with several concept links (README: 30328 krl, 33481 lud). A repeated
key with differing sememe fields is a recorded conflict, never silently
resolved. Sememes are never merged by identical meaning_ru and
meaning_ru is never split by commas.
"""
import datetime
import os
import re
import subprocess
from collections import Counter, defaultdict

from . import __version__
from . import sources

SEMEME_FIELDS = ('lemma_id', 'meaning_n', 'lemma', 'pos',
                 'meaning_ru', 'meaning_en')


def _now():
    return datetime.datetime.now().isoformat(timespec='seconds')


def git_commit_of(path):
    try:
        res = subprocess.run(['git', '-C', path, 'rev-parse', 'HEAD'],
                             capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return None


def _norm_formulation(text):
    return re.sub(r'\s+', ' ', text.casefold()).strip(' .;')


def build_registry(data_dir):
    """Read all meanings; return (registry, links, diagnostics).

    registry: (lang, meaning_id) -> sememe dict with SEMEME_FIELDS
              plus ru_null/en_null flags.
    links: list of dicts {lang, meaning_id, concept_id, category_export}.
    """
    registry = {}
    links = []
    diag = {'file_rows': Counter(), 'row_duplicates': Counter(),
            'field_conflicts': [], 'cross_lang_id_collisions': set(),
            'ids_by_lang': defaultdict(set)}
    for lang in sources.LANGS:
        path = os.path.join(data_dir, 'dict', 'meanings_%s.csv.zst' % lang)
        rows = sources.read_zst_csv(path)
        diag['file_rows'][lang] = len(rows)
        for row in rows:
            mid = (row.get('meaning_id') or '').strip()
            key = (lang, mid)
            ru, ru_null = sources.norm_value(row.get('meaning_ru'))
            en, en_null = sources.norm_value(row.get('meaning_en'))
            fields = {
                'lemma_id': (row.get('lemma_id') or '').strip(),
                'meaning_n': (row.get('meaning_n') or '').strip(),
                'lemma': (row.get('lemma') or '').strip(),
                'pos': (row.get('pos') or '').strip(),
                'meaning_ru': ru,
                'meaning_en': en,
            }
            link = {
                'lang': lang, 'meaning_id': mid,
                'concept_id': (row.get('concept_id') or '').strip(),
                'category_export': (row.get('category_id') or '').strip(),
            }
            diag['ids_by_lang'][lang].add(mid)
            if key in registry:
                existing = registry[key]
                if all(existing[f] == fields[f] for f in SEMEME_FIELDS):
                    if link in links:
                        diag['row_duplicates'][lang] += 1
                    links.append(link)
                else:
                    diff = [f for f in SEMEME_FIELDS
                            if existing[f] != fields[f]]
                    diag['field_conflicts'].append({
                        'lang': lang, 'meaning_id': mid,
                        'differing_fields': diff,
                        'first': {f: existing[f] for f in diff},
                        'second': {f: fields[f] for f in diff},
                    })
            else:
                registry[key] = dict(fields, ru_null=ru_null, en_null=en_null)
                links.append(link)
    # meaning_id values reused across languages (allowed but tracked)
    seen = {}
    for lang in sources.LANGS:
        for mid in diag['ids_by_lang'][lang]:
            if mid in seen and seen[mid] != lang:
                diag['cross_lang_id_collisions'].add((seen[mid], lang, mid))
            else:
                seen[mid] = lang
    return registry, links, diag


def load_reference(data_dir):
    """Concepts, WDH categories, lemma registries, example index."""
    concepts_rows = sources.read_tsv(
        os.path.join(data_dir, 'semantics', 'concepts.csv'))
    concept_by_id = {}
    concept_dupes = []
    for row in concepts_rows:
        cid = (row.get('concept_id') or '').strip()
        cat = (row.get('category_id') or '').strip()
        if cid in concept_by_id:
            if concept_by_id[cid]['category_id'] != cat:
                concept_dupes.append(cid)
        else:
            concept_by_id[cid] = {
                'category_id': cat,
                'concept_ru': (row.get('concept_ru') or '').strip(),
                'concept_en': (row.get('concept_en') or '').strip(),
            }
    categories = {}
    for row in sources.read_tsv(os.path.join(
            data_dir, 'semantics', 'concept_categories_wdh.tsv')):
        cid = (row.get('category_id') or '').strip()
        categories[cid] = {
            'name_ru': (row.get('name_ru') or '').strip(),
            'name_en': (row.get('name_en') or '').strip(),
            'wdh': (row.get('wdh') or '').strip(),
        }
    lemmas = {}
    for lang in sources.LANGS:
        rows = sources.read_zst_csv(os.path.join(
            data_dir, 'dict', 'morphology', 'lemmas_%s.csv.zst' % lang))
        lemmas[lang] = {(row.get('lemma_id') or '').strip()
                        for row in rows if (row.get('lemma_id') or '').strip()}
    examples = defaultdict(list)   # (lang, meaning_id) -> [example, ...]
    for lang in sources.LANGS:
        rows = sources.read_zst_csv(os.path.join(
            data_dir, 'dict', 'examples_%s.csv.zst' % lang))
        for row in rows:
            mid = (row.get('meaning_id') or '').strip()
            text, _ = sources.norm_value(row.get('example'))
            examples[(lang, mid)].append(text)
    return {'concepts': concept_by_id, 'categories': categories,
            'concept_dupes': concept_dupes, 'lemmas': lemmas,
            'examples': examples}


def link_table(links, ref):
    """Resolve every sememe-concept link; detect mismatches and breaks."""
    out = []
    broken_concepts = []
    category_mismatches = []
    for link in links:
        chain_cat = ''
        concept_ru = ''
        concept_id = link['concept_id']
        if concept_id:
            concept = ref['concepts'].get(concept_id)
            if concept is None:
                broken_concepts.append(link)
            else:
                chain_cat = concept['category_id']
                concept_ru = concept['concept_ru']
        export_cat = link['category_export']
        if chain_cat and export_cat and export_cat != chain_cat:
            category_mismatches.append({
                'lang': link['lang'], 'meaning_id': link['meaning_id'],
                'concept_id': concept_id,
                'category_export': export_cat, 'category_chain': chain_cat,
            })
        out.append({
            **link, 'concept_ru': concept_ru, 'category_chain': chain_cat,
            'category_known': chain_cat in ref['categories'],
        })
    return out, broken_concepts, category_mismatches


def summarize(registry, links_resolved, ref, diag):
    """All counts used by the report; per language and per lang x pos."""
    links_by_sememe = defaultdict(list)
    sem_cats_chain = defaultdict(set)
    sem_cats_export = defaultdict(set)
    for link in links_resolved:
        key = (link['lang'], link['meaning_id'])
        links_by_sememe[key].append(link)
        if link['category_chain']:
            sem_cats_chain[key].add(link['category_chain'])
        if link['category_export']:
            sem_cats_export[key].add(link['category_export'])

    per_lang = {}
    per_lang_pos = defaultdict(Counter)
    pos_total = Counter()
    formulations_raw = defaultdict(set)
    formulations_norm = defaultdict(set)
    formulation_counts = defaultdict(Counter)
    for (lang, mid), s in registry.items():
        sem_links = links_by_sememe.get((lang, mid), [])
        cats_chain = sem_cats_chain.get((lang, mid), set())
        n_examples = len(ref['examples'].get((lang, mid), []))
        row = Counter({
            'sememes': 1,
            'with_ru': 1 if s['meaning_ru'] else 0,
            'ru_null': 1 if s['ru_null'] else 0,
            'with_en': 1 if s['meaning_en'] else 0,
            'with_example': 1 if n_examples else 0,
            'with_concept':
                1 if any(l['concept_id'] for l in sem_links) else 0,
            'multi_concept':
                1 if len({l['concept_id'] for l in sem_links
                          if l['concept_id']}) >= 2 else 0,
            'with_category_chain': 1 if cats_chain else 0,
            'with_category_export':
                1 if sem_cats_export.get((lang, mid)) else 0,
        })
        per_lang_pos[(lang, s['pos'])].update(row)
        pos_total[s['pos']] += 1
        per_lang.setdefault(lang, Counter()).update(row)
        if s['meaning_ru']:
            formulations_raw[lang].add(s['meaning_ru'])
            norm = _norm_formulation(s['meaning_ru'])
            formulations_norm[lang].add(norm)
            formulation_counts[lang][norm] += 1
    for lang in per_lang:
        per_lang[lang] = dict(per_lang[lang])
        per_lang[lang]['file_rows'] = diag['file_rows'].get(lang, 0)
        per_lang[lang]['unique_raw_formulations'] = len(formulations_raw[lang])
        per_lang[lang]['unique_norm_formulations'] = \
            len(formulations_norm[lang])

    # lemma coverage
    sem_by_lemma = defaultdict(set)
    broken_lemma_refs = []
    for (lang, mid), s in registry.items():
        sem_by_lemma[(lang, s['lemma_id'])].add(mid)
        if s['lemma_id'] and \
                s['lemma_id'] not in ref['lemmas'].get(lang, set()):
            broken_lemma_refs.append({'lang': lang, 'meaning_id': mid,
                                      'lemma_id': s['lemma_id']})
    lemmas_summary = {}
    for lang in sources.LANGS:
        all_lemmas = ref['lemmas'].get(lang, set())
        with_sem = {lid for (l, lid) in sem_by_lemma if l == lang}
        dist = Counter(len(mids) for (l, _lid), mids
                       in sem_by_lemma.items() if l == lang)
        lemmas_summary[lang] = {
            'lemmas_registry': len(all_lemmas),
            'lemmas_with_sememes': len(with_sem),
            'lemmas_without_sememes': len(all_lemmas - with_sem),
            'sememes_per_lemma_1': dist.get(1, 0),
            'sememes_per_lemma_2': dist.get(2, 0),
            'sememes_per_lemma_3plus':
                sum(n for k, n in dist.items() if k >= 3),
        }

    example_broken = sorted(
        key for key in ref['examples'] if key not in registry)

    return {
        'per_lang': per_lang,
        'per_lang_pos': {'%s|%s' % k: dict(v)
                         for k, v in sorted(per_lang_pos.items())},
        'pos_total': dict(pos_total),
        'lemmas_summary': lemmas_summary,
        'formulation_counts': formulation_counts,
        'links_by_sememe': links_by_sememe,
        'sem_cats_chain': sem_cats_chain,
        'sem_cats_export': sem_cats_export,
        'broken_lemma_refs': broken_lemma_refs,
        'example_broken': example_broken,
    }


def wdh_overview(registry, links_resolved, ref, stats, max_examples=5):
    """Category table with concept counts, unique sememes, examples."""
    concepts_by_cat = Counter(
        c['category_id'] for c in ref['concepts'].values()
        if c['category_id'] in ref['categories'])
    sem_by_cat = defaultdict(set)
    for link in links_resolved:
        if link['category_chain']:
            sem_by_cat[link['category_chain']].add(
                (link['lang'], link['meaning_id']))
    rows = []
    for cat_id in sorted(ref['categories']):
        meta = ref['categories'][cat_id]
        sem_keys = sorted(sem_by_cat.get(cat_id, ()))
        examples = []
        for (lang, mid) in sem_keys[:max_examples]:
            s = registry.get((lang, mid), {})
            ru = (s.get('meaning_ru') or '')[:60]
            examples.append('%s:%s | %s | %s | %s'
                            % (lang, mid, s.get('lemma', ''),
                               s.get('pos', ''), ru))
        rows.append({
            'category_id': cat_id,
            'name_ru': meta['name_ru'],
            'wdh': meta['wdh'],
            'n_concepts': concepts_by_cat.get(cat_id, 0),
            'n_sememes': len(sem_keys),
            'examples': examples,
        })
    multi = sum(1 for key, cats in stats['sem_cats_chain'].items()
                if len(cats) >= 2)
    return rows, multi
