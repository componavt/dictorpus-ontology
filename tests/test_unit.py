"""Unit tests: normalization, catalog, graphs, projection, overlaps, HTML."""
import json
import os
import tempfile
import unittest

from ruwordnet_inspect import graphs, model, overlaps, xmlsource
from ruwordnet_inspect.htmlview import _json_for_script, build_document
from tests.fixtures import write_rwn

# Fixture synsets: domains (d*) and non-domains (nd*, s*).
SYNSETS = [
    ('10-N', 'НАУКА', 'определение науки', 'N'),          # domain, top
    ('20-N', 'БИОЛОГИЯ', 'наука о живом', 'N'),           # domain
    ('30-N', 'БОТАНИКА', '', 'N'),                        # domain, no def
    ('40-N', 'ФИЗИКА', '', 'N'),                          # domain, isolated
    ('50-N', 'ПРОМЕЖУТОЧНЫЙ УЗЕЛ', 'недомен', 'N'),       # nd
    ('60-N', 'ВЕЩЬ', '', 'N'),                            # nd
    ('70-N', 'ЦИКЛ-А', '', 'N'),                          # nd, in cycle
    ('80-N', 'ЦИКЛ-Б', '', 'N'),                          # nd, in cycle
    ('90-N', 'СЛУЧАЙ-ИЗ', '', 'N'),                       # domain, instance-like
    ('95-N', 'ПЕТЛЯ', '', 'N'),                           # domain, self-loop via nd
    ('97-N', 'ПЕТЛЯ-СЕРЕДИНА', '', 'N'),                  # nd in the loop
    ('110-N', 'ВЗАИМНО-1', '', 'N'),                      # domain, mutual cycle
    ('120-N', 'ВЗАИМНО-2', '', 'N'),                      # domain, mutual cycle
    ('200-N', 'РОЗА', 'цветок', 'N'),                     # assigned synset
    ('210-Adj', 'РОЗОВЫЙ', '', 'Adj'),                    # assigned synset
    ('220-V', 'ЦВЕСТИ', '', 'V'),                         # assigned synset
    ('230-N', 'ОДИНОЧНЫЙ', '', 'N'),                      # single-domain synset
]

# hypernym semantics: parent_id = more specific, child_id = more general.
RELATIONS = [
    # БОТАНИКА IS-A БИОЛОГИЯ (direct domain->domain edge)
    ('hypernym', '20-N', '30-N'),
    # БИОЛОГИЯ IS-A НАУКА (direct)
    ('hypernym', '10-N', '20-N'),
    # БОТАНИКА IS-A ПРОМЕЖУТОЧНЫЙ (domain -> nd)
    ('hypernym', '50-N', '30-N'),
    # ПРОМЕЖУТОЧНЫЙ IS-A НАУКА (nd -> domain) => projected via_non_domain
    ('hypernym', '10-N', '50-N'),
    # ФИЗИКА IS-A ВЕЩЬ: only nd parents, no projected domain ancestor
    ('hypernym', '60-N', '40-N'),
    # ФИЗИКА -> ЦИКЛ-Б: domain hanging over an endless nd cycle
    ('hypernym', '80-N', '40-N'),
    # nd cycle: ЦИКЛ-А <-> ЦИКЛ-Б
    ('hypernym', '80-N', '70-N'),
    ('hypernym', '70-N', '80-N'),
    # domain self-reachable: ПЕТЛЯ -> ПЕТЛЯ-СЕРЕДИНА -> ПЕТЛЯ
    ('hypernym', '97-N', '95-N'),
    ('hypernym', '95-N', '97-N'),
    # mutual projected cycle ВЗАИМНО-1 <-> ВЗАИМНО-2 (direct edges)
    ('hypernym', '120-N', '110-N'),
    ('hypernym', '110-N', '120-N'),
    # СЛУЧАЙ-ИЗ IS-A НАУКА (direct domain->domain)
    ('hypernym', '10-N', '90-N'),
    # domain assignments: source(synset)=parent_id, domain=child_id
    ('domain', '10-N', '200-N'),
    ('domain', '20-N', '200-N'),
    ('domain', '20-N', '210-Adj'),
    ('domain', '30-N', '200-N'),
    ('domain', '40-N', '220-V'),
    ('domain', '90-N', '230-N'),
    ('domain', '95-N', '200-N'),
    ('domain', '110-N', '220-V'),
    ('domain', '120-N', '220-V'),
    # duplicates of one domain row
    ('domain', '20-N', '200-N'),
    # broken link
    ('domain', '999-N', '200-N'),
]


def make_env():
    tmp = tempfile.mkdtemp(prefix='rwn-test-')
    root = write_rwn(tmp, SYNSETS, RELATIONS)
    registry, _diag = xmlsource.read_synsets(root)
    rows, _counts = xmlsource.read_relations(root)
    rel = model.NormalizedRelations()
    for row in rows:
        if row['name'] in model.DIRECTED_BY_AUDIT:
            rel.add(row['name'], row['parent_id'], row['child_id'],
                    row['source_file'], resolve=lambda s: s in registry)
    return root, registry, rel


class TestDirection(unittest.TestCase):
    def test_hypernym_source_is_specific(self):
        _root, registry, rel = make_env()
        # row ('hypernym', child='20-N', parent='30-N') means БОТАНИКА IS-A
        # БИОЛОГИЯ => normalized source='30-N', target='20-N'
        self.assertIn(('hypernym', '30-N', '20-N'), rel.edges)
        self.assertEqual(registry['30-N']['ruthes_name'], 'БОТАНИКА')
        self.assertEqual(registry['20-N']['ruthes_name'], 'БИОЛОГИЯ')

    def test_domain_source_is_synset(self):
        _root, _registry, rel = make_env()
        # row ('domain', child='20-N', parent='200-N') binds synset 200-N
        # to domain 20-N => normalized source='200-N', target='20-N'
        self.assertIn(('domain', '200-N', '20-N'), rel.edges)

    def test_duplicates_and_broken_links(self):
        _root, _registry, rel = make_env()
        # 9 unique valid rows + 1 duplicate + 1 broken = 11 XML rows
        self.assertEqual(rel.xml_rows['domain'], 11)
        self.assertEqual(rel.duplicates.get(('domain', '200-N', '20-N')), 1)
        self.assertEqual(rel.unresolved, [('domain', '200-N', '999-N')])


class TestCatalog(unittest.TestCase):
    def setUp(self):
        _root, registry, rel = make_env()
        self.registry = registry
        self.ids, self.catalog, self.assignments = \
            model.build_domain_catalog(rel, registry)
        model.attach_examples(self.catalog, registry, per_pos=1)

    def test_domain_set(self):
        # targets of domain edges: 20,30,40,95,90,110,120
        self.assertEqual(self.ids, ['10-N', '110-N', '120-N', '20-N', '30-N',
                                    '40-N', '90-N', '95-N'])

    def test_sizes_and_pos(self):
        self.assertEqual(self.catalog['20-N']['assigned_count'], 2)
        self.assertEqual(self.catalog['20-N']['pos_counts'],
                         {'N': 1, 'Adj': 1, 'V': 0})
        self.assertEqual(self.catalog['40-N']['pos_counts']['V'], 1)

    def test_multi_domain(self):
        # 200-N is bound to 10-N, 20-N, 30-N, 95-N; 210-Adj only to 20-N
        self.assertEqual(self.catalog['20-N']['multi_domain_assigned'], 1)
        # 230-N is bound to the single domain 90-N
        self.assertEqual(self.catalog['90-N']['multi_domain_assigned'], 0)

    def test_empty_definition_kept(self):
        self.assertEqual(self.catalog['30-N']['definition'], '')

    def test_examples_belong_and_deterministic(self):
        entry = self.catalog['20-N']
        ids = [s['synset_id'] for s in entry['examples']['N']]
        self.assertEqual(ids, ['200-N'])

    def test_lemmas(self):
        root, _reg, rel = make_env()
        lemmas = xmlsource.read_lemmas_for(root, ['20-N'])
        self.assertEqual(lemmas, {})


class TestDirectSubgraph(unittest.TestCase):
    def setUp(self):
        root, registry, rel = make_env()
        self.registry = registry
        self.ids, _cat, _assign = model.build_domain_catalog(rel, registry)
        self.dset = set(self.ids)
        hyper = rel.unique_edges('hypernym')
        direct_edges = [(s, t) for (s, t) in hyper
                        if s in self.dset and t in self.dset]
        self.metrics = graphs.direct_subgraph_metrics(self.ids, direct_edges)
        self.direct_edges = direct_edges

    def test_edge_set(self):
        # domain-domain hypernym edges: 30->20, 20->10, 90->10, 95->97*,
        # 110->120, 120->110 (97 is nd so 95->97 excluded)
        self.assertIn(('30-N', '20-N'), self.direct_edges)
        self.assertIn(('20-N', '10-N'), self.direct_edges)
        self.assertNotIn(('95-N', '97-N'), self.direct_edges)

    def test_counts(self):
        self.assertEqual(self.metrics['node_count'], 8)
        # (30,20), (20,10), (90,10), (110,120), (120,110)
        self.assertEqual(self.metrics['unique_edge_count'], 5)
        # ФИЗИКА (40) and ПЕТЛЯ (95) have no in-D parents or children
        self.assertEqual(self.metrics['isolated_nodes'], ['40-N', '95-N'])
        # СЛУЧАЙ-ИЗ (90) has parent 10-N
        self.assertNotIn('90-N', self.metrics['nodes_without_parent_domain'])
        self.assertEqual(self.metrics['nodes_with_multiple_parents'], [])
        # mutual cycle 110<->120 forms an SCC of size 2
        sccs = self.metrics['strongly_connected_components_size_gt1']
        self.assertEqual(sccs, [['110-N', '120-N']])


class TestProjection(unittest.TestCase):
    def setUp(self):
        root, registry, rel = make_env()
        self.registry = registry
        self.ids, self.catalog, _assign = \
            model.build_domain_catalog(rel, registry)
        self.hyper = rel.unique_edges('hypernym')
        self.projected, self.warnings, self.proj_edges = \
            graphs.project_all(self.ids, self.hyper)

    def test_via_non_domain(self):
        # 30 (БОТАНИКА) -> 50 (nd) -> 10 (НАУКА): projected ancestor 10,
        # via_non_domain, length 2
        res = self.projected['30-N']['10-N']
        self.assertEqual(res['kind'], 'via_non_domain')
        self.assertEqual(res['path_length'], 2)
        self.assertEqual(res['witness_path'], ['30-N', '50-N', '10-N'])

    def test_direct_beats_longer_path(self):
        # 20 (БИОЛОГИЯ) -> 10 directly; also 20->30... no, 30 is child.
        res = self.projected['20-N']['10-N']
        self.assertEqual(res['kind'], 'direct')
        self.assertEqual(res['witness_path'], ['20-N', '10-N'])

    def test_stop_at_first_domain(self):
        # 30 has edges: ->20 (domain, stop) and ->50 (nd) ->10 (domain).
        # Ancestor 20 only via direct edge; 10 reachable through 50.
        res30 = self.projected['30-N']
        self.assertIn('20-N', res30)
        self.assertIn('10-N', res30)
        # 95's only hypernym is 97 (nd) which loops back to 95: nothing beyond
        res95 = self.projected['95-N']
        self.assertEqual(res95, {})

    def test_self_reachable_warning_and_no_self_ancestor(self):
        kinds = [w['type'] for w in self.warnings]
        self.assertIn('self_reachable', kinds)
        self.assertNotIn('95-N', self.projected['95-N'])
        # ВЗАИМНО pair is a projected cycle
        self.assertIn('projected_domain_cycle', kinds)

    def test_nondomain_cycle_terminates(self):
        # 40 -> 80 <-> 70 (endless nd cycle, no domains inside): BFS finishes
        self.assertEqual(self.projected['40-N'], {})
        # 90 -> 10 direct edge found normally
        res = self.projected['90-N']
        self.assertIn('10-N', res)
        self.assertEqual(res['10-N']['kind'], 'direct')

    def test_branches_of_different_lengths(self):
        # 30 reaches 20 directly (len 1) and 10 via nd (len 2)
        self.assertEqual(self.projected['30-N']['20-N']['path_length'], 1)
        self.assertEqual(self.projected['30-N']['10-N']['path_length'], 2)

    def test_witnesses_valid(self):
        errors = graphs.validate_witnesses(
            self.projected, set(self.hyper), set(self.ids))
        self.assertEqual(errors, [])


class TestOverlaps(unittest.TestCase):
    def test_overlap_numbers(self):
        _root, registry, rel = make_env()
        ids, catalog, _assign = model.build_domain_catalog(rel, registry)
        rows = overlaps.domain_overlaps(catalog)
        pair = [r for r in rows
                if {r['domain_a'], r['domain_b']} == {'20-N', '30-N'}]
        self.assertEqual(len(pair), 1)
        r = pair[0]
        self.assertEqual(r['intersection'], 1)   # 200-N
        self.assertEqual(r['size_a'], 2)
        self.assertEqual(r['size_b'], 1)
        self.assertAlmostEqual(r['jaccard'], 1 / 2)
        self.assertAlmostEqual(r['share_of_smaller'], 1.0)


class TestHtml(unittest.TestCase):
    def test_script_escaping(self):
        payload = {'x': '</script><b>&' }
        encoded = _json_for_script(payload)
        self.assertNotIn('</script>', encoded)
        self.assertIn('<\\/', encoded)
        decoded = json.loads(encoded.replace('<\\/', '</'))
        self.assertEqual(decoded, payload)

    def test_document_escapes_and_embeds(self):
        data = {
            'meta': {'source_dir': '/tmp/x', 'tool_version': 't',
                     'started_at': 'now', 'synset_count': 1,
                     'domain_count': 1, 'domain_xml_rows': 1,
                     'assignment_pairs': 1, 'assigned_synsets': 1,
                     'assigned_share_pct': 1.0, 'hypernym_between_xml': 0,
                     'hypernym_between_unique': 0, 'direct_nodes': 1,
                     'direct_edges': 0, 'direct_no_parent': 1,
                     'direct_isolated': 1, 'direct_multi_parent': 0,
                     'proj_total': 0, 'proj_direct': 0, 'proj_via': 0},
            'domains': [{
                'domain_id': '10-N',
                'ruthes_name': '<script>alert(1)</script> & "кавычки"',
                'definition': '<b>жирный</b>',
                'lemmas': ['</script>'],
                'assigned_count': 1, 'count_N': 1, 'count_Adj': 0,
                'count_V': 0, 'multi_domain_assigned': 0,
                'hypernyms_outside': 0, 'isolated': True,
                'parents_direct': [], 'children_direct': [], 'projected': [],
                'examples': {},
            }],
            'isolated': ['10-N'],
            'warnings': [],
        }
        doc = build_document(data)
        # the only raw </script> closings are the two legitimate block ends;
        # payload-embedded '</' is escaped, so it cannot terminate the block
        self.assertEqual(doc.count('</script>'), 2)
        start = doc.index('<script id="data" type="application/json">') \
            + len('<script id="data" type="application/json">')
        end = doc.index('</script>', start)
        payload_text = doc[start:end]
        self.assertNotIn('</script>', payload_text)
        payload = json.loads(payload_text.strip().replace('<\\/', '</'))
        self.assertEqual(payload['domains'][0]['ruthes_name'],
                         '<script>alert(1)</script> & "кавычки"')
        # names are rendered client-side via textContent, never innerHTML
        self.assertNotIn('innerHTML', doc)


if __name__ == '__main__':
    unittest.main()
