"""Pure Python vector / matrix math (no Maya dependency).

Conventions match Maya:

* Vectors are 3 element sequences ``(x, y, z)``.
* Matrices are flat lists of 16 floats in Maya's row major order. The first
  three rows are the X, Y and Z axes of the transform and the fourth row is
  the translation (``cmds.xform(q=True, matrix=True)`` returns exactly this).
* Points are row vectors multiplied on the left: ``p' = p * M``. Therefore
  ``mult(child_local, parent_world)`` gives the child world matrix.
* Angles are in degrees unless stated otherwise.
"""

import math

EPSILON = 1e-9
AXES = ("x", "y", "z")
AXIS_INDEX = {"x": 0, "y": 1, "z": 2}
ROTATE_ORDERS = ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")


# ---------------------------------------------------------------------------
# Scalars
# ---------------------------------------------------------------------------
def clamp(value, minimum=0.0, maximum=1.0):
    return max(minimum, min(maximum, value))


def lerp(a, b, t):
    return a + (b - a) * t


def remap(value, old_min, old_max, new_min=0.0, new_max=1.0, clamped=True):
    if abs(old_max - old_min) < EPSILON:
        return new_min
    t = (value - old_min) / float(old_max - old_min)
    if clamped:
        t = clamp(t)
    return new_min + (new_max - new_min) * t


def linstep(edge0, edge1, value):
    return remap(value, edge0, edge1, 0.0, 1.0, clamped=True)


def smoothstep(edge0, edge1, value):
    t = linstep(edge0, edge1, value)
    return t * t * (3.0 - 2.0 * t)


def distribute(count, start=0.0, end=1.0):
    """Return ``count`` evenly spaced values between ``start`` and ``end``."""
    if count <= 0:
        return []
    if count == 1:
        return [(start + end) * 0.5]
    step = (end - start) / float(count - 1)
    return [start + step * i for i in range(count)]


# ---------------------------------------------------------------------------
# Vectors
# ---------------------------------------------------------------------------
def vec(value):
    return (float(value[0]), float(value[1]), float(value[2]))


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a, factor):
    return (a[0] * factor, a[1] * factor, a[2] * factor)


def negate(a):
    return (-a[0], -a[1], -a[2])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def length(a):
    return math.sqrt(dot(a, a))


def distance(a, b):
    return length(sub(a, b))


def normalize(a):
    size = length(a)
    if size < EPSILON:
        return (0.0, 0.0, 0.0)
    return (a[0] / size, a[1] / size, a[2] / size)


def lerp_vector(a, b, t):
    return (lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t))


def midpoint(a, b):
    return lerp_vector(a, b, 0.5)


def centroid(points):
    points = list(points)
    if not points:
        return (0.0, 0.0, 0.0)
    count = float(len(points))
    return (
        sum(p[0] for p in points) / count,
        sum(p[1] for p in points) / count,
        sum(p[2] for p in points) / count,
    )


def bounding_box(points):
    points = list(points)
    if not points:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    mins = tuple(min(p[i] for p in points) for i in range(3))
    maxs = tuple(max(p[i] for p in points) for i in range(3))
    return mins, maxs


def angle_between(a, b):
    """Angle between two vectors in degrees."""
    na, nb = normalize(a), normalize(b)
    return math.degrees(math.acos(clamp(dot(na, nb), -1.0, 1.0)))


def is_parallel(a, b, tolerance=1e-6):
    return length(cross(normalize(a), normalize(b))) < tolerance


def axis_vector(axis):
    """``'x'`` -> (1, 0, 0), ``'-y'`` -> (0, -1, 0) ..."""
    axis = axis.lower().strip()
    sign = -1.0 if axis.startswith("-") else 1.0
    index = AXIS_INDEX[axis.lstrip("+-")]
    result = [0.0, 0.0, 0.0]
    result[index] = sign
    return tuple(result)


def reflect(point, axis="x"):
    """Mirror a point (or direction) across the plane normal to ``axis``."""
    index = AXIS_INDEX[axis.lstrip("+-").lower()]
    result = list(point)
    result[index] = -result[index]
    return tuple(result)


def closest_point_on_line(point, line_start, line_end, clamp_to_segment=False):
    direction = sub(line_end, line_start)
    denom = dot(direction, direction)
    if denom < EPSILON:
        return tuple(line_start)
    t = dot(sub(point, line_start), direction) / denom
    if clamp_to_segment:
        t = clamp(t)
    return add(line_start, scale(direction, t))


def plane_normal(a, b, c):
    """Normal of the plane passing through three points (unit length)."""
    return normalize(cross(sub(b, a), sub(c, a)))


def project_on_plane(point, plane_point, normal):
    normal = normalize(normal)
    offset = dot(sub(point, plane_point), normal)
    return sub(point, scale(normal, offset))


def best_fit_plane_normal(points):
    """Approximate plane normal using Newell's method (robust for chains)."""
    points = list(points)
    nx = ny = nz = 0.0
    count = len(points)
    for i in range(count):
        current = points[i]
        nxt = points[(i + 1) % count]
        nx += (current[1] - nxt[1]) * (current[2] + nxt[2])
        ny += (current[2] - nxt[2]) * (current[0] + nxt[0])
        nz += (current[0] - nxt[0]) * (current[1] + nxt[1])
    return normalize((nx, ny, nz))


def pole_vector_position(start, mid, end, distance_factor=1.0):
    """Ideal pole vector position for a 3 joint chain.

    The result lies in the plane of the chain, in the direction the middle
    joint bends, at ``distance_factor`` times the chain length from ``mid``.
    """
    chain_length = distance(start, mid) + distance(mid, end)
    projected = closest_point_on_line(mid, start, end)
    direction = sub(mid, projected)
    if length(direction) < 1e-5:
        # Straight chain - pick any direction perpendicular to the chain.
        limb = normalize(sub(end, start))
        helper = (0.0, 0.0, 1.0) if abs(limb[2]) < 0.9 else (1.0, 0.0, 0.0)
        direction = cross(limb, helper)
    direction = normalize(direction)
    return add(mid, scale(direction, chain_length * distance_factor))


def planarize(points, normal=None):
    """Project every point onto the plane through first/last points.

    Useful to make an arm or leg chain perfectly planar before building an IK.
    When ``normal`` is omitted the best fit plane through the first, the
    furthest (from the start-end line) and the last point is used.
    """
    points = [vec(p) for p in points]
    if len(points) < 3:
        return points
    first, last = points[0], points[-1]
    if normal is None:
        furthest = max(
            points[1:-1],
            key=lambda p: distance(p, closest_point_on_line(p, first, last)),
        )
        normal = plane_normal(first, furthest, last)
        if length(normal) < EPSILON:
            return points
    return [project_on_plane(p, first, normal) for p in points]


# ---------------------------------------------------------------------------
# Matrices (flat 16 lists, row major, Maya convention)
# ---------------------------------------------------------------------------
IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)


def identity():
    return list(IDENTITY)


def from_axes(x_axis, y_axis, z_axis, translate=(0.0, 0.0, 0.0)):
    return [
        x_axis[0], x_axis[1], x_axis[2], 0.0,
        y_axis[0], y_axis[1], y_axis[2], 0.0,
        z_axis[0], z_axis[1], z_axis[2], 0.0,
        translate[0], translate[1], translate[2], 1.0,
    ]  # fmt: skip


def axes(matrix):
    """Return ``(x_axis, y_axis, z_axis, translate)`` of a matrix."""
    m = matrix
    return (
        (m[0], m[1], m[2]),
        (m[4], m[5], m[6]),
        (m[8], m[9], m[10]),
        (m[12], m[13], m[14]),
    )


def get_translation(matrix):
    return (matrix[12], matrix[13], matrix[14])


def set_translation(matrix, translate):
    result = list(matrix)
    result[12], result[13], result[14] = translate
    return result


def get_scale(matrix):
    x, y, z, _t = axes(matrix)
    return (length(x), length(y), length(z))


def mult(a, b):
    """Matrix product ``a * b`` (apply ``a`` first, then ``b``)."""
    result = [0.0] * 16
    for row in range(4):
        for col in range(4):
            result[row * 4 + col] = (
                a[row * 4 + 0] * b[0 * 4 + col]
                + a[row * 4 + 1] * b[1 * 4 + col]
                + a[row * 4 + 2] * b[2 * 4 + col]
                + a[row * 4 + 3] * b[3 * 4 + col]
            )
    return result


def mult_all(*matrices):
    result = identity()
    for matrix in matrices:
        result = mult(result, matrix)
    return result


def transpose(matrix):
    return [matrix[col * 4 + row] for row in range(4) for col in range(4)]


def inverse(matrix):
    """General 4x4 inverse (Gauss-Jordan elimination with pivoting)."""
    m = [list(matrix[row * 4:row * 4 + 4]) + [1.0 if row == i else 0.0 for i in range(4)] for row in range(4)]
    for col in range(4):
        pivot = max(range(col, 4), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            raise ValueError("Matrix is singular and cannot be inverted")
        m[col], m[pivot] = m[pivot], m[col]
        factor = m[col][col]
        m[col] = [v / factor for v in m[col]]
        for row in range(4):
            if row != col:
                ratio = m[row][col]
                if ratio:
                    m[row] = [rv - ratio * cv for rv, cv in zip(m[row], m[col])]
    return [m[row][4 + col] for row in range(4) for col in range(4)]


def transform_point(point, matrix):
    x, y, z = point
    m = matrix
    return (
        x * m[0] + y * m[4] + z * m[8] + m[12],
        x * m[1] + y * m[5] + z * m[9] + m[13],
        x * m[2] + y * m[6] + z * m[10] + m[14],
    )


def transform_vector(vector, matrix):
    x, y, z = vector
    m = matrix
    return (
        x * m[0] + y * m[4] + z * m[8],
        x * m[1] + y * m[5] + z * m[9],
        x * m[2] + y * m[6] + z * m[10],
    )


def orthonormalize(matrix, primary="x", secondary="y"):
    """Remove scale and shear, keeping ``primary`` exact and ``secondary`` close."""
    x, y, z, t = axes(matrix)
    rows = {"x": x, "y": y, "z": z}
    a = normalize(rows[primary])
    b = rows[secondary]
    third = [k for k in AXES if k not in (primary, secondary)][0]
    order = {primary: a}
    c = normalize(_cross_for(primary, secondary, a, b))
    order[third] = c
    order[secondary] = normalize(_cross_for(third, primary, c, a))
    return from_axes(order["x"], order["y"], order["z"], t)


def _cross_for(first, second, a, b):
    """Return the third axis such that the resulting frame is right handed."""
    sequence = "xyzxy"
    if sequence.find(first + second) != -1:  # cyclic (x,y)->z, (y,z)->x, (z,x)->y
        return cross(a, b)
    return cross(b, a)


def is_identity(matrix, tolerance=1e-5):
    return all(abs(a - b) <= tolerance for a, b in zip(matrix, IDENTITY))


def is_close(a, b, tolerance=1e-5):
    return all(abs(x - y) <= tolerance for x, y in zip(a, b))


def aim_matrix(position, aim_vector, up_vector, aim_axis="x", up_axis="y"):
    """Build a matrix at ``position`` whose ``aim_axis`` points along ``aim_vector``.

    ``aim_axis`` and ``up_axis`` accept signed axes (``"-x"``, ``"z"`` ...).
    """
    aim_name = aim_axis.lstrip("+-").lower()
    up_name = up_axis.lstrip("+-").lower()
    if aim_name == up_name:
        raise ValueError("aim_axis and up_axis must be different axes")
    aim = normalize(aim_vector)
    if length(aim) < EPSILON:
        raise ValueError("aim_vector has zero length")
    up = normalize(up_vector)
    if length(up) < EPSILON or is_parallel(aim, up):
        helper = (0.0, 1.0, 0.0) if abs(aim[1]) < 0.95 else (0.0, 0.0, 1.0)
        up = helper
    side = normalize(cross(aim, up))
    up = normalize(cross(side, aim))

    aim_sign = -1.0 if aim_axis.startswith("-") else 1.0
    up_sign = -1.0 if up_axis.startswith("-") else 1.0
    rows = {aim_name: scale(aim, aim_sign), up_name: scale(up, up_sign)}
    third = [k for k in AXES if k not in rows][0]
    i = AXIS_INDEX[third]
    nxt, nxt2 = AXES[(i + 1) % 3], AXES[(i + 2) % 3]
    rows[third] = normalize(cross(rows[nxt], rows[nxt2]))
    return from_axes(rows["x"], rows["y"], rows["z"], position)


MIRROR_MODES = ("behavior", "orientation", "position")


def mirror_matrix(matrix, axis="x", mode="behavior"):
    """Mirror a world matrix across the plane normal to ``axis``.

    Modes:

    * ``behavior``    - like Maya's mirrorJoint *behavior*: identical rotation
      values on both sides produce mirrored motion.
    * ``orientation`` - the mirrored orientation is the reflection conjugate,
      world aligned objects stay world aligned (good for IK/foot controls).
    * ``position``    - only the position is mirrored, orientation is kept.
    """
    if mode not in MIRROR_MODES:
        raise ValueError("mode must be one of %s" % (MIRROR_MODES,))
    x, y, z, t = axes(matrix)
    index = AXIS_INDEX[axis.lstrip("+-").lower()]
    new_t = reflect(t, axis)
    if mode == "position":
        return from_axes(x, y, z, new_t)
    if mode == "behavior":
        rows = [negate(reflect(v, axis)) for v in (x, y, z)]
    else:
        rows = []
        for i, v in enumerate((x, y, z)):
            mirrored = reflect(v, axis)
            rows.append(negate(mirrored) if i == index else mirrored)
    return from_axes(rows[0], rows[1], rows[2], new_t)


# ---------------------------------------------------------------------------
# Euler rotations
# ---------------------------------------------------------------------------
def rotation_matrix(axis, degrees):
    """Row-vector rotation matrix about a single world axis."""
    radians = math.radians(degrees)
    c, s = math.cos(radians), math.sin(radians)
    axis = axis.lower()
    if axis == "x":
        rows = ((1, 0, 0), (0, c, s), (0, -s, c))
    elif axis == "y":
        rows = ((c, 0, -s), (0, 1, 0), (s, 0, c))
    elif axis == "z":
        rows = ((c, s, 0), (-s, c, 0), (0, 0, 1))
    else:
        raise ValueError("axis must be x, y or z")
    return from_axes(rows[0], rows[1], rows[2])


def euler_to_matrix(rotation, order="xyz", translate=(0.0, 0.0, 0.0)):
    """Compose a matrix from Euler angles (degrees) using a Maya rotate order."""
    order = order.lower()
    if order not in ROTATE_ORDERS:
        raise ValueError("Unknown rotate order %r" % order)
    values = dict(zip(AXES, rotation))
    result = identity()
    for axis in order:
        result = mult(result, rotation_matrix(axis, values[axis]))
    return set_translation(result, translate)


def matrix_to_euler(matrix, order="xyz"):
    """Decompose the rotation of a matrix into Euler angles (degrees)."""
    order = order.lower()
    if order not in ROTATE_ORDERS:
        raise ValueError("Unknown rotate order %r" % order)
    clean = orthonormalize(matrix)
    # Column-convention rotation matrix R = transpose(M) (3x3 part).
    r = [[clean[col * 4 + row] for col in range(3)] for row in range(3)]
    i, j, k = (AXIS_INDEX[a] for a in order)
    even = order in ("xyz", "yzx", "zxy")
    sign = 1.0 if even else -1.0

    sin_b = clamp(-sign * r[k][i], -1.0, 1.0)
    b = math.asin(sin_b)
    if abs(math.cos(b)) > 1e-6:
        a = math.atan2(sign * r[k][j], r[k][k])
        c = math.atan2(sign * r[j][i], r[i][i])
    else:  # gimbal lock - put everything into the first rotation
        c = 0.0
        a = math.atan2(-sign * r[j][k], r[j][j])
    angles = {order[0]: math.degrees(a), order[1]: math.degrees(b), order[2]: math.degrees(c)}
    return (angles["x"], angles["y"], angles["z"])


def compose(translate=(0.0, 0.0, 0.0), rotate=(0.0, 0.0, 0.0), scale_values=(1.0, 1.0, 1.0), order="xyz"):
    """Compose ``S * R * T`` - the same order Maya uses for simple transforms."""
    s = from_axes((scale_values[0], 0, 0), (0, scale_values[1], 0), (0, 0, scale_values[2]))
    r = euler_to_matrix(rotate, order)
    return set_translation(mult(s, r), translate)


def decompose(matrix, order="xyz"):
    """Return ``(translate, rotate, scale)`` of a matrix (no shear support)."""
    x, y, z, t = axes(matrix)
    sx, sy, sz = length(x), length(y), length(z)
    # Negative determinant -> flip one axis so the rotation stays proper.
    if dot(cross(x, y), z) < 0:
        sx = -sx
    rot = from_axes(
        scale(x, 1.0 / sx if sx else 0.0),
        scale(y, 1.0 / sy if sy else 0.0),
        scale(z, 1.0 / sz if sz else 0.0),
    )
    return t, matrix_to_euler(rot, order), (sx, sy, sz)


def mirror_axis_signs(source_matrix, target_matrix, axis="x"):
    """Per-axis sign relationship between two (rest) frames across a mirror.

    Returns ``(sx, sy, sz)`` with ``+1``/``-1`` values where ``s_i`` is the
    sign of ``dot(reflect(source_axis_i), target_axis_i)``. Mirroring a pose
    from source to target then becomes::

        target_translate[i] = s_i * source_translate[i]
        target_rotate[i]    = -s_i * source_rotate[i]
    """
    src = axes(source_matrix)[:3]
    dst = axes(target_matrix)[:3]
    signs = []
    for s_axis, d_axis in zip(src, dst):
        value = dot(normalize(reflect(s_axis, axis)), normalize(d_axis))
        signs.append(1.0 if value >= 0 else -1.0)
    return tuple(signs)
