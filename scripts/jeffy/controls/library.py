"""Control curve shape library (pure Python data).

Every shape is a list of curves. A curve is a dict::

    {"points": [(x, y, z), ...], "degree": 1 or 3, "periodic": bool}

Shapes are authored lying in the XZ plane / facing +Y with a radius of about
one unit; :func:`orient_points` rotates them to face any axis. Arrows point
toward +Z.

User shapes saved with :func:`jeffy.controls.shapes.save_to_library` live as
JSON files in ``<maya app dir>/jeffy_toolkit/shapes`` and are merged into the
library by :func:`get_shape` / :func:`list_shapes`.
"""

import math
import os

# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------


def _curve(points, degree=1, periodic=False):
    return {"points": [tuple(float(v) for v in p) for p in points], "degree": degree, "periodic": periodic}


def _circle_cv_radius(sections):
    """CV radius so a periodic cubic through ``sections`` CVs has radius 1."""
    return 6.0 / (4.0 + 2.0 * math.cos(2.0 * math.pi / sections))


def _ring(radius=1.0, sections=8, plane="xz", center=(0.0, 0.0, 0.0), phase=0.0, cv=True):
    """Points on a circle. ``cv=True`` compensates for cubic smoothing."""
    r = radius * (_circle_cv_radius(sections) if cv else 1.0)
    points = []
    for i in range(sections):
        angle = 2.0 * math.pi * i / sections + phase
        a, b = math.cos(angle) * r, math.sin(angle) * r
        if plane == "xz":
            p = (a, 0.0, b)
        elif plane == "xy":
            p = (a, b, 0.0)
        else:  # yz
            p = (0.0, a, b)
        points.append((p[0] + center[0], p[1] + center[1], p[2] + center[2]))
    return points


def _circle(radius=1.0, sections=8, plane="xz", center=(0.0, 0.0, 0.0)):
    return _curve(_ring(radius, sections, plane, center), degree=3, periodic=True)


def _polygon(sides, radius=1.0, phase=0.0):
    pts = _ring(radius, sides, "xz", phase=phase, cv=False)
    return _curve(pts + [pts[0]])


def _arc_points(radius, start_deg, end_deg, steps, plane="xz", center=(0.0, 0.0, 0.0)):
    points = []
    for i in range(steps + 1):
        angle = math.radians(start_deg + (end_deg - start_deg) * i / float(steps))
        a, b = math.cos(angle) * radius, math.sin(angle) * radius
        if plane == "xz":
            p = (a, 0.0, b)
        elif plane == "xy":
            p = (a, b, 0.0)
        else:
            p = (0.0, a, b)
        points.append((p[0] + center[0], p[1] + center[1], p[2] + center[2]))
    return points


def _closed(points):
    points = list(points)
    return _curve(points + [points[0]])


def _scale_points(points, factor):
    if isinstance(factor, (int, float)):
        factor = (factor, factor, factor)
    return [(p[0] * factor[0], p[1] * factor[1], p[2] * factor[2]) for p in points]


def _translate_points(points, offset):
    return [(p[0] + offset[0], p[1] + offset[1], p[2] + offset[2]) for p in points]


def _rotate_y(points, degrees):
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return [(p[0] * c + p[2] * s, p[1], -p[0] * s + p[2] * c) for p in points]


# ---------------------------------------------------------------------------
# Shape definitions
# ---------------------------------------------------------------------------
def _arrow_outline(length=2.0, width=0.5, head_width=1.0, head_length=0.8):
    """Flat arrow outline in XZ pointing +Z, base at -length/2."""
    half = length / 2.0
    w, hw = width / 2.0, head_width / 2.0
    neck = half - head_length
    return [(-w, 0, -half), (-w, 0, neck), (-hw, 0, neck), (0, 0, half), (hw, 0, neck), (w, 0, neck),
            (w, 0, -half), (-w, 0, -half)]


def _double_arrow_outline(length=2.0, width=0.4, head_width=0.9, head_length=0.6):
    half = length / 2.0
    w, hw = width / 2.0, head_width / 2.0
    neck = half - head_length
    return [(-w, 0, -neck), (-w, 0, neck), (-hw, 0, neck), (0, 0, half), (hw, 0, neck), (w, 0, neck),
            (w, 0, -neck), (hw, 0, -neck), (0, 0, -half), (-hw, 0, -neck), (-w, 0, -neck)]


def _quad_arrow_outline(size=1.0, width=0.2, head_width=0.45, head_length=0.3):
    w, hw = width, head_width
    neck = size - head_length
    quarter = [(w, 0, w), (w, 0, neck), (hw, 0, neck), (0, 0, size), (-hw, 0, neck), (-w, 0, neck)]
    points = []
    # quarters are laid out clockwise seen from above so the outline closes
    for angle in (0, -90, -180, -270):
        points.extend(_rotate_y(quarter, angle))
    return points + [points[0]]


def _arc_arrow(start_deg, end_deg, radius=1.0, head_length=0.3, head_width=0.2, steps=10, double=False):
    """Arc in XZ with an arrow head at the end (and the start if ``double``)."""
    curves = [_curve(_arc_points(radius, start_deg, end_deg, steps))]
    direction = 1.0 if end_deg > start_deg else -1.0

    def head(angle_deg, sign):
        a = math.radians(angle_deg)
        tip = (math.cos(a) * radius, 0.0, math.sin(a) * radius)
        travel = (-math.sin(a) * sign, 0.0, math.cos(a) * sign)
        side = (math.cos(a), 0.0, math.sin(a))
        back = (tip[0] - travel[0] * head_length, 0.0, tip[2] - travel[2] * head_length)
        return _curve([
            (back[0] + side[0] * head_width, 0.0, back[2] + side[2] * head_width),
            tip,
            (back[0] - side[0] * head_width, 0.0, back[2] - side[2] * head_width),
        ])

    curves.append(head(end_deg, direction))
    if double:
        curves.append(head(start_deg, -direction))
    return curves

def _sphere(radius=1.0):
    return [_circle(radius, 8, "xz"), _circle(radius, 8, "xy"), _circle(radius, 8, "yz")]


def _cube(size=1.0):
    s = size
    pts = [(-s, s, s), (s, s, s), (s, s, -s), (-s, s, -s), (-s, s, s), (-s, -s, s), (s, -s, s), (s, s, s),
           (s, -s, s), (s, -s, -s), (s, s, -s), (s, -s, -s), (-s, -s, -s), (-s, s, -s), (-s, -s, -s), (-s, -s, s)]
    return [_curve(pts)]


def _box(x=1.0, y=1.0, z=1.0, offset=(0.0, 0.0, 0.0)):
    pts = _cube(1.0)[0]["points"]
    return [_curve(_translate_points(_scale_points(pts, (x, y, z)), offset))]


def _pyramid():
    pts = [(-1, 0, 1), (1, 0, 1), (1, 0, -1), (-1, 0, -1), (-1, 0, 1), (0, 1.5, 0), (1, 0, 1), (1, 0, -1),
           (0, 1.5, 0), (-1, 0, -1)]
    return [_curve(pts)]


def _octahedron():
    pts = [(0, 1, 0), (1, 0, 0), (0, -1, 0), (-1, 0, 0), (0, 1, 0), (0, 0, 1), (0, -1, 0), (0, 0, -1),
           (0, 1, 0), (1, 0, 0), (0, 0, 1), (-1, 0, 0), (0, 0, -1), (1, 0, 0)]
    return [_curve(pts)]


def _cone():
    base = _circle(1.0)
    lines = []
    for x, z in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        lines.append(_curve([(x, 0, z), (0, 2, 0)]))
    return [base] + lines


def _cylinder(radius=1.0, height=2.0):
    half = height / 2.0
    top = _circle(radius, 8, "xz", (0, half, 0))
    bottom = _circle(radius, 8, "xz", (0, -half, 0))
    lines = [_curve([(x * radius, half, z * radius), (x * radius, -half, z * radius)])
             for x, z in ((1, 0), (-1, 0), (0, 1), (0, -1))]
    return [top, bottom] + lines


def _capsule(radius=0.5, length=2.0):
    half = length / 2.0 - radius
    right = _arc_points(radius, -90, 90, 8, center=(half, 0, 0))
    left = _arc_points(radius, 90, 270, 8, center=(-half, 0, 0))
    return [_closed(right + left)]

def _locator(size=1.0):
    s = size
    return [_curve([(-s, 0, 0), (s, 0, 0)]), _curve([(0, -s, 0), (0, s, 0)]), _curve([(0, 0, -s), (0, 0, s)])]


def _pin(head="square", height=1.5, head_size=0.25):
    stem = _curve([(0, 0, 0), (0, height, 0)])
    hs = head_size
    if head == "square":
        top = _curve([(-hs, height, 0), (hs, height, 0), (hs, height + 2 * hs, 0), (-hs, height + 2 * hs, 0),
                      (-hs, height, 0)])
        return [stem, top]
    if head == "circle":
        return [stem, _circle(hs, 8, "xy", (0, height + hs, 0))]
    if head == "sphere":
        center = (0, height + hs, 0)
        return [stem, _circle(hs, 8, "xy", center), _circle(hs, 8, "yz", center), _circle(hs, 8, "xz", center)]
    if head == "diamond":
        c = height + hs
        top = _curve([(0, c + hs, 0), (hs, c, 0), (0, c - hs, 0), (-hs, c, 0), (0, c + hs, 0), (0, c, hs),
                      (0, c - hs, 0), (0, c, -hs), (0, c + hs, 0)])
        return [stem, top]
    if head == "arrow":
        top = _curve([(-hs, height, 0), (0, height + 2 * hs, 0), (hs, height, 0), (-hs, height, 0)])
        return [stem, top]
    raise ValueError(head)


def _star(points=5, outer=1.0, inner=0.45):
    pts = []
    for i in range(points * 2):
        r = outer if i % 2 == 0 else inner
        angle = math.pi * i / points + math.pi / 2.0
        pts.append((math.cos(angle) * r, 0, math.sin(angle) * r))
    return [_closed(pts)]


def _gear(teeth=8, outer=1.0, inner=0.8, hole=0.4):
    pts = []
    steps = teeth * 4
    for i in range(steps):
        angle = 2.0 * math.pi * i / steps
        r = outer if (i % 4) in (1, 2) else inner
        pts.append((math.cos(angle) * r, 0, math.sin(angle) * r))
    return [_closed(pts), _circle(hole)]


def _cog(lobes=8, outer=1.0, inner=0.8):
    sections = lobes * 2
    pts = []
    for i in range(sections):
        angle = 2.0 * math.pi * i / sections
        r = outer if i % 2 == 0 else inner
        pts.append((math.cos(angle) * r, 0, math.sin(angle) * r))
    return [_curve(pts, degree=3, periodic=True)]


def _crown(points=6, radius=1.0, low=0.0, high=0.5):
    top = []
    for i in range(points * 2):
        angle = 2.0 * math.pi * i / (points * 2)
        h = high if i % 2 == 0 else low + (high - low) * 0.4
        top.append((math.cos(angle) * radius, h, math.sin(angle) * radius))
    return [_circle(radius), _closed(top)]


def _foot():
    pts = [(0.0, 0, -1.0), (0.35, 0, -0.9), (0.45, 0, -0.4), (0.4, 0, 0.1), (0.55, 0, 0.6), (0.5, 0, 0.95),
           (0.2, 0, 1.15), (-0.2, 0, 1.15), (-0.45, 0, 0.9), (-0.45, 0, 0.3), (-0.35, 0, -0.4), (-0.35, 0, -0.9)]
    return [_curve(pts, degree=3, periodic=True)]


def _hand():
    pts = [(-0.5, 0, -1.0), (0.5, 0, -1.0), (0.55, 0, 0.0), (0.5, 0, 0.9), (0.3, 0, 1.0), (0.2, 0, 0.3),
           (0.1, 0, 1.15), (-0.1, 0, 1.15), (-0.2, 0, 0.3), (-0.3, 0, 1.0), (-0.5, 0, 0.9), (-0.55, 0, 0.0),
           (-0.9, 0, 0.35), (-1.0, 0, 0.2), (-0.55, 0, -0.5)]
    return [_curve(pts, degree=3, periodic=True)]


def _eye():
    upper = _arc_points(1.25, 37, 143, 8, center=(0, 0, -0.75))
    lower = _arc_points(1.25, 217, 323, 8, center=(0, 0, 0.75))
    almond = [(p[0], 0, p[2]) for p in upper] + [(p[0], 0, p[2]) for p in lower]
    return [_closed(almond), _circle(0.3)]


def _rounded_square(size=1.0, corner=0.3, steps=4):
    pts = []
    s = size - corner
    for cx, cz, start in ((s, s, 0), (-s, s, 90), (-s, -s, 180), (s, -s, 270)):
        pts.extend(_arc_points(corner, start, start + 90, steps, center=(cx, 0, cz)))
    return [_closed(pts)]


def _circle_arrows(radius=1.0):
    shapes = [_circle(radius)]
    head = 0.25
    for angle in (0, 90, 180, 270):
        arrow = [(-head, 0, radius + 0.1), (0, 0, radius + 0.1 + head * 1.6), (head, 0, radius + 0.1),
                 (-head, 0, radius + 0.1)]
        shapes.append(_curve(_rotate_y(arrow, angle)))
    return shapes


def _master(radius=1.0):
    """Big circle with a forward pointing notch - the classic world control."""
    shapes = [_circle(radius)]
    shapes.append(_curve([(-0.25, 0, radius * 1.02), (0, 0, radius * 1.35), (0.25, 0, radius * 1.02)]))
    return shapes


def _target():
    return [_circle(1.0), _circle(0.5), _curve([(-1.25, 0, 0), (1.25, 0, 0)]), _curve([(0, 0, -1.25), (0, 0, 1.25)])]


def _quad_arrow_curved(size=0.9):
    """Four arrows projected on a sphere - eyes, shoulders, look-at controls."""
    flat = _quad_arrow_outline(size, width=0.12, head_width=0.3, head_length=0.25)
    pts = []
    for x, _y, z in flat:
        d = min(0.999, x * x + z * z)
        pts.append((x, math.sqrt(1.0 - d) - 0.4, z))
    return [_curve(pts)]


def _dumbbell(length=1.0, radius=0.25):
    return [_curve([(0, 0, 0), (0, length, 0)]), _circle(radius, 8, "xy", (0, length + radius, 0)),
            _circle(radius, 8, "yz", (0, length + radius, 0))]


def _u_shape():
    arc = _arc_points(0.6, 180, 360, 8, center=(0, 0, 0.4))
    arc = [(p[0], 0, -p[2] + 0.8) for p in arc]
    return [_curve([(-0.6, 0, -0.8)] + arc + [(0.6, 0, -0.8)])]

def _teardrop():
    arc = _arc_points(0.6, 140, 400, 10, center=(0, 0, -0.2))
    return [_closed(arc + [(0, 0, 1.0)])]

def _half_sphere(radius=1.0):
    arc1 = _curve(_arc_points(radius, 0, 180, 8, "xy"), degree=3)
    arc2 = _curve(_arc_points(radius, 0, 180, 8, "yz"), degree=3)
    return [_circle(radius), arc1, arc2]


def _circle_pointer():
    return [_circle(1.0), _curve([(-0.25, 0, 1.15), (0, 0, 1.6), (0.25, 0, 1.15), (-0.25, 0, 1.15)])]


def _cross():
    t = 0.3
    pts = [(-t, 0, -1), (t, 0, -1), (t, 0, -t), (1, 0, -t), (1, 0, t), (t, 0, t), (t, 0, 1), (-t, 0, 1),
           (-t, 0, t), (-1, 0, t), (-1, 0, -t), (-t, 0, -t), (-t, 0, -1)]
    return [_curve(pts)]


def _cross_3d():
    t = 0.25
    return [_box(1.0, t, t)[0], _box(t, 1.0, t)[0], _box(t, t, 1.0)[0]]


def _square_cross():
    return [_curve([(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1), (-1, 0, -1)]),
            _curve([(-1, 0, -1), (1, 0, 1)]), _curve([(1, 0, -1), (-1, 0, 1)])]


def _arrow_3d():
    flat = _arrow_outline(2.0, 0.4, 1.0, 0.8)
    vertical = [(0, x, z) for x, _y, z in flat]
    return [_curve(flat), _curve(vertical)]


def _hip():
    return _box(1.2, 0.4, 0.8)


def _chest():
    pts = _ring(1.0, 8, "xz", cv=False)
    top = _translate_points(_scale_points(pts, (1.0, 1.0, 0.7)), (0, 0.3, 0))
    bottom = _translate_points(_scale_points(pts, (0.8, 1.0, 0.6)), (0, -0.3, 0))
    curves = [_closed(top), _closed(bottom)]
    for a, b in zip(top[::2], bottom[::2]):
        curves.append(_curve([a, b]))
    return curves


def _spiral(turns=2.0, steps=24):
    pts = []
    for i in range(steps + 1):
        t = i / float(steps)
        angle = 2.0 * math.pi * turns * t
        r = 0.2 + 0.8 * t
        pts.append((math.cos(angle) * r, 0, math.sin(angle) * r))
    return [_curve(pts, degree=3)]


def _flower(petals=6):
    pts = []
    sections = petals * 4
    for i in range(sections):
        angle = 2.0 * math.pi * i / sections
        r = 0.4 + 0.6 * abs(math.sin(petals * angle / 2.0))
        pts.append((math.cos(angle) * r, 0, math.sin(angle) * r))
    return [_curve(pts, degree=3, periodic=True)]


def _heart():
    pts = []
    steps = 24
    for i in range(steps):
        t = 2.0 * math.pi * i / steps
        x = 16 * math.sin(t) ** 3
        z = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((x / 16.0, 0, z / 16.0))
    return [_curve(pts, degree=3, periodic=True)]


SHAPES = {
    # 2D basics
    "circle": [_circle()],
    "half_circle": [_curve(_arc_points(1.0, 0, 180, 8), degree=3)],
    "square": [_curve([(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1), (-1, 0, -1)])],
    "rectangle": [_curve([(-1, 0, -0.5), (1, 0, -0.5), (1, 0, 0.5), (-1, 0, 0.5), (-1, 0, -0.5)])],
    "rounded_square": _rounded_square(),
    "triangle": [_curve([(-1, 0, -0.75), (1, 0, -0.75), (0, 0, 1), (-1, 0, -0.75)])],
    "diamond": [_curve([(0, 0, 1), (1, 0, 0), (0, 0, -1), (-1, 0, 0), (0, 0, 1)])],
    "hexagon": [_polygon(6)],
    "octagon": [_polygon(8, phase=math.pi / 8)],
    "star": _star(),
    "cross": _cross(),
    "square_cross": _square_cross(),
    "capsule": _capsule(),
    "teardrop": _teardrop(),
    "heart": _heart(),
    "line": [_curve([(0, 0, 0), (0, 1, 0)])],
    "spiral": _spiral(),
    "flower": _flower(),
    "target": _target(),
    "circle_pointer": _circle_pointer(),
    "u_shape": _u_shape(),
    # arrows
    "arrow": [_curve(_arrow_outline())],
    "double_arrow": [_curve(_double_arrow_outline())],
    "quad_arrow": [_curve(_quad_arrow_outline())],
    "curved_arrow": _arc_arrow(45, 135),
    "double_curved_arrow": _arc_arrow(30, 150, double=True),
    "semicircle_arrow": _arc_arrow(10, 170, steps=12),
    "quad_arrow_curved": _quad_arrow_curved(),
    "arrow_3d": _arrow_3d(),
    "circle_arrows": _circle_arrows(),
    # 3D
    "sphere": _sphere(),
    "half_sphere": _half_sphere(),
    "cube": _cube(),
    "box_flat": _box(1.0, 0.25, 1.0),
    "pyramid": _pyramid(),
    "octahedron": _octahedron(),
    "cone": _cone(),
    "cylinder": _cylinder(),
    "locator": _locator(),
    "cross_3d": _cross_3d(),
    "dumbbell": _dumbbell(),
    # pins / lollipops
    "pin_square": _pin("square"),
    "pin_circle": _pin("circle"),
    "pin_sphere": _pin("sphere"),
    "pin_diamond": _pin("diamond"),
    "pin_arrow": _pin("arrow"),
    # rig specific
    "master": _master(),
    "cog": _cog(),
    "gear": _gear(),
    "crown": _crown(),
    "foot": _foot(),
    "hand": _hand(),
    "eye": _eye(),
    "hip": _hip(),
    "chest": _chest(),
}

#: Suggested shapes per usage - used by the UI and the auto-rigger.
CATEGORIES = {
    "2D": ["circle", "half_circle", "square", "rectangle", "rounded_square", "triangle", "diamond", "hexagon",
           "octagon", "star", "cross", "square_cross", "capsule", "teardrop", "heart", "line", "spiral",
           "flower", "target", "circle_pointer", "u_shape"],
    "Arrows": ["arrow", "double_arrow", "quad_arrow", "curved_arrow", "double_curved_arrow",
               "semicircle_arrow", "quad_arrow_curved", "arrow_3d", "circle_arrows"],
    "3D": ["sphere", "half_sphere", "cube", "box_flat", "pyramid", "octahedron", "cone", "cylinder", "locator",
           "cross_3d", "dumbbell"],
    "Pins": ["pin_square", "pin_circle", "pin_sphere", "pin_diamond", "pin_arrow"],
    "Rig": ["master", "cog", "gear", "crown", "foot", "hand", "eye", "hip", "chest"],
}


# ---------------------------------------------------------------------------
# Transform helpers
# ---------------------------------------------------------------------------
def orient_points(points, axis="y"):
    """Rotate shape points authored facing +Y so they face ``axis``."""
    axis = axis.lower()
    if axis in ("y", "+y"):
        return [tuple(p) for p in points]
    if axis == "-y":
        return [(p[0], -p[1], -p[2]) for p in points]
    if axis in ("x", "+x"):
        return [(p[1], -p[0], p[2]) for p in points]
    if axis == "-x":
        return [(-p[1], p[0], p[2]) for p in points]
    if axis in ("z", "+z"):
        return [(p[0], -p[2], p[1]) for p in points]
    if axis == "-z":
        return [(p[0], p[2], -p[1]) for p in points]
    raise ValueError("axis must be one of x, -x, y, -y, z, -z")


def transform_shape(curves, size=1.0, axis="y", offset=(0.0, 0.0, 0.0)):
    """Return a copy of shape data scaled, oriented and offset."""
    result = []
    for curve in curves:
        points = _scale_points(curve["points"], size)
        points = orient_points(points, axis)
        points = _translate_points(points, offset)
        new = dict(curve)
        new["points"] = points
        result.append(new)
    return result


def knots_for(count, degree, periodic):
    """Knot vector for ``count`` CVs (overlapping CVs included when periodic)."""
    if degree == 1:
        return [float(i) for i in range(count)]
    if periodic:
        return [float(i) for i in range(-(degree - 1), count)]
    spans = count - degree
    knots = [0.0] * degree
    knots += [float(i) for i in range(1, spans)]
    knots += [float(spans)] * degree
    return knots


def validate(curves):
    """Raise ``ValueError`` if shape data cannot become a NURBS curve."""
    if not curves:
        raise ValueError("Shape has no curves")
    for curve in curves:
        degree = curve.get("degree", 1)
        count = len(curve["points"])
        if degree not in (1, 2, 3, 5, 7):
            raise ValueError("Unsupported degree %s" % degree)
        if curve.get("periodic") and count < degree + 1:
            raise ValueError("Periodic curve needs at least %d points" % (degree + 1))
        if not curve.get("periodic") and count < degree + 1:
            raise ValueError("Open curve of degree %d needs at least %d points" % (degree, degree + 1))
    return True


# ---------------------------------------------------------------------------
# User library
# ---------------------------------------------------------------------------
def user_library_dir():
    from jeffy.core import fileio

    return fileio.user_dir("shapes")


def _user_shapes():
    try:
        folder = user_library_dir()
    except Exception:
        return {}
    shapes = {}
    if not os.path.isdir(folder):
        return shapes
    from jeffy.core import fileio

    for name in sorted(os.listdir(folder)):
        if not name.endswith(".json"):
            continue
        try:
            data = fileio.read_json(os.path.join(folder, name))
            curves = data["curves"] if isinstance(data, dict) else data
            validate(curves)
            shapes[os.path.splitext(name)[0]] = curves
        except (ValueError, KeyError, OSError):
            continue
    return shapes


def list_shapes(include_user=True):
    names = list(SHAPES)
    if include_user:
        names += [n for n in _user_shapes() if n not in SHAPES]
    return names


def get_shape(name):
    """Return a deep copy of the shape data for ``name``."""
    if name in SHAPES:
        curves = SHAPES[name]
    else:
        user = _user_shapes()
        if name not in user:
            raise KeyError("Unknown control shape %r" % name)
        curves = user[name]
    return [{"points": [tuple(p) for p in c["points"]], "degree": c.get("degree", 1),
             "periodic": c.get("periodic", False)} for c in curves]
