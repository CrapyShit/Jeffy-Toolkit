"""Pure Python symmetry helpers (mirror maps, mirrored shapes and weights)."""

from jeffy.core import mathlib
from jeffy.geometry.spatial import SpatialHash

POSITIVE_TO_NEGATIVE = "+to-"
NEGATIVE_TO_POSITIVE = "-to+"


def _axis_index(axis):
    return mathlib.AXIS_INDEX[axis.lstrip("+-").lower()]


def build_mirror_map(points, axis="x", tolerance=1e-3):
    """``map[i]`` = index of the point mirrored to point ``i`` (``-1`` if none).

    Points on the symmetry plane map to themselves.
    """
    grid = SpatialHash(points)
    result = []
    for point in points:
        index, dist = grid.nearest(mathlib.reflect(point, axis), max_distance=tolerance * 10.0)
        result.append(index if dist <= tolerance else -1)
    return result


def side_of(point, axis="x", tolerance=1e-4):
    value = point[_axis_index(axis)]
    if value > tolerance:
        return 1
    if value < -tolerance:
        return -1
    return 0


def symmetry_report(points, mirror_map, axis="x"):
    """Return ``(unmatched_indices, is_symmetric)``."""
    unmatched = [i for i, j in enumerate(mirror_map) if j == -1]
    return unmatched, not unmatched


def mirror_positions(points, mirror_map, axis="x", direction=POSITIVE_TO_NEGATIVE, tolerance=1e-4):
    """Copy one side onto the other (absolute positions)."""
    source_side = 1 if direction == POSITIVE_TO_NEGATIVE else -1
    result = [tuple(p) for p in points]
    index = _axis_index(axis)
    for i, point in enumerate(points):
        side = side_of(point, axis, tolerance)
        j = mirror_map[i]
        if j == -1:
            continue
        if side == -source_side:
            result[i] = mathlib.reflect(points[j], axis)
        elif side == 0:
            flat = list(point)
            flat[index] = 0.0
            result[i] = tuple(flat)
    return result


def flip_positions(points, mirror_map, axis="x"):
    """Mirror everything to the opposite side."""
    result = [tuple(p) for p in points]
    for i, j in enumerate(mirror_map):
        if j != -1:
            result[i] = mathlib.reflect(points[j], axis)
    return result


def mirror_target(base_points, target_points, mirror_map, axis="x"):
    """Mirror a blendshape target: deltas of side A applied to side B.

    Returns new absolute positions: ``base[i] + reflect(delta[map[i]])``.
    Unmatched vertices keep their target position.
    """
    result = []
    for i, base in enumerate(base_points):
        j = mirror_map[i]
        if j == -1:
            result.append(tuple(target_points[i]))
            continue
        delta = mathlib.sub(target_points[j], base_points[j])
        result.append(mathlib.add(base, mathlib.reflect(delta, axis)))
    return result


def split_weights(points, axis="x", falloff=0.1, center=0.0):
    """Smooth 0..1 weights: 1 on the positive side, 0 on the negative side.

    ``falloff`` is the total width of the blend zone around ``center``.
    """
    index = _axis_index(axis)
    half = max(falloff / 2.0, 1e-9)
    return [mathlib.smoothstep(center - half, center + half, p[index]) for p in points]


def split_target(base_points, target_points, weights):
    """Apply per-vertex weights to target deltas -> new absolute positions."""
    result = []
    for base, target, weight in zip(base_points, target_points, weights):
        delta = mathlib.sub(target, base)
        result.append(mathlib.add(base, mathlib.scale(delta, weight)))
    return result


def mirror_weights(weights, mirror_map, points=None, axis="x", direction=POSITIVE_TO_NEGATIVE):
    """Mirror per-vertex scalar weights.

    Without ``points`` every value is flipped; with ``points`` only the
    destination side receives the source side values.
    """
    result = list(weights)
    source_side = 1 if direction == POSITIVE_TO_NEGATIVE else -1
    for i, j in enumerate(mirror_map):
        if j == -1:
            continue
        if points is None or side_of(points[i], axis) == -source_side:
            result[i] = weights[j]
    return result
