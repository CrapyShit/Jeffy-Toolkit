"""Utility node network helpers.

Every function accepts plugs (``"node.attr"`` strings) or constants for its
inputs and returns the *output plug* of the node it creates, so networks can
be chained::

    from jeffy.core import nodes
    scale = nodes.divide(nodes.distance_between(a, b), rest_length)
    nodes.connect(nodes.clamp(scale, 1, 10), "joint.sx")

Only classic nodes (available in every Maya version) plus the Maya 2020+
matrix nodes are used.
"""

from maya import cmds

from jeffy.core import attributes, naming, plugins

_counter = {"value": 0}


def _name(name, default):
    if name:
        return naming.unique_name(name)
    _counter["value"] += 1
    return naming.unique_name("%s_%s" % (default, naming.suffix("utility")))


def create(node_type, name=None, **attrs):
    """Create a utility node and set/connect attributes from keyword args."""
    node = cmds.createNode(node_type, name=_name(name, node_type), skipSelect=True)
    for attr, value in attrs.items():
        attributes.set_or_connect(value, "%s.%s" % (node, attr))
    return node


def connect(source, destination):
    """Connect or set (``source`` may be a constant)."""
    attributes.set_or_connect(source, destination)


def _is_plug(value):
    return isinstance(value, str)


# ---------------------------------------------------------------------------
# Scalar math
# ---------------------------------------------------------------------------
def multiply(a, b, name=None):
    node = create("multDoubleLinear", name)
    connect(a, node + ".input1")
    connect(b, node + ".input2")
    return node + ".output"


def add(a, b, name=None):
    node = create("addDoubleLinear", name)
    connect(a, node + ".input1")
    connect(b, node + ".input2")
    return node + ".output"


def sum_values(values, name=None):
    node = create("plusMinusAverage", name, operation=1)
    for i, value in enumerate(values):
        connect(value, "%s.input1D[%d]" % (node, i))
    return node + ".output1D"


def subtract(a, b, name=None):
    node = create("plusMinusAverage", name, operation=2)
    connect(a, node + ".input1D[0]")
    connect(b, node + ".input1D[1]")
    return node + ".output1D"


def average(values, name=None):
    node = create("plusMinusAverage", name, operation=3)
    for i, value in enumerate(values):
        connect(value, "%s.input1D[%d]" % (node, i))
    return node + ".output1D"


def _multiply_divide(a, b, operation, name):
    node = create("multiplyDivide", name, operation=operation)
    connect(a, node + ".input1X")
    connect(b, node + ".input2X")
    return node + ".outputX"


def divide(a, b, name=None):
    return _multiply_divide(a, b, 2, name)


def power(a, b, name=None):
    return _multiply_divide(a, b, 3, name)


def sqrt(a, name=None):
    return power(a, 0.5, name)


def negate(a, name=None):
    return multiply(a, -1.0, name)


def reverse(a, name=None):
    """``1 - a``."""
    node = create("reverse", name)
    connect(a, node + ".inputX")
    return node + ".outputX"


def clamp(value, minimum, maximum, name=None):
    node = create("clamp", name)
    connect(value, node + ".inputR")
    connect(minimum, node + ".minR")
    connect(maximum, node + ".maxR")
    return node + ".outputR"


CONDITION_OPERATIONS = {"==": 0, "!=": 1, ">": 2, ">=": 3, "<": 4, "<=": 5}


def condition(first, operation, second, if_true, if_false, name=None):
    """``if_true if first <op> second else if_false`` (op: ``==, !=, >, >=, <, <=``)."""
    op = CONDITION_OPERATIONS[operation] if isinstance(operation, str) else operation
    node = create("condition", name, operation=op)
    connect(first, node + ".firstTerm")
    connect(second, node + ".secondTerm")
    connect(if_true, node + ".colorIfTrueR")
    connect(if_false, node + ".colorIfFalseR")
    return node + ".outColorR"


def maximum(a, b, name=None):
    return condition(a, ">", b, a, b, name)


def minimum(a, b, name=None):
    return condition(a, "<", b, a, b, name)


def absolute(a, name=None):
    return condition(a, "<", 0, negate(a), a, name)


def blend(a, b, weight, name=None):
    """Linear interpolation ``a + (b - a) * weight``."""
    node = create("blendColors", name)
    connect(b, node + ".color1R")
    connect(a, node + ".color2R")
    connect(weight, node + ".blender")
    return node + ".outputR"


def remap(value, in_min=0.0, in_max=1.0, out_min=0.0, out_max=1.0, name=None):
    node = create("remapValue", name)
    connect(value, node + ".inputValue")
    connect(in_min, node + ".inputMin")
    connect(in_max, node + ".inputMax")
    connect(out_min, node + ".outputMin")
    connect(out_max, node + ".outputMax")
    return node + ".outValue"


def set_range(value, in_min, in_max, out_min, out_max, name=None):
    node = create("setRange", name)
    connect(value, node + ".valueX")
    connect(in_min, node + ".oldMinX")
    connect(in_max, node + ".oldMaxX")
    connect(out_min, node + ".minX")
    connect(out_max, node + ".maxX")
    return node + ".outValueX"


def sin_cos(angle_degrees, name=None):
    """Return ``(sin, cos)`` plugs of an angle (degrees) using quatNodes.

    Trick: a rotation of ``2a`` around X has quaternion ``(sin a, 0, 0, cos a)``.
    """
    plugins.ensure_plugin(plugins.QUAT_NODES)
    node = create("eulerToQuat", name)
    doubled = multiply(angle_degrees, 2.0)
    connect(doubled, node + ".inputRotateX")
    return node + ".outputQuatX", node + ".outputQuatW"


# ---------------------------------------------------------------------------
# Vector / matrix
# ---------------------------------------------------------------------------
def distance_between(a, b, name=None):
    """Live distance between two transforms (world space)."""
    node = create("distanceBetween", name)
    cmds.connectAttr(a + ".worldMatrix[0]", node + ".inMatrix1")
    cmds.connectAttr(b + ".worldMatrix[0]", node + ".inMatrix2")
    return node + ".distance"


def decompose_matrix(matrix_plug, name=None):
    """Return the ``decomposeMatrix`` node (several outputs)."""
    plugins.ensure_plugin(plugins.MATRIX_NODES)
    node = create("decomposeMatrix", name)
    connect(matrix_plug, node + ".inputMatrix")
    return node


def compose_matrix(translate=None, rotate=None, scale=None, name=None):
    plugins.ensure_plugin(plugins.MATRIX_NODES)
    node = create("composeMatrix", name)
    for value, attr in ((translate, "inputTranslate"), (rotate, "inputRotate"), (scale, "inputScale")):
        if value is not None:
            connect(value, "%s.%s" % (node, attr))
    return node + ".outputMatrix"


def mult_matrix(matrices, name=None):
    """Multiply matrices in order (first is applied first)."""
    node = create("multMatrix", name)
    for i, value in enumerate(matrices):
        connect(value, "%s.matrixIn[%d]" % (node, i))
    return node + ".matrixSum"


def inverse_matrix(matrix_plug, name=None):
    plugins.ensure_plugin(plugins.MATRIX_NODES)
    node = create("inverseMatrix", name)
    connect(matrix_plug, node + ".inputMatrix")
    return node + ".outputMatrix"


def pick_matrix(matrix_plug, translate=True, rotate=True, scale=True, shear=True, name=None):
    node = create("pickMatrix", name, useTranslate=translate, useRotate=rotate, useScale=scale,
                  useShear=shear)
    connect(matrix_plug, node + ".inputMatrix")
    return node + ".outputMatrix"


def blend_matrix(base, targets, weights, name=None):
    """``blendMatrix`` node (Maya 2020+). ``weights`` may be plugs or floats."""
    node = create("blendMatrix", name)
    connect(base, node + ".inputMatrix")
    for i, (target, weight) in enumerate(zip(targets, weights)):
        connect(target, "%s.target[%d].targetMatrix" % (node, i))
        connect(weight, "%s.target[%d].weight" % (node, i))
    return node + ".outputMatrix"


def vector_product(a, b=None, operation=1, matrix=None, normalize=False, name=None):
    """``vectorProduct``: 1 dot, 2 cross, 3 vector*matrix, 4 point*matrix."""
    node = create("vectorProduct", name, operation=operation, normalizeOutput=normalize)
    connect(a, node + ".input1")
    if b is not None:
        connect(b, node + ".input2")
    if matrix is not None:
        connect(matrix, node + ".matrix")
    return node + ".output"


def angle_between(vector1, vector2, name=None):
    node = create("angleBetween", name)
    connect(vector1, node + ".vector1")
    connect(vector2, node + ".vector2")
    return node + ".angle"


def point_matrix_mult(point, matrix_plug, vector_only=False, name=None):
    node = create("pointMatrixMult", name, vectorMultiply=vector_only)
    connect(point, node + ".inPoint")
    connect(matrix_plug, node + ".inMatrix")
    return node + ".output"


def connect_matrix_to_transform(matrix_plug, node, translate=True, rotate=True, scale=True, shear=False,
                                name=None):
    """Drive a transform's channels from a matrix plug via ``decomposeMatrix``."""
    dm = decompose_matrix(matrix_plug, name=name)
    if translate:
        cmds.connectAttr(dm + ".outputTranslate", node + ".translate", force=True)
    if rotate:
        cmds.connectAttr(dm + ".outputRotate", node + ".rotate", force=True)
        cmds.connectAttr(node + ".rotateOrder", dm + ".inputRotateOrder", force=True)
    if scale:
        cmds.connectAttr(dm + ".outputScale", node + ".scale", force=True)
    if shear:
        cmds.connectAttr(dm + ".outputShear", node + ".shear", force=True)
    return dm


def curve_info(curve, name=None):
    """``curveInfo`` node; returns the ``arcLength`` plug."""
    from jeffy.core import dag

    shape = dag.get_shape(curve) or curve
    node = create("curveInfo", name)
    cmds.connectAttr(shape + ".worldSpace[0]", node + ".inputCurve")
    return node + ".arcLength"
