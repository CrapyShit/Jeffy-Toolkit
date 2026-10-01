import random

import pytest

from jeffy.core import mathlib
from jeffy.geometry import symmetry
from jeffy.geometry.spatial import SpatialHash, closest_indices


def _cloud(count=400, seed=1):
    rng = random.Random(seed)
    return [(rng.uniform(-10, 10), rng.uniform(-10, 10), rng.uniform(-10, 10)) for _ in range(count)]


def test_nearest_matches_brute_force():
    points = _cloud()
    grid = SpatialHash(points)
    rng = random.Random(7)
    for _ in range(200):
        query = (rng.uniform(-15, 15), rng.uniform(-15, 15), rng.uniform(-15, 15))
        index, dist = grid.nearest(query)
        brute = min(range(len(points)), key=lambda i: mathlib.distance(points[i], query))
        assert dist == pytest.approx(mathlib.distance(points[brute], query))


def test_nearest_far_away_query():
    grid = SpatialHash([(0, 0, 0), (1, 0, 0)])
    index, dist = grid.nearest((100, 0, 0))
    assert index == 1 and dist == pytest.approx(99)


def test_nearest_max_distance():
    grid = SpatialHash([(0, 0, 0)])
    assert grid.nearest((5, 0, 0), max_distance=1.0)[0] == -1


def test_within():
    points = [(0, 0, 0), (0.5, 0, 0), (3, 0, 0)]
    assert sorted(SpatialHash(points).within((0, 0, 0), 1.0)) == [0, 1]


def test_closest_indices():
    assert closest_indices([(0, 0, 0), (10, 0, 0)], [(9, 0, 0), (1, 0, 0)]) == [1, 0]


def _symmetric_cloud():
    half = [p for p in _cloud(150, 3) if p[0] > 0.01]
    center = [(0.0, float(i), 1.0) for i in range(5)]
    return half + [mathlib.reflect(p, "x") for p in half] + center


def test_mirror_map():
    points = _symmetric_cloud()
    mirror_map = symmetry.build_mirror_map(points)
    assert -1 not in mirror_map
    for i, j in enumerate(mirror_map):
        assert mathlib.distance(mathlib.reflect(points[i], "x"), points[j]) < 1e-6
    unmatched, ok = symmetry.symmetry_report(points + [(5.0, 5.0, 5.0)],
                                             symmetry.build_mirror_map(points + [(5.0, 5.0, 5.0)]))
    assert not ok and unmatched == [len(points)]


def test_mirror_target_and_flip():
    base = _symmetric_cloud()
    mirror_map = symmetry.build_mirror_map(base)
    target = [mathlib.add(p, (0, 1, 0)) if p[0] > 0.01 else p for p in base]
    mirrored = symmetry.mirror_target(base, target, mirror_map)
    for original, new in zip(base, mirrored):
        if original[0] < -0.01:
            assert new[1] == pytest.approx(original[1] + 1)
        elif original[0] > 0.01:
            assert new == pytest.approx(original)
    flipped = symmetry.flip_positions(base, mirror_map)
    assert all(mathlib.distance(a, b) < 1e-6 for a, b in zip(sorted(flipped), sorted(base)))


def test_mirror_positions_symmetrize():
    base = _symmetric_cloud()
    mirror_map = symmetry.build_mirror_map(base)
    moved = [mathlib.add(p, (0, 0, 2)) if p[0] > 0.01 else p for p in base]
    result = symmetry.mirror_positions(moved, mirror_map, direction=symmetry.POSITIVE_TO_NEGATIVE)
    for i, point in enumerate(base):
        if point[0] < -0.01:
            assert result[i][2] == pytest.approx(point[2] + 2)


def test_split_weights_sum_to_one():
    points = [(x / 10.0, 0, 0) for x in range(-20, 21)]
    weights = symmetry.split_weights(points, "x", falloff=1.0)
    assert weights[0] == 0.0 and weights[-1] == 1.0
    assert weights[20] == pytest.approx(0.5)
    left = symmetry.split_target(points, [(p[0], 1, 0) for p in points], weights)
    right = symmetry.split_target(points, [(p[0], 1, 0) for p in points], [1 - w for w in weights])
    for a, b in zip(left, right):
        assert a[1] + b[1] == pytest.approx(1.0)


def test_mirror_weights():
    points = [(1, 0, 0), (-1, 0, 0), (0, 0, 0)]
    mirror_map = symmetry.build_mirror_map(points)
    assert symmetry.mirror_weights([1.0, 0.0, 0.5], mirror_map, points) == [1.0, 1.0, 0.5]
    assert symmetry.mirror_weights([1.0, 0.0, 0.5], mirror_map) == [0.0, 1.0, 0.5]
