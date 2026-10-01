"""Reverse foot setup (roll, bank, twists, toe tap).

Pivot hierarchy (each pivot has an oriented ``ZRO`` group above it)::

    ik control
    `-- heel > toe tip > outer bank > inner bank
                                       |-- ball   > ankle target + ball IK
                                       `-- toeTap > toe IK

Attributes added on the IK control: ``roll``, ``rollBreak``,
``rollStraight``, ``bank``, ``heelTwist``, ``toeTwist``, ``ballTwist`` and
``toeTap``.

The roll follows the classic "rolling foot": negative values pivot on the
heel, positive values lift the heel around the ball until ``rollBreak``,
then blend onto the toe tip until ``rollStraight``.
"""

from maya import cmds

from jeffy.core import attributes, mathlib, matrix, naming, nodes, transform
from jeffy.rig import common


def foot_frame(heel, toe, up=(0.0, 1.0, 0.0)):
    """Orientation matrix for the pivots: Z forward (heel -> toe), Y up."""
    forward = mathlib.sub(toe, heel)
    forward = mathlib.normalize((forward[0], 0.0, forward[2])) if abs(up[1]) > 0.5 else mathlib.normalize(forward)
    if mathlib.length(forward) < 1e-6:
        forward = (0.0, 0.0, 1.0)
    x_axis = mathlib.normalize(mathlib.cross(up, forward))
    y_axis = mathlib.normalize(mathlib.cross(forward, x_axis))
    return mathlib.from_axes(x_axis, y_axis, forward)


def _pivot(name, side, position, frame, parent):
    zero = common.create_group(naming.compose(name + "Piv", side, "zero"), parent=parent)
    world = mathlib.set_translation(frame, position)
    matrix.set_world_matrix(zero, world, scale=False)
    return cmds.createNode("transform", name=naming.unique_name(naming.compose(name + "Piv", side, "group")),
                           parent=zero, skipSelect=True)


def build_reverse_foot(ik_control, end_target, ankle, ball, toe, heel_pos, inner_pos, outer_pos, name="foot",
                       side=None, roll_break=30.0, roll_straight=60.0):
    """Build a reverse foot under ``ik_control``.

    :param end_target: the node the leg IK aims for (``ik.build_ik`` returns
        it as ``end``); it is re-parented under the ball pivot.
    :param ankle, ball, toe: IK joints of the foot (ankle is the leg end)
    :param heel_pos, inner_pos, outer_pos: world positions of the pivots
    :returns: dict with ``pivots``, ``ball_handle``, ``toe_handle``
    """
    ankle_pos = transform.get_position(ankle)
    ball_pos = transform.get_position(ball)
    toe_pos = transform.get_position(toe)
    ground = min(heel_pos[1], toe_pos[1])
    toe_tip = (toe_pos[0], ground, toe_pos[2])
    frame = foot_frame(heel_pos, toe_tip)
    x_axis = mathlib.axes(frame)[0]
    outward = 1.0 if mathlib.dot(x_axis, mathlib.sub(outer_pos, inner_pos)) >= 0 else -1.0

    heel = _pivot(name + "Heel", side, heel_pos, frame, ik_control)
    toe_piv = _pivot(name + "Toe", side, toe_tip, frame, heel)
    outer = _pivot(name + "Outer", side, outer_pos, frame, toe_piv)
    inner = _pivot(name + "Inner", side, inner_pos, frame, outer)
    ball_piv = _pivot(name + "Ball", side, ball_pos, frame, inner)
    toe_tap = _pivot(name + "ToeTap", side, ball_pos, frame, inner)

    end_target = cmds.parent(end_target, ball_piv)[0]
    cmds.xform(end_target, worldSpace=True, translation=ankle_pos)

    ball_handle = cmds.ikHandle(startJoint=ankle, endEffector=ball, solver="ikSCsolver",
                                name=naming.compose(name + "Ball", side, "ik_handle"))[0]
    toe_handle = cmds.ikHandle(startJoint=ball, endEffector=toe, solver="ikSCsolver",
                               name=naming.compose(name + "Toe", side, "ik_handle"))[0]
    ball_handle = cmds.parent(ball_handle, ball_piv)[0]
    toe_handle = cmds.parent(toe_handle, toe_tap)[0]
    common.hide([ball_handle, toe_handle])

    ctl = ik_control
    attributes.add_separator(ctl, "foot")
    roll = attributes.add_attr(ctl, "roll", "float", default=0.0)
    roll_break_attr = attributes.add_attr(ctl, "rollBreak", "float", default=roll_break, minimum=0.0)
    roll_straight_attr = attributes.add_attr(ctl, "rollStraight", "float", default=roll_straight, minimum=0.0)
    bank = attributes.add_attr(ctl, "bank", "float", default=0.0)
    heel_twist = attributes.add_attr(ctl, "heelTwist", "float", default=0.0)
    toe_twist = attributes.add_attr(ctl, "toeTwist", "float", default=0.0)
    ball_twist = attributes.add_attr(ctl, "ballTwist", "float", default=0.0)
    tap = attributes.add_attr(ctl, "toeTap", "float", default=0.0)

    base = name + "Roll"
    # heel: negative roll only
    cmds.connectAttr(nodes.clamp(roll, -180.0, 0.0, name=naming.compose(base + "Heel", side, "clamp")),
                     heel + ".rotateX")
    # toe blend 0..1 between break and straight angles
    toe_blend = nodes.remap(roll, roll_break_attr, roll_straight_attr, 0.0, 1.0,
                            name=naming.compose(base + "ToeBlend", side, "remap"))
    ball_roll = nodes.multiply(nodes.clamp(roll, 0.0, roll_break_attr), nodes.reverse(toe_blend),
                               name=naming.compose(base + "Ball", side, "utility"))
    cmds.connectAttr(ball_roll, ball_piv + ".rotateX")
    cmds.connectAttr(nodes.multiply(roll, toe_blend, name=naming.compose(base + "Toe", side, "utility")),
                     toe_piv + ".rotateX")
    # bank: positive rolls onto the outer edge
    cmds.connectAttr(nodes.multiply(nodes.clamp(bank, 0.0, 180.0), -outward), outer + ".rotateZ")
    cmds.connectAttr(nodes.multiply(nodes.clamp(bank, -180.0, 0.0), -outward), inner + ".rotateZ")
    # twists and toe tap (positive lifts the toes)
    cmds.connectAttr(heel_twist, heel + ".rotateY")
    cmds.connectAttr(toe_twist, toe_piv + ".rotateY")
    cmds.connectAttr(ball_twist, ball_piv + ".rotateY")
    cmds.connectAttr(nodes.negate(tap), toe_tap + ".rotateX")

    return {
        "pivots": {"heel": heel, "toe": toe_piv, "outer": outer, "inner": inner, "ball": ball_piv,
                   "toe_tap": toe_tap},
        "ball_handle": ball_handle,
        "toe_handle": toe_handle,
        "end_target": end_target,
    }
