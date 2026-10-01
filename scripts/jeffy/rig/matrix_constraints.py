"""Matrix based constraints (no constraint nodes, parallel evaluation friendly).

* :func:`matrix_constraint` - parent/point/orient/scale like behaviour,
  driving either ``offsetParentMatrix`` (Maya 2020+) or decomposed channels.
* :func:`blend_matrix_constraint` - weighted multi target constraint with
  ``blendMatrix``.
* :func:`aim_matrix_constraint` - aim behaviour with ``aimMatrix``.
"""

from maya import cmds

from jeffy.core import mathlib, matrix, naming, nodes, plugins, transform


def _offset(driven, driver):
    return mathlib.mult(matrix.get_world_matrix(driven), mathlib.inverse(matrix.get_world_matrix(driver)))


def matrix_constraint(driver, driven, maintain_offset=True, translate=True, rotate=True, scale=True,
                      use_offset_parent_matrix=None, name=None):
    """Constrain ``driven`` to ``driver`` with matrix nodes.

    When every channel is constrained (and the node is not a joint with a
    custom rotate order...), the result is written to ``offsetParentMatrix``
    and the driven channels are zeroed - the fastest option. Otherwise the
    matrix is decomposed into the selected channels; joint orients are
    compensated automatically.

    Returns the created ``multMatrix`` node.
    """
    plugins.ensure_matrix_plugins()
    base = name or "%s_matrixCon" % naming.short_name(driven)
    full = translate and rotate and scale
    if use_offset_parent_matrix is None:
        use_offset_parent_matrix = full and cmds.attributeQuery("offsetParentMatrix", node=driven, exists=True)

    offset = _offset(driven, driver) if maintain_offset else mathlib.identity()
    mm = cmds.createNode("multMatrix", name=naming.unique_name(base + "_MM"), skipSelect=True)
    index = 0
    if not mathlib.is_identity(offset):
        matrix.set_matrix_attr("%s.matrixIn[%d]" % (mm, index), offset)
        index += 1
    cmds.connectAttr(driver + ".worldMatrix[0]", "%s.matrixIn[%d]" % (mm, index))
    index += 1
    cmds.connectAttr(driven + ".parentInverseMatrix[0]", "%s.matrixIn[%d]" % (mm, index))
    index += 1

    if use_offset_parent_matrix:
        transform.reset(driven)
        if cmds.nodeType(driven) == "joint":
            cmds.setAttr(driven + ".jointOrient", 0, 0, 0)
        cmds.connectAttr(mm + ".matrixSum", driven + ".offsetParentMatrix", force=True)
        return mm

    opm = matrix.get_offset_parent_matrix(driven)
    if not mathlib.is_identity(opm):
        matrix.set_matrix_attr("%s.matrixIn[%d]" % (mm, index), mathlib.inverse(opm))
        index += 1

    dm = nodes.decompose_matrix(mm + ".matrixSum", name=base + "_DM")
    if translate:
        cmds.connectAttr(dm + ".outputTranslate", driven + ".translate", force=True)
    if scale:
        cmds.connectAttr(dm + ".outputScale", driven + ".scale", force=True)
    if rotate:
        rotate_source = dm
        if cmds.nodeType(driven) == "joint":
            joint_orient = cmds.getAttr(driven + ".jointOrient")[0]
            if any(abs(v) > 1e-6 for v in joint_orient):
                inverse_orient = mathlib.inverse(mathlib.euler_to_matrix(joint_orient, "xyz"))
                orient_mm = cmds.createNode("multMatrix", name=naming.unique_name(base + "_JO_MM"),
                                            skipSelect=True)
                cmds.connectAttr(mm + ".matrixSum", orient_mm + ".matrixIn[0]")
                matrix.set_matrix_attr(orient_mm + ".matrixIn[1]", inverse_orient)
                rotate_source = nodes.decompose_matrix(orient_mm + ".matrixSum", name=base + "_JO_DM")
        cmds.connectAttr(driven + ".rotateOrder", rotate_source + ".inputRotateOrder", force=True)
        cmds.connectAttr(rotate_source + ".outputRotate", driven + ".rotate", force=True)
    return mm


def blend_matrix_constraint(drivers, driven, weights=None, maintain_offset=True, name=None):
    """Weighted constraint to several drivers using ``blendMatrix`` (2020+).

    ``weights`` may be floats or plugs; returns the ``blendMatrix`` node.
    Target ``i`` blends on top of target ``i-1`` (layered like Maya's
    blendMatrix), so use weights like ``[1, 0.5]`` for a 50/50 blend of two.
    """
    base = name or "%s_blendCon" % naming.short_name(driven)
    weights = weights or [1.0] + [1.0 / (i + 1) for i in range(1, len(drivers))]
    world_mats = []
    for driver in drivers:
        offset = _offset(driven, driver) if maintain_offset else mathlib.identity()
        mm = cmds.createNode("multMatrix", name=naming.unique_name(base + "_MM"), skipSelect=True)
        matrix.set_matrix_attr(mm + ".matrixIn[0]", offset)
        cmds.connectAttr(driver + ".worldMatrix[0]", mm + ".matrixIn[1]")
        world_mats.append(mm + ".matrixSum")
    bm = cmds.createNode("blendMatrix", name=naming.unique_name(base + "_BM"), skipSelect=True)
    cmds.connectAttr(world_mats[0], bm + ".inputMatrix")
    for i, (mat, weight) in enumerate(zip(world_mats[1:], weights[1:])):
        cmds.connectAttr(mat, "%s.target[%d].targetMatrix" % (bm, i))
        nodes.connect(weight, "%s.target[%d].weight" % (bm, i))
    local = cmds.createNode("multMatrix", name=naming.unique_name(base + "_local_MM"), skipSelect=True)
    cmds.connectAttr(bm + ".outputMatrix", local + ".matrixIn[0]")
    cmds.connectAttr(driven + ".parentInverseMatrix[0]", local + ".matrixIn[1]")
    transform.reset(driven)
    if cmds.nodeType(driven) == "joint":
        cmds.setAttr(driven + ".jointOrient", 0, 0, 0)
    cmds.connectAttr(local + ".matrixSum", driven + ".offsetParentMatrix", force=True)
    return bm


def aim_matrix_constraint(driven, target, up_object=None, aim_axis=(1, 0, 0), up_axis=(0, 1, 0),
                          world_up=(0, 1, 0), name=None):
    """Aim ``driven`` at ``target`` with an ``aimMatrix`` node (2020+).

    The driven node keeps its position; orientation goes to
    ``offsetParentMatrix``.
    """
    base = name or "%s_aimCon" % naming.short_name(driven)
    am = cmds.createNode("aimMatrix", name=naming.unique_name(base + "_AM"), skipSelect=True)
    rest = cmds.createNode("composeMatrix", name=naming.unique_name(base + "_rest_CM"), skipSelect=True)
    world = matrix.get_world_matrix(driven)
    cmds.setAttr(rest + ".inputTranslate", *mathlib.get_translation(world))
    position_mm = cmds.createNode("multMatrix", name=naming.unique_name(base + "_pos_MM"), skipSelect=True)
    cmds.connectAttr(rest + ".outputMatrix", position_mm + ".matrixIn[0]")
    parent_world = cmds.getAttr(driven + ".parentMatrix[0]")
    matrix.set_matrix_attr(position_mm + ".matrixIn[1]", mathlib.inverse(parent_world))
    cmds.connectAttr(driven + ".parentMatrix[0]", position_mm + ".matrixIn[2]")
    cmds.connectAttr(position_mm + ".matrixSum", am + ".inputMatrix")
    cmds.connectAttr(target + ".worldMatrix[0]", am + ".primaryTargetMatrix")
    cmds.setAttr(am + ".primaryInputAxis", *aim_axis)
    cmds.setAttr(am + ".secondaryInputAxis", *up_axis)
    if up_object:
        cmds.connectAttr(up_object + ".worldMatrix[0]", am + ".secondaryTargetMatrix")
        cmds.setAttr(am + ".secondaryMode", 1)  # aim at the up object
    else:
        cmds.setAttr(am + ".secondaryMode", 2)  # align with world vector
        cmds.setAttr(am + ".secondaryTargetVector", *world_up)
    local = cmds.createNode("multMatrix", name=naming.unique_name(base + "_local_MM"), skipSelect=True)
    cmds.connectAttr(am + ".outputMatrix", local + ".matrixIn[0]")
    cmds.connectAttr(driven + ".parentInverseMatrix[0]", local + ".matrixIn[1]")
    transform.reset(driven, scale=False)
    if cmds.nodeType(driven) == "joint":
        cmds.setAttr(driven + ".jointOrient", 0, 0, 0)
    cmds.connectAttr(local + ".matrixSum", driven + ".offsetParentMatrix", force=True)
    return am


def remove_matrix_constraint(driven, keep_world=True):
    """Disconnect a matrix constraint from ``driven`` (world pose kept)."""
    world = matrix.get_world_matrix(driven)
    for attr in ("offsetParentMatrix", "translate", "rotate", "scale"):
        plug = "%s.%s" % (driven, attr)
        if not cmds.objExists(plug):
            continue
        for source in cmds.listConnections(plug, source=True, destination=False, plugs=True) or []:
            cmds.disconnectAttr(source, plug)
    if cmds.attributeQuery("offsetParentMatrix", node=driven, exists=True):
        matrix.set_matrix_attr(driven + ".offsetParentMatrix", mathlib.identity())
    if keep_world:
        matrix.set_world_matrix(driven, world)
