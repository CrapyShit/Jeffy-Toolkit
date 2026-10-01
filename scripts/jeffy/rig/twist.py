"""Twist extraction and twist joints.

The twist extractor isolates the rotation around one axis without flipping
(quaternion swing/twist decomposition built from matrix + quat nodes)::

    twist = twist.twist_extractor("L_hand_JNT", "L_forearm_JNT")
    twist.create_twist_joints("L_forearm_JNT", "L_hand_JNT", count=3)
"""

from maya import cmds

from jeffy.core import mathlib, matrix, naming, nodes, plugins
from jeffy.joints import tools as joint_tools
from jeffy.rig import common


def twist_extractor(driver, reference, axis="x", name=None):
    """Plug with the twist angle (degrees) of ``driver`` around its ``axis``,
    relative to ``reference`` and measured from the current (rest) pose.
    """
    plugins.ensure_matrix_plugins()
    axis = axis.lstrip("+-").lower()
    base = name or "%s_twist" % naming.short_name(driver)
    rest_relative = mathlib.mult(matrix.get_world_matrix(driver),
                                 mathlib.inverse(matrix.get_world_matrix(reference)))
    mm = cmds.createNode("multMatrix", name=naming.unique_name(base + "_MM"), skipSelect=True)
    cmds.connectAttr(driver + ".worldMatrix[0]", mm + ".matrixIn[0]")
    cmds.connectAttr(reference + ".worldInverseMatrix[0]", mm + ".matrixIn[1]")
    matrix.set_matrix_attr(mm + ".matrixIn[2]", mathlib.inverse(rest_relative))

    dm = nodes.decompose_matrix(mm + ".matrixSum", name=base + "_DM")
    normalize = cmds.createNode("quatNormalize", name=naming.unique_name(base + "_QN"), skipSelect=True)
    component = "outputQuat" + axis.upper()
    cmds.connectAttr(dm + "." + component, normalize + ".inputQuat" + axis.upper())
    cmds.connectAttr(dm + ".outputQuatW", normalize + ".inputQuatW")
    to_euler = cmds.createNode("quatToEuler", name=naming.unique_name(base + "_Q2E"), skipSelect=True)
    cmds.connectAttr(normalize + ".outputQuat", to_euler + ".inputQuat")
    return to_euler + ".outputRotate" + axis.upper()


def create_twist_joints(start, end, count=3, name=None, side=None, mode="forward", driver=None, reference=None,
                        axis=None, radius_scale=0.5):
    """Create ``count`` twist joints between ``start`` and ``end``.

    * ``forward`` (forearm): twist joints take a growing fraction of the
      twist of ``driver`` (default ``end``) relative to ``start``.
    * ``reverse`` (upper arm/thigh): twist joints counter-rotate the twist of
      ``start`` relative to ``reference`` (default the parent of ``start``),
      more strongly near the root - removing candy wrapping at the shoulder.

    Returns the created joints (children of ``start``).
    """
    axis = (axis or common.primary_axis(end)).lstrip("+-")
    parsed = naming.parse(start)
    base = name or (parsed["name"] or naming.short_name(start)) + "Twist"
    side = side if side is not None else parsed["side"]
    start_pos = cmds.xform(start, query=True, worldSpace=True, translation=True)
    end_pos = cmds.xform(end, query=True, worldSpace=True, translation=True)
    radius = cmds.getAttr(start + ".radius") * radius_scale

    if mode == "forward":
        source = twist_extractor(driver or end, start, axis, name=naming.compose(base, side, "utility"))
    elif mode == "reverse":
        reference = reference or (cmds.listRelatives(start, parent=True) or [None])[0]
        if not reference:
            raise ValueError("%s has no parent to measure twist from - pass reference" % start)
        source = twist_extractor(start, reference, axis, name=naming.compose(base, side, "utility"))
    else:
        raise ValueError("mode must be 'forward' or 'reverse'")

    joints = []
    for i in range(count):
        if mode == "forward":
            fraction = (i + 1) / float(count + 1)
            weight = fraction
        else:
            fraction = i / float(count)
            weight = -(1.0 - fraction)
        joint = joint_tools.create_joint(naming.compose("%s%02d" % (base, i + 1), side, "joint"), parent=start,
                                         radius=radius)
        cmds.setAttr(joint + ".jointOrient", 0, 0, 0)
        cmds.xform(joint, worldSpace=True, translation=mathlib.lerp_vector(start_pos, end_pos, fraction))
        driven = nodes.multiply(source, weight, name=naming.compose("%s%02d" % (base, i + 1), side, "utility"))
        cmds.connectAttr(driven, "%s.rotate%s" % (joint, axis.upper()))
        joints.append(joint)
    return joints
