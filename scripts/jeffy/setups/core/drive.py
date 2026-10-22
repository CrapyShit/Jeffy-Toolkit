"""Drive bind joints from setup outputs (matrix nodes, no constraints).

A bind joint keeps its place in the skeleton, its joint orient and its
rotate order. Its translate / rotate / scale channels are driven so its world
matrix equals the output's world matrix:

``local = output.worldMatrix * parent.worldInverseMatrix [* parentScale]``

* With ``segmentScaleCompensate`` (the joint default) the parent's own scale
  is put back (``* composeMatrix(parent.scale)``) and the translation is
  divided by it, so a stretched (scaled) parent never shears its children.
* The joint orient (and rotate axis) are taken out of the rotation.
* ``scale_stretch``: the joint also scales along its bone axis by
  ``distance(output, child output) / rest length`` (film rigs). Otherwise the
  scale is the uniform rig scale only (game safe).

The rest values (and locks) of every driven channel are recorded so
:func:`release` can put the skeleton back exactly as it was.
"""

from maya import cmds

from jeffy.core import mathlib, matrix, naming, nodes, plugins

CHANNELS = ("translate", "rotate", "scale")
AXES = "XYZ"


def _children_plugs(channel):
    return ["%s%s" % (channel, axis) for axis in AXES]


def record_rest(joint):
    """Rest values and locks of a joint's transform channels (JSON friendly)."""
    data = {}
    for channel in CHANNELS:
        data[channel] = list(cmds.getAttr("%s.%s" % (joint, channel))[0])
    locked = []
    for channel in CHANNELS:
        for attr in [channel] + _children_plugs(channel):
            if cmds.getAttr("%s.%s" % (joint, attr), lock=True):
                locked.append(attr)
    data["locked"] = locked
    return data


def incoming(joint):
    """Plugs already driving the joint's translate / rotate / scale channels."""
    result = []
    for channel in CHANNELS:
        for attr in [channel] + _children_plugs(channel):
            plug = "%s.%s" % (joint, attr)
            result.extend(cmds.listConnections(plug, source=True, destination=False, plugs=True,
                                               skipConversionNodes=True) or [])
    return result


def _unlock(joint, locked):
    for attr in locked:
        cmds.setAttr("%s.%s" % (joint, attr), lock=False)


def _name(joint, part):
    return naming.unique_name("%s_%s" % (naming.strip_namespace(joint), part))


def drive(joint, output, child_output=None, scale_stretch=False):
    """Drive ``joint`` from the world matrix of ``output`` (a transform).

    :param child_output: output of the next joint in the chain, needed for
        ``scale_stretch`` (the bone axis and rest length are measured to it)
    :returns: the created nodes
    """
    plugins.ensure_plugin(plugins.MATRIX_NODES)
    rest = record_rest(joint)
    _unlock(joint, rest["locked"])
    created = []
    parent = (cmds.listRelatives(joint, parent=True, fullPath=True) or [None])[0]

    mm = cmds.createNode("multMatrix", name=_name(joint, "drive_MM"), skipSelect=True)
    created.append(mm)
    cmds.connectAttr(output + ".worldMatrix[0]", mm + ".matrixIn[0]")
    compensate = False
    if parent:
        cmds.connectAttr(parent + ".worldInverseMatrix[0]", mm + ".matrixIn[1]")
        compensate = cmds.nodeType(parent) == "joint" and cmds.getAttr(joint + ".segmentScaleCompensate")
        if compensate:
            parent_scale = cmds.createNode("composeMatrix", name=_name(joint, "parentScale_CM"), skipSelect=True)
            created.append(parent_scale)
            cmds.connectAttr(parent + ".scale", parent_scale + ".inputScale")
            cmds.connectAttr(parent_scale + ".outputMatrix", mm + ".matrixIn[2]")

    dm = cmds.createNode("decomposeMatrix", name=_name(joint, "drive_DM"), skipSelect=True)
    created.append(dm)
    cmds.connectAttr(mm + ".matrixSum", dm + ".inputMatrix")

    # translate (divided by the parent scale when it is compensated)
    if compensate:
        divide = cmds.createNode("multiplyDivide", name=_name(joint, "drive_MD"), skipSelect=True)
        created.append(divide)
        cmds.setAttr(divide + ".operation", 2)
        cmds.connectAttr(dm + ".outputTranslate", divide + ".input1")
        cmds.connectAttr(parent + ".scale", divide + ".input2")
        cmds.connectAttr(divide + ".output", joint + ".translate", force=True)
    else:
        cmds.connectAttr(dm + ".outputTranslate", joint + ".translate", force=True)

    # rotate: R = RA^-1 * (RA * R * JO) * JO^-1
    orient = cmds.getAttr(joint + ".jointOrient")[0] if cmds.nodeType(joint) == "joint" else (0.0, 0.0, 0.0)
    rotate_axis = cmds.getAttr(joint + ".rotateAxis")[0]
    rotate_source = dm
    if any(abs(v) > 1e-6 for v in orient) or any(abs(v) > 1e-6 for v in rotate_axis):
        rot_mm = cmds.createNode("multMatrix", name=_name(joint, "orient_MM"), skipSelect=True)
        created.append(rot_mm)
        index = 0
        if any(abs(v) > 1e-6 for v in rotate_axis):
            matrix.set_matrix_attr("%s.matrixIn[%d]" % (rot_mm, index),
                                   mathlib.inverse(mathlib.euler_to_matrix(rotate_axis, "xyz")))
            index += 1
        cmds.connectAttr(mm + ".matrixSum", "%s.matrixIn[%d]" % (rot_mm, index))
        index += 1
        if any(abs(v) > 1e-6 for v in orient):
            matrix.set_matrix_attr("%s.matrixIn[%d]" % (rot_mm, index),
                                   mathlib.inverse(mathlib.euler_to_matrix(orient, "xyz")))
        rotate_source = cmds.createNode("decomposeMatrix", name=_name(joint, "orient_DM"), skipSelect=True)
        created.append(rotate_source)
        cmds.connectAttr(rot_mm + ".matrixSum", rotate_source + ".inputMatrix")
    cmds.connectAttr(joint + ".rotateOrder", rotate_source + ".inputRotateOrder", force=True)
    cmds.connectAttr(rotate_source + ".outputRotate", joint + ".rotate", force=True)

    # scale
    if scale_stretch and child_output:
        created.extend(_scale_stretch(joint, output, child_output, dm))
    else:
        cmds.connectAttr(dm + ".outputScale", joint + ".scale", force=True)
    return created, rest


def _scale_stretch(joint, output, child_output, dm):
    """Bone axis scale = distance(output, child) / rest length; others = rig scale."""
    created = []
    # bone axis: the child output's position seen from the output (outputs share the joints' orientation)
    out_world = matrix.get_world_matrix(output)
    child_world = matrix.get_world_matrix(child_output)
    local = mathlib.transform_point(mathlib.get_translation(child_world), mathlib.inverse(out_world))
    axis = max(range(3), key=lambda i: abs(local[i]))
    world_scale = mathlib.length(mathlib.axes(out_world)[0]) or 1.0
    rest_length = mathlib.distance(mathlib.get_translation(out_world), mathlib.get_translation(child_world))
    rest_length = max(rest_length / world_scale, 1e-6)

    distance = cmds.createNode("distanceBetween", name=_name(joint, "stretch_DIST"), skipSelect=True)
    created.append(distance)
    cmds.connectAttr(output + ".worldMatrix[0]", distance + ".inMatrix1")
    cmds.connectAttr(child_output + ".worldMatrix[0]", distance + ".inMatrix2")
    ratio = nodes.create("multiplyDivide", name=_name(joint, "stretch_MD"), operation=2)
    created.append(ratio)
    cmds.connectAttr(distance + ".distance", ratio + ".input1X")
    cmds.setAttr(ratio + ".input2X", rest_length)
    for index, axis_name in enumerate(AXES):
        target = "%s.scale%s" % (joint, axis_name)
        if index == axis:
            cmds.connectAttr(ratio + ".outputX", target, force=True)
        else:
            cmds.connectAttr("%s.outputScale%s" % (dm, axis_name), target, force=True)
    return created


def release(joint, rest):
    """Disconnect the driven channels of ``joint`` and restore ``rest``."""
    if not cmds.objExists(joint):
        return
    for channel in CHANNELS:
        for attr in [channel] + _children_plugs(channel):
            plug = "%s.%s" % (joint, attr)
            for source in cmds.listConnections(plug, source=True, destination=False, plugs=True) or []:
                try:
                    cmds.disconnectAttr(source, plug)
                except RuntimeError:
                    pass
    if rest:
        for channel in CHANNELS:
            values = rest.get(channel)
            if values:
                for axis, value in zip(AXES, values):
                    plug = "%s.%s%s" % (joint, channel, axis)
                    if not cmds.getAttr(plug, lock=True):
                        cmds.setAttr(plug, value)
        for attr in rest.get("locked", []):
            cmds.setAttr("%s.%s" % (joint, attr), lock=True)
