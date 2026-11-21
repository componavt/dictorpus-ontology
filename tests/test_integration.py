"""Integration test: full build() on a synthetic dump.

Checks that all ten output files appear, numbers agree with the fixture,
inputs are proven unchanged, and witness validation passes.
"""
import json
import os
import tempfile
import unittest

from ruwordnet_inspect.build import build
from tests.fixtures import write_rwn
from tests.test_unit import RELATIONS, SYNSETS

OUTPUT_FILES = ['manifest.json', 'domains.tsv', 'domain_assignments.tsv',
                'domain_hypernyms_direct.tsv',
                'domain_hypernyms_projected.tsv', 'domain_overlaps.tsv',
                'graph_diagnostics.json', 'domains_graph.json', 'index.html',
                'print.html', 'report.md']


class TestBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='rwn-build-')
        cls.rwn = write_rwn(os.path.join(cls.tmp, 'rwn'),
                            SYNSETS, RELATIONS)
        cls.out = os.path.join(cls.tmp, 'work')
        cls.summary = build(cls.rwn, cls.out)

    def test_all_outputs_exist(self):
        for name in OUTPUT_FILES:
            self.assertTrue(os.path.isfile(os.path.join(self.out, name)),
                            'missing output: %s' % name)
        self.assertEqual(sorted(os.listdir(self.out)), sorted(OUTPUT_FILES))

    def test_summary_numbers(self):
        s = self.summary
        self.assertEqual(s['synset_count'], 17)
        self.assertEqual(s['domain_count'], 8)
        self.assertEqual(s['domain_xml_rows'], 11)
        self.assertEqual(s['assignment_pairs'], 9)
        self.assertEqual(s['assigned_synsets'], 4)  # 200,210,220,230
        self.assertEqual(s['hypernym_between_xml'], 5)
        self.assertEqual(s['hypernym_between_unique'], 5)
        self.assertEqual(s['direct']['unique_edge_count'], 5)
        self.assertEqual(s['projected']['total'], 6)
        self.assertEqual(s['projected']['direct'], 5)
        self.assertEqual(s['projected']['via'], 1)

    def test_inputs_unchanged_and_witnesses(self):
        self.assertTrue(self.summary['checks']['input_files_unchanged'])
        self.assertEqual(self.summary['checks']['witness_errors'], [])
        self.assertTrue(self.summary['checks']['pos_sum_matches_assignments'])
        self.assertTrue(self.summary['checks']['examples_belong_to_domain'])

    def test_assignments_tsv(self):
        path = os.path.join(self.out, 'domain_assignments.tsv')
        with open(path, encoding='utf-8') as fh:
            lines = fh.read().strip().split('\n')
        self.assertEqual(lines[0].split('\t'), ['synset_id', 'domain_id'])
        self.assertEqual(len(lines) - 1, 9)

    def test_domains_tsv_has_definition_and_lemmas(self):
        path = os.path.join(self.out, 'domains.tsv')
        with open(path, encoding='utf-8') as fh:
            lines = fh.read().strip().split('\n')
        self.assertEqual(len(lines) - 1, 8)
        row = [l for l in lines if l.startswith('30-N\t')][0]
        fields = row.split('\t')
        self.assertEqual(fields[1], 'БОТАНИКА')
        self.assertEqual(fields[2], '')  # empty definition kept empty

    def test_manifest(self):
        with open(os.path.join(self.out, 'manifest.json'),
                  encoding='utf-8') as fh:
            m = json.load(fh)
        self.assertEqual(len(m['inputs']), 9)
        self.assertIn('Условия публикации не установлены',
                      m['provenance']['note_ru'])
        self.assertEqual(m['params']['out_dir'], self.out)

    def test_diagnostics(self):
        with open(os.path.join(self.out, 'graph_diagnostics.json'),
                  encoding='utf-8') as fh:
            d = json.load(fh)
        self.assertEqual(
            d['relations']['unresolved_links'],
            [{'relation': 'domain', 'source': '200-N', 'target': '999-N'}])
        self.assertEqual(
            len(d['relations']['duplicates_detail']), 1)
        # reference numbers come from the real audit; fixture must mismatch
        self.assertFalse(d['checks']['reference']['synset_count']['match'])
        self.assertTrue(d['checks']['reference'] is not None)

    def test_index_html_embeds_data(self):
        with open(os.path.join(self.out, 'index.html'),
                  encoding='utf-8') as fh:
            doc = fh.read()
        self.assertIn('БОТАНИКА', doc)
        self.assertNotIn('src="http', doc)  # no external resources

    def test_print_html_boss_digest(self):
        with open(os.path.join(self.out, 'print.html'),
                  encoding='utf-8') as fh:
            doc = fh.read()
        # boss digest: numbered catalog, no interactive or diagnostic blocks
        self.assertIn('Тематические категории RuWordNet', doc)
        self.assertIn('Всего категорий: 8', doc)
        self.assertNotIn('<script', doc)
        self.assertNotIn('Карточка', doc)
        self.assertNotIn('Легенда', doc)
        self.assertNotIn('Предупреждения', doc)
        self.assertNotIn('Изолированные', doc)
        # all 8 fixture domains present as rows; numbering is sequential
        for name in ('БОТАНИКА', 'ФИЗИКА', 'НАУКА'):
            self.assertIn('<td>%s</td>' % name, doc)
        # multi-domain membership explained explicitly
        self.assertIn('Значения на пересечении тем', doc)
        self.assertIn('несколько категорий', doc)
        rows = [line for line in doc.split('\n')
                if line.startswith('<tr><td class="num">')
                and not line.startswith('<tr><td class="num"></td>')]
        self.assertEqual(len(rows), 8)
        self.assertTrue(rows[0].startswith('<tr><td class="num">1</td>'))
        self.assertTrue(rows[-1].startswith('<tr><td class="num">8</td>'))
        # origin note kept
        self.assertIn('Условия публикации не установлены', doc)

    def test_report_md(self):
        with open(os.path.join(self.out, 'report.md'),
                  encoding='utf-8') as fh:
            text = fh.read()
        self.assertIn('Единым деревом это не является', text)
        self.assertIn('Условия публикации не установлены', text)


if __name__ == '__main__':
    unittest.main()
