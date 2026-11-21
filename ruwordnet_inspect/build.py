"""Build pipeline: stages A-F of the domain browser plus stage G checks.

Read-only towards the source XML: files are only opened for reading, and
input hashes are verified again after the build to prove nothing changed.
"""
import datetime
import os
import subprocess
import time

from . import __version__
from . import graphs, model, outputs, overlaps as overlaps_mod
from . import xmlsource
from .htmlview import write_index_html
from .printview import write_print_html

# Reference numbers from audit report 001 (2026-11-19). Used for
# cross-checking only; the build never adjusts results to match.
AUDIT_REFERENCE = {
    'synset_count': 59905,
    'domain_xml_rows': 38608,
    'domain_count': 144,
    'assigned_synsets': 25374,
    'hypernym_between_xml': 38,
}


def _now():
    return datetime.datetime.now().isoformat(timespec='seconds')


def _git_commit():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        res = subprocess.run(['git', '-C', repo, 'rev-parse', 'HEAD'],
                             capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return None


def _git_ignored(path):
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        res = subprocess.run(['git', '-C', repo, 'check-ignore', '-q', path],
                             capture_output=True, timeout=10)
        return res.returncode == 0
    except Exception:
        return None


def build(ruwordnet_dir, out_dir):
    """Run the whole pipeline; return a summary dict for the caller."""
    started_at = _now()
    t0 = time.monotonic()
    ruwordnet_dir = os.path.abspath(ruwordnet_dir)
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    # ---- inputs and hashes (stage A) ----
    inputs = []
    input_hashes = {}
    for fname in xmlsource.INPUT_FILES:
        path = os.path.join(ruwordnet_dir, fname)
        digest = xmlsource.sha256_of(path)
        input_hashes[fname] = digest
        inputs.append({'name': fname, 'size_bytes': os.path.getsize(path),
                       'sha256': digest})

    registry, synset_diag = xmlsource.read_synsets(ruwordnet_dir)
    rel_rows, xml_counts = xmlsource.read_relations(ruwordnet_dir)

    # Direction per audit 001: source = parent_id, target = child_id.
    # Verified on synthetic fixtures in tests; mismatches would surface as
    # unreadable direction samples below, never silently reversed.
    relations = model.NormalizedRelations()
    for row in rel_rows:
        if row['name'] in model.DIRECTED_BY_AUDIT:
            relations.add(row['name'], row['parent_id'], row['child_id'],
                          row['source_file'],
                          resolve=lambda sid: sid in registry)
        else:
            relations.other_names[row['name']] = \
                relations.other_names.get(row['name'], 0) + 1
    direction_samples = model.check_direction_examples(relations, registry)

    # ---- domain catalog (stage B) ----
    domain_ids, catalog, assignments = model.build_domain_catalog(
        relations, registry)
    lemmas = xmlsource.read_lemmas_for(ruwordnet_dir, domain_ids)
    for d in domain_ids:
        catalog[d]['lemmas'] = lemmas.get(d, [])
    model.attach_examples(catalog, registry, per_pos=5)

    assigned_synsets = len({s for (s, _d) in assignments})
    assignment_counts = {}
    for (s, _d) in assignments:
        assignment_counts[s] = assignment_counts.get(s, 0) + 1
    multi_domain_synsets = sum(1 for n in assignment_counts.values() if n >= 2)
    total_synsets = len(registry)

    # ---- direct subgraph (stage C) ----
    domain_set = set(domain_ids)
    hyper_edges = relations.unique_edges('hypernym')
    direct_edges = [(s, t) for (s, t) in hyper_edges
                    if s in domain_set and t in domain_set]
    # XML record count between domains (before dedup), for the audit check
    hypernym_between_xml = sum(
        1 for row in rel_rows
        if row['name'] == 'hypernym'
        and row['parent_id'] in domain_set and row['child_id'] in domain_set)
    direct = graphs.direct_subgraph_metrics(domain_ids, direct_edges)

    # ---- projected graph (stage D) ----
    projected, warnings, proj_edges = graphs.project_all(domain_ids,
                                                         hyper_edges)
    witness_errors = graphs.validate_witnesses(
        projected, set(hyper_edges), domain_set)

    # per-domain extras
    hyper_adj = graphs.adjacency(hyper_edges)
    direct_parents = {}
    direct_children = {}
    for child, parent in direct_edges:
        direct_parents.setdefault(child, []).append(parent)
        direct_children.setdefault(parent, []).append(child)
    extras = {}
    for d in domain_ids:
        extras[d] = {
            'parents': sorted(direct_parents.get(d, [])),
            'children': sorted(direct_children.get(d, [])),
            'hypernyms_outside': sum(1 for t in hyper_adj.get(d, ())
                                     if t not in domain_set),
            'isolated': d in set(direct['isolated_nodes']),
        }

    # ---- overlaps (stage E) ----
    overlap_rows = overlaps_mod.domain_overlaps(catalog)
    top_inter = overlaps_mod.top_by_intersection(overlap_rows, 20)
    top_jacc = overlaps_mod.top_by_jaccard(overlap_rows, 20)

    # ---- stage G checks ----
    domain_xml_rows = relations.xml_rows.get('domain', 0)
    domain_duplicates = len(relations.duplicates)
    checks = {
        'reference': {},
        'pos_sum_matches_assignments': None,
        'examples_belong_to_domain': True,
        'witness_errors': witness_errors,
        'input_files_unchanged': None,
        'out_dir_git_ignored': _git_ignored(out_dir),
        'duplicate_edges': domain_duplicates,
        'unresolved_count': len(relations.unresolved),
        'hypernym_between_xml': hypernym_between_xml,
    }
    for key, expected in AUDIT_REFERENCE.items():
        actual = {
            'synset_count': total_synsets,
            'domain_xml_rows': domain_xml_rows,
            'domain_count': len(domain_ids),
            'assigned_synsets': assigned_synsets,
            'hypernym_between_xml': hypernym_between_xml,
        }[key]
        checks['reference'][key] = {
            'expected': expected, 'actual': actual,
            'match': expected == actual,
        }
    pos_sum = sum(catalog[d]['pos_counts']['N'] + catalog[d]['pos_counts']['Adj']
                  + catalog[d]['pos_counts']['V'] for d in domain_ids)
    checks['pos_sum_matches_assignments'] = (pos_sum == len(assignments))
    for d, entry in catalog.items():
        allowed = set(entry['assigned_synsets'])
        for _pos, items in entry['examples'].items():
            for sample in items:
                if sample['synset_id'] not in allowed:
                    checks['examples_belong_to_domain'] = False

    # ---- outputs (stage F) ----
    outputs.write_manifest(os.path.join(out_dir, 'manifest.json'), {
        'started_at': started_at,
        'finished_at': _now(),
        'duration_sec': round(time.monotonic() - t0, 1),
        'tool': {'name': 'ruwordnet_inspect', 'version': __version__,
                 'git_commit': _git_commit()},
        'params': {'ruwordnet_dir': ruwordnet_dir, 'out_dir': out_dir},
        'inputs': inputs,
        'provenance': {
            'source': 'local RuWordNet dump, archive rwn-2021-05-02 '
                      '(version taken from the archive name)',
            'note_ru': 'Локальный исследовательский результат. '
                       'Условия публикации не установлены.',
            'note_en': 'Local research result. Publication terms are not '
                       'established.',
        },
    })
    outputs.write_domains_tsv(os.path.join(out_dir, 'domains.tsv'),
                              catalog, extras)
    outputs.write_assignments_tsv(
        os.path.join(out_dir, 'domain_assignments.tsv'), assignments)
    outputs.write_direct_tsv(os.path.join(out_dir, 'domain_hypernyms_direct.tsv'),
                             direct_edges, catalog)
    outputs.write_projected_tsv(
        os.path.join(out_dir, 'domain_hypernyms_projected.tsv'),
        projected, catalog)
    outputs.write_overlaps_tsv(os.path.join(out_dir, 'domain_overlaps.tsv'),
                               overlap_rows, catalog)
    outputs.write_graph_json(os.path.join(out_dir, 'domains_graph.json'),
                             domain_ids, catalog, direct_edges, proj_edges)

    html_data = _html_payload(ruwordnet_dir, started_at, total_synsets,
                              domain_xml_rows, len(assignments),
                              assigned_synsets, hypernym_between_xml,
                              domain_ids, catalog, extras, projected, direct,
                              warnings, proj_edges)
    html_data['meta']['multi_domain_synsets'] = multi_domain_synsets
    write_index_html(os.path.join(out_dir, 'index.html'), html_data)
    write_print_html(os.path.join(out_dir, 'print.html'), html_data,
                     multi_domain_synsets)

    outputs.write_report_md(
        os.path.join(out_dir, 'report.md'),
        _report_payload(ruwordnet_dir, total_synsets, domain_xml_rows,
                        len(assignments), assigned_synsets, domain_ids,
                        catalog, registry, direct, projected, warnings,
                        proj_edges, top_inter, direction_samples, checks))

    diagnostics = {
        'synsets': synset_diag,
        'relations': {
            'xml_rows_per_file': {'%s|%s' % k: v
                                  for k, v in sorted(xml_counts.items())},
            'xml_rows_per_name': relations.xml_rows,
            'other_relation_names_ignored': relations.other_names,
            'unique_edges_per_name': {
                name: sum(1 for (r, _s, _t) in relations.edges if r == name)
                for name in sorted({r for (r, _s, _t) in relations.edges})},
            'duplicate_edge_occurrences': domain_duplicates,
            'duplicates_detail': [
                {'relation': r, 'source': s, 'target': t, 'repeats': n}
                for (r, s, t), n in sorted(relations.duplicates.items())],
            'unresolved_links': [
                {'relation': r, 'source': s, 'target': t}
                for (r, s, t) in relations.unresolved],
        },
        'direction_samples': direction_samples,
        'direct_subgraph': _metric_counts(direct),
        'projected_warnings': warnings,
        'checks': checks,
    }
    outputs.write_json(os.path.join(out_dir, 'graph_diagnostics.json'),
                       diagnostics)

    # Prove inputs unchanged: re-hash and compare.
    unchanged = all(
        xmlsource.sha256_of(os.path.join(ruwordnet_dir, fname)) == digest
        for fname, digest in input_hashes.items())
    checks['input_files_unchanged'] = unchanged

    return {
        'out_dir': out_dir,
        'synset_count': total_synsets,
        'domain_count': len(domain_ids),
        'domain_xml_rows': domain_xml_rows,
        'assignment_pairs': len(assignments),
        'assigned_synsets': assigned_synsets,
        'hypernym_between_xml': hypernym_between_xml,
        'hypernym_between_unique': len(direct_edges),
        'direct': _metric_counts(direct),
        'projected': {
            'total': len(proj_edges),
            'direct': sum(1 for d in projected.values()
                          for info in d.values()
                          if info['kind'] == 'direct'),
            'via': sum(1 for d in projected.values() for info in d.values()
                       if info['kind'] == 'via_non_domain'),
            'warnings': len(warnings),
        },
        'checks': checks,
        'outputs': sorted(os.listdir(out_dir)),
    }


def _metric_counts(direct):
    return {
        'node_count': direct['node_count'],
        'unique_edge_count': direct['unique_edge_count'],
        'nodes_without_parent_domain': len(direct['nodes_without_parent_domain']),
        'nodes_without_child_domain': len(direct['nodes_without_child_domain']),
        'isolated_nodes': len(direct['isolated_nodes']),
        'nodes_with_multiple_parents': len(direct['nodes_with_multiple_parents']),
        'self_loops': len(direct['self_loops']),
        'weakly_connected_components': len(direct['weakly_connected_components']),
        'strongly_connected_components_size_gt1':
            len(direct['strongly_connected_components_size_gt1']),
    }


def _html_payload(source_dir, started_at, total_synsets, domain_xml_rows,
                  assignment_pairs, assigned_synsets, hypernym_between_xml,
                  domain_ids, catalog, extras, projected, direct, warnings,
                  proj_edges):
    meta = {
        'source_dir': source_dir,
        'tool_version': __version__,
        'started_at': started_at,
        'synset_count': total_synsets,
        'domain_count': len(domain_ids),
        'domain_xml_rows': domain_xml_rows,
        'assignment_pairs': assignment_pairs,
        'assigned_synsets': assigned_synsets,
        'assigned_share_pct': 100.0 * assigned_synsets / total_synsets,
        'hypernym_between_xml': hypernym_between_xml,
        'hypernym_between_unique': direct['unique_edge_count'],
        'direct_nodes': direct['node_count'],
        'direct_edges': direct['unique_edge_count'],
        'direct_no_parent': len(direct['nodes_without_parent_domain']),
        'direct_isolated': len(direct['isolated_nodes']),
        'direct_multi_parent': len(direct['nodes_with_multiple_parents']),
        'proj_total': len(proj_edges),
        'proj_direct': sum(1 for d in projected.values() for i in d.values()
                           if i['kind'] == 'direct'),
        'proj_via': sum(1 for d in projected.values() for i in d.values()
                        if i['kind'] == 'via_non_domain'),
    }
    domains = []
    for d in sorted(domain_ids):
        e = catalog[d]
        domains.append({
            'domain_id': d,
            'ruthes_name': e['ruthes_name'],
            'definition': e['definition'],
            'lemmas': e.get('lemmas', []),
            'assigned_count': e['assigned_count'],
            'count_N': e['pos_counts']['N'],
            'count_Adj': e['pos_counts']['Adj'],
            'count_V': e['pos_counts']['V'],
            'multi_domain_assigned': e['multi_domain_assigned'],
            'hypernyms_outside': extras[d]['hypernyms_outside'],
            'isolated': extras[d]['isolated'],
            'parents_direct': extras[d]['parents'],
            'children_direct': extras[d]['children'],
            'projected': [
                {'id': anc, 'kind': info['kind'],
                 'path_length': info['path_length'],
                 'path': info['witness_path']}
                for anc, info in sorted(projected.get(d, {}).items())],
            'examples': e.get('examples', {}),
        })
    return {
        'meta': meta,
        'domains': domains,
        'isolated': sorted(direct['isolated_nodes']),
        'warnings': warnings,
    }


def _report_payload(source_dir, total_synsets, domain_xml_rows,
                    assignment_pairs, assigned_synsets, domain_ids, catalog,
                    registry, direct, projected, warnings, proj_edges,
                    top_inter, direction_samples, checks):
    top15 = sorted(catalog.values(),
                   key=lambda e: (-e['assigned_count'], e['domain_id']))[:15]
    m = _metric_counts(direct)
    direct_cnt = {
        'node_count': m['node_count'],
        'unique_edge_count': m['unique_edge_count'],
        'no_parent': m['nodes_without_parent_domain'],
        'no_child': m['nodes_without_child_domain'],
        'isolated': m['isolated_nodes'],
        'multi_parent': m['nodes_with_multiple_parents'],
        'weak_components': m['weakly_connected_components'],
        'self_loops': m['self_loops'],
        'scc_gt1': m['strongly_connected_components_size_gt1'],
    }
    proj_direct = sum(1 for d in projected.values() for i in d.values()
                      if i['kind'] == 'direct')
    proj_via = sum(1 for d in projected.values() for i in d.values()
                   if i['kind'] == 'via_non_domain')
    only_direct_parents = sum(
        1 for d in projected.values() if any(i['kind'] == 'direct'
                                             for i in d.values()))
    gained_extra = sum(
        1 for d, res in projected.items()
        if any(i['kind'] == 'via_non_domain' for i in res.values()))

    branch_samples = []
    name_of = lambda x: (registry.get(x, {}) or {}).get('ruthes_name') or x
    for entry in top15[:5]:
        d = entry['domain_id']
        res = projected.get(d, {})
        for anc, info in sorted(res.items()):
            names = ' -> '.join(name_of(x) for x in info['witness_path'])
            branch_samples.append('%s: %s (%s, длина %d)'
                                  % (entry['ruthes_name'], names,
                                     info['kind'], info['path_length']))
        if not res:
            branch_samples.append('%s: ближайших доменных предков нет'
                                  % entry['ruthes_name'])

    overlaps_top = [{
        'name_a': catalog[r['domain_a']]['ruthes_name'],
        'name_b': catalog[r['domain_b']]['ruthes_name'],
        'intersection': r['intersection'], 'size_a': r['size_a'],
        'size_b': r['size_b'], 'jaccard': r['jaccard'],
    } for r in top_inter[:10]]

    mismatch = ['%s: ожидается %s, получено %s'
                % (k, v['expected'], v['actual'])
                for k, v in checks['reference'].items() if not v['match']]
    limitations = [
        'Домены — не отдельный справочник, а обычные синсеты: определение '
        'домена существует только через связи domain.',
        'Примеры синсетов в карточках — детерминированная выборка по '
        'порядку ID, а не экспертно отобранные типичные представители.',
        'Проецированный граф даёт только ближайших доменных предков; это не '
        'транзитивное замыкание и не сокращение таксономии.',
        'Определения доменов показаны только те, что есть в XML; пустые '
        'остались пустыми.',
        'Связи instance hypernym в проецировании не участвовали.',
    ]
    if mismatch:
        limitations.append('Расхождение с аудитом 001: ' + '; '.join(mismatch))
    if checks['witness_errors']:
        limitations.append('Ошибки проверки путей-свидетелей: %d'
                           % len(checks['witness_errors']))

    return {
        'source_dir': source_dir,
        'tool_version': __version__,
        'synset_count': total_synsets,
        'domain_xml_rows': domain_xml_rows,
        'assignment_pairs': assignment_pairs,
        'domain_count': len(domain_ids),
        'assigned_synsets': assigned_synsets,
        'assigned_share_pct': 100.0 * assigned_synsets / total_synsets,
        'domain_duplicates': checks.get('duplicate_edges'),
        'unresolved_count': checks.get('unresolved_count', 0),
        'hypernym_between_xml': checks.get('hypernym_between_xml'),
        'hypernym_between_unique': direct['unique_edge_count'],
        'direct': direct_cnt,
        'proj': {'total': len(proj_edges), 'direct': proj_direct,
                 'via': proj_via, 'gained_extra': gained_extra,
                 'warnings': len(warnings)},
        'top15': top15,
        'branch_samples': branch_samples,
        'overlaps_top': overlaps_top,
        'limitations': limitations,
        'direction_samples': direction_samples,
    }
