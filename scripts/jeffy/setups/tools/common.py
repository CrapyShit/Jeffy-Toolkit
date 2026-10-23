"""Helpers shared by the belt tools (chains, labels, bone axes...)."""

from maya import cmds

from jeffy.core import dag, mathlib, matrix, naming, transform
from jeffy.setups.core import scene
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
    (FK stretch) and ``pre_rotate_plug`` (a rotate plug, or one plug / None per
    axis) adds a rotation in the ZRO's own frame (master, curl, foot pivots).
    Returns the created nodes.
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
        if isinstance(pre_rotate_plug, (list, tuple)):  # one plug (or None) per axis
            for axis, plug in zip("XYZ", pre_rotate_plug):
                if plug:
                    cmds.connectAttr(plug, pre + ".inputRotate" + axis)
        else:
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


# ---------------------------------------------------------------------------
# Frames along a bone (twist / ribbon)
# ---------------------------------------------------------------------------
def axis_vector_of(node, index):
    """World direction (unit) of local axis ``index`` of ``node``."""
    return mathlib.normalize(mathlib.axes(matrix.get_world_matrix(node))[index])


def bone_axis_index(node, target):
    """Local axis index of ``node`` pointing the most toward ``target`` and its sign."""
    local = mathlib.transform_point(position(target), mathlib.inverse(matrix.get_world_matrix(node)))
    index = max(range(3), key=lambda i: abs(local[i]))
    return index, (1.0 if local[index] >= 0 else -1.0)


def aim_frame(name, start, target, up_node, up_vector, aim_axis, up_axis):
    """``aimMatrix`` at ``start``: ``aim_axis`` aims at ``target``, ``up_axis`` aligns with
    ``up_vector`` expressed in ``up_node`` space (world when ``up_node`` is None).

    Returns the output matrix plug.
    """
    node = cmds.createNode("aimMatrix", name=naming.unique_name(name), skipSelect=True)
    cmds.connectAttr(start + ".worldMatrix[0]", node + ".inputMatrix")
    cmds.connectAttr(target + ".worldMatrix[0]", node + ".primaryTargetMatrix")
    cmds.setAttr(node + ".primaryInputAxis", *aim_axis)
    cmds.setAttr(node + ".primaryMode", 1)  # aim
    cmds.setAttr(node + ".secondaryInputAxis", *up_axis)
    cmds.setAttr(node + ".secondaryMode", 2)  # align
    cmds.setAttr(node + ".secondaryTargetVector", *up_vector)
    if up_node:
        cmds.connectAttr(up_node + ".worldMatrix[0]", node + ".secondaryTargetMatrix")
    return node + ".outputMatrix"


def bone_frame(name, start, target, up_node=None):
    """Frame at ``start`` aiming at ``target`` whose roll comes from ``up_node``.

    ``up_node`` None: ``start``'s own roll. Another node (the parent setup's
    output): the frame does not roll with ``start`` (no-roll / counter twist).
    At rest the frame has ``start``'s orientation.
    """
    index, sign = bone_axis_index(start, target)
    aim_axis = [0.0, 0.0, 0.0]
    aim_axis[index] = sign
    up_index = (index + 1) % 3
    up_axis = [0.0, 0.0, 0.0]
    up_axis[up_index] = 1.0
    up_world = axis_vector_of(start, up_index)
    source = up_node or start
    up_local = mathlib.normalize(mathlib.transform_vector(up_world, mathlib.inverse(
        mathlib.orthonormalize(matrix.get_world_matrix(source)))))
    return aim_frame(name, start, target, source, up_local, aim_axis, up_axis)


def blend_matrices(name, first, second, weight, translate=1.0, rotate=1.0):
    """``blendMatrix`` from ``first`` toward ``second`` (plugs). Returns the output plug."""
    node = cmds.createNode("blendMatrix", name=naming.unique_name(name), skipSelect=True)
    cmds.connectAttr(first, node + ".inputMatrix")
    cmds.connectAttr(second, node + ".target[0].targetMatrix")
    if isinstance(weight, str):
        cmds.connectAttr(weight, node + ".target[0].weight")
    else:
        cmds.setAttr(node + ".target[0].weight", weight)
    cmds.setAttr(node + ".target[0].translateWeight", translate)
    cmds.setAttr(node + ".target[0].rotateWeight", rotate)
    cmds.setAttr(node + ".target[0].scaleWeight", 0.0)
    cmds.setAttr(node + ".target[0].shearWeight", 0.0)
    return node + ".outputMatrix"


def offset_plug(name, plug, rest_target, rest_source):
    """``offset * plug`` where the offset maps ``rest_source`` (the plug's rest value) onto ``rest_target``."""
    node = cmds.createNode("multMatrix", name=naming.unique_name(name), skipSelect=True)
    matrix.set_matrix_attr(node + ".matrixIn[0]", mathlib.mult(rest_target, mathlib.inverse(rest_source)))
    cmds.connectAttr(plug, node + ".matrixIn[1]")
    return node + ".matrixSum"


def plug_matrix(plug):
    """Current value of a matrix plug (16 floats)."""
    return list(cmds.getAttr(plug))


def chain_outputs(setup):
    """``[(bind joint, output)]`` of a setup, in chain order (parent first)."""
    pairs = []
    for joint in setup.driven:
        output = scene.output_driving(joint)
        if output:
            pairs.append((joint, output))
    pairs.sort(key=lambda pair: (cmds.ls(pair[0], long=True) or [""])[0].count("|"))
    return pairs


def pole_vector(prefix, side, handle, start, target):
    """``handle.poleVector`` = (target - start) in the handle's parent space (no constraint node)."""
    start_dm = cmds.createNode("decomposeMatrix", name=naming.unique_name(naming.compose(prefix + "PvStart", side,
                                                                                       "DM")), skipSelect=True)
    cmds.connectAttr(start + ".worldMatrix[0]", start_dm + ".inputMatrix")
    aim_dm = cmds.createNode("decomposeMatrix", name=naming.unique_name(naming.compose(prefix + "PvTarget", side,
                                                                                     "DM")), skipSelect=True)
    cmds.connectAttr(target + ".worldMatrix[0]", aim_dm + ".inputMatrix")
    vector = cmds.createNode("plusMinusAverage", name=naming.unique_name(naming.compose(prefix + "PvVector", side,
                                                                                      "PMA")), skipSelect=True)
    cmds.setAttr(vector + ".operation", 2)
    cmds.connectAttr(aim_dm + ".outputTranslate", vector + ".input3D[0]")
    cmds.connectAttr(start_dm + ".outputTranslate", vector + ".input3D[1]")
    local = cmds.createNode("vectorProduct", name=naming.unique_name(naming.compose(prefix + "PvLocal", side,
                                                                                  "UTL")), skipSelect=True)
    cmds.setAttr(local + ".operation", 3)  # vector * matrix
    cmds.connectAttr(vector + ".output3D", local + ".input1")
    parent_inverse = matrix.parent_inverse_plug(handle)
    if parent_inverse:
        cmds.connectAttr(parent_inverse, local + ".matrix")
    cmds.connectAttr(local + ".output", handle + ".poleVector", force=True)
