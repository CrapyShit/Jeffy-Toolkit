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


def _rotate_attr(axis):
    return "rotate" + axis.lstrip("-").upper()


def _chain_fractions(joints):
    """Length fraction (0 -> 1) of every joint along the chain."""
    from jeffy.core import mathlib

    positions = [cmds.xform(j, query=True, worldSpace=True, translation=True) for j in joints]
    lengths = [0.0]
    for a, b in zip(positions, positions[1:]):
        lengths.append(lengths[-1] + mathlib.distance(a, b))
    total = lengths[-1] or 1.0
    return [value / total for value in lengths]


def _hat(t, center, step):
    """Weight of a control at ``center`` for a joint at ``t`` (1 on the control,
    0 on its neighbours)."""
    return max(0.0, 1.0 - abs(t - center) / step)


def build_hybrid_spline(
    joints,
    name="spline",
    side=None,
    num_controls=3,
    control_parent=None,
    systems_parent=None,
    shape="circle",
    fk_shape="square",
    size=1.0,
    up_axis="y",
    stretch=True,
    volume=True,
    per_joint_switch=True,
    color_value=None,
):
    """Spline IK with an FK control on every joint, layered on top of the IK.

    ::

        IK controls  -> curve -> spline IK chain (shape, stretch, twist)
        FK controls  -> one per joint, each under the previous one, following
                        the IK chain; rotating one bends everything below it
        bind joints  -> follow the FK controls

    * The IK controls drive the curve through *tangent* points, so rotating a
      control bends the curve around it like a Bezier handle
      (``tangentLength`` on each control sets how far its influence reaches).
      The first and last controls twist the chain (advanced twist), the
      middle ones add twist spread to their neighbours, and the last joint
      follows the rotation of the last control.
    * ``ikBlend`` (on the last IK control) blends the whole chain between
      following the IK (1) and pure FK (0). With ``per_joint_switch`` each
      joint also gets its own ``ik01``, ``ik02``... attribute: a joint at 0
      ignores the IK and only follows its FK control, the joints below it
      keep their IK shape relative to it, so there is never a gap.

    :param joints: the bind joints, root -> tip (at least 3)
    :returns: dict with ``ik_controls``, ``fk_controls``, ``ik_joints``,
        ``curve``, ``handle``, ``settings``, ``switch`` (master plug),
        ``joint_switches`` and ``group``
    """
    from jeffy.core import mathlib

    joints = [naming.short_name(j) for j in joints]
    if len(joints) < 3:
        raise ValueError("Spline IK needs at least 3 joints")
    num_controls = max(2, int(num_controls))
    forward = common.primary_axis(joints[1])
    axis = forward.lstrip("-")
    base = name
    group = common.create_group(naming.compose(base + "Hybrid", side, "group"), parent=systems_parent,
                                visible=False)

    # IK chain (a copy of the bind chain, following the bind chain's parent)
    parent = (cmds.listRelatives(joints[0], parent=True) or [None])[0]
    chain_parent = common.follow_group(naming.compose(base + "IkFollow", side, "group"), parent, parent=group) \
        if parent else group
    ik_joints = joint_tools.duplicate_chain(joints[0], joints[-1], search="_JNT", replace="_IK_JNT")
    ik_joints[0] = cmds.parent(ik_joints[0], chain_parent)[0]
    ik_joints = [naming.short_name(j) for j in ik_joints]

    # curve points: control, tangent, tangent, control, ... (3n - 2 points)
    guide = curves.curve_from_joints(joints, name=naming.compose(base + "Guide", side, "curve"), degree=3)
    points = curves.positions_along(guide, 3 * num_controls - 2)
    cmds.delete(guide)

    ik_controls = []
    drivers = []  # node driving each curve point
    previous = None
    for i in range(num_controls):
        position = points[3 * i]
        closest = min(joints, key=lambda j: sum(
            (a - b) ** 2 for a, b in zip(cmds.xform(j, query=True, worldSpace=True, translation=True), position)))
        label = "%sIK%02d" % (base, i + 1)
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
        ik_controls.append(ctl)

    curve = curves.curve_from_points(points, name=naming.compose(base, side, "curve"), degree=3, through=False)
    curve = cmds.parent(curve, group)[0]
    cmds.setAttr(curve + ".inheritsTransform", 0)
    shape_node = cmds.listRelatives(curve, shapes=True, fullPath=False)[0]
    for index, node in enumerate(drivers):
        decompose = nodes.decompose_matrix(node + ".worldMatrix[0]",
                                           name=naming.compose("%sPoint%02d" % (base, index), side,
                                                               "decompose_matrix"))
        cmds.connectAttr(decompose + ".outputTranslate", "%s.controlPoints[%d]" % (shape_node, index), force=True)

    handle, effector = cmds.ikHandle(startJoint=ik_joints[0], endEffector=ik_joints[-1], solver="ikSplineSolver",
                                     curve=curve, createCurve=False, parentCurve=False, rootOnCurve=True,
                                     simplifyCurve=False, name=naming.compose(base, side, "ik_handle"))
    cmds.rename(effector, naming.compose(base, side, "effector"))
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

    settings = ik_controls[-1].node
    result = {"ik_controls": ik_controls, "ik_joints": ik_joints, "curve": curve, "handle": handle,
              "settings": settings, "group": group}
    if stretch or volume:
        result.update(add_stretch(ik_joints, curve, settings, name=base, side=side, forward=forward,
                                  scale_node=ik_controls[0].zero, stretch=stretch, volume=volume))

    # switches -----------------------------------------------------------------
    attributes.add_separator(settings, "ikFk")
    switch = attributes.add_attr(settings, "ikBlend", "float", default=1.0, minimum=0.0, maximum=1.0)
    weights = []
    joint_switches = []
    for i in range(len(joints)):
        if per_joint_switch:
            plug = attributes.add_attr(settings, "ik%02d" % (i + 1), "float", default=1.0, minimum=0.0, maximum=1.0)
            joint_switches.append(plug)
            weights.append(nodes.multiply(switch, plug, name=naming.compose("%sIk%02d" % (base, i + 1), side,
                                                                            "multiply_divide")))
        else:
            weights.append(switch)

    # FK layer -----------------------------------------------------------------
    fractions = _chain_fractions(joints)
    step = 1.0 / (num_controls - 1)
    middle = list(range(1, num_controls - 1))
    rotate_attr = _rotate_attr(forward)
    fk_controls = []
    fk_parent = control_parent
    for i, (bind, ik_joint) in enumerate(zip(joints, ik_joints)):
        label = (naming.parse(bind)["name"] or "%s%02d" % (base, i + 1)) + "FK"
        ctl = Control.create(label, side=side, shape=fk_shape, size=size * 0.8, axis=axis, parent=fk_parent,
                             match=bind, offsets=("zero", "offset"), lock=("s", "v"), color_value=color_value)
        if fk_controls:
            ctl.set_parent_tag(fk_controls[-1].node)
        zero = ctl.zero
        cmds.xform(zero, objectSpace=True, translation=(0, 0, 0), rotation=(0, 0, 0), scale=(1, 1, 1))
        if i == 0:
            follow = nodes.mult_matrix([ik_joint + ".worldMatrix[0]", zero + ".parentInverseMatrix[0]"],
                                       name=naming.compose(label + "Ik", side, "mult_matrix"))
        else:
            follow = ik_joint + ".matrix"
        follow = nodes.pick_matrix(follow, scale=False, shear=False,
                                   name=naming.compose(label + "Ik", side, "pick_matrix"))
        # pure FK: the IK pose at build time, frozen
        rest = cmds.getAttr(ik_joint + ".matrix")
        if i == 0:
            rest = mathlib.mult(cmds.getAttr(ik_joint + ".worldMatrix[0]"),
                                cmds.getAttr(zero + ".parentInverseMatrix[0]"))
        blend = cmds.createNode("blendMatrix", name=naming.compose(label, side, "blend_matrix"), skipSelect=True)
        cmds.setAttr(blend + ".inputMatrix", *rest, type="matrix")
        cmds.connectAttr(follow, blend + ".target[0].targetMatrix")
        cmds.connectAttr(weights[i], blend + ".target[0].weight")
        cmds.connectAttr(blend + ".outputMatrix", zero + ".offsetParentMatrix", force=True)

        # twist of the middle IK controls, spread to their neighbours. The FK
        # controls are a hierarchy, so each one only adds the difference.
        if i > 0 and middle:
            terms = []
            for k in middle:
                factor = _hat(fractions[i], k * step, step) - _hat(fractions[i - 1], k * step, step)
                if abs(factor) > 1e-4:
                    terms.append(nodes.multiply(ik_controls[k].node + "." + rotate_attr, factor))
            if terms:
                total = terms[0] if len(terms) == 1 else nodes.sum_values(
                    terms, name=naming.compose(label + "Twist", side, "plus_minus"))
                cmds.connectAttr(total, "%s.%s" % (zero, rotate_attr), force=True)

        cmds.parentConstraint(ctl.node, bind, maintainOffset=False)
        cmds.connectAttr(ik_joint + ".scale", bind + ".scale", force=True)
        fk_controls.append(ctl)
        fk_parent = ctl.node

    cmds.setAttr(ik_joints[0] + ".visibility", 0)
    result.update({"fk_controls": fk_controls, "switch": switch, "joint_switches": joint_switches})
    return result
