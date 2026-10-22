"""Helpers shared by the belt tools (chains, labels, bone axes...)."""

from maya import cmds

from jeffy.core import dag, mathlib, matrix, naming, transform
from jeffy.setups.core.schema import SetupError

AXES = "xyz"


def chain(start, end=None):
    """Joints from ``start`` to ``end`` (short unique names). ``end`` empty = ``[start]``."""
    if not end or end == start:
        return [start]
    try:
        long_names = dag.get_chain(start, end)
    except ValueError:
        message = "%s is not below %s in the hierarchy" % (naming.short_name(end), naming.short_name(start))
        raise SetupError(message) from None
    result = []
    for node in long_names:
        if cmds.nodeType(node) != "joint":
            raise SetupError("%s (between %s and %s) is not a joint" % (naming.short_name(node), start, end))
        result.append(cmds.ls(node)[0])
    return result


def is_child(parent, child):
    """``child`` is directly parented under ``parent``."""
    found = cmds.listRelatives(child, parent=True, fullPath=True) or []
    return bool(found) and found[0] == (cmds.ls(parent, long=True) or [None])[0]


def label(joint):
    """``L_upperArm_JNT`` -> ``upperArm``."""
    parsed = naming.parse(joint)
    return parsed["name"] or naming.strip_namespace(joint)


def position(node):
    return transform.get_position(node)


def length(a, b):
    return mathlib.distance(position(a), position(b))


def child_joint(joint):
    children = cmds.listRelatives(joint, children=True, type="joint") or []
    return children[0] if children else None


def bone_axis(joint, child=None):
    """Signed local axis (``x``, ``-y``...) pointing from ``joint`` to ``child``.

    Without a child, the first child joint is used; ``x`` when there is none.
    """
    child = child or child_joint(joint)
    if not child:
        return "x"
    local = mathlib.transform_point(position(child), mathlib.inverse(matrix.get_world_matrix(joint)))
    index = max(range(3), key=lambda i: abs(local[i]))
    return ("-" if local[index] < 0 else "") + AXES[index]


def segment_length(joint, child=None):
    child = child or child_joint(joint)
    return length(joint, child) if child else 0.0


def world_matrix(node):
    """World matrix with unit scale (orientation + position)."""
    return mathlib.orthonormalize(matrix.get_world_matrix(node))


def compose_zero(zero, length_plug=None, pre_rotate_plug=None, rotate_order_plug=None):
    """Move a ``ZRO``'s rest pose into its ``offsetParentMatrix``.

    ``offsetParentMatrix = [pre rotation] * restLocal(translate * length)``:
    the ZRO channels become zero, ``length_plug`` scales the rest translation
    (FK stretch) and ``pre_rotate_plug`` adds a rotation in the ZRO's own
    frame (master / curl controls). Returns the created nodes.
    """
    created = []
    rest_translate = list(cmds.getAttr(zero + ".translate")[0])
    rest_rotate = list(cmds.getAttr(zero + ".rotate")[0])
    rest = cmds.createNode("composeMatrix", name=naming.unique_name("%s_rest_CM" % naming.strip_namespace(zero)),
                           skipSelect=True)
    created.append(rest)
    cmds.setAttr(rest + ".inputRotate", *rest_rotate)
    cmds.setAttr(rest + ".inputRotateOrder", cmds.getAttr(zero + ".rotateOrder"))
    if length_plug:
        scaled = cmds.createNode("multiplyDivide", name=naming.unique_name("%s_length_MD"
                                                                           % naming.strip_namespace(zero)),
                                 skipSelect=True)
        created.append(scaled)
        cmds.setAttr(scaled + ".input1", *rest_translate)
        for axis in "XYZ":
            cmds.connectAttr(length_plug, scaled + ".input2" + axis)
        cmds.connectAttr(scaled + ".output", rest + ".inputTranslate")
    else:
        cmds.setAttr(rest + ".inputTranslate", *rest_translate)
    result = rest + ".outputMatrix"
    if pre_rotate_plug:
        pre = cmds.createNode("composeMatrix", name=naming.unique_name("%s_pre_CM" % naming.strip_namespace(zero)),
                              skipSelect=True)
        created.append(pre)
        cmds.connectAttr(pre_rotate_plug, pre + ".inputRotate")
        if rotate_order_plug:
            cmds.connectAttr(rotate_order_plug, pre + ".inputRotateOrder")
        mm = cmds.createNode("multMatrix", name=naming.unique_name("%s_pre_MM" % naming.strip_namespace(zero)),
                             skipSelect=True)
        created.append(mm)
        cmds.connectAttr(pre + ".outputMatrix", mm + ".matrixIn[0]")
        cmds.connectAttr(result, mm + ".matrixIn[1]")
        result = mm + ".matrixSum"
    transform.reset(zero)
    cmds.connectAttr(result, zero + ".offsetParentMatrix", force=True)
    return created
