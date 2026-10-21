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
from jeffy.rig import common, fk

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


def build_tangent_curve(joints, name="spline", side=None, num_controls=3, control_parent=None, curve_parent=None,
                        shape="circle", size=1.0, color_value=None):
    """IK controls driving a curve through *tangent* points.

    Each control owns the curve point under it and the tangent points on each
    side of it (like a Bezier handle), so rotating any control - the middle
    ones too - bends the curve around it. ``tangentLength`` on each control
    scales its tangents.

    :returns: ``(controls, curve)``
    """
    num_controls = max(2, int(num_controls))
    axis = common.primary_axis(joints[1]).lstrip("-")
    guide = curves.curve_from_joints(joints, name=naming.compose(name + "Guide", side, "curve"), degree=3)
    points = curves.positions_along(guide, 3 * num_controls - 2)
    cmds.delete(guide)

    controls = []
    drivers = []  # node driving each curve point, in order
    previous = None
    for i in range(num_controls):
        position = points[3 * i]
        closest = min(joints, key=lambda j: sum(
            (a - b) ** 2 for a, b in zip(cmds.xform(j, query=True, worldSpace=True, translation=True), position)))
        label = "%sIK%02d" % (name, i + 1)
        ctl = Control.create(label, side=side, shape=shape, size=size, axis=axis, parent=control_parent,
                             match=closest, offsets=("zero", "space"), color_value=color_value)
        cmds.xform(ctl.zero, worldSpace=True, translation=position)
        if previous:
            ctl.set_parent_tag(previous)
        previous = ctl.node
        tangent_attr = attributes.add_attr(ctl.node, "tangentLength", "float", default=1.0, minimum=0.0)
        tangent_group = common.create_group(naming.compose(label + "Tangent", side, "group"), parent=ctl.node)
        cmds.xform(tangent_group, objectSpace=True, translation=(0, 0, 0), rotation=(0, 0, 0))
        for channel in "XYZ":
            cmds.connectAttr(tangent_attr, "%s.scale%s" % (tangent_group, channel))
        tangents = []
        for index, suffix in ((3 * i - 1, "In"), (3 * i + 1, "Out")):
            if 0 <= index < len(points):
                tangents.append(common.create_locator(naming.compose(label + suffix, side, "locator"),
                                                      parent=tangent_group, position=points[index]))
        if i > 0:
            drivers.append(tangents.pop(0))
        drivers.append(ctl.node)
        drivers.extend(tangents)
        controls.append(ctl)

    curve = curves.curve_from_points(points, name=naming.compose(name, side, "curve"), degree=3, through=False)
    if curve_parent:
        curve = cmds.parent(curve, curve_parent)[0]
    cmds.setAttr(curve + ".inheritsTransform", 0)
    shape_node = cmds.listRelatives(curve, shapes=True)[0]
    for index, node in enumerate(drivers):
        decompose = nodes.decompose_matrix(node + ".worldMatrix[0]",
                                           name=naming.compose("%sPoint%02d" % (name, index), side,
                                                               "decompose_matrix"))
        cmds.connectAttr(decompose + ".outputTranslate", "%s.controlPoints[%d]" % (shape_node, index), force=True)
    return controls, curve


def build_spline_ikfk(
    joints,
    name="spline",
    side=None,
    num_controls=3,
    control_parent=None,
    systems_parent=None,
    shape="circle",
    fk_shape="circle",
    size=1.0,
    up_axis="y",
    stretch=True,
    volume=True,
    default_mode=1.0,
    color_value=None,
):
    """Spline IK chain and FK chain with an ``ikFk`` switch (0 FK, 1 IK).

    Like an IK/FK limb: the bind ``joints`` blend between an FK copy (one
    control per joint) and a spline IK copy. The IK controls drive the curve
    through tangent points, so rotating any of them - the middle ones too -
    bends the curve; the first and last also twist the chain and the last
    joint follows the last control's rotation.

    :returns: dict with ``settings``, ``switch``, ``ik_controls``,
        ``fk_controls``, ``ik_joints``, ``fk_joints``, ``curve``, ``handle``
        and ``group``
    """
    joints = [naming.short_name(j) for j in joints]
    if len(joints) < 3:
        raise ValueError("Spline IK needs at least 3 joints")
    forward = common.primary_axis(joints[1])
    group = common.create_group(naming.compose(name + "SplineRig", side, "group"), parent=systems_parent,
                                visible=False)

    # the copies follow the bind chain's parent; their roots stay free (the
    # spline solver and the FK control drive them)
    parent = (cmds.listRelatives(joints[0], parent=True) or [None])[0]
    chain_parent = common.follow_group(naming.compose(name + "ChainFollow", side, "group"), parent, parent=group) \
        if parent else group
    chains = {}
    for key in ("FK", "IK"):
        chain = joint_tools.duplicate_chain(joints[0], joints[-1], search="_JNT", replace="_%s_JNT" % key)
        chain[0] = cmds.parent(chain[0], chain_parent)[0]
        chains[key] = [naming.short_name(j) for j in chain]
    fk_joints, ik_joints = chains["FK"], chains["IK"]

    holder = control_parent
    if holder is None and parent:
        holder = common.follow_group(naming.compose(name + "Follow", side, "group"), parent)

    # IK -------------------------------------------------------------------------
    ik_group = common.create_group(naming.compose(name + "IKControls", side, "group"), parent=holder)
    ik_controls, curve = build_tangent_curve(joints, name=name, side=side, num_controls=num_controls,
                                             control_parent=ik_group, curve_parent=group, shape=shape, size=size,
                                             color_value=color_value)
    handle, effector = cmds.ikHandle(startJoint=ik_joints[0], endEffector=ik_joints[-1], solver="ikSplineSolver",
                                     curve=curve, createCurve=False, parentCurve=False, rootOnCurve=True,
                                     simplifyCurve=False, name=naming.compose(name, side, "ik_handle"))
    cmds.rename(effector, naming.compose(name, side, "effector"))
    handle = cmds.parent(handle, group)[0]
    cmds.setAttr(handle + ".dTwistControlEnable", 1)
    cmds.setAttr(handle + ".dWorldUpType", 4)
    cmds.setAttr(handle + ".dForwardAxis", FORWARD_AXIS[forward])
    cmds.setAttr(handle + ".dWorldUpAxis", UP_AXIS[up_axis])
    cmds.setAttr(handle + ".dWorldUpVector", *UP_VECTORS[up_axis])
    cmds.setAttr(handle + ".dWorldUpVectorEnd", *UP_VECTORS[up_axis])
    cmds.connectAttr(ik_controls[0].node + ".worldMatrix[0]", handle + ".dWorldUpMatrix")
    cmds.connectAttr(ik_controls[-1].node + ".worldMatrix[0]", handle + ".dWorldUpMatrixEnd")
    # the solver leaves the end joint free: it follows the last control
    cmds.orientConstraint(ik_controls[-1].node, ik_joints[-1], maintainOffset=True)

    # FK -------------------------------------------------------------------------
    fk_group = common.create_group(naming.compose(name + "FKControls", side, "group"), parent=holder)
    fk_result = fk.build_fk_chain(fk_joints, name=name + "FK", side=side, shape=fk_shape, size=size * 1.2,
                                  axis=forward.lstrip("-"), parent=fk_group, color_value=color_value)
    fk_controls = fk_result["controls"]

    # settings + switch ------------------------------------------------------------
    settings = Control.create(name + "Settings", side=side, shape="gear", size=size * 0.4, parent=holder,
                              match=joints[-1], lock=("t", "r", "s", "v"), color_value="white")
    cmds.parentConstraint(joints[-1], settings.zero, maintainOffset=True)
    switch = attributes.add_attr(settings.node, "ikFk", "float", default=default_mode, minimum=0.0, maximum=1.0)
    if stretch or volume:
        add_stretch(ik_joints, curve, settings.node, name=name, side=side, forward=forward,
                    scale_node=ik_controls[0].zero, stretch=stretch, volume=volume)

    reverse = nodes.reverse(switch, name=naming.compose(name + "IkFk", side, "reverse"))
    for bind, fk_joint, ik_joint in zip(joints, fk_joints, ik_joints):
        constraint = cmds.parentConstraint(fk_joint, ik_joint, bind, maintainOffset=False)[0]
        cmds.setAttr(constraint + ".interpType", 2)
        weights = common.constraint_weight_plugs(constraint)
        cmds.connectAttr(reverse, weights[0])
        cmds.connectAttr(switch, weights[1])
        blend_scale = cmds.createNode("blendColors", name=naming.unique_name(bind + "_scale_BLD"), skipSelect=True)
        cmds.connectAttr(ik_joint + ".scale", blend_scale + ".color1")
        cmds.connectAttr(fk_joint + ".scale", blend_scale + ".color2")
        cmds.connectAttr(switch, blend_scale + ".blender")
        cmds.connectAttr(blend_scale + ".output", bind + ".scale", force=True)

    fk_vis = nodes.condition(switch, "<", 1.0, 1.0, 0.0, name=naming.compose(name + "FkVis", side, "condition"))
    ik_vis = nodes.condition(switch, ">", 0.0, 1.0, 0.0, name=naming.compose(name + "IkVis", side, "condition"))
    cmds.connectAttr(fk_vis, fk_group + ".visibility")
    cmds.connectAttr(ik_vis, ik_group + ".visibility")
    for ctl in ik_controls + fk_controls:
        attributes.add_proxy(switch, ctl.node)

    return {"settings": settings, "switch": switch, "ik_controls": ik_controls, "fk_controls": fk_controls,
            "ik_joints": ik_joints, "fk_joints": fk_joints, "curve": curve, "handle": handle, "group": group}
