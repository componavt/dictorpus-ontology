"""Graph algorithms for the domain browser.

Two representations:
- direct subgraph: unique hypernym edges whose both ends are domains
  (stage C). Stored specific -> general.
- projected graph: for every domain, the nearest domain ancestors reachable
  upward through zero or more non-domain synsets (stage D).

No hyponym rows are used (they duplicate hypernym in the opposite
direction); no transitive reduction is performed silently: only nearest
domains are reported, exactly as defined by the task.
"""
from collections import deque


def adjacency(edges):
    """Sorted adjacency {source: [target, ...]} from (source, target) pairs."""
    adj = {}
    for s, t in edges:
        adj.setdefault(s, []).append(t)
    for s in adj:
        adj[s].sort()
    return adj


def direct_subgraph_metrics(domain_ids, edges):
    """Stage C metrics for the immediate domain subgraph.

    `edges` are unique specific->general hypernym edges with both ends in D.
    Parent = more general side (edge target), child = more specific side.
    """
    nodes = set(domain_ids)
    edge_list = sorted(set(edges))
    adj_out = adjacency(edge_list)   # child -> parents
    adj_in = {}
    for s, t in edge_list:
        adj_in.setdefault(t, []).append(s)

    no_parent = sorted(n for n in nodes if n not in adj_out or not adj_out[n])
    no_child = sorted(n for n in nodes if n not in adj_in or not adj_in[n])
    isolated = sorted(n for n in nodes
                      if (n not in adj_out or not adj_out[n])
                      and (n not in adj_in or not adj_in[n]))
    multi_parent = sorted(n for n in nodes
                          if n in adj_out and len(set(adj_out[n])) >= 2)
    self_loops = sorted((s, t) for s, t in edge_list if s == t)
    weak = weak_components(nodes, edge_list)
    sccs = tarjan_scc(nodes, edge_list)
    big_sccs = sorted([sorted(c) for c in sccs if len(c) > 1])

    return {
        'node_count': len(nodes),
        'unique_edge_count': len(edge_list),
        'edges': edge_list,
        'nodes_without_parent_domain': no_parent,
        'nodes_without_child_domain': no_child,
        'isolated_nodes': isolated,
        'nodes_with_multiple_parents': multi_parent,
        'self_loops': self_loops,
        'weakly_connected_components': [sorted(c) for c in weak],
        'strongly_connected_components_size_gt1': big_sccs,
    }


def weak_components(nodes, edges):
    """Weakly connected components via BFS on the undirected projection."""
    undirected = {}
    for s, t in edges:
        undirected.setdefault(s, set()).add(t)
        undirected.setdefault(t, set()).add(s)
    seen = set()
    comps = []
    for n in sorted(nodes):
        if n in seen:
            continue
        comp = []
        queue = deque([n])
        seen.add(n)
        while queue:
            cur = queue.popleft()
            comp.append(cur)
            for nxt in sorted(undirected.get(cur, ())):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        comps.append(comp)
    return comps


def tarjan_scc(nodes, edges):
    """Iterative Tarjan strongly connected components."""
    adj = adjacency(edges)
    index_counter = [0]
    index = {}
    lowlink = {}
    on_stack = set()
    stack = []
    result = []

    for root in sorted(nodes):
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            node, pi = work[-1]
            if pi == 0:
                index[node] = index_counter[0]
                lowlink[node] = index_counter[0]
                index_counter[0] += 1
                stack.append(node)
                on_stack.add(node)
            recurse = False
            neighbors = adj.get(node, [])
            for i in range(pi, len(neighbors)):
                nxt = neighbors[i]
                if nxt not in index:
                    work[-1] = (node, i + 1)
                    work.append((nxt, 0))
                    recurse = True
                    break
                elif nxt in on_stack:
                    lowlink[node] = min(lowlink[node], index[nxt])
            if recurse:
                continue
            if lowlink[node] == index[node]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                result.append(comp)
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])
    return result


def projected_ancestors(start, full_adj, domain_set):
    """Stage D: nearest domain ancestors of `start` in the full hypernym DAG.

    BFS upward (specific -> general). Each branch stops at the first domain
    it meets; expansion beyond a found domain never happens. The start
    domain can never become its own ancestor; if it is reachable from itself
    through non-domain nodes, this is recorded as a cycle warning.

    Returns (results, warnings) where results maps ancestor_domain ->
    dict(kind, path_length, witness_path) and warnings is a list of dicts.
    Deterministic: neighbors are visited in sorted order.
    """
    results = {}
    warnings = []
    visited = {start}
    queue = deque([(start, [start])])
    while queue:
        node, path = queue.popleft()
        for nxt in full_adj.get(node, ()):
            if nxt == start:
                warnings.append({
                    'type': 'self_reachable',
                    'domain': start,
                    'witness': path + [start],
                })
                continue
            if nxt in domain_set:
                candidate = {
                    'kind': 'direct' if len(path) == 1 else 'via_non_domain',
                    'path_length': len(path),
                    'witness_path': path + [nxt],
                }
                prev = results.get(nxt)
                if prev is None or candidate['path_length'] < prev['path_length']:
                    results[nxt] = candidate
                # first domain met on this branch: do not expand beyond it
            else:
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, path + [nxt]))
    return results, warnings


def project_all(domain_ids, full_hypernym_edges):
    """Run stage D for every domain; aggregate warnings and cycle checks."""
    full_adj = adjacency(full_hypernym_edges)
    domain_set = set(domain_ids)
    projected = {}
    warnings = []
    for d in domain_ids:
        results, warns = projected_ancestors(d, full_adj, domain_set)
        projected[d] = results
        warnings.extend(warns)

    # Cycles spanning several domains in the projected graph: if two domains
    # are mutual ancestors through projected edges, warn.
    proj_edges = []
    for d, results in projected.items():
        for anc in results:
            proj_edges.append((d, anc))
    sccs = tarjan_scc(set(domain_ids), proj_edges)
    domain_cycles = sorted(sorted(c) for c in sccs if len(c) > 1)
    for cyc in domain_cycles:
        warnings.append({
            'type': 'projected_domain_cycle',
            'domains': cyc,
        })
    return projected, warnings, proj_edges


def validate_witnesses(projected, full_edge_set, domain_set):
    """Stage G check: every witness path is a real hypernym walk.

    Checks: consecutive ids are unique hypernym edges; internal nodes are
    not domains; the final node is a domain different from the start.
    """
    errors = []
    for start, results in projected.items():
        for anc, info in results.items():
            path = info['witness_path']
            if path[0] != start or path[-1] != anc:
                errors.append((start, anc, 'bad endpoints'))
                continue
            for a, b in zip(path, path[1:]):
                if (a, b) not in full_edge_set:
                    errors.append((start, anc, 'missing edge %s->%s' % (a, b)))
            for internal in path[1:-1]:
                if internal in domain_set:
                    errors.append((start, anc,
                                   'internal node %s is a domain' % internal))
    return errors
