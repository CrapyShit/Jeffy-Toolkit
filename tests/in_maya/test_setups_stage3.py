"""Stage 3 of the Setup Belt in real Maya: Spline IK/FK, Aim, Fleshy Lids, Jaw, Hand.

Run with ``mayapy tests/in_maya/run.py``.
"""

import skeleton
from maya import cmds
from test_setups_stage1 import ARM, assert_close, assert_no_constraints, assert_no_pop, close, pos, scene_nodes, wm

from jeffy.core import mathlib
from jeffy.setups.core import attach, scene
from jeffy.setups.tools.fk_chain import FkChain
from jeffy.setups.tools.ikfk_limb import IkFkLimb
from jeffy.setups.tools.rig_base import RigBase
from jeffy.setups.tools.spline import SplineIkFk

SPINE = ("C_spine01_JNT", "C_spine02_JNT", "C_chest_JNT")


def rig(**skeleton_options):
    skeleton.build_biped(**skeleton_options)
    before = skeleton.world_matrices()
    RigBase.build(root_joint="C_root_JNT", name="hero")
    return before


# ---------------------------------------------------------------------------
# Spline IK/FK
# ---------------------------------------------------------------------------
def test_spine():
    before = rig()
    spine = SplineIkFk.build(start="C_spine01_JNT", end="C_chest_JNT", pelvis="C_pelvis_JNT", mode="spine")
    assert spine.name == "spine"
    assert_no_pop(before)
    assert_no_constraints()
    for ctl in ("C_spineCog_CTL", "C_spineHips_CTL", "C_spineHipsIk_CTL", "C_spineChestIk_CTL", "C_spineFK1_CTL"):
        assert cmds.objExists(ctl), ctl
    # COG moves everything
    cmds.setAttr("C_spineCog_CTL.translateY", 10)
    for joint in ("C_pelvis_JNT",) + SPINE:
        assert_close(pos(joint), [before[joint][12], before[joint][13] + 10, before[joint][14]], joint, 0.01)
    cmds.setAttr("C_spineCog_CTL.translateY", 0)
    # hips rotate the pelvis without moving the spine
    cmds.setAttr("C_spineHips_CTL.rotateX", 30)
    assert not close(wm("C_pelvis_JNT")[:12], before["C_pelvis_JNT"][:12])
    assert_close(wm("C_chest_JNT"), before["C_chest_JNT"], "independent hips", 0.01)
    cmds.setAttr("C_spineHips_CTL.rotateX", 0)
    # the chest control moves the chest; stretch keeps or changes the length
    rest_length = mathlib.distance(pos("C_spine01_JNT"), pos("C_chest_JNT"))
    cmds.setAttr("C_spineChestIk_CTL.translateY", 10)
    assert mathlib.distance(pos("C_spine01_JNT"), pos("C_chest_JNT")) > rest_length + 5, "stretch"
    cmds.setAttr("C_spineCog_CTL.stretch", 0)
    length = sum(mathlib.distance(pos(a), pos(b)) for a, b in zip(SPINE, SPINE[1:]))
    rest = sum(mathlib.distance(before[a][12:15], before[b][12:15]) for a, b in zip(SPINE, SPINE[1:]))
    assert abs(length - rest) < rest * 0.08, (length, rest)
    cmds.setAttr("C_spineCog_CTL.stretch", 1)
    cmds.setAttr("C_spineChestIk_CTL.translateY", 0)
    # FK layer carries the IK controls
    cmds.setAttr("C_spineFK2_CTL.rotateZ", 25)
    assert not close(pos("C_chest_JNT"), before["C_chest_JNT"][12:15])
    from jeffy.setups.core import controls

    assert controls.role_of("C_spineChestIk_CTL") == "chest" and controls.role_of("C_spineCog_CTL") == "cog"


def test_spine_attaches_arms_and_volume():
    rig()
    FkChain.build(start="L_clavicle_JNT")
    IkFkLimb.build(name="arm", **ARM)
    SplineIkFk.build(start="C_spine01_JNT", end="C_chest_JNT", pelvis="C_pelvis_JNT")
    assert "chest" in attach.space_labels("L_armIK_CTL")
    shoulder = pos("L_shoulder_JNT")
    cmds.setAttr("C_spineChestIk_CTL.rotateZ", 20)
    assert not close(pos("L_shoulder_JNT"), shoulder), "the clavicle and arm follow the chest"
    cmds.setAttr("C_spineChestIk_CTL.rotateZ", 0)
    cmds.setAttr("C_spineChestIk_CTL.translateY", 15)
    assert min(cmds.getAttr("C_spine02_JNT.scale")[0]) < 0.99, "volume thins the spine"


def test_neck_head_spaces():
    before = rig(long_neck=True)
    SplineIkFk.build(start="C_neck01_JNT", end="C_neck03_JNT", head="C_head_JNT", mode="neck")
    assert_no_pop(before)
    assert attach.space_labels("C_neckHead_CTL")[0] == "neck"
    head = wm("C_head_JNT")
    cmds.setAttr("C_neckFK1_CTL.rotateZ", 20)
    assert not close(wm("C_head_JNT")[:12], head[:12]), "neck space: the head turns with the neck"
    cmds.setAttr("C_neckFK1_CTL.rotateZ", 0)
    attach.switch("C_neckHead_CTL", "world")
    cmds.setAttr("C_neckFK1_CTL.rotateZ", 20)
    assert_close(wm("C_head_JNT")[:12], head[:12], "world space: the head keeps its orientation", 0.01)


def test_tail_chain_switch_and_wave():
    before = rig(tail=True)
    SplineIkFk.build(start="C_tail01_JNT", end="C_tail06_JNT", mode="chain", name="tail", ik_controls=3)
    assert_no_pop(before)
    assert_no_constraints()
    tip = pos("C_tail06_JNT")
    cmds.setAttr("C_tailIK3_CTL.translateY", 10)
    assert not close(pos("C_tail06_JNT"), tip), "IK moves the tail"
    cmds.setAttr("C_tailSettings_CTL.ikFk", 0)
    assert_close(pos("C_tail06_JNT"), tip, "FK: back to the FK pose", 0.01)
    cmds.setAttr("C_tailSettings_CTL.waveAmplitude", 20)
    cmds.currentTime(1)
    first = pos("C_tail06_JNT")
    cmds.currentTime(12)
    assert not close(pos("C_tail06_JNT"), first), "the wave moves with time"
    cmds.setAttr("C_tailSettings_CTL.waveAmplitude", 0)
    assert_close(pos("C_tail06_JNT"), tip, "amplitude 0 stops the wave", 0.01)


def test_spline_delete_restores():
    skeleton.build_biped(tail=True, long_neck=True)
    before = skeleton.world_matrices()
    nodes_before = scene_nodes()
    base = RigBase.build(root_joint="C_root_JNT", name="hero")
    SplineIkFk.build(start="C_spine01_JNT", end="C_chest_JNT", pelvis="C_pelvis_JNT")
    SplineIkFk.build(start="C_neck01_JNT", end="C_neck03_JNT", head="C_head_JNT", mode="neck")
    SplineIkFk.build(start="C_tail01_JNT", end="C_tail06_JNT", mode="chain", name="tail")
    cmds.setAttr("C_spineChestIk_CTL.translateY", 5)
    base.delete()
    assert_no_pop(before)
    leftovers = sorted(scene_nodes() - nodes_before)
    assert not leftovers, leftovers


# ---------------------------------------------------------------------------
# Aim / Lids
# ---------------------------------------------------------------------------
def test_aim_eyes_and_fk_override():
    from jeffy.setups.tools.aim import Aim

    before = rig(face=True)
    aim = Aim.build(joints=["L_eye_JNT", "R_eye_JNT"])
    assert aim.name == "eyes" and aim.side == "C"
    assert_no_pop(before)
    assert_no_constraints()
    eye = wm("L_eye_JNT")
    cmds.setAttr("C_eyesTarget_CTL.translateX", 20)
    assert not close(wm("L_eye_JNT")[:12], eye[:12]), "the eyes look at the target"
    turned = wm("L_eye_JNT")
    cmds.setAttr("L_eyeFK_CTL.rotateY", 10)
    assert not close(wm("L_eye_JNT")[:12], turned[:12]), "FK override on top of the aim"
    cmds.setAttr("L_eyeFK_CTL.rotateY", 0)
    cmds.setAttr("L_eyeFK_CTL.aim", 0)
    assert_close(wm("L_eye_JNT"), eye, "aim 0: plain FK", 0.01)


def test_fleshy_lids():
    from jeffy.setups.tools.aim import Aim
    from jeffy.setups.tools.lids import FleshyLids

    before = rig(face=True)
    Aim.build(joints=["L_eye_JNT", "R_eye_JNT"])
    lids = FleshyLids.build(base="L_eyeFK_CTL", eye="L_eye_JNT",
                            upper=["L_upperLid_JNT", "L_upperLid01_JNT", "L_upperLid02_JNT", "L_upperLid03_JNT"],
                            lower=["L_lowerLid_JNT"])
    assert lids.mirror is not None, "mirrored to the right eye"
    assert_no_pop(before)
    upper = wm("L_upperLid_JNT")
    lower = wm("L_lowerLid_JNT")
    cmds.setAttr("C_eyesTarget_CTL.translateY", 15)  # look up
    assert not close(wm("L_upperLid_JNT")[:12], upper[:12]), "the upper lid follows the eye"
    cmds.setAttr("L_eyeLidsUpper_CTL.eyeFollow", 0)
    cmds.setAttr("L_eyeLidsLower_CTL.eyeFollow", 0)
    cmds.setAttr("L_eyeLidsUpper_CTL.sideFollow", 0)
    cmds.setAttr("L_eyeLidsLower_CTL.sideFollow", 0)
    assert_close(wm("L_upperLid_JNT"), upper, "eyeFollow 0", 0.01)
    assert_close(wm("L_lowerLid_JNT"), lower, "eyeFollow 0 (lower)", 0.01)
    cmds.setAttr("L_eyeLidsUpper_CTL.rotateX", 20)
    assert not close(wm("L_upperLid01_JNT")[12:15], before["L_upperLid01_JNT"][12:15]), "the lid control"


# ---------------------------------------------------------------------------
# Jaw
# ---------------------------------------------------------------------------
def test_jaw_chin_control():
    from jeffy.setups.tools.jaw import Jaw

    before = rig(face=True)
    Jaw.build(jaw="C_jaw_JNT", chin="C_chin_JNT")
    assert_no_pop(before)
    chin = before["C_chin_JNT"][12:15]
    cmds.setAttr("C_jawChin_CTL.translateY", -2)
    assert pos("C_chin_JNT")[1] < chin[1] - 0.5, "moving the chin control down opens the jaw"
    cmds.setAttr("C_jawChin_CTL.translateY", -100)
    open_max = pos("C_chin_JNT")
    cmds.setAttr("C_jawChin_CTL.translateY", -200)
    assert_close(pos("C_chin_JNT"), open_max, "open is clamped", 0.001)
    cmds.setAttr("C_jawChin_CTL.translateY", 0)
    cmds.setAttr("C_jawChin_CTL.translateX", 2)
    assert pos("C_chin_JNT")[0] > 0.5, "side"
    cmds.setAttr("C_jawChin_CTL.translateX", 0)
    cmds.setAttr("C_jawChin_CTL.translateZ", 1)
    assert pos("C_chin_JNT")[2] > chin[2] + 0.5, "forward"
    cmds.setAttr("C_jawChin_CTL.translateZ", 0)
    cmds.setAttr("C_jawChin_CTL.open", 10)
    assert pos("C_chin_JNT")[1] < chin[1] - 0.5, "open attribute"


# ---------------------------------------------------------------------------
# Hand
# ---------------------------------------------------------------------------
FINGERS = ["L_thumb01_JNT", "L_indexMeta_JNT", "L_middleMeta_JNT", "L_ringMeta_JNT", "L_pinkyMeta_JNT"]


def test_hand_poses_and_masters():
    from jeffy.setups.tools.hand import Hand

    before = rig(fingers=True)
    IkFkLimb.build(name="arm", **ARM)
    hand = Hand.build(wrist="L_wrist_JNT", fingers=FINGERS)
    assert hand.mirror is not None and cmds.objExists("R_hand_CTL")
    assert_no_pop(before)
    assert_no_constraints()
    for ctl in ("L_indexMaster_CTL", "L_indexMetaFK_CTL", "L_index01FK_CTL", "L_thumb01FK_CTL"):
        assert cmds.objExists(ctl), ctl
    assert not cmds.objExists("L_thumbMetaFK_CTL"), "auto: the thumb has no metacarpal"
    tip = pos("L_index04_JNT")
    cmds.setAttr("L_hand_CTL.curl", 5)
    assert pos("L_index04_JNT")[1] < tip[1] - 1, "curl bends the fingers toward the palm (down in T pose)"
    cmds.setAttr("L_hand_CTL.curl", 0)
    cmds.setAttr("L_hand_CTL.fist", 5)  # 10 is a full fist: the tips come back under the knuckles
    assert pos("L_pinky04_JNT")[1] < before["L_pinky04_JNT"][13] - 1, "fist"
    cmds.setAttr("L_hand_CTL.fist", 0)
    index_tip, pinky_tip = pos("L_index04_JNT"), pos("L_pinky04_JNT")
    cmds.setAttr("L_hand_CTL.spread", 10)
    spread = mathlib.distance(pos("L_index04_JNT"), pos("L_pinky04_JNT"))
    assert spread > mathlib.distance(index_tip, pinky_tip) + 0.5, "spread opens the fingers"
    cmds.setAttr("L_hand_CTL.spread", 0)
    cmds.setAttr("L_middleMaster_CTL.rotateZ", -40)
    assert not close(pos("L_middle04_JNT"), before["L_middle04_JNT"][12:15]), "master bends the finger"
    cmds.setAttr("L_middleMaster_CTL.rotateZ", 0)
    cmds.setAttr("L_hand_CTL.cup", 10)
    assert not close(pos("L_pinky01_JNT"), before["L_pinky01_JNT"][12:15]), "cup rolls the pinky metacarpal"
    cmds.setAttr("L_hand_CTL.cup", 0)
    # the hand follows the arm
    cmds.setAttr("L_armIK_CTL.translateY", -10)
    assert not close(pos("L_index01_JNT"), before["L_index01_JNT"][12:15])


def test_hand_ik_finger_contact():
    from jeffy.setups.tools.hand import Hand

    before = rig(fingers=True)
    IkFkLimb.build(name="arm", mirror=False, **ARM)
    Hand.build(wrist="L_wrist_JNT", fingers=FINGERS, ik=True, mirror=False)
    assert_no_pop(before)
    cmds.setAttr("L_hand_CTL.indexIk", 1)
    assert_no_pop(before)
    attach.switch("L_indexIK_CTL", "world")
    tip = pos("L_index03_JNT")
    cmds.setAttr("L_armIK_CTL.translateX", 1.5)  # push the hand toward the fingertip: the finger bends
    assert_close(pos("L_index03_JNT"), tip, "the IK fingertip stays on its contact point", 0.05)
    assert not close(pos("L_middle03_JNT"), before["L_middle03_JNT"][12:15]), "FK fingers follow the hand"


def test_stage3_delete_restores():
    skeleton.build_biped(face=True, fingers=True, long_neck=True, tail=True)
    before = skeleton.world_matrices()
    nodes_before = scene_nodes()
    from jeffy.setups.tools.aim import Aim
    from jeffy.setups.tools.hand import Hand
    from jeffy.setups.tools.jaw import Jaw
    from jeffy.setups.tools.lids import FleshyLids

    base = RigBase.build(root_joint="C_root_JNT", name="hero")
    SplineIkFk.build(start="C_spine01_JNT", end="C_chest_JNT", pelvis="C_pelvis_JNT")
    SplineIkFk.build(start="C_neck01_JNT", end="C_neck03_JNT", head="C_head_JNT", mode="neck")
    IkFkLimb.build(name="arm", **ARM)
    Hand.build(wrist="L_wrist_JNT", fingers=FINGERS, ik=True)
    Aim.build(joints=["L_eye_JNT", "R_eye_JNT"])
    FleshyLids.build(base="L_eyeFK_CTL", eye="L_eye_JNT", upper=["L_upperLid_JNT"], lower=["L_lowerLid_JNT"])
    Jaw.build(jaw="C_jaw_JNT")
    assert_no_pop(before)
    cmds.setAttr("C_jawChin_CTL.translateY", -1)
    base.delete()
    assert not scene.all_setups()
    assert_no_pop(before)
    leftovers = sorted(scene_nodes() - nodes_before)
    assert not leftovers, leftovers
