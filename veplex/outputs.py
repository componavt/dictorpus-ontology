"""Writers and the inventory pipeline runner (task 006 outputs)."""
import csv
import json
import os

from . import __version__
from . import inventory as inv
from . import sources


def write_tsv(path, header, rows):
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.writer(fh, delimiter='\t', lineterminator='\n')
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def write_json(path, payload):
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
        fh.write('\n')


LANG_ORDER = {'vep': 0, 'krl': 1, 'olo': 2, 'lud': 3}


def run_inventory(data_dir, out_dir):
    data_dir = os.path.abspath(data_dir)
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    started = inv._now()

    registry, links, diag = inv.build_registry(data_dir)
    ref = inv.load_reference(data_dir)
    links_resolved, broken_concepts, category_mismatches = \
        inv.link_table(links, ref)
    stats = inv.summarize(registry, links_resolved, ref, diag)
    wdh_rows, multi_cat_sememes = inv.wdh_overview(
        registry, links_resolved, ref, stats)

    # --- sememes.tsv ---
    header = ['lang', 'meaning_id', 'lemma_id', 'meaning_n', 'lemma', 'pos',
              'meaning_ru', 'ru_null', 'meaning_en', 'n_examples',
              'concept_ids', 'n_concepts', 'categories_chain',
              'categories_export']
    rows = []
    for (lang, mid) in sorted(registry, key=lambda k: (LANG_ORDER.get(k[0], 9), int(k[1]) if k[1].isdigit() else 0)):
        s = registry[(lang, mid)]
        sem_links = stats['links_by_sememe'].get((lang, mid), [])
        concept_ids = sorted({l['concept_id'] for l in sem_links
                              if l['concept_id']})
        rows.append([
            lang, mid, s['lemma_id'], s['meaning_n'], s['lemma'], s['pos'],
            s['meaning_ru'], 'yes' if s['ru_null'] else '',
            s['meaning_en'],
            len(ref['examples'].get((lang, mid), [])),
            ';'.join(concept_ids), len(concept_ids),
            ';'.join(sorted(stats['sem_cats_chain'].get((lang, mid), ()))),
            ';'.join(sorted(stats['sem_cats_export'].get((lang, mid), ()))),
        ])
    write_tsv(os.path.join(out_dir, 'sememes.tsv'), header, rows)

    # --- sememe_examples.tsv (first example per sememe, for B1 hints) ---
    first_examples = []
    for (lang, mid), texts in sorted(ref['examples'].items()):
        if texts and (lang, mid) in registry and texts[0]:
            first_examples.append([lang, mid, texts[0]])
    write_tsv(os.path.join(out_dir, 'sememe_examples.tsv'),
              ['lang', 'meaning_id', 'example'], first_examples)

    # --- sememe_concepts.tsv ---
    write_tsv(
        os.path.join(out_dir, 'sememe_concepts.tsv'),
        ['lang', 'meaning_id', 'concept_id', 'concept_ru',
         'category_id_export', 'category_id_chain', 'category_known'],
        [[l['lang'], l['meaning_id'], l['concept_id'], l['concept_ru'],
          l['category_export'], l['category_chain'],
          'yes' if l['category_known'] else 'no']
         for l in links_resolved])

    # --- summary tables ---
    lang_metrics = ['file_rows', 'sememes', 'with_ru', 'ru_null', 'with_en',
                    'unique_raw_formulations', 'unique_norm_formulations',
                    'with_example', 'with_concept', 'multi_concept',
                    'with_category_chain', 'with_category_export']
    write_tsv(os.path.join(out_dir, 'summary_by_lang.tsv'),
              ['lang'] + lang_metrics,
              [[lang] + [stats['per_lang'][lang].get(m, 0)
                         for m in lang_metrics]
               for lang in sorted(stats['per_lang'],
                                  key=lambda l: LANG_ORDER.get(l, 9))])
    pos_metrics = ['sememes', 'with_ru', 'with_example', 'with_concept',
                   'with_category_chain']
    write_tsv(os.path.join(out_dir, 'summary_by_lang_pos.tsv'),
              ['lang', 'pos'] + pos_metrics,
              [[k.split('|')[0], k.split('|')[1]]
               + [v.get(m, 0) for m in pos_metrics]
               for k, v in stats['per_lang_pos'].items()])
    write_tsv(os.path.join(out_dir, 'lemmas_summary.tsv'),
              ['lang'] + list(next(iter(stats['lemmas_summary'].values()),
                                   {}).keys()),
              [[lang] + list(vals.values())
               for lang, vals in sorted(stats['lemmas_summary'].items(),
                                        key=lambda kv: LANG_ORDER.get(kv[0], 9))])
    top_rows = []
    for lang in sorted(stats['formulation_counts'],
                       key=lambda l: LANG_ORDER.get(l, 9)):
        for norm, n in stats['formulation_counts'][lang].most_common(15):
            if n >= 5:
                top_rows.append([lang, norm, n])
    write_tsv(os.path.join(out_dir, 'formulations_top.tsv'),
              ['lang', 'formulation_normalized', 'n_sememes'], top_rows)

    # --- quality tables ---
    write_tsv(os.path.join(out_dir, 'conflicts.tsv'),
              ['lang', 'meaning_id', 'differing_fields', 'first', 'second'],
              [[c['lang'], c['meaning_id'], ';'.join(c['differing_fields']),
                json.dumps(c['first'], ensure_ascii=False),
                json.dumps(c['second'], ensure_ascii=False)]
               for c in diag['field_conflicts']])
    broken_rows = ([['concept_id_unresolved', l['lang'], l['meaning_id'],
                     l['concept_id']] for l in broken_concepts]
                   + [['lemma_id_unresolved', r['lang'], r['meaning_id'],
                       r['lemma_id']] for r in stats['broken_lemma_refs']]
                   + [['example_unknown_meaning', k[0], k[1], '']
                      for k in stats['example_broken']])
    write_tsv(os.path.join(out_dir, 'broken_links.tsv'),
              ['type', 'lang', 'meaning_id', 'ref'], broken_rows)
    write_tsv(os.path.join(out_dir, 'category_mismatches.tsv'),
              ['lang', 'meaning_id', 'concept_id', 'category_export',
               'category_chain'],
              [[m['lang'], m['meaning_id'], m['concept_id'],
                m['category_export'], m['category_chain']]
               for m in category_mismatches])

    # --- WDH overview ---
    write_tsv(os.path.join(out_dir, 'categories_wdh_overview.tsv'),
              ['category_id', 'name_ru', 'wdh', 'n_concepts', 'n_sememes',
               'examples'],
              [[r['category_id'], r['name_ru'], r['wdh'], r['n_concepts'],
                r['n_sememes'], ' || '.join(r['examples'])]
               for r in wdh_rows])

    # --- manifest ---
    manifest = {
        'started_at': started,
        'finished_at': inv._now(),
        'tool': {'name': 'veplex', 'version': __version__},
        'params': {'data_dir': data_dir, 'out_dir': out_dir},
        'data': {
            'source': 'dictorpus-data snapshot (git clone by tag)',
            'tag': 'v2026.13',
            'commit_sha': inv.git_commit_of(data_dir),
            'inputs': sources.input_inventory(data_dir),
        },
        'notes': {
            'registry_key': '(lang, meaning_id)',
            'sememe': 'one dictionary meaning of an article',
            'provenance': 'Derived locally from the public dictorpus-data '
                          'export; working artifact, not published.',
        },
    }
    write_json(os.path.join(out_dir, 'manifest.json'), manifest)

    # --- report.md (Russian, human) ---
    report = _build_report(registry, diag, ref, stats, wdh_rows,
                           multi_cat_sememes, broken_concepts,
                           category_mismatches, manifest)
    with open(os.path.join(out_dir, 'report.md'), 'w',
              encoding='utf-8') as fh:
        fh.write(report)

    totals = {
        'sememes': len(registry),
        'per_lang': stats['per_lang'],
        'pos_total': stats['pos_total'],
        'multi_cat_sememes': multi_cat_sememes,
        'field_conflicts': len(diag['field_conflicts']),
        'broken_links': len(broken_rows),
        'category_mismatches': len(category_mismatches),
        'outputs': sorted(os.listdir(out_dir)),
    }
    return totals


def _build_report(registry, diag, ref, stats, wdh_rows, multi_cat_sememes,
                  broken_concepts, category_mismatches, manifest):
    per_lang = stats['per_lang']
    total = {m: sum(v.get(m, 0) for v in per_lang.values())
             for m in ('file_rows', 'sememes', 'with_ru', 'ru_null',
                       'with_en', 'with_example', 'with_concept',
                       'multi_concept', 'with_category_chain',
                       'with_category_export')}
    uniq_raw = sum(v['unique_raw_formulations'] for v in per_lang.values())
    uniq_norm = sum(v['unique_norm_formulations'] for v in per_lang.values())
    n_langs = len(per_lang)

    lines = []
    lines.append('# Инвентаризация словарных значений ВепКар (veplex, этап A)\n')
    lines.append('Снимок: dictorpus-data %s, commit %s. Сборка: %s, '
                 'инструмент veplex %s.\n'
                 % (manifest['data']['tag'],
                    (manifest['data']['commit_sha'] or '?')[:9],
                    manifest['finished_at'], manifest['tool']['version']))
    lines.append('## Объём материала\n')
    lines.append('| язык | строк файла | семем | с толкованием ru | '
                 'с примерами | с концептом | с категорией (цепочка) |\n')
    lines.append('|------|-------------|-------|------------------|'
                 '------------|-------------|------------------------|\n')
    for lang in sorted(per_lang, key=lambda l: LANG_ORDER.get(l, 9)):
        v = per_lang[lang]
        lines.append('| %s | %d | %d | %d | %d | %d | %d |\n'
                     % (lang, v['file_rows'], v['sememes'], v['with_ru'],
                        v['with_example'], v['with_concept'],
                        v['with_category_chain']))
    lines.append('| **итого** | **%d** | **%d** | **%d** | **%d** | **%d** | '
                 '**%d** |\n'
                 % (total['file_rows'], total['sememes'], total['with_ru'],
                    total['with_example'], total['with_concept'],
                    total['with_category_chain']))
    share_ru = 100.0 * total['with_ru'] / total['sememes']
    share_cat = 100.0 * total['with_category_chain'] / total['sememes']
    lines.append('\nИтого семем: %d; с русским толкованием: %d (%.1f%%); '
                 'уникальных формулировок: %d сырых, %d нормализованных; '
                 'семем с несколькими концептами: %d.\n'
                 % (total['sememes'], total['with_ru'], share_ru,
                    uniq_raw, uniq_norm, total['multi_concept']))
    lines.append('Связь со старой системой (через концепт → WDH-категория): '
                 '%d семем (%.1f%%); многодоменных (2+ категории): %d.\n'
                 % (total['with_category_chain'], share_cat,
                    multi_cat_sememes))

    lines.append('\n## Части речи (все языки)\n\n')
    lines.append('| pos | семем |\n|-----|-------|\n')
    for pos, n in sorted(stats['pos_total'].items(),
                         key=lambda kv: -kv[1]):
        lines.append('| %s | %d |\n' % (pos, n))

    lines.append('\n## Леммы\n\n')
    lines.append('| язык | лемм в реестре | со значениями | без значений | '
                 '1 знач. | 2 знач. | 3+ знач. |\n')
    lines.append('|------|----------------|---------------|--------------|'
                 '---------|---------|----------|\n')
    for lang, v in sorted(stats['lemmas_summary'].items(),
                          key=lambda kv: LANG_ORDER.get(kv[0], 9)):
        lines.append('| %s | %d | %d | %d | %d | %d | %d |\n'
                     % (lang, v['lemmas_registry'], v['lemmas_with_sememes'],
                        v['lemmas_without_sememes'],
                        v['sememes_per_lemma_1'], v['sememes_per_lemma_2'],
                        v['sememes_per_lemma_3plus']))

    lines.append('\n## Качество данных\n')
    lines.append('- повторов meaning_id (связь с 2 концептами): ожидается 2 '
                 '(30328 krl, 33481 lud); конфликтов полей: %d; дублей строк: '
                 '%d; коллизий meaning_id между языками: %d.\n'
                 % (len(diag['field_conflicts']),
                    sum(diag['row_duplicates'].values()),
                    len(diag['cross_lang_id_collisions'])))
    lines.append('- неразрешённых ссылок: концепты %d, леммы %d, примеры %d; '
                 'несовпадений category_id (экспорт vs цепочка): %d.\n'
                 % (len(broken_concepts), len(stats['broken_lemma_refs']),
                    len(stats['example_broken']), len(category_mismatches)))

    cats_with = [r for r in wdh_rows if r['n_sememes'] > 0]
    cats_without = [r for r in wdh_rows if r['n_sememes'] == 0]
    lines.append('\n## Старые категории (WDH)\n')
    lines.append('Категорий всего: %d; с хотя бы одной семемой: %d; пустых: '
                 '%d. Сумма семем по категориям больше числа '
                 'категоризированных семем из-за многодоменных (%d).\n'
                 % (len(wdh_rows), len(cats_with), len(cats_without),
                    multi_cat_sememes))
    lines.append('\nТоп-10 категорий по числу семем:\n\n'
                 '| cat | название | wdh | семем |\n'
                 '|-----|----------|-----|-------|\n')
    for r in sorted(cats_with, key=lambda r: -r['n_sememes'])[:10]:
        lines.append('| %s | %s | %s | %d |\n'
                     % (r['category_id'], r['name_ru'][:40], r['wdh'][:30],
                        r['n_sememes']))

    lines.append('\n## Готовность к этапу B\n')
    if share_ru >= 90:
        lines.append('- Русская сторона покрывает %.1f%% семем — материала '
                     'для смыслового анализа достаточно.\n' % share_ru)
    else:
        lines.append('- Внимание: только %.1f%% семем имеют русское '
                     'толкование — оценить судьбу остальных до '
                     'группировки.\n' % share_ru)
    if total['with_example'] < total['sememes'] * 0.2:
        lines.append('- Примеры есть лишь у %d семем — для кратких '
                     'толкований контекст будет дефицитом.\n'
                     % total['with_example'])
    lines.append('- Наиболее переиспользуемые формулировки — '
                  'formulations_top.tsv (кандидаты в омонимичные группы).\n')
    lines.append('- SQL-дамп у разработчика не запрашивался.\n')
    lines.append('\nПроизводный рабочий артефакт по публичной выгрузке '
                 'dictorpus-data; не публиковался.\n')
    return ''.join(lines)
