"""Tests for the veplex inventory (task 006) on synthetic exports."""
import io
import csv
import os
import tempfile
import unittest
from compression import zstd

from veplex import inventory as inv
from veplex import outputs
from veplex import sources

MEANING_HEADER = ('id,meaning_id,lemma_id,meaning_n,lemma,lang,pos,'
                  'meaning_ru,meaning_en,concept_id,category_id')
LEMMA_HEADER = 'lemma_id,lemma,lang,pos_id,pos'


def write_zst_csv(path, header, rows):
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator='\n')
    writer.writerow(header.split(','))
    writer.writerows(rows)
    with open(path, 'wb') as fh:
        fh.write(zstd.compress(buf.getvalue().encode('utf-8')))


def make_data(root):
    """Synthetic dictorpus-data snapshot covering all tricky cases."""
    os.makedirs(os.path.join(root, 'dict', 'morphology'), exist_ok=True)
    os.makedirs(os.path.join(root, 'semantics'), exist_ok=True)

    # vep meanings:
    #  1) two rows, same sememe, two concepts (the 30328 pattern)
    #  2) same meaning_ru in another sememe (must NOT merge)
    #  3) \\N as meaning_ru (SQL NULL)
    #  4) export category mismatching the concept chain
    write_zst_csv(
        os.path.join(root, 'dict', 'meanings_vep.csv.zst'), MEANING_HEADER, [
            (1, 10, 1, 1, 'kodi', 'vep', 'NOUN', 'дом', 'house', 100, 'B11'),
            (2, 10, 1, 1, 'kodi', 'vep', 'NOUN', 'дом', 'house', 101, 'A11'),
            (3, 11, 2, 1, "pert'", 'vep', 'NOUN', 'дом', '', 100, 'B11'),
            (4, 12, 3, 1, 'vozuk', 'vep', 'NOUN', r'\N', '', '', ''),
            (5, 13, 4, 1, 'vezad', 'vep', 'VERB', 'вести', '', 100, 'X99'),
        ])
    # field conflict: same key 10 twice with different meaning_ru
    write_zst_csv(
        os.path.join(root, 'dict', 'meanings_krl.csv.zst'), MEANING_HEADER, [
            (1, 10, 1, 1, 'kodi', 'krl', 'NOUN', 'дом', '', 100, 'B11'),
            (2, 10, 1, 1, 'kodi', 'krl', 'NOUN', 'изба', '', 100, 'B11'),
            (3, 20, 2, 2, 'ajaš', 'krl', 'NOUN', 'час', 'hour', 103, ''),
            (4, 30, 3, 1, 'tungai', 'krl', 'NOUN', 'идти', '', 999, ''),
        ])
    for lang, lemma_id in (('olo', 77), ('lud', 1)):   # olo: broken lemma ref
        write_zst_csv(
            os.path.join(root, 'dict', 'meanings_%s.csv.zst' % lang),
            MEANING_HEADER, [(1, 50, lemma_id, 1, 'x', lang, 'NOUN',
                              'вещь', '', '', '')])

    write_zst_csv(
        os.path.join(root, 'dict', 'examples_vep.csv.zst'),
        'id,meaning_id,example', [
            (1, 10, 'использование дома, пример с запятой'),
            (2, 10, 'второй пример'),
            (3, 77, 'пример несуществующей семемы'),
        ])
    for lang in ('krl', 'olo', 'lud'):
        write_zst_csv(
            os.path.join(root, 'dict', 'examples_%s.csv.zst' % lang),
            'id,meaning_id,example', [])

    write_zst_csv(
        os.path.join(root, 'dict', 'morphology', 'lemmas_vep.csv.zst'),
        LEMMA_HEADER, [(1, 'kodi', 'vep', 1, 'NOUN'),
                       (2, "pert'", 'vep', 1, 'NOUN'),
                       (3, 'vozuk', 'vep', 1, 'NOUN'),
                       (4, 'vezad', 'vep', 1, 'VERB'),
                       (9, 'kehl', 'vep', 1, 'NOUN')])
    for lang in ('krl', 'olo', 'lud'):
        write_zst_csv(
            os.path.join(root, 'dict', 'morphology',
                         'lemmas_%s.csv.zst' % lang),
            LEMMA_HEADER, [(1, 'kodi', lang, 1, 'NOUN'),
                           (2, 'tungai', lang, 1, 'NOUN'),
                           (3, 'ajaš', lang, 1, 'NOUN'),
                           (1 if lang == 'lud' else 9, 'x', lang, 1, 'NOUN')])

    with open(os.path.join(root, 'semantics', 'concepts.csv'), 'w',
              encoding='utf-8') as fh:
        fh.write('category_id\tpos\tconcept_id\tconcept_ru\tconcept_en\t'
                 'definition_ru\tdefinition_en\n')
        fh.write('B11\tNOUN\t100\tжилище\tdwelling\tопределение\tdef\n')
        fh.write('A11\tNOUN\t101\tнебо\tsky\tопределение\tdef\n')
        fh.write('B42\tNOUN\t103\tвремя\ttime\tопределение\tdef\n')
    with open(os.path.join(root, 'semantics', 'concept_categories_wdh.tsv'),
              'w', encoding='utf-8') as fh:
        fh.write('category_id\tname_ru\tname_en\twdh\n')
        fh.write('B11\tЖилище\tDwelling\tdwelling\n')
        fh.write('A11\tНебо\tSky\tsky\n')
        fh.write('B42\tВремя\tTime\ttime\n')
    return root


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.root = make_data(tempfile.mkdtemp(prefix='veplex-test-'))
        self.registry, self.links, self.diag = inv.build_registry(self.root)

    def test_two_concept_rows_is_one_sememe(self):
        # vep 10: two rows differing only in id/concept_id/category_id
        self.assertIn(('vep', '10'), self.registry)
        self.assertEqual(len(self.registry), 9)  # vep 4 + krl 3 + olo 1 + lud 1
        sem_links = [l for l in self.links
                     if (l['lang'], l['meaning_id']) == ('vep', '10')]
        self.assertEqual(len(sem_links), 2)
        vep_conflicts = [c for c in self.diag['field_conflicts']
                         if c['lang'] == 'vep']
        self.assertEqual(vep_conflicts, [])

    def test_field_conflict_recorded(self):
        # krl 10 appears twice with different meaning_ru
        conflicts = [c for c in self.diag['field_conflicts']
                     if c['lang'] == 'krl' and c['meaning_id'] == '10']
        self.assertEqual(len(conflicts), 1)
        self.assertIn('meaning_ru', conflicts[0]['differing_fields'])

    def test_identical_ru_not_merged(self):
        # vep 10 and vep 11 both 'дом' -> stay separate sememes
        self.assertIn(('vep', '11'), self.registry)

    def test_cross_lang_same_id_kept_separate_and_tracked(self):
        # meaning_id 10 in vep+krl; 50 in olo+lud
        self.assertIn(('vep', '10'), self.registry)
        self.assertIn(('krl', '10'), self.registry)
        self.assertEqual(len(self.diag['cross_lang_id_collisions']), 2)

    def test_null_vs_empty_ru(self):
        self.assertTrue(self.registry[('vep', '12')]['ru_null'])


class TestPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = make_data(tempfile.mkdtemp(prefix='veplex-run-'))
        cls.out = os.path.join(cls.root, '..', 'out')
        cls.out = os.path.abspath(os.path.join(tempfile.mkdtemp(
            prefix='veplex-out-')))
        cls.totals = outputs.run_inventory(cls.root, cls.out)

    def test_outputs_exist(self):
        for name in ('manifest.json', 'sememes.tsv', 'sememe_concepts.tsv',
                     'sememe_examples.tsv', 'summary_by_lang.tsv',
                     'summary_by_lang_pos.tsv', 'lemmas_summary.tsv',
                     'formulations_top.tsv', 'conflicts.tsv',
                     'broken_links.tsv', 'category_mismatches.tsv',
                     'categories_wdh_overview.tsv', 'report.md'):
            self.assertTrue(os.path.isfile(os.path.join(self.out, name)),
                            'missing: %s' % name)

    def test_broken_links_reported(self):
        with open(os.path.join(self.out, 'broken_links.tsv'),
                  encoding='utf-8') as fh:
            text = fh.read()
        self.assertIn('concept_id_unresolved', text)   # concept 999 (krl 30)
        self.assertIn('example_unknown_meaning', text)  # example -> vep 77
        self.assertIn('lemma_id_unresolved', text)      # vep 13 lemma 4? no...

    def test_category_mismatch_reported(self):
        # vep 13: export X99 vs chain B11
        with open(os.path.join(self.out, 'category_mismatches.tsv'),
                  encoding='utf-8') as fh:
            text = fh.read()
        self.assertIn('X99', text)
        self.assertIn('B11', text)

    def test_wdh_overview_counts(self):
        rows = {}
        with open(os.path.join(self.out, 'categories_wdh_overview.tsv'),
                  encoding='utf-8', newline='') as fh:
            for row in csv.DictReader(fh, delimiter='\t'):
                rows[row['category_id']] = row
        # B11 collects: vep 10, vep 11, vep 13, krl 10 = 4 sememes
        self.assertEqual(int(rows['B11']['n_sememes']), 4)
        self.assertEqual(rows['B11']['examples'].count(' | ') >= 1, True)
        # B42 has krl 20 via concept 103
        self.assertEqual(int(rows['B42']['n_sememes']), 1)

    def test_manifest_records_inputs(self):
        with open(os.path.join(self.out, 'manifest.json'),
                  encoding='utf-8') as fh:
            import json
            m = json.load(fh)
        self.assertEqual(len(m['data']['inputs']), 14)
        self.assertEqual(m['data']['tag'], 'v2026.13')


class TestSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = make_data(tempfile.mkdtemp(prefix='veplex-s-'))
        cls.out = tempfile.mkdtemp(prefix='veplex-sout-')
        outputs.run_inventory(cls.root, cls.out)

    def test_sample_covers_strata_deterministically(self):
        from veplex.sample import build_sample, write_sample
        rows1 = build_sample(self.out, per_lang=2, n_short=2, n_long=2,
                             seed=7)
        rows2 = build_sample(self.out, per_lang=2, n_short=2, n_long=2,
                             seed=7)
        self.assertEqual(rows1, rows2)
        kinds = {r[1] for r in rows1}
        self.assertIn('random', kinds)
        path = write_sample(self.out, rows1)
        with open(path, encoding='utf-8') as fh:
            self.assertIn('meaning_ru', fh.read())


if __name__ == '__main__':
    unittest.main()
