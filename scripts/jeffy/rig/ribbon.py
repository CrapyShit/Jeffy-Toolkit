"""Ribbon rigs (NURBS surface + follicles) - bendy limbs, spines, eyebrows...

::

    from jeffy.rig import ribbon
    result = ribbon.build_ribbon(["L_upArm_JNT", "L_elbow_JNT"], name="upArmBendy",
                                 side="L", num_joints=5, num_controls=3)
"""

from maya import cmds

from jeffy.controls.control import Control
from jeffy.core import attributes, mathlib, naming, transform
from jeffy.geometry import surfaces
from jeffy.joints import tools as joint_tools
from jeffy.rig import attach, common


def build_ribbon(
    nodes_or_points,
    name="ribbon",
    side=None,
    num_joints=5,
    num_controls=3,
    width=None,
    up_vector=(0.0, 0.0, 1.0),
    control_parent=None,
    systems_parent=None,
    shape="circle",
    size=1.0,
    axis="x",
    scale_node=None,
    color_value=None,
):
    """Build a ribbon through nodes (or positions).

    :param nodes_or_points: two or more transforms or world positions
    :param num_joints: output (bind) joints, one per follicle
    :param num_controls: controls along the ribbon (skinned to the surface)
    :param up_vector: world direction the ribbon width spreads along
    :param scale_node: node whose world scale drives the follicle scale
        (defaults to ``control_parent``) so the ribbon is global scale aware
    :returns: dict with ``surface``, ``controls``, ``joints``, ``follicles``,
        ``control_joints`` and ``group``
    """
    points = [transform.get_position(n) if isinstance(n, str) else tuple(n) for n in nodes_or_points]
    if len(points) < 2:
        raise ValueError("A ribbon needs at least two points")
    length = sum(mathlib.distance(a, b) for a, b in zip(points, points[1:]))
    width = width or length * 0.15

    if len(points) == 2:
        points = [mathlib.lerp_vector(points[0], points[1], t) for t in mathlib.distribute(4)]
    group = common.create_group(naming.compose(name + "Ribbon", side, "group"), parent=systems_parent)
    surface = surfaces.ribbon_from_points(points, width=width, up_vector=up_vector,
                                          name=naming.compose(name, side, "surface"),
                                          spans=max(2, num_controls - 1))
    surface = cmds.parent(surface, group)[0]
    cmds.setAttr(surface + ".inheritsTransform", 0)
    cmds.setAttr(surface + ".visibility", 0)

    # follicles + output joints ----------------------------------------------
    follicle_grp = common.create_group(naming.compose(name + "Follicles", side, "group"), parent=group)
    cmds.setAttr(follicle_grp + ".inheritsTransform", 0)
    follicles = attach.follicles_along_surface(surface, num_joints, name=naming.compose(name, side, ""),
                                               parent=follicle_grp)
    scale_source = scale_node or control_parent
    scale = common.world_scale_plug(scale_source) if scale_source else None
    joints = []
    for i, follicle in enumerate(follicles):
        joint = joint_tools.create_joint(naming.compose("%s%02d" % (name, i + 1), side, "joint"), parent=follicle)
        cmds.setAttr(joint + ".jointOrient", 0, 0, 0)
        joints.append(joint)
        if scale:
            for axis_name in "XYZ":
                cmds.connectAttr(scale, "%s.scale%s" % (follicle, axis_name))

    # controls -----------------------------------------------------------------
    controls = []
    control_joints = []
    for i, u in enumerate(mathlib.distribute(num_controls, 0.0, 1.0)):
        position = surfaces.point_at_uv(surface, u, 0.5)
        label = "%sBend%02d" % (name, i + 1)
        ctl = Control.create(label, side=side, shape=shape, size=size, axis=axis, parent=control_parent,
                             position=position, offsets=("zero", "offset"), color_value=color_value,
                             secondary=True)
        # orient the control like the closest follicle
        closest = follicles[int(round(u * (len(follicles) - 1)))]
        cmds.matchTransform(ctl.zero, closest, rotation=True, position=False)
        cmds.xform(ctl.zero, worldSpace=True, translation=position)
        joint = joint_tools.create_joint(naming.compose(label, side, "joint"), parent=ctl.node)
        cmds.setAttr(joint + ".jointOrient", 0, 0, 0)
        cmds.setAttr(joint + ".visibility", 0)
        controls.append(ctl)
        control_joints.append(joint)

    cmds.skinCluster(control_joints + [surface], toSelectedBones=True, maximumInfluences=2, dropoffRate=4.0,
                     name=naming.compose(name + "Ribbon", side, "skin_cluster"))
    return {
        "surface": surface,
        "controls": controls,
        "control_joints": control_joints,
        "joints": joints,
        "follicles": follicles,
        "group": group,
    }


def attach_ends(result, start_driver, end_driver, mid_follow=True):
    """Constrain the first/last ribbon controls to drivers; middle controls
    follow a blend of both ends (classic bendy limb behaviour)."""
    controls = result["controls"]
    cmds.parentConstraint(start_driver, controls[0].zero, maintainOffset=True)
    cmds.parentConstraint(end_driver, controls[-1].zero, maintainOffset=True)
    if mid_follow and len(controls) > 2:
        count = len(controls) - 1
        for i, ctl in enumerate(controls[1:-1], 1):
            weight = i / float(count)
            constraint = cmds.parentConstraint(start_driver, end_driver, ctl.zero, maintainOffset=True)[0]
            cmds.setAttr(constraint + ".interpType", 2)
            plugs = common.constraint_weight_plugs(constraint)
            cmds.setAttr(plugs[0], 1.0 - weight)
            cmds.setAttr(plugs[1], weight)
    return result


def add_bendy_visibility(result, attr_node, attr="bendyControls"):
    plug = attributes.add_attr(attr_node, attr, "bool", default=False, keyable=False, channel_box=True)
    for ctl in result["controls"]:
        cmds.connectAttr(plug, ctl.zero + ".visibility", force=True)
    return plug
