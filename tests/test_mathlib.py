import itertools
import math
import random

import pytest

from jeffy.core import mathlib as m


def close(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_vectors():
    assert m.add((1, 2, 3), (1, 1, 1)) == (2, 3, 4)
    assert m.cross((1, 0, 0), (0, 1, 0)) == (0, 0, 1)
    assert m.dot((1, 2, 3), (4, 5, 6)) == 32
    assert close(m.normalize((3, 0, 4)), (0.6, 0, 0.8))
    assert m.normalize((0, 0, 0)) == (0, 0, 0)
    assert m.distance((0, 0, 0), (3, 4, 0)) == 5
    assert m.angle_between((1, 0, 0), (0, 1, 0)) == pytest.approx(90.0)
    assert m.axis_vector("-y") == (0.0, -1.0, 0.0)
    assert m.reflect((1, 2, 3), "x") == (-1, 2, 3)


def test_scalars():
    assert m.clamp(5, 0, 1) == 1
    assert m.remap(5, 0, 10, 0, 1) == 0.5
    assert m.remap(20, 0, 10, 0, 1) == 1.0
    assert m.smoothstep(0, 1, 0.5) == 0.5
    assert m.distribute(3, 0, 1) == [0.0, 0.5, 1.0]
    assert m.distribute(1) == [0.5]
    assert m.distribute(0) == []


def test_rotation_convention_matches_maya():
    # rotateZ 90 turns the X axis into +Y (Maya, row vectors)
    mtx = m.euler_to_matrix((0, 0, 90))
    assert close(mtx[0:3], (0, 1, 0))
    # rotateX 90 turns the Y axis into +Z
    mtx = m.euler_to_matrix((90, 0, 0))
    assert close(mtx[4:7], (0, 0, 1))
    # rotateY 90 turns the X axis into -Z
    mtx = m.euler_to_matrix((0, 90, 0))
    assert close(mtx[0:3], (0, 0, -1))


@pytest.mark.parametrize("order", m.ROTATE_ORDERS)
def test_euler_roundtrip(order):
    rng = random.Random(order)
    for _ in range(300):
        rotation = [rng.uniform(-179, 179) for _ in range(3)]
        mtx = m.euler_to_matrix(rotation, order)
        back = m.matrix_to_euler(mtx, order)
        assert m.is_close(mtx, m.euler_to_matrix(back, order), 1e-6)


@pytest.mark.parametrize("order", m.ROTATE_ORDERS)
def test_euler_small_angles_are_exact(order):
    rotation = (10.0, 20.0, 30.0)
    assert close(m.matrix_to_euler(m.euler_to_matrix(rotation, order), order), rotation, 1e-6)


@pytest.mark.parametrize("order", m.ROTATE_ORDERS)
def test_gimbal_lock(order):
    for middle in (90.0, -90.0):
        values = {order[0]: 25.0, order[1]: middle, order[2]: 40.0}
        rotation = (values["x"], values["y"], values["z"])
        mtx = m.euler_to_matrix(rotation, order)
        assert m.is_close(mtx, m.euler_to_matrix(m.matrix_to_euler(mtx, order), order), 1e-6)


def test_inverse_and_mult():
    mtx = m.compose((1, 2, 3), (10, 20, 30), (1, 2, 3))
    assert m.is_close(m.mult(mtx, m.inverse(mtx)), m.IDENTITY)
    with pytest.raises(ValueError):
        m.inverse([0.0] * 16)


def test_compose_decompose_roundtrip():
    for order in m.ROTATE_ORDERS:
        mtx = m.compose((4, -2, 7), (35, -60, 120), (1, 2, 0.5), order)
        t, r, s = m.decompose(mtx, order)
        assert close(t, (4, -2, 7))
        assert close(s, (1, 2, 0.5))
        assert m.is_close(m.compose(t, r, s, order), mtx, 1e-6)


def test_transform_point():
    mtx = m.compose((10, 0, 0), (0, 0, 90))
    assert close(m.transform_point((1, 0, 0), mtx), (10, 1, 0))
    assert close(m.transform_vector((1, 0, 0), mtx), (0, 1, 0))


AXES = ["x", "-x", "y", "-y", "z", "-z"]


@pytest.mark.parametrize("aim,up", [(a, u) for a, u in itertools.product(AXES, AXES) if a[-1] != u[-1]])
def test_aim_matrix(aim, up):
    aim_vec = m.normalize((1.0, 2.0, 0.5))
    mtx = m.aim_matrix((1, 2, 3), aim_vec, (0, 1, 0), aim, up)
    x, y, z, t = m.axes(mtx)
    rows = {"x": x, "y": y, "z": z}
    sign = -1.0 if aim.startswith("-") else 1.0
    assert close(m.scale(rows[aim[-1]], sign), aim_vec)
    assert abs(m.dot(m.cross(x, y), z) - 1.0) < 1e-6  # right handed, orthonormal
    up_sign = -1.0 if up.startswith("-") else 1.0
    assert m.dot(m.scale(rows[up[-1]], up_sign), (0, 1, 0)) > 0
    assert t == (1, 2, 3)


def test_aim_matrix_parallel_up():
    mtx = m.aim_matrix((0, 0, 0), (0, 1, 0), (0, 1, 0))
    x, y, z, _t = m.axes(mtx)
    assert abs(m.dot(m.cross(x, y), z) - 1.0) < 1e-6


def test_orthonormalize():
    mtx = m.compose((0, 0, 0), (10, 20, 30), (2, 3, 4))
    clean = m.orthonormalize(mtx)
    x, y, z, _t = m.axes(clean)
    assert close((m.length(x), m.length(y), m.length(z)), (1, 1, 1))
    assert abs(m.dot(x, y)) < 1e-9 and abs(m.dot(y, z)) < 1e-9


def test_mirror_matrix_behavior():
    world = m.compose((5, 1, 2), (10, 20, 30))
    mirrored = m.mirror_matrix(world, "x", "behavior")
    for src, dst in zip(m.axes(world)[:3], m.axes(mirrored)[:3]):
        assert close(dst, m.negate(m.reflect(src, "x")))
    assert close(m.get_translation(mirrored), (-5, 1, 2))
    x, y, z, _t = m.axes(mirrored)
    assert abs(m.dot(m.cross(x, y), z) - 1.0) < 1e-6


def test_mirror_matrix_orientation_keeps_world_aligned():
    world = m.set_translation(m.identity(), (3, 4, 5))
    mirrored = m.mirror_matrix(world, "x", "orientation")
    assert m.is_close(mirrored, m.set_translation(m.identity(), (-3, 4, 5)))


def test_mirror_axis_signs():
    world = m.compose((5, 1, 2), (10, 20, 30))
    assert m.mirror_axis_signs(world, m.mirror_matrix(world, "x", "behavior")) == (-1.0, -1.0, -1.0)
    identity = m.identity()
    assert m.mirror_axis_signs(identity, identity) == (-1.0, 1.0, 1.0)


def test_pole_vector_position():
    pole = m.pole_vector_position((0, 0, 0), (1, 0, -0.5), (2, 0, 0), 1.0)
    assert pole[2] < -0.5  # same side as the bend
    assert abs(pole[1]) < 1e-9  # in the chain plane
    straight = m.pole_vector_position((0, 0, 0), (1, 0, 0), (2, 0, 0))
    assert m.length(m.sub(straight, (1, 0, 0))) > 1.0


def test_planarize():
    points = [(0, 0, 0), (1, 0.2, 1), (2, -0.1, 0.5), (3, 0, 0)]
    planar = m.planarize(points)
    normal = m.plane_normal(planar[0], planar[1], planar[-1])
    for point in planar:
        assert abs(m.dot(m.sub(point, planar[0]), normal)) < 1e-9
    assert close(planar[0], points[0]) and close(planar[-1], points[-1])


def test_best_fit_plane_normal():
    normal = m.best_fit_plane_normal([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)])
    assert close(normal, (0, 0, 1))


def test_angles_helpers():
    assert math.isclose(m.angle_between((1, 0, 0), (1, 0, 0)), 0.0, abs_tol=1e-6)
    assert m.is_parallel((1, 0, 0), (-2, 0, 0))
