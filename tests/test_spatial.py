import random

import pytest

from jeffy.core import mathlib
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
