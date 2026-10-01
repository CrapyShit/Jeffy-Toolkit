"""Scene matrix helpers built on :mod:`jeffy.core.mathlib`.

These functions read/write matrices of scene nodes. The math itself lives in
``mathlib`` (pure Python, unit tested).
"""

from maya import cmds

from jeffy.core import mathlib

ROTATE_ORDERS = ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")


def get_world_matrix(node):
    return cmds.xform(node, query=True, worldSpace=True, matrix=True)


def get_local_matrix(node):
    """Local TRS matrix (``.matrix`` attribute, without offsetParentMatrix)."""
    return cmds.getAttr(node + ".matrix")


def has_offset_parent_matrix(node):
    return cmds.attributeQuery("offsetParentMatrix", node=node, exists=True)


def get_offset_parent_matrix(node):
    if has_offset_parent_matrix(node):
        return cmds.getAttr(node + ".offsetParentMatrix")
    return mathlib.identity()


def get_parent_matrix(node):
    """World matrix of the parent space (offsetParentMatrix * parent world)."""
    parent_world = cmds.getAttr(node + ".parentMatrix[0]")
    return mathlib.mult(get_offset_parent_matrix(node), parent_world)


def get_rest_matrix(node):
    """World matrix the node would have with identity local transforms."""
    return get_parent_matrix(node)


def set_matrix_attr(full_plug, matrix):
    cmds.setAttr(full_plug, *list(matrix), type="matrix")


def get_rotate_order(node):
    return ROTATE_ORDERS[cmds.getAttr(node + ".rotateOrder")]


def offset_matrix(child, parent):
    """Matrix of ``child`` expressed in ``parent`` space."""
    return mathlib.mult(get_world_matrix(child), mathlib.inverse(get_world_matrix(parent)))


def _settable(node, attr):
    full = "%s.%s" % (node, attr)
    if not cmds.getAttr(full, settable=True):
        return False
    return True


def _set3(node, attr, values):
    names = [attr + axis for axis in ("X", "Y", "Z")]
    for name, value in zip(names, values):
        if _settable(node, name):
            cmds.setAttr("%s.%s" % (node, name), value)


def set_world_matrix(node, matrix, translate=True, rotate=True, scale=True):
    """Place ``node`` so that its world matrix becomes ``matrix``.

    Works for transforms and joints (``jointOrient`` and ``rotateAxis`` are
    taken into account and kept). Pivots are assumed to be at the origin,
    which is the case for rig nodes. Locked/connected channels are skipped.
    """
    local = mathlib.mult(matrix, mathlib.inverse(get_parent_matrix(node)))
    x_axis, y_axis, z_axis, position = mathlib.axes(local)
    sx, sy, sz = mathlib.length(x_axis), mathlib.length(y_axis), mathlib.length(z_axis)
    if mathlib.dot(mathlib.cross(x_axis, y_axis), z_axis) < 0:
        sx = -sx
    rotation = mathlib.from_axes(
        mathlib.scale(x_axis, 1.0 / sx),
        mathlib.scale(y_axis, 1.0 / sy),
        mathlib.scale(z_axis, 1.0 / sz),
    )

    # Maya composes: [S] * [RA] * [R] * [JO] * [T]  ->  R = RA^-1 * rot * JO^-1
    rotate_axis = cmds.getAttr(node + ".rotateAxis")[0]
    if any(abs(v) > 1e-9 for v in rotate_axis):
        rotation = mathlib.mult(mathlib.inverse(mathlib.euler_to_matrix(rotate_axis, "xyz")), rotation)
    if cmds.nodeType(node) == "joint":
        joint_orient = cmds.getAttr(node + ".jointOrient")[0]
        rotation = mathlib.mult(rotation, mathlib.inverse(mathlib.euler_to_matrix(joint_orient, "xyz")))

    if translate:
        _set3(node, "translate", position)
    if rotate:
        _set3(node, "rotate", mathlib.matrix_to_euler(rotation, get_rotate_order(node)))
    if scale:
        _set3(node, "scale", (sx, sy, sz))


def set_joint_orient_from_matrix(joint, world_matrix):
    """Orient a joint (``jointOrient``) to ``world_matrix``, zeroing rotate.

    The joint position is not changed. Children are NOT compensated - see
    :func:`jeffy.joints.orient` for the safe, child preserving version.
    """
    parent_rotation = mathlib.orthonormalize(get_parent_matrix(joint))
    target = mathlib.orthonormalize(world_matrix)
    local = mathlib.mult(target, mathlib.inverse(parent_rotation))
    rotate_axis = cmds.getAttr(joint + ".rotateAxis")[0]
    if any(abs(v) > 1e-9 for v in rotate_axis):
        cmds.setAttr(joint + ".rotateAxis", 0, 0, 0)
    for axis in "XYZ":
        if _settable(joint, "rotate" + axis):
            cmds.setAttr("%s.rotate%s" % (joint, axis), 0)
    orient = mathlib.matrix_to_euler(local, "xyz")
    cmds.setAttr(joint + ".jointOrient", *orient)


def mirror_world_matrix(node, axis="x", mode="behavior"):
    return mathlib.mirror_matrix(get_world_matrix(node), axis=axis, mode=mode)


def matrix_from_points(origin, aim_point, up_point=None, aim_axis="x", up_axis="y", world_up=(0, 1, 0)):
    """Aim matrix at ``origin`` looking at ``aim_point``.

    The up vector points toward ``up_point`` when given, otherwise ``world_up``.
    """
    aim_vector = mathlib.sub(aim_point, origin)
    up_vector = mathlib.sub(up_point, origin) if up_point is not None else world_up
    return mathlib.aim_matrix(origin, aim_vector, up_vector, aim_axis, up_axis)
