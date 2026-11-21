"""Normalized relation model and domain catalog for RuWordNet.

Direction convention (verified in audit 001 and re-verified by tests):
for relation names "hypernym" and "domain" the synset in @parent_id is the
source (the more specific synset for hypernym; the bound synset for domain)
and the synset in @child_id is the target (the more general synset; the
domain node). Any mismatch found on real data is reported, never silently
reversed.
"""

# Relations whose direction is established by the audit (parent -> child).
DIRECTED_BY_AUDIT = frozenset({'hypernym', 'domain'})


class NormalizedRelations:
    """Deduplicated normalized edges plus provenance statistics."""

    def __init__(self):
        self.edges = {}       # (relation, source, target) -> first source_file
        self.duplicates = {}  # (relation, source, target) -> repeat count
        self.xml_rows = {}    # relation -> XML record count (raw)
        self.unresolved = []  # (relation, source, target) with missing ends
        self.other_names = {}  # relation name -> count, outside audit scope
        self.direction_samples = []  # human-readable direction evidence

    def add(self, relation, source, target, source_file, resolve):
        """Add one raw XML row (already mapped to source/target)."""
        self.xml_rows[relation] = self.xml_rows.get(relation, 0) + 1
        if relation not in DIRECTED_BY_AUDIT:
            self.other_names[relation] = self.other_names.get(relation, 0) + 1
            return
        if not resolve(source) or not resolve(target):
            self.unresolved.append((relation, source, target))
            return
        key = (relation, source, target)
        if key in self.edges:
            self.duplicates[key] = self.duplicates.get(key, 0) + 1
        else:
            self.edges[key] = source_file

    def unique_edges(self, relation):
        """Sorted list of (source, target) for a relation name."""
        return sorted((s, t) for (r, s, t) in self.edges if r == relation)


def check_direction_examples(relations, registry, limit=6):
    """Collect readable evidence that source->target reads specific->general.

    For hypernym: target should name a broader concept than source.
    For domain: target should be one of the domain nodes (N synsets used as
    domains). We only verify that ends exist and record samples for the
    report; the direction decision itself comes from the audit.
    """
    samples = []
    for (relation, source, target), src_file in sorted(relations.edges.items()):
        if relation == 'hypernym' and len(samples) < limit:
            s = registry.get(source)
            t = registry.get(target)
            if s and t:
                samples.append('%s: "%s" IS-A "%s" (%s)'
                               % (src_file, t['ruthes_name'],
                                  s['ruthes_name'], source))
    return samples


def build_domain_catalog(relations, registry):
    """Stage B: domain set D and per-domain catalog entries.

    Returns (domain_ids_sorted, catalog dict, assignments list).
    Assignments are unique (synset_id, domain_id) pairs, not propagated
    along hypernymy.
    """
    assignment_pairs = set()
    domain2synsets = {}
    synset2domains = {}
    for (relation, source, target) in relations.edges:
        if relation == 'domain':
            assignment_pairs.add((source, target))  # source=synset, target=domain
            domain2synsets.setdefault(target, set()).add(source)
            synset2domains.setdefault(source, []).append(target)

    domain_ids = sorted(domain2synsets)

    catalog = {}
    for d in domain_ids:
        synsets = sorted(domain2synsets[d])
        pos_counts = {'N': 0, 'Adj': 0, 'V': 0}
        for s in synsets:
            rec = registry.get(s)
            if rec and rec['part_of_speech'] in pos_counts:
                pos_counts[rec['part_of_speech']] += 1
        multi = sum(1 for s in synsets if len(synset2domains[s]) >= 2)
        rec = registry.get(d, {})
        catalog[d] = {
            'domain_id': d,
            'ruthes_name': rec.get('ruthes_name'),
            'definition': rec.get('definition', ''),
            'assigned_synsets': synsets,
            'assigned_count': len(synsets),
            'pos_counts': pos_counts,
            'multi_domain_assigned': multi,
        }
    assignments = sorted(assignment_pairs)
    return domain_ids, catalog, assignments


def attach_examples(catalog, registry, per_pos=5):
    """Deterministic examples: up to `per_pos` synsets per POS sorted by id.

    These are viewing samples in id order, not expert-picked typical
    representatives of the domain.
    """
    for d, entry in catalog.items():
        by_pos = {}
        for s in entry['assigned_synsets']:
            rec = registry.get(s)
            if not rec:
                continue
            pos = rec['part_of_speech']
            by_pos.setdefault(pos, [])
            if len(by_pos[pos]) < per_pos:
                by_pos[pos].append({
                    'synset_id': s,
                    'ruthes_name': rec['ruthes_name'],
                    'definition': rec['definition'],
                })
        entry['examples'] = by_pos
