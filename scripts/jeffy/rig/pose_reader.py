"""Pose readers - drive correctives from joint poses (no RBF plugin needed).

* :func:`create_cone_reader` - 1.0 when a joint points like it does now
  (the *target pose*), fading to 0 at ``cone_angle`` degrees away.
* :func:`create_twist_reader` - remapped twist angle.
* :func:`connect_to_blendshape` - drive a blendshape target with a reader.

Typical corrective workflow: pose the elbow at 90 degrees, create a cone
reader on the forearm, sculpt the corrective and connect it.
"""

from maya import cmds

from jeffy.core import attributes, mathlib, matrix, naming, nodes
from jeffy.rig import twist as twist_tools


def create_cone_reader(joint, parent=None, axis="x", cone_angle=60.0, name=None):
    """Create a cone pose reader for the current pose of ``joint``.

    Returns the reader locator; its ``weight`` attribute is the output.
    """
    parent = parent or (cmds.listRelatives(joint, parent=True) or [None])[0]
    if not parent:
        raise ValueError("%s has no parent - pass the parent/reference node" % joint)
    base = name or "%s_reader" % naming.short_name(joint)
    reader = cmds.spaceLocator(name=naming.unique_name(base + "_LOC"))[0]
    cmds.parent(reader, parent, relative=True)
    cmds.setAttr(reader + ".visibility", 0)
    weight = attributes.add_attr(reader, "weight", "float", default=0.0, keyable=False, channel_box=True)
    angle_attr = attributes.add_attr(reader, "coneAngle", "float", default=cone_angle, minimum=0.001)
    current_angle = attributes.add_attr(reader, "currentAngle", "float", default=0.0, keyable=False,
                                        channel_box=True)

    vector = mathlib.axis_vector(axis)
    local = cmds.createNode("multMatrix", name=naming.unique_name(base + "_MM"), skipSelect=True)
    cmds.connectAttr(joint + ".worldMatrix[0]", local + ".matrixIn[0]")
    cmds.connectAttr(parent + ".worldInverseMatrix[0]", local + ".matrixIn[1]")
    direction = nodes.vector_product(vector, operation=3, matrix=local + ".matrixSum", normalize=True,
                                     name=base + "_VP")
    relative = mathlib.mult(matrix.get_world_matrix(joint), mathlib.inverse(matrix.get_world_matrix(parent)))
    target = mathlib.normalize(mathlib.transform_vector(vector, relative))
    angle = nodes.angle_between(direction, target, name=base + "_AB")
    cmds.connectAttr(angle, current_angle)
    remapped = nodes.remap(angle, 0.0, angle_attr, 1.0, 0.0, name=base + "_RMV")
    cmds.connectAttr(remapped, weight)
    return reader


def create_twist_reader(joint, reference=None, axis="x", min_angle=0.0, max_angle=90.0, name=None):
    """Reader giving 0..1 while ``joint`` twists from ``min_angle`` to ``max_angle``."""
    reference = reference or cmds.listRelatives(joint, parent=True)[0]
    base = name or "%s_twistReader" % naming.short_name(joint)
    reader = cmds.spaceLocator(name=naming.unique_name(base + "_LOC"))[0]
    cmds.parent(reader, reference, relative=True)
    cmds.setAttr(reader + ".visibility", 0)
    weight = attributes.add_attr(reader, "weight", "float", default=0.0, keyable=False, channel_box=True)
    twist = twist_tools.twist_extractor(joint, reference, axis, name=base)
    cmds.connectAttr(nodes.remap(twist, min_angle, max_angle, 0.0, 1.0, name=base + "_RMV"), weight)
    return reader


def connect_to_blendshape(reader, blendshape, target):
    """Connect ``reader.weight`` to a blendshape target (alias or index)."""
    if isinstance(target, int):
        plug = "%s.weight[%d]" % (blendshape, target)
    else:
        plug = "%s.%s" % (blendshape, target)
    cmds.connectAttr(reader + ".weight", plug, force=True)
    return plug
