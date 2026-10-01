"""Pure Python skin weight math (no Maya dependency, unit tested).

Weights are stored *flat* and vertex major, exactly like
``MFnSkinCluster.getWeights`` returns them::

    flat[vertex * influence_count + influence]
"""


def rows(flat, count):
    """Split a flat list into per vertex rows."""
    return [list(flat[i:i + count]) for i in range(0, len(flat), count)]


def flatten(row_list):
    result = []
    for row in row_list:
        result.extend(row)
    return result


def normalize_row(row, locked=None):
    """Scale a row to sum 1 (locked influence weights are kept as is)."""
    locked = locked or ()
    locked_sum = sum(row[i] for i in locked)
    free = [i for i in range(len(row)) if i not in locked]
    free_sum = sum(row[i] for i in free)
    target = max(0.0, 1.0 - locked_sum)
    result = list(row)
    if free_sum > 1e-12:
        factor = target / free_sum
        for i in free:
            result[i] = row[i] * factor
    elif free:
        share = target / len(free) if target > 0 else 0.0
        for i in free:
            result[i] = share
    return result


def normalize(flat, count, locked=None):
    return flatten(normalize_row(r, locked) for r in rows(flat, count))


def prune_row(row, threshold):
    pruned = [w if w >= threshold else 0.0 for w in row]
    if sum(pruned) <= 0:
        return list(row)
    return normalize_row(pruned)


def prune(flat, count, threshold=0.01):
    return flatten(prune_row(r, threshold) for r in rows(flat, count))


def limit_row(row, max_influences):
    """Keep the ``max_influences`` largest weights and renormalize."""
    nonzero = [(w, i) for i, w in enumerate(row) if w > 0.0]
    if len(nonzero) <= max_influences:
        return list(row)
    keep = set(i for _w, i in sorted(nonzero, reverse=True)[:max_influences])
    return normalize_row([w if i in keep else 0.0 for i, w in enumerate(row)])


def limit_influences(flat, count, max_influences=4):
    return flatten(limit_row(r, max_influences) for r in rows(flat, count))


def max_influences_used(flat, count, threshold=1e-6):
    return max((sum(1 for w in r if w > threshold) for r in rows(flat, count)), default=0)


def vertices_over_limit(flat, count, limit, threshold=1e-6):
    return [v for v, r in enumerate(rows(flat, count)) if sum(1 for w in r if w > threshold) > limit]


def move_weights(flat, count, source, target, vertices=None, amount=1.0):
    """Move (a fraction of) the weight of influence ``source`` onto ``target``."""
    result = list(flat)
    vertex_count = len(flat) // count
    for v in (range(vertex_count) if vertices is None else vertices):
        offset = v * count
        moved = result[offset + source] * amount
        result[offset + source] -= moved
        result[offset + target] += moved
    return result


def average_rows(row_list):
    if not row_list:
        return []
    size = len(row_list[0])
    total = [0.0] * size
    for row in row_list:
        for i, w in enumerate(row):
            total[i] += w
    return normalize_row([w / len(row_list) for w in total])


def smooth(flat, count, neighbors, vertices=None, iterations=1, strength=0.5, locked=None):
    """Laplacian smoothing of weights over mesh connectivity.

    :param neighbors: ``neighbors[v]`` = connected vertex indices
    :param vertices: vertices to smooth (default all)
    :param locked: influence indices whose weights must not change
    """
    current = rows(flat, count)
    targets = list(range(len(current))) if vertices is None else list(vertices)
    locked = set(locked or ())
    for _iteration in range(iterations):
        updated = {}
        for v in targets:
            adjacent = neighbors[v]
            if not adjacent:
                continue
            avg = [0.0] * count
            for n in adjacent:
                row = current[n]
                for i in range(count):
                    avg[i] += row[i]
            inv = 1.0 / len(adjacent)
            row = current[v]
            new_row = [row[i] if i in locked else row[i] * (1.0 - strength) + avg[i] * inv * strength
                       for i in range(count)]
            updated[v] = normalize_row(new_row, locked)
        for v, row in updated.items():
            current[v] = row
    return flatten(current)


def to_sparse(flat, count, influences, threshold=1e-6):
    """``{influence: [[vertex, weight], ...]}`` - compact for JSON files."""
    result = {name: [] for name in influences}
    for v, row in enumerate(rows(flat, count)):
        for i, w in enumerate(row):
            if w > threshold:
                result[influences[i]].append([v, w])
    return result


def from_sparse(sparse, influences, vertex_count):
    """Inverse of :func:`to_sparse` (influences missing from ``sparse`` = 0)."""
    count = len(influences)
    flat = [0.0] * (vertex_count * count)
    for i, name in enumerate(influences):
        for vertex, weight in sparse.get(name, ()):
            if vertex < vertex_count:
                flat[vertex * count + i] = weight
    return flat


def remap_vertices(flat, count, mapping):
    """New flat array where target vertex ``t`` takes source row ``mapping[t]``."""
    source = rows(flat, count)
    result = []
    for index in mapping:
        result.extend(source[index] if 0 <= index < len(source) else [0.0] * count)
    return result


def reorder_influences(flat, old_order, new_order):
    """Re-map columns to a new influence order (unknown influences dropped)."""
    old_count = len(old_order)
    positions = [old_order.index(name) if name in old_order else -1 for name in new_order]
    result = []
    for row in rows(flat, old_count):
        result.extend(row[p] if p >= 0 else 0.0 for p in positions)
    return result
