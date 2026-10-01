import pytest

from jeffy.controls import library


@pytest.mark.parametrize("name", sorted(library.SHAPES))
def test_shape_valid(name):
    curves = library.get_shape(name)
    assert library.validate(curves)
    for curve in curves:
        for point in curve["points"]:
            assert len(point) == 3
            assert all(abs(v) < 5.0 for v in point), "shape %s is too large" % name


def test_categories_cover_library():
    categorized = [name for names in library.CATEGORIES.values() for name in names]
    assert sorted(categorized) == sorted(library.SHAPES)
    assert len(categorized) == len(set(categorized))


def test_library_is_extensive():
    assert len(library.SHAPES) >= 50


@pytest.mark.parametrize("count,degree,periodic,expected", [
    (4, 1, False, 4),
    (4, 3, False, 6),
    (11, 3, True, 13),
    (8, 3, False, 10),
])
def test_knot_counts(count, degree, periodic, expected):
    knots = library.knots_for(count, degree, periodic)
    assert len(knots) == expected == count + degree - 1 or degree == 1
    assert knots == sorted(knots)


def test_open_cubic_knots_clamped():
    assert library.knots_for(4, 3, False) == [0, 0, 0, 1, 1, 1]


def test_circle_radius_is_one():
    # a periodic cubic through the CVs passes at (P0 + 4P1 + P2) / 6
    points = library.get_shape("circle")[0]["points"]
    a, b, c = points[0], points[1], points[2]
    mid = [(a[i] + 4 * b[i] + c[i]) / 6.0 for i in range(3)]
    assert abs(sum(v * v for v in mid) ** 0.5 - 1.0) < 1e-6


@pytest.mark.parametrize("axis,expected", [
    ("y", (0, 1, 0)), ("-y", (0, -1, 0)), ("x", (1, 0, 0)), ("-x", (-1, 0, 0)), ("z", (0, 0, 1)),
    ("-z", (0, 0, -1)),
])
def test_orient_points_maps_up_axis(axis, expected):
    assert library.orient_points([(0, 1, 0)], axis)[0] == pytest.approx(expected)


def test_orient_points_rejects_bad_axis():
    with pytest.raises(ValueError):
        library.orient_points([(0, 1, 0)], "w")


def test_transform_shape():
    curves = library.transform_shape(library.get_shape("square"), size=2.0, axis="y", offset=(0, 1, 0))
    assert curves[0]["points"][0] == (-2.0, 1.0, -2.0)


def test_get_shape_returns_copy():
    first = library.get_shape("cube")
    first[0]["points"][0] = (99, 99, 99)
    assert library.get_shape("cube")[0]["points"][0] != (99, 99, 99)


def test_unknown_shape():
    with pytest.raises(KeyError):
        library.get_shape("definitely_not_a_shape")


def test_validate_errors():
    with pytest.raises(ValueError):
        library.validate([])
    with pytest.raises(ValueError):
        library.validate([{"points": [(0, 0, 0), (1, 0, 0)], "degree": 3, "periodic": False}])
