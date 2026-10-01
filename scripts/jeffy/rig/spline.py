"""Spline IK chains with stretch, squash/volume and advanced twist.

Typical use: spines, necks, tails, tentacles::

    from jeffy.rig import spline
    result = spline.build_spline_ik(joints, name="spine", side="C", num_controls=3)
"""

import math

from maya import cmds

from jeffy.controls.control import Control
from jeffy.core import attributes, naming, nodes
from jeffy.geometry import curves
from jeffy.joints import tools as joint_tools
from jeffy.rig import common

FORWARD_AXIS = {"x": 0, "-x": 1, "y": 2, "-y": 3, "z": 4, "-z": 5}
UP_AXIS = {"y": 0, "-y": 1, "z": 3, "-z": 4, "x": 6, "-x": 7}
UP_VECTORS = {"x": (1, 0, 0), "-x": (-1, 0, 0), "y": (0, 1, 0), "-y": (0, -1, 0), "z": (0, 0, 1), "-z": (0, 0, -1)}


def build_spline_ik(
    joints,
    name="spline",
    side=None,
    num_controls=3,
    control_parent=None,
    systems_parent=None,
    shape="circle",
    size=1.0,
    up_axis="y",
    stretch=True,
    volume=True,
    twist=True,
    settings_node=None,
    color_value=None,
):
    """Drive ``joints`` with a spline IK and ``num_controls`` controls.

    Controls drive *control joints* that are skinned to the IK curve, so any
    number of controls gives a smooth result.

    :param up_axis: joint axis used for the advanced twist up vector
    :param settings_node: node receiving ``stretch``/``volume`` attributes
        (defaults to the last control)
    :returns: dict with ``controls``, ``control_joints``, ``curve``,
        ``handle``, ``group``
    """
    if len(joints) < 3:
        raise ValueError("Spline IK needs at least 3 joints")
    forward = common.primary_axis(joints[1])
    base = name
    group = common.create_group(naming.compose(base + "Spline", side, "group"), parent=systems_parent,
                                visible=False)

    curve = curves.curve_from_joints(joints, name=naming.compose(base, side, "curve"), degree=3,
                                     spans=max(1, num_controls - 1))
    curve = cmds.parent(curve, group)[0]
    cmds.setAttr(curve + ".inheritsTransform", 0)

    # control joints + controls ------------------------------------------------
    positions = curves.positions_along(curve, num_controls)
    controls = []
    control_joints = []
    previous = control_parent
    for i, position in enumerate(positions):
        closest = min(joints, key=lambda j: sum(
            (a - b) ** 2 for a, b in zip(cmds.xform(j, query=True, worldSpace=True, translation=True), position)))
        label = "%sIK%02d" % (base, i + 1)
        ctl = Control.create(label, side=side, shape=shape, size=size, axis=forward.lstrip("-"),
                             parent=control_parent, match=closest, offsets=("zero", "space"),
                             color_value=color_value)
        cmds.xform(ctl.zero, worldSpace=True, translation=position)
        joint = joint_tools.create_joint(naming.compose(label, side, "joint"), parent=ctl.node)
        cmds.setAttr(joint + ".jointOrient", 0, 0, 0)
        cmds.setAttr(joint + ".visibility", 0)
        controls.append(ctl)
        control_joints.append(joint)
        if previous and previous != control_parent:
            ctl.set_parent_tag(previous)
        previous = ctl.node

    cmds.skinCluster(control_joints + [curve], toSelectedBones=True, maximumInfluences=2, dropoffRate=4.0,
                     name=naming.compose(base + "Curve", side, "skin_cluster"))

    handle, effector = cmds.ikHandle(startJoint=joints[0], endEffector=joints[-1], solver="ikSplineSolver",
                                     curve=curve, createCurve=False, parentCurve=False, rootOnCurve=True,
                                     simplifyCurve=False, name=naming.compose(base, side, "ik_handle"))
    cmds.rename(effector, naming.compose(base, side, "effector"))
    handle = cmds.parent(handle, group)[0]

    if twist:
        cmds.setAttr(handle + ".dTwistControlEnable", 1)
        cmds.setAttr(handle + ".dWorldUpType", 4)  # object rotation up (start/end)
        cmds.setAttr(handle + ".dForwardAxis", FORWARD_AXIS[forward])
        cmds.setAttr(handle + ".dWorldUpAxis", UP_AXIS[up_axis])
        vector = UP_VECTORS[up_axis]
        cmds.setAttr(handle + ".dWorldUpVector", *vector)
        cmds.setAttr(handle + ".dWorldUpVectorEnd", *vector)
        cmds.connectAttr(control_joints[0] + ".worldMatrix[0]", handle + ".dWorldUpMatrix")
        cmds.connectAttr(control_joints[-1] + ".worldMatrix[0]", handle + ".dWorldUpMatrixEnd")

    settings = settings_node or controls[-1].node
    result = {"controls": controls, "control_joints": control_joints, "curve": curve, "handle": handle,
              "group": group}
    if stretch or volume:
        result.update(add_stretch(joints, curve, settings, name=base, side=side, forward=forward,
                                  scale_node=controls[0].zero, stretch=stretch, volume=volume))
    return result


def add_stretch(joints, curve, settings, name="spline", side=None, forward=None, scale_node=None, stretch=True,
                volume=True):
    """Stretch (translate based) and volume preservation for a curve chain."""
    forward = forward or common.primary_axis(joints[1])
    attributes.add_separator(settings, "stretch")
    stretch_attr = attributes.add_attr(settings, "stretch", "float", default=1.0, minimum=0.0, maximum=1.0)
    plugs = {"stretch": stretch_attr}

    arc = nodes.curve_info(curve, name=naming.compose(name + "Arc", side, "utility"))
    rest = cmds.getAttr(arc)
    if scale_node:
        scale = common.world_scale_plug(scale_node, name=naming.compose(name + "Scale", side, "decompose_matrix"))
        rest_length = nodes.multiply(rest, scale)
    else:
        rest_length = rest
    ratio = nodes.divide(arc, rest_length, name=naming.compose(name + "Ratio", side, "multiply_divide"))
    factor = nodes.blend(1.0, ratio, stretch_attr, name=naming.compose(name + "Stretch", side, "blend"))
    if not stretch:
        cmds.setAttr(stretch_attr, 0)
        attributes.lock_hide(settings, ["stretch"])

    for joint in joints[1:]:
        attr = common.axis_attr(forward)
        value = cmds.getAttr("%s.%s" % (joint, attr))
        cmds.connectAttr(nodes.multiply(factor, value), "%s.%s" % (joint, attr), force=True)

    if volume:
        volume_attr = attributes.add_attr(settings, "volume", "float", default=0.0, minimum=0.0, maximum=1.0)
        plugs["volume"] = volume_attr
        inverse = nodes.power(factor, -0.5, name=naming.compose(name + "Volume", side, "multiply_divide"))
        count = len(joints)
        others = [a for a in "xyz" if a != forward.lstrip("-")]
        for i, joint in enumerate(joints):
            profile = math.sin(math.pi * (i + 0.5) / count)
            weight = nodes.multiply(volume_attr, profile)
            value = nodes.blend(1.0, inverse, weight)
            for axis in others:
                cmds.connectAttr(value, "%s.scale%s" % (joint, axis.upper()), force=True)
    return plugs
