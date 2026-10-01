import pytest

from jeffy.deformers import weights as w
from jeffy.geometry import proxy


def test_rows_flatten():
    flat = [1, 2, 3, 4, 5, 6]
    assert w.rows(flat, 3) == [[1, 2, 3], [4, 5, 6]]
    assert w.flatten(w.rows(flat, 2)) == flat


def test_normalize_row():
    assert w.normalize_row([1.0, 1.0]) == [0.5, 0.5]
    assert w.normalize_row([0.0, 0.0]) == [0.5, 0.5]
    assert w.normalize_row([0.5, 0.5, 0.5], locked=[0]) == pytest.approx([0.5, 0.25, 0.25])


def test_limit_and_prune():
    row = [0.4, 0.3, 0.2, 0.1]
    limited = w.limit_row(row, 2)
    assert limited[2] == limited[3] == 0.0
    assert sum(limited) == pytest.approx(1.0)
    assert limited[0] > limited[1]
    pruned = w.prune_row([0.995, 0.005], 0.01)
    assert pruned == pytest.approx([1.0, 0.0])


def test_over_limit():
    flat = [0.5, 0.5, 0.0, 0.3, 0.3, 0.4]
    assert w.max_influences_used(flat, 3) == 3
    assert w.vertices_over_limit(flat, 3, 2) == [1]


def test_move_weights():
    flat = [0.6, 0.4, 0.5, 0.5]
    moved = w.move_weights(flat, 2, 0, 1, vertices=[0])
    assert moved == [0.0, 1.0, 0.5, 0.5]


def test_average_rows():
    assert w.average_rows([[1.0, 0.0], [0.0, 1.0]]) == [0.5, 0.5]
    assert w.average_rows([]) == []


def test_smooth_moves_toward_neighbors():
    # 3 vertices in a line, vertex 1 fully on influence 0, neighbours on 1
    flat = [0.0, 1.0, 1.0, 0.0, 0.0, 1.0]
    neighbors = [[1], [0, 2], [1]]
    result = w.smooth(flat, 2, neighbors, vertices=[1], iterations=1, strength=1.0)
    assert result[2:4] == pytest.approx([0.0, 1.0])
    assert result[0:2] == flat[0:2]


def test_smooth_respects_locks():
    flat = [0.2, 0.8, 0.9, 0.1, 0.9, 0.1]
    neighbors = [[1, 2], [0], [0]]
    result = w.smooth(flat, 2, neighbors, vertices=[0], iterations=3, strength=1.0, locked=[0])
    assert result[0] == pytest.approx(0.2)
    assert sum(result[0:2]) == pytest.approx(1.0)


def test_sparse_roundtrip():
    flat = [1.0, 0.0, 0.25, 0.75]
    influences = ["a", "b"]
    sparse = w.to_sparse(flat, 2, influences)
    assert sparse == {"a": [[0, 1.0], [1, 0.25]], "b": [[1, 0.75]]}
    assert w.from_sparse(sparse, influences, 2) == flat


def test_remap_and_reorder():
    flat = [1.0, 0.0, 0.0, 1.0]
    assert w.remap_vertices(flat, 2, [1, 1, 0]) == [0.0, 1.0, 0.0, 1.0, 1.0, 0.0]
    assert w.reorder_influences(flat, ["a", "b"], ["b", "c", "a"]) == [0.0, 0.0, 1.0, 1.0, 0.0, 0.0]


def test_face_influence_map():
    flat = [1.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 1.0]
    faces = [[0, 1, 2], [1, 2, 3]]
    assert proxy.face_influence_map(flat, 2, faces) == [0, 1]
