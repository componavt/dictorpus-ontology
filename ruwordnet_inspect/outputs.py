"""Stage F output writers: TSV, JSON, manifest and the human report.

TSV files are written with csv.writer(delimiter='\\t'); fields are never
concatenated by hand.
"""
import csv
import io
import json
import os


def write_json(path, payload):
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=False)
        fh.write('\n')


def _write_tsv(path, header, rows):
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.writer(fh, delimiter='\t', lineterminator='\n')
        writer.writerow(header)
        writer.writerows(rows)


def write_manifest(path, manifest):
    write_json(path, manifest)


def write_domains_tsv(path, catalog, extra):
    """extra: {domain_id: {parents, children, hypernyms_outside, isolated}}."""
    header = ['domain_id', 'ruthes_name', 'definition', 'assigned_count',
              'count_N', 'count_Adj', 'count_V', 'multi_domain_assigned',
              'direct_parent_domains', 'direct_child_domains',
              'hypernyms_outside_domain_set', 'isolated_in_direct_subgraph',
              'lemmas']
    rows = []
    for d in sorted(catalog):
        e = catalog[d]
        x = extra[d]
        rows.append([
            d,
            e['ruthes_name'] or '',
            e['definition'],
            e['assigned_count'],
            e['pos_counts']['N'], e['pos_counts']['Adj'], e['pos_counts']['V'],
            e['multi_domain_assigned'],
            '; '.join(x['parents']),
            '; '.join(x['children']),
            x['hypernyms_outside'],
            'yes' if x['isolated'] else 'no',
            '; '.join(e.get('lemmas', [])),
        ])
    _write_tsv(path, header, rows)


def write_assignments_tsv(path, assignments):
    _write_tsv(path, ['synset_id', 'domain_id'],
               [[s, d] for (s, d) in assignments])


def write_direct_tsv(path, direct_edges, catalog):
    rows = []
    for child, parent in direct_edges:
        rows.append([
            child,
            parent,
            (catalog.get(child) or {}).get('ruthes_name') or '',
            (catalog.get(parent) or {}).get('ruthes_name') or '',
        ])
    _write_tsv(path,
               ['child_domain_id', 'parent_domain_id',
                'child_ruthes_name', 'parent_ruthes_name'],
               rows)


def write_projected_tsv(path, projected, catalog):
    rows = []
    for d in sorted(projected):
        for anc in sorted(projected[d]):
            info = projected[d][anc]
            rows.append([
                d,
                anc,
                (catalog.get(d) or {}).get('ruthes_name') or '',
                (catalog.get(anc) or {}).get('ruthes_name') or '',
                info['kind'],
                info['path_length'],
                json.dumps(info['witness_path'], ensure_ascii=False),
            ])
    _write_tsv(path,
               ['domain_id', 'ancestor_domain_id', 'domain_ruthes_name',
                'ancestor_ruthes_name', 'kind', 'path_length', 'witness_path'],
               rows)


def write_overlaps_tsv(path, rows, catalog):
    out = []
    for r in rows:
        out.append([
            r['domain_a'], r['domain_b'],
            (catalog.get(r['domain_a']) or {}).get('ruthes_name') or '',
            (catalog.get(r['domain_b']) or {}).get('ruthes_name') or '',
            r['intersection'], r['size_a'], r['size_b'],
            '%.4f' % r['jaccard'], '%.4f' % r['share_of_smaller'],
        ])
    _write_tsv(path,
               ['domain_a', 'domain_b', 'name_a', 'name_b', 'common_synsets',
                'size_a', 'size_b', 'jaccard', 'share_of_smaller'],
               out)


def write_graph_json(path, domain_ids, catalog, direct_edges, proj_edges):
    nodes = []
    for d in sorted(domain_ids):
        e = catalog[d]
        nodes.append({
            'domain_id': d,
            'ruthes_name': e['ruthes_name'],
            'assigned_count': e['assigned_count'],
        })
    edges = []
    for child, parent in sorted(direct_edges):
        edges.append({
            'type': 'direct_hypernym',
            'source': child,   # more specific domain
            'target': parent,  # more general domain
        })
    for child, parent in sorted(proj_edges):
        edges.append({
            'type': 'projected_nearest_ancestor',
            'source': child,
            'target': parent,
        })
    write_json(path, {'nodes': nodes, 'edges': edges})


def write_report_md(path, data):
    """Human report in Russian; `data` is a plain dict assembled by build."""
    buf = io.StringIO()
    w = buf.write

    w('# Обозреватель доменной схемы RuWordNet — отчёт\n\n')
    w('Поставка: %s. Инструмент: ruwordnet_inspect %s.\n\n'
      % (data['source_dir'], data['tool_version']))
    w('Отчёт построен автоматически из локальных XML; числа воспроизводятся '
      'командой из manifest.json.\n\n')

    w('## Что является доменом в этой поставке\n\n')
    w('Домены — это обычные синсеты (все — существительные, N), назначенные '
      'связями `domain`; отдельного справочника доменов в поставке нет. '
      'Ниже — только фактически найденные связи, никаких добавленных '
      'категорий.\n\n')

    w('## Ключевые числа\n\n')
    w('- синсетов: %d; XML-записей domain: %d; уникальных назначений '
      'synset→domain: %d\n' % (data['synset_count'], data['domain_xml_rows'],
                               data['assignment_pairs']))
    w('- уникальных доменов: %d; синсетов с прямым назначением: %d (%.1f%%)\n'
      % (data['domain_count'], data['assigned_synsets'],
         data['assigned_share_pct']))
    w('- дубликаты XML-записей domain: %d; неразрешённые ссылки: %d\n'
      % (data['domain_duplicates'], data['unresolved_count']))
    w('- XML-записей hypernym между доменами: %d; уникальных рёбер между '
      'доменами: %d\n' % (data['hypernym_between_xml'],
                          data['hypernym_between_unique']))
    w('\n')

    w('## Два представления графа доменов\n\n')
    w('**Непосредственный подграф доменов** (рёбра hypernym, оба конца — '
      'домены):\n\n')
    w('- узлов: %d; уникальных рёбер: %d\n'
      % (data['direct']['node_count'], data['direct']['unique_edge_count']))
    w('- без родительского домена: %d; без дочерних: %d; изолированных: %d\n'
      % (data['direct']['no_parent'], data['direct']['no_child'],
         data['direct']['isolated']))
    w('- с несколькими родителями: %d; слабосвязных компонент: %d\n'
      % (data['direct']['multi_parent'], data['direct']['weak_components']))
    w('- петель: %d; сильно связных компонент (размер >1): %d\n\n'
      % (data['direct']['self_loops'], data['direct']['scc_gt1']))
    why_not_tree = []
    if data['direct']['isolated']:
        why_not_tree.append('изолированные домены (%d)'
                            % data['direct']['isolated'])
    if data['direct']['multi_parent']:
        why_not_tree.append('многородительские узлы (%d)'
                            % data['direct']['multi_parent'])
    if data['direct']['weak_components'] > 1:
        why_not_tree.append('%d слабосвязных компонент'
                            % data['direct']['weak_components'])
    if why_not_tree:
        w('Единым деревом это не является: %s.\n\n'
          % '; '.join(why_not_tree))
    else:
        w('Структура связна и без многородительских узлов.\n\n')
    w('**Проецированный граф** (ближайшие доменные предки через недоменные '
      'узлы):\n\n')
    w('- рёбер всего: %d; из них direct: %d, via_non_domain: %d\n'
      % (data['proj']['total'], data['proj']['direct'],
         data['proj']['via']))
    w('- доменов, получивших хотя бы одного проецированного предка помимо '
      'прямых: %d\n' % data['proj']['gained_extra'])
    w('- предупреждений о циклах: %d\n\n' % data['proj']['warnings'])
    w('Различие: непосредственный подграф видит только связи домен→домен; '
      'проецированный добавляет предков, достижимых через промежуточные '
      'недоменные синсеты, останавливаясь на первом встреченном домене.\n\n')

    w('## 15 крупнейших доменов\n\n')
    w('| домен | ID | всего | N | Adj | V |\n')
    w('|-------|----|-------|---|-----|---|\n')
    for e in data['top15']:
        w('| %s | %s | %d | %d | %d | %d |\n'
          % (e['ruthes_name'], e['domain_id'], e['assigned_count'],
             e['pos_counts']['N'], e['pos_counts']['Adj'],
             e['pos_counts']['V']))
    w('\n')

    w('## Примеры ветвей\n\n')
    for line in data['branch_samples']:
        w('- %s\n' % line)
    w('\n')

    w('## Пересечения доменов (топ-10 по абсолютному пересечению)\n\n')
    w('| A | B | общих | |A| | |B| | Jaccard |\n')
    w('|---|---|-------|----|----|---------|\n')
    for r in data['overlaps_top']:
        w('| %s | %s | %d | %d | %d | %.3f |\n'
          % (r['name_a'], r['name_b'], r['intersection'], r['size_a'],
             r['size_b'], r['jaccard']))
    w('\nПересечения — статистика совместной привязки синсетов; они не '
      'превращаются в иерархические отношения.\n\n')

    w('## Ограничения\n\n')
    for line in data['limitations']:
        w('- %s\n' % line)
    w('\n')

    w('## Локальный исследовательский результат. Условия публикации не '
      'установлены.\n')

    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(buf.getvalue())
