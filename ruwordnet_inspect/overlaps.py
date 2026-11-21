"""Stage E: intersections of directly assigned synset sets between domains.

Statistics only: overlaps never become hierarchical relations and never
introduce new hypernym edges.
"""
from itertools import combinations


def domain_overlaps(catalog):
    """All domain pairs with non-empty intersection of assigned synsets."""
    items = [(d, set(catalog[d]['assigned_synsets']))
             for d in sorted(catalog)]
    rows = []
    for (d1, s1), (d2, s2) in combinations(items, 2):
        inter = s1 & s2
        if not inter:
            continue
        union = len(s1 | s2)
        smaller = min(len(s1), len(s2))
        rows.append({
            'domain_a': d1,
            'domain_b': d2,
            'intersection': len(inter),
            'size_a': len(s1),
            'size_b': len(s2),
            'jaccard': len(inter) / union,
            'share_of_smaller': len(inter) / smaller,
        })
    rows.sort(key=lambda r: (-r['intersection'], r['domain_a'], r['domain_b']))
    return rows


def top_by_intersection(rows, limit=20):
    return rows[:limit]


def top_by_jaccard(rows, min_size=20, limit=20):
    eligible = [r for r in rows
                if r['size_a'] >= min_size and r['size_b'] >= min_size]
    eligible.sort(key=lambda r: (-r['jaccard'], r['domain_a'], r['domain_b']))
    return eligible[:limit]
