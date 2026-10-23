"""Stage 2 of the Setup Belt in real Maya: auto-snap, Twist, Ribbon, Reverse Foot.

Run with ``mayapy tests/in_maya/run.py``.
"""

import skeleton
from maya import cmds
from test_setups_stage1 import (
    ARM,
    LEG,
    assert_close,
    assert_no_constraints,
    assert_no_pop,
    base,
    close,
    pos,
    scene_nodes,
    wm,
)

from jeffy.core import mathlib
from jeffy.setups.core import scene
from jeffy.setups.tools.fk_chain import FkChain
from jeffy.setups.tools.ikfk_limb import IkFkLimb
from jeffy.setups.tools.ribbon import Ribbon
from jeffy.setups.tools.rig_base import RigBase
from jeffy.setups.tools.twist import Twist


def arm(**options):
    values = dict(ARM)
    values.update(options)
    return IkFkLimb.build(name="arm", **values)


# ---------------------------------------------------------------------------
# Auto-snap
# ---------------------------------------------------------------------------
def test_auto_snap_keeps_the_bend():
    base()
    arm()
    cmds.setAttr("L_armIK_CTL.translate", -8, -12, 9)
    cmds.setAttr("L_armPole_CTL.translateY", 15)
    ik_pose = dict((j, wm(j)) for j in ARM.values())
    cmds.setAttr("L_armSettings_CTL.ikFk", 0)  # plain channel box edit
    for joint, matrix in ik_pose.items():
        assert_close(wm(joint), matrix, "switch to FK keeps the pose (%s)" % joint, 0.01)
    cmds.setAttr("L_elbowFK_CTL.rotateZ", -25)
    fk_wrist = pos("L_wrist_JNT")
    cmds.setAttr("L_shoulderFK_CTL.ikFk", 1)  # through the proxy attribute
    assert cmds.getAttr("L_armSettings_CTL.ikFk") == 1.0
    assert_close(pos("L_wrist_JNT"), fk_wrist, "switch to IK keeps the pose", 0.01)
    cmds.setAttr("L_armSettings_CTL.autoSnap", 0)
    cmds.setAttr("L_armIK_CTL.translateY", 0)
    cmds.setAttr("L_armSettings_CTL.ikFk", 0)
    assert not close(pos("L_wrist_JNT"), pos("L_armIK_CTL")), "autoSnap off: plain switch"
    assert cmds.objExists("jeffySetupBelt_autoSnap_SN")


# ---------------------------------------------------------------------------
# Twist
# ---------------------------------------------------------------------------
def test_twist_on_arm():
    base()
    before = skeleton.world_matrices()
    arm()
    layer = Twist.build(base="L_armIK_CTL", count=3)
    assert layer.mirror is not None
    assert_no_pop(before)
    assert_no_constraints()
    upper = ["L_shoulderTwist%02d_JNT" % i for i in (1, 2, 3)]
    lower = ["L_elbowTwist%02d_JNT" % i for i in (1, 2, 3)]
    for joint in upper + lower:
        assert cmds.objExists(joint)
    assert cmds.listRelatives(upper[0], parent=True) == ["L_shoulder_JNT"]
    # forward twist: roll the wrist (FK) -> the forearm twist joints follow progressively
    cmds.setAttr("L_armSettings_CTL.autoSnap", 0)
    cmds.setAttr("L_armSettings_CTL.ikFk", 0)
    rest = [wm(j) for j in lower]
    cmds.setAttr("L_wristFK_CTL.rotateX", 60)  # X runs down the bones in the test skeleton
    angles = [roll_angle(r, wm(j), 0) for r, j in zip(rest, lower)]
    assert angles[0] < angles[1] < angles[2] < 60.5, angles
    assert angles[2] > 30, angles
    # positions stay on the forearm
    for joint in lower:
        p = pos(joint)
        closest = mathlib.closest_point_on_line(p, pos("L_elbow_JNT"), pos("L_wrist_JNT"))
        assert mathlib.distance(p, closest) < 0.01
    layer.delete(mirror=True)
    assert not cmds.objExists(upper[0]) and not cmds.objExists("R_shoulderTwist01_JNT")


def roll_angle(rest, current, axis):
    """Angle (degrees) between the rest and current non-bone axis (roll around the bone)."""
    other = (axis + 1) % 3
    a = mathlib.normalize(mathlib.axes(rest)[other])
    b = mathlib.normalize(mathlib.axes(current)[other])
    return mathlib.angle_between(a, b)


def test_twist_counter_on_upper_arm():
    base()
    FkChain.build(start="L_clavicle_JNT", mirror=False)
    arm(mirror=False)
    Twist.build(base="L_armIK_CTL", mirror=False)
    cmds.setAttr("L_armSettings_CTL.autoSnap", 0)
    cmds.setAttr("L_armSettings_CTL.ikFk", 0)
    upper = ["L_shoulderTwist%02d_JNT" % i for i in (1, 2, 3)]
    rest = [wm(j) for j in upper]
    cmds.setAttr("L_shoulderFK_CTL.rotateX", 60)  # roll the upper arm
    angles = [roll_angle(r, wm(j), 0) for r, j in zip(rest, upper)]
    assert angles[0] < angles[1] < angles[2], angles
    assert angles[0] < 25 and angles[2] > 35, angles


# ---------------------------------------------------------------------------
# Ribbon
# ---------------------------------------------------------------------------
def test_ribbon_on_arm():
    base()
    before = skeleton.world_matrices()
    arm()
    layer = Ribbon.build(base="L_armIK_CTL")
    assert_no_pop(before)
    assert_no_constraints()
    joints = ["L_armRibbon%02d_JNT" % i for i in range(1, 11)]
    for joint in joints:
        assert cmds.objExists(joint), joint
    rest = dict((j, wm(j)) for j in joints)
    # at rest the ribbon joints sit on the bones
    for joint in joints[:5]:
        p = pos(joint)
        closest = mathlib.closest_point_on_line(p, pos("L_shoulder_JNT"), pos("L_elbow_JNT"))
        assert mathlib.distance(p, closest) < 0.01, joint
    # bend control moves the middle of the upper arm, not its ends
    cmds.setAttr("L_shoulderBend_CTL.translateY", 5)
    assert not close(pos(joints[2]), rest[joints[2]][12:15])
    assert_close(pos(joints[0]), rest[joints[0]][12:15], "ribbon start stays on the shoulder", 0.01)
    cmds.setAttr("L_shoulderBend_CTL.translateY", 0)
    # stretch thins the joints (film mode)
    cmds.setAttr("L_armIK_CTL.stretch", 1)
    cmds.setAttr("L_armIK_CTL.translateX", 30)
    scale = cmds.getAttr(joints[2] + ".scale")[0]
    assert min(scale) < 0.97, scale
    cmds.setAttr("L_armSettings_CTL.volume", 0)
    assert close(cmds.getAttr(joints[2] + ".scale")[0], (1, 1, 1), 0.01)
    assert cmds.attributeQuery("bendyVis", node="L_armSettings_CTL", exists=True)
    layer.delete(mirror=True)
    assert not cmds.objExists(joints[0])
    assert not cmds.attributeQuery("bendyVis", node="L_armSettings_CTL", exists=True)


def test_ribbon_game_safe_and_rebuild():
    base()
    limb = arm(mirror=False)
    Ribbon.build(base="L_armIK_CTL", game_safe=True, joints=3, mirror=False)
    assert cmds.listRelatives("L_armRibbon01_JNT", parent=True) == ["L_shoulder_JNT"]
    assert not cmds.attributeQuery("volume", node="L_armSettings_CTL", exists=True)
    limb = limb.rebuild(options={"knee": "no-flip"})
    assert cmds.objExists("L_armRibbon06_JNT"), "the ribbon is rebuilt with the limb"
    assert [s.TYPE for s in limb.layers()] == ["ribbon"]


def test_twist_and_ribbon_exclusive():
    base()
    arm(mirror=False)
    Ribbon.build(base="L_armIK_CTL", mirror=False)
    try:
        Twist.build(base="L_armIK_CTL", mirror=False)
    except Exception as error:
        assert "Ribbon" in str(error)
    else:
        raise AssertionError("twist on a ribbon limb should fail")


def test_ribbon_on_fk_chain_and_delete_everything():
    skeleton.build_biped()
    before = skeleton.world_matrices()
    nodes_before = scene_nodes()
    rig = RigBase.build(root_joint="C_root_JNT", name="hero")
    FkChain.build(start="C_spine01_JNT", end="C_chest_JNT", name="spine")
    Ribbon.build(base="C_spine01FK_CTL", joints=4)
    arm()
    Twist.build(base="L_armIK_CTL")
    IkFkLimb.build(name="leg", **LEG)
    Ribbon.build(base="L_legIK_CTL")
    assert_no_pop(before)
    rig.delete()
    assert not scene.all_setups()
    assert_no_pop(before)
    leftovers = sorted(scene_nodes() - nodes_before)
    assert not leftovers, "left after delete: %s" % leftovers


# ---------------------------------------------------------------------------
# Reverse Foot
# ---------------------------------------------------------------------------
def leg_with_foot(**options):
    values = dict(LEG)
    values.update(options)
    leg = IkFkLimb.build(name="leg", **values)
    from jeffy.setups.tools.foot import ReverseFoot

    foot = ReverseFoot.build(base="L_legIK_CTL", ball="L_ball_JNT", toe="L_toe_JNT",
                             mirror=options.get("mirror", True))
    return leg, foot


def test_reverse_foot_roll_bank_tap():
    base()
    before = skeleton.world_matrices()
    _leg, foot = leg_with_foot()
    assert_no_pop(before)
    assert_no_constraints()
    assert foot.mirror is not None and cmds.objExists("R_legFootRoll_CTL")
    ankle, ball, toe = pos("L_ankle_JNT"), pos("L_ball_JNT"), pos("L_toe_JNT")
    cmds.setAttr("L_legFootRoll_CTL.rotateX", -20)  # heel
    assert pos("L_toe_JNT")[1] > toe[1] + 1, "heel roll lifts the toes"
    cmds.setAttr("L_legFootRoll_CTL.rotateX", 20)  # ball
    assert pos("L_ankle_JNT")[1] > ankle[1] + 1, "ball roll lifts the heel"
    assert_close(pos("L_ball_JNT"), ball, "the ball stays on the ground", 0.05)
    cmds.setAttr("L_legFootRoll_CTL.rotateX", 80)  # past rollStraight: on the toe tip
    assert pos("L_ball_JNT")[1] > ball[1] + 1, "toe roll lifts the ball"
    assert_close(pos("L_toe_JNT"), toe, "the toe tip stays on the ground", 0.05)
    cmds.setAttr("L_legFootRoll_CTL.rotateX", 0)
    inner = pos("L_legInnerPivot_CTL")
    cmds.setAttr("L_legFootRoll_CTL.rotateZ", 20)
    assert pos("L_legInnerPivot_CTL")[1] > inner[1] + 0.5, "positive bank rolls on the outer edge"
    cmds.setAttr("L_legFootRoll_CTL.rotateZ", -20)
    assert_close(pos("L_legInnerPivot_CTL"), inner, "negative bank pivots on the inner edge", 0.01)
    assert pos("L_ankle_JNT")[0] < ankle[0], "negative bank tilts toward the inside"
    cmds.setAttr("L_legFootRoll_CTL.rotateZ", 0)
    cmds.setAttr("L_legFootRoll_CTL.toeTap", 30)
    assert pos("L_toe_JNT")[1] > toe[1] + 1, "toe tap"
    cmds.setAttr("L_legFootRoll_CTL.toeTap", 0)
    # right side rolls the same way
    r_toe = pos("R_toe_JNT")
    cmds.setAttr("R_legFootRoll_CTL.rotateX", -20)
    assert pos("R_toe_JNT")[1] > r_toe[1] + 1


def test_reverse_foot_snap_and_delete():
    base()
    before = skeleton.world_matrices()
    _leg, foot = leg_with_foot(mirror=False)
    cmds.setAttr("L_legIK_CTL.translate", 3, 10, 6)
    cmds.setAttr("L_legFootRoll_CTL.rotateX", 25)
    cmds.setAttr("L_legFootRoll_CTL.toeTap", 15)
    ik_pose = dict((j, wm(j)) for j in ("L_hip_JNT", "L_knee_JNT", "L_ankle_JNT", "L_ball_JNT"))
    cmds.setAttr("L_legSettings_CTL.ikFk", 0)  # auto-snap to FK
    for joint, matrix in ik_pose.items():
        assert_close(wm(joint), matrix, "FK keeps the foot pose (%s)" % joint, 0.01)
    cmds.setAttr("L_ballFK_CTL.rotateZ", 20)
    fk_ball = wm("L_ball_JNT")
    fk_ankle = pos("L_ankle_JNT")
    fk_toe = pos("L_toe_JNT")
    cmds.setAttr("L_legFootRoll_CTL.ikFk", 1)  # through the roll control's proxy
    assert cmds.getAttr("L_legFootRoll_CTL.rotateX") == 0.0, "snapping to IK resets the roll"
    assert_close(pos("L_ankle_JNT"), fk_ankle, "IK keeps the ankle", 0.01)
    toe_length = mathlib.distance(fk_ball[12:15], fk_toe)
    assert mathlib.distance(pos("L_toe_JNT"), fk_toe) < toe_length * 0.1, "toe tap follows the FK toe"
    foot.delete()
    cmds.setAttr("L_legIK_CTL.translate", 0, 0, 0)
    cmds.setAttr("L_legIK_CTL.rotate", 0, 0, 0)
    cmds.setAttr("L_legPole_CTL.translate", 0, 0, 0)
    assert not cmds.objExists("L_legFootRoll_CTL")
    assert cmds.listRelatives("L_legIkEnd_GRP", parent=True) == ["L_legIK_CTL"]
    assert_no_pop(before)


def test_reverse_foot_guides_and_rebuild():
    base()
    from jeffy.setups.tools.foot import ReverseFoot

    leg = IkFkLimb.build(name="leg", mirror=False, **LEG)
    found = ReverseFoot.preview({"base": "L_legIK_CTL", "ball": "L_ball_JNT", "toe": "L_toe_JNT"}, {})
    assert set(found) == {"heel", "toe", "inner", "outer", "roll"}
    cmds.setAttr(found["heel"] + ".translateZ", -12)
    ReverseFoot.create({"base": "L_legIK_CTL", "ball": "L_ball_JNT", "toe": "L_toe_JNT"}, {"mirror": False})
    heel = pos("L_legHeelPivot_CTL")
    assert abs(heel[2] + 12) < 0.01, heel
    leg = leg.rebuild(options={"knee": "no-flip"})
    assert cmds.objExists("L_legFootRoll_CTL"), "the foot is rebuilt with the leg"
    assert_close(pos("L_legHeelPivot_CTL"), heel, "rebuild keeps the guides")
