"""B2/007 support: inputs, encoding with cache, rubrics, samples.

Heavy imports (sentence_transformers) are lazy so the core veplex tests
stay stdlib-only. Model inputs are exact ``meaning_ru`` texts (main run,
no POS mixed in); the cache key is (model_id, text). Sememes are never
merged: every (lang, meaning_id) keeps its own row pointing to an input.
"""
import csv
import hashlib
import os
import random
import re

from . import sources

LANG_ORDER = {'vep': 0, 'krl': 1, 'olo': 2, 'lud': 3}
DEGENERATE = ('', ':', '::')


def load_registry(out_dir):
    """Sememe registry from the stage-A output."""
    with open(os.path.join(out_dir, 'sememes.tsv'), encoding='utf-8',
              newline='') as fh:
        return list(csv.DictReader(fh, delimiter='\t'))


def input_status(ru):
    """Classify the encoding input for a sememe row."""
    text = (ru or '').strip()
    if text in DEGENERATE or not re.search(r'[а-яёa-z]', text, re.I):
        return 'degenerate'
    if len(text) <= 2:
        return 'ultrashort'
    return 'ok'


def build_inputs(out_dir):
    """Unique ok-inputs + per-sememe status table. Deterministic order."""
    rows = load_registry(out_dir)
    sem_status = []
    inputs = {}
    for r in rows:
        status = input_status(r['meaning_ru'])
        sem_status.append((r['lang'], r['meaning_id'], status,
                           r['meaning_ru']))
        if status == 'ok':
            inputs.setdefault(r['meaning_ru'], len(inputs))
    uniq = sorted(inputs, key=lambda t: inputs[t])
    return rows, sem_status, uniq


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def extract_rubrics(irina_docx, out_tsv):
    """Extract the 18 rubrics (name + description) from Irina's DOCX."""
    import docx
    d = docx.Document(irina_docx)
    table = d.tables[0]
    header = [c.text.strip() for c in table.rows[0].cells]
    col_name = header.index('Wordnet')
    col_desc = next((i for i, h in enumerate(header) if 'включа' in h),
                    None)
    out = []
    for row in table.rows[1:]:
        cells = [c.text.strip() for c in row.cells]
        num = cells[0]
        name = cells[col_name] if col_name is not None else ''
        desc = cells[col_desc] if col_desc is not None else ''
        out.append((num, name, desc))
    with open(out_tsv, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(['num', 'name', 'description', 'note'])
        for num, name, desc in out:
            note = 'empty description (from Fedotkin column)' \
                if not desc else ''
            w.writerow([num, name, desc, note])
    return out, sha256_file(irina_docx)


def sample_random(sem_keys, n, seed):
    rng = random.Random(seed)
    pool = sorted(sem_keys, key=lambda k: (LANG_ORDER.get(k[0], 9),
                                           k[1].zfill(12)))
    return rng.sample(pool, min(n, len(pool)))


def write_sample(path, rows, header):
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(header)
        w.writerows(rows)


class Encoder:
    """E5 or rubert-tiny2 with an on-disk vector cache (numpy .npz)."""

    def __init__(self, model_id, cache_dir, prefix='', device='cpu'):
        self.model_id = model_id
        self.prefix = prefix
        self.device = device
        os.makedirs(cache_dir, exist_ok=True)
        slug = re.sub(r'[^A-Za-z0-9._-]', '_', model_id)
        self.cache_path = os.path.join(cache_dir, slug + '.npz')
        self._model = None
        self._texts = []
        self._index = {}

    def _ensure_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                self.model_id, device=self.device)
        return self._model

    def _load_cache(self):
        import numpy as np
        if os.path.exists(self.cache_path) and not self._texts:
            data = np.load(self.cache_path, allow_pickle=True)
            self._texts = list(data['texts'])
            self._vecs = data['vecs']
            self._index = {t: i for i, t in enumerate(self._texts)}

    def encode_new(self, texts, batch_size=64, show_progress=False):
        """Encode texts not yet in cache; return full vector matrix
        aligned with the given list order."""
        import numpy as np
        self._load_cache()
        todo = [t for t in texts if t not in self._index]
        if todo:
            model = self._ensure_model()
            new_vecs = model.encode(
                [self.prefix + t for t in todo], batch_size=batch_size,
                normalize_embeddings=True, show_progress_bar=show_progress)
            if not hasattr(self, '_vecs') or len(self._texts) == 0:
                self._vecs = new_vecs.astype('float32')
                self._texts = list(todo)
            else:
                self._vecs = np.vstack([self._vecs,
                                        new_vecs.astype('float32')])
                self._texts.extend(todo)
            self._index = {t: i for i, t in enumerate(self._texts)}
            np.savez_compressed(
                self.cache_path,
                texts=np.array(self._texts, dtype=object),
                vecs=self._vecs)
        return np.array([self._index[t] for t in texts]), self._vecs
