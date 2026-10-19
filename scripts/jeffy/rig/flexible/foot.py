"""Course style reverse foot (videos 10 and 11), wired with utility nodes only.

Pivots are empty groups (translate/rotate 0) whose rotate/scale pivots are
placed on the foot, nested like the course::

    IK control
      root (ankle) > heel > inner > outer > end (toe tip) > ball > ankle
                                                                     `- leg IK handle (+ stretch end)
                                                           `- ball IK handle
                                                  `- toe (on the ball) > toe IK handle

Attributes on the IK control: ``Roll`` (-10..20), ``Bank``, ``HeelTwist``,
``ToeTwist``, ``ToeTap`` and the settings ``ToeFlex`` (9), ``RollBack`` (3),
``RollEnd`` (90), ``BankAmount`` (5), ``ToeStraightAngle`` (8).

Roll, with R = Roll and S = ToeStraightAngle (degrees)::

    heel.rx = min(R, 0) * RollBack
    ball.rx = max(B * ToeFlex, 0)   when R > 0,  B = R (R <= S) or S - 2 (R - S)
    end.rx  = min(max(R - S, 0) * 15, RollEnd)

Bank: positive values roll onto the inner pivot, negative onto the outer one,
times ``BankAmount`` (outputs swapped on the right side, as in the course).
The pivots are world aligned: the foot should point down +Z (as the course rig).
"""

from maya import cmds

from jeffy.core import attributes, naming, transform
from jeffy.rig.flexible import common

DEFAULTS = (("ToeFlex", 9.0), ("RollBack", 3.0), ("RollEnd", 90.0), ("BankAmount", 5.0),
            ("ToeStraightAngle", 8.0))


def _pivot(name, side, parent, position):
    group = common.group(name + "Pivot", side, parent=parent)
    cmds.xform(group, worldSpace=True, pivots=position)
    return group


def build_reverse_foot(ik_control, ankle, ball, toe, heel_pos, inner_pos, outer_pos, name="foot", side=None,
                       follow=None, mirror=None):
    """Build the course reverse foot under ``ik_control``.

    :param ankle, ball, toe: IK joints of the foot
    :param follow: nodes moved under the ankle pivot (leg IK handle, stretch
        end...). Default: every transform child of the IK control.
    :param mirror: swap the bank outputs (default: ``side == 'R'``)
    :returns: dict with ``pivots``, ``handles`` and ``nodes``
    """
    side = side if side is not None else naming.side_from_name(ik_control)
    mirror = (side == naming.SIDE_RIGHT) if mirror is None else mirror
    if follow is None:
        follow = [c for c in cmds.listRelatives(ik_control, children=True, type="transform", fullPath=True) or []
                  if not cmds.objectType(c, isAType="constraint")]
    ankle_pos = transform.get_position(ankle)
    ball_pos = transform.get_position(ball)
    toe_pos = transform.get_position(toe)
    ground = heel_pos[1]
    tip_pos = (toe_pos[0], ground, toe_pos[2])

    ball_handle = cmds.ikHandle(startJoint=ankle, endEffector=ball, solver="ikSCsolver",
                                name=naming.unique_name(naming.compose(name + "Ball", side, "ik_handle")))[0]
    toe_handle = cmds.ikHandle(startJoint=ball, endEffector=toe, solver="ikSCsolver",
                               name=naming.unique_name(naming.compose(name + "Toe", side, "ik_handle")))[0]

    root = _pivot(name + "Root", side, ik_control, ankle_pos)
    heel = _pivot(name + "Heel", side, root, heel_pos)
    inner = _pivot(name + "Inner", side, heel, inner_pos)
    outer = _pivot(name + "Outer", side, inner, outer_pos)
    end = _pivot(name + "End", side, outer, tip_pos)
    ball_piv = _pivot(name + "Ball", side, end, ball_pos)
    ankle_piv = _pivot(name + "Ankle", side, ball_piv, ankle_pos)
    toe_piv = _pivot(name + "Toe", side, end, ball_pos)

    for node in follow:
        cmds.parent(node, ankle_piv)
    ball_handle = cmds.parent(ball_handle, ball_piv)[0]
    toe_handle = cmds.parent(toe_handle, toe_piv)[0]
    for handle in (ball_handle, toe_handle):
        cmds.setAttr(handle + ".visibility", 0)

    ctl = ik_control
    attributes.add_separator(ctl, "pose")
    roll = attributes.add_attr(ctl, "Roll", "float", default=0.0, minimum=-10.0, maximum=20.0)
    bank = attributes.add_attr(ctl, "Bank", "float", default=0.0)
    heel_twist = attributes.add_attr(ctl, "HeelTwist", "float", default=0.0)
    toe_twist = attributes.add_attr(ctl, "ToeTwist", "float", default=0.0)
    toe_tap = attributes.add_attr(ctl, "ToeTap", "float", default=0.0)
    attributes.add_separator(ctl, "settings")
    settings = {attr: attributes.add_attr(ctl, attr, "float", default=value) for attr, value in DEFAULTS}

    # direct ------------------------------------------------------------------
    cmds.connectAttr(heel_twist, heel + ".rotateY")
    cmds.connectAttr(toe_twist, end + ".rotateY")
    cmds.connectAttr(toe_tap, toe_piv + ".rotateX")

    nodes = {}
    # bank ------------------------------------------------------------------
    cond = common.node("condition", name + "Bank", side, "condition", operation=2)
    cmds.connectAttr(bank, cond + ".firstTerm")
    cmds.connectAttr(bank, cond + ".colorIfTrueR")
    cmds.connectAttr(bank, cond + ".colorIfFalseG")
    cmds.setAttr(cond + ".colorIfFalseR", 0)
    cmds.setAttr(cond + ".colorIfTrueG", 0)
    multi = common.node("multiplyDivide", name + "Bank", side, "multiply_divide")
    cmds.connectAttr(cond + ".outColorR", multi + ".input1X")
    cmds.connectAttr(cond + ".outColorG", multi + ".input1Y")
    cmds.connectAttr(settings["BankAmount"], multi + ".input2X")
    cmds.connectAttr(settings["BankAmount"], multi + ".input2Y")
    first, second = (outer, inner) if mirror else (inner, outer)
    cmds.connectAttr(multi + ".outputX", first + ".rotateZ")
    cmds.connectAttr(multi + ".outputY", second + ".rotateZ")
    nodes.update(bank_condition=cond, bank_multi=multi)

    # roll ------------------------------------------------------------------
    straight = settings["ToeStraightAngle"]
    roll_pma = common.node("plusMinusAverage", name + "Roll", side, "plus_minus", operation=2)
    cmds.connectAttr(roll, roll_pma + ".input1D[0]")
    cmds.connectAttr(straight, roll_pma + ".input1D[1]")
    ball_multi = common.node("multiplyDivide", name + "RollBall", side, "multiply_divide")
    cmds.connectAttr(roll_pma + ".output1D", ball_multi + ".input1X")
    cmds.setAttr(ball_multi + ".input2X", 2)
    cmds.connectAttr(settings["ToeFlex"], ball_multi + ".input1Y")
    cmds.setAttr(ball_multi + ".input2Y", 1)
    ball_pma = common.node("plusMinusAverage", name + "RollBall", side, "plus_minus", operation=2)
    cmds.connectAttr(straight, ball_pma + ".input1D[0]")
    cmds.connectAttr(ball_multi + ".outputX", ball_pma + ".input1D[1]")
    ball_cond = common.node("condition", name + "RollBall", side, "condition", operation=2)
    cmds.connectAttr(roll, ball_cond + ".firstTerm")
    cmds.connectAttr(straight, ball_cond + ".secondTerm")
    cmds.connectAttr(ball_pma + ".output1D", ball_cond + ".colorIfTrueR")
    cmds.connectAttr(roll, ball_cond + ".colorIfFalseR")

    heel_cond = common.node("condition", name + "RollHeel", side, "condition", operation=2)
    cmds.connectAttr(roll, heel_cond + ".firstTerm")
    cmds.setAttr(heel_cond + ".colorIfTrueR", 0)
    cmds.connectAttr(ball_cond + ".outColorR", heel_cond + ".colorIfTrueG")
    cmds.connectAttr(roll, heel_cond + ".colorIfFalseR")
    cmds.setAttr(heel_cond + ".colorIfFalseG", 0)

    tip_pma = common.node("plusMinusAverage", name + "TipToe", side, "plus_minus", operation=2)
    cmds.connectAttr(roll, tip_pma + ".input1D[0]")
    cmds.connectAttr(straight, tip_pma + ".input1D[1]")
    tip_cond = common.node("condition", name + "TipToe", side, "condition", operation=2)
    cmds.connectAttr(roll, tip_cond + ".firstTerm")
    cmds.connectAttr(straight, tip_cond + ".secondTerm")
    cmds.connectAttr(tip_pma + ".output1D", tip_cond + ".colorIfTrueR")
    cmds.setAttr(tip_cond + ".colorIfFalseR", 0)

    roll_multi = common.node("multiplyDivide", name + "Roll", side, "multiply_divide")
    cmds.connectAttr(heel_cond + ".outColorR", roll_multi + ".input1X")
    cmds.connectAttr(heel_cond + ".outColorG", roll_multi + ".input1Y")
    cmds.connectAttr(tip_cond + ".outColorR", roll_multi + ".input1Z")
    cmds.connectAttr(settings["RollBack"], roll_multi + ".input2X")
    cmds.connectAttr(ball_multi + ".outputY", roll_multi + ".input2Y")
    cmds.setAttr(roll_multi + ".input2Z", 15)
    cmds.connectAttr(roll_multi + ".outputX", heel + ".rotateX")

    clamp = common.node("condition", name + "RollClamp", side, "condition", operation=2)
    cmds.connectAttr(roll_multi + ".outputY", clamp + ".firstTerm")
    cmds.connectAttr(roll_multi + ".outputY", clamp + ".colorIfTrueR")
    cmds.setAttr(clamp + ".colorIfFalseR", 0)
    cmds.connectAttr(clamp + ".outColorR", ball_piv + ".rotateX")

    end_cond = common.node("condition", name + "RollEnd", side, "condition", operation=2)
    cmds.connectAttr(roll_multi + ".outputZ", end_cond + ".firstTerm")
    cmds.connectAttr(settings["RollEnd"], end_cond + ".secondTerm")
    cmds.connectAttr(settings["RollEnd"], end_cond + ".colorIfTrueR")
    cmds.connectAttr(roll_multi + ".outputZ", end_cond + ".colorIfFalseR")
    cmds.connectAttr(end_cond + ".outColorR", end + ".rotateX")
    nodes.update(roll_pma=roll_pma, ball_multi=ball_multi, ball_pma=ball_pma, ball_condition=ball_cond,
                 heel_condition=heel_cond, tiptoe_pma=tip_pma, tiptoe_condition=tip_cond, roll_multi=roll_multi,
                 clamp_condition=clamp, end_condition=end_cond)
    pivots = {"root": root, "heel": heel, "inner": inner, "outer": outer, "end": end, "ball": ball_piv,
              "ankle": ankle_piv, "toe": toe_piv}
    common.store(ctl, "footPivots", [pivots[k] for k in ("root", "heel", "inner", "outer", "end", "ball", "ankle",
                                                           "toe")])
    return {"pivots": pivots, "handles": {"ball": ball_handle, "toe": toe_handle}, "nodes": nodes}
