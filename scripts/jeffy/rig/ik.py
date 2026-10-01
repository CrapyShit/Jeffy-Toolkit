"""IK chains with stretch, soft IK, elbow/knee pinning and pole vectors.

The stretch/soft network (all utility nodes, scale aware)::

    D   = distance(root, end) / root world scale
    L   = upper * upperLength + lower * lowerLength
    sd  = max(softness * L * 0.25, eps)          soft distance
    da  = L - sd
    Ds  = D > da ? da + sd * (1 - e^(-(D - da) / sd)) : D
    f   = lerp(1, D / Ds, stretch)               length factor

The IK handle is point constrained to a locator aimed at the control at
distance ``Ds`` (weight ``1 - stretch``) and to the control (weight
``stretch``), so soft IK and stretch combine seamlessly.
"""

import math

from maya import cmds

from jeffy.controls.control import Control
from jeffy.core import attributes, mathlib, naming, nodes, transform
from jeffy.geometry import curves
from jeffy.rig import common

EPSILON = 0.0001


def pole_vector_position(start, mid, end, distance_factor=1.0):
    """World position for a pole vector control of a 3 joint chain."""
    return mathlib.pole_vector_position(
        transform.get_position(start), transform.get_position(mid), transform.get_position(end), distance_factor
    )


def build_ik(
    joints,
    name="limb",
    side=None,
    parent=None,
    control_parent=None,
    systems_parent=None,
    solver="ikRPsolver",
    pole_vector=True,
    pole_distance=1.0,
    stretch=True,
    soft=True,
    pin=True,
    ik_shape="cube",
    pole_shape="octahedron",
    size=1.0,
    orient_control="world",
    color_value=None,
    orient_end=True,
):
    """Build an IK setup on a chain of 3 (or more) joints.

    :param joints: root -> end joints (the chain's root should already follow
        its parent - e.g. constrained to the clavicle)
    :param parent: node the IK root locator follows (usually the limb parent)
    :param control_parent: parent of the IK and pole vector controls
    :param systems_parent: parent of the non animator nodes (hidden)
    :param orient_control: ``world`` or ``joint`` orientation for the IK control
    :param orient_end: orient constrain the end joint to the IK control
        (turn off when a reverse foot drives the end joint)
    :returns: dict with ``ik_control``, ``pole_control``, ``handle``,
        ``root``, ``end``, ``group`` and the attribute plugs
    """
    if len(joints) < 2:
        raise ValueError("IK needs at least two joints")
    start, end = joints[0], joints[-1]
    axis = common.primary_axis(joints[1])
    base = name + "IK"

    group = common.create_group(naming.compose(base, side, "group"), parent=systems_parent, visible=False)
    root = common.create_locator(naming.compose(base + "Root", side, "locator"), match=start)
    root = cmds.parent(root, parent)[0] if parent else cmds.parent(root, group)[0]

    # controls -------------------------------------------------------------
    ik_ctl = Control.create(base, side=side, shape=ik_shape, size=size, parent=control_parent, match=end,
                            match_rotation=(orient_control == "joint"), offsets=("zero", "space"),
                            color_value=color_value)
    end_ref = common.create_locator(naming.compose(base + "End", side, "locator"), parent=ik_ctl.node, match=end)

    handle, effector = cmds.ikHandle(startJoint=start, endEffector=end, solver=solver,
                                     name=naming.compose(base, side, "ik_handle"))
    cmds.rename(effector, naming.compose(base, side, "effector"))
    handle = cmds.parent(handle, group)[0]
    if orient_end:
        cmds.orientConstraint(end_ref, end, maintainOffset=True)

    ctl = ik_ctl.node
    attributes.add_separator(ctl, "ik")
    twist = attributes.add_attr(ctl, "twist", "float", default=0.0)
    cmds.connectAttr(twist, handle + ".twist")

    pole_ctl = None
    if pole_vector and solver == "ikRPsolver" and len(joints) >= 3:
        mid = joints[len(joints) // 2] if len(joints) > 3 else joints[1]
        position = pole_vector_position(start, mid, end, pole_distance)
        pole_ctl = Control.create(name + "Pole", side=side, shape=pole_shape, size=size * 0.4,
                                  parent=control_parent, position=position, offsets=("zero", "space"),
                                  lock=("r", "s", "v"), color_value=color_value)
        cmds.poleVectorConstraint(pole_ctl.node, handle)
        line = curves.create_connector_line(mid, pole_ctl.node, name=naming.compose(name + "Pole", side, "curve"),
                                            parent=control_parent or group)
        cmds.setAttr(line + ".overrideEnabled", 1)
        cmds.setAttr(line + ".overrideDisplayType", 1)

    result = {
        "ik_control": ik_ctl,
        "pole_control": pole_ctl,
        "handle": handle,
        "root": root,
        "end": end_ref,
        "group": group,
        "axis": axis,
    }

    if stretch or soft:
        result.update(_stretch_network(joints, name, side, root, end_ref, handle, ctl, group, axis,
                                       pole_ctl.node if (pin and pole_ctl) else None, stretch, soft))
    else:
        cmds.pointConstraint(end_ref, handle)

    attributes.lock_hide(handle, ("t", "r", "s"), hide=False)
    common.hide([handle, root, end_ref])
    return result


def _stretch_network(joints, name, side, root, end_ref, handle, ctl, group, axis, pole, stretch, soft):
    base = name + "IK"
    plugs = {}
    stretch_attr = attributes.add_attr(ctl, "stretch", "float", default=0.0, minimum=0.0, maximum=1.0)
    softness = attributes.add_attr(ctl, "softness", "float", default=0.0, minimum=0.0, maximum=1.0)
    if not soft:
        attributes.lock_hide(ctl, ["softness"])
    if not stretch:
        attributes.lock_hide(ctl, ["stretch"])
    plugs["stretch"] = stretch_attr
    plugs["softness"] = softness

    children = joints[1:]
    rest = [common.segment_length(j, axis) for j in children]
    signs = [common.axis_sign(j, axis) for j in children]
    three = len(joints) == 3

    # current normalised distance
    distance = nodes.distance_between(root, end_ref, name=naming.compose(base + "Dist", side, "distance"))
    scale = common.world_scale_plug(root, name=naming.compose(base + "Scale", side, "decompose_matrix"))
    norm = nodes.divide(distance, scale, name=naming.compose(base + "NormDist", side, "multiply_divide"))

    # chain length with multipliers
    if three:
        upper_mult = attributes.add_attr(ctl, "upperLength", "float", default=1.0, minimum=0.001)
        lower_mult = attributes.add_attr(ctl, "lowerLength", "float", default=1.0, minimum=0.001)
        upper = nodes.multiply(rest[0], upper_mult)
        lower = nodes.multiply(rest[1], lower_mult)
        chain_length = nodes.add(upper, lower, name=naming.compose(base + "Length", side, "utility"))
        segments = [upper, lower]
    else:
        total = sum(rest)
        length_mult = attributes.add_attr(ctl, "length", "float", default=1.0, minimum=0.001)
        chain_length = nodes.multiply(total, length_mult)
        segments = [nodes.multiply(r, length_mult) for r in rest]

    # soft IK
    soft_dist = nodes.clamp(nodes.multiply(nodes.multiply(softness, chain_length), 0.25), EPSILON, 1.0e9)
    da = nodes.subtract(chain_length, soft_dist)
    over = nodes.subtract(norm, da)
    exponent = nodes.clamp(nodes.divide(nodes.negate(over), soft_dist), -50.0, 50.0)
    exp_term = nodes.power(math.e, exponent)
    soft_value = nodes.add(da, nodes.multiply(soft_dist, nodes.reverse(exp_term)))
    soft_distance = nodes.condition(norm, ">", da, soft_value, norm,
                                    name=naming.compose(base + "Soft", side, "condition"))

    ratio = nodes.divide(norm, soft_distance)
    factor = nodes.blend(1.0, ratio, stretch_attr, name=naming.compose(base + "Factor", side, "blend"))
    plugs["factor"] = factor

    # soft locator aimed from the root at the end reference
    aim_grp = common.create_group(naming.compose(base + "Aim", side, "group"), parent=root, match=root)
    cmds.aimConstraint(end_ref, aim_grp, aimVector=(1, 0, 0), upVector=(0, 1, 0), worldUpType="none")
    soft_loc = common.create_locator(naming.compose(base + "Soft", side, "locator"), parent=aim_grp)
    cmds.connectAttr(soft_distance, soft_loc + ".translateX")
    constraint = cmds.pointConstraint(soft_loc, end_ref, handle)[0]
    weights = common.constraint_weight_plugs(constraint)
    cmds.connectAttr(nodes.reverse(stretch_attr), weights[0])
    cmds.connectAttr(stretch_attr, weights[1])

    # apply lengths to joints
    finals = [nodes.multiply(seg, factor) for seg in segments]
    if three and pole:
        pin = attributes.add_attr(ctl, "pin", "float", default=0.0, minimum=0.0, maximum=1.0)
        plugs["pin"] = pin
        upper_pin = nodes.divide(nodes.distance_between(root, pole), scale)
        lower_pin = nodes.divide(nodes.distance_between(pole, end_ref), scale)
        finals = [nodes.blend(finals[0], upper_pin, pin), nodes.blend(finals[1], lower_pin, pin)]
    for joint, value, sign in zip(children, finals, signs):
        target = "%s.%s" % (joint, common.axis_attr(axis))
        if sign < 0:
            value = nodes.negate(value)
        cmds.connectAttr(value, target, force=True)
    return plugs


def ik_on_selection(**kwargs):
    """Build an IK on the selected start and end joints."""
    from jeffy.core import dag

    selection = cmds.ls(selection=True, type="joint") or []
    if len(selection) != 2:
        raise ValueError("Select the start and end joints")
    chain = [naming.short_name(j) for j in dag.get_chain(selection[0], selection[1])]
    parsed = naming.parse(chain[0])
    kwargs.setdefault("name", parsed["name"] or "limb")
    kwargs.setdefault("side", parsed["side"])
    return build_ik(chain, **kwargs)
