"""Stage 1 of the Setup Belt in real Maya: Rig Base, FK Chain, IK/FK Limb, Spaces.

Run with ``mayapy tests/in_maya/run.py``.
"""

import skeleton
from maya import cmds

from jeffy.core import mathlib
from jeffy.setups.core import attach, scene
from jeffy.setups.tools.fk_chain import FkChain
from jeffy.setups.tools.ikfk_limb import IkFkLimb, snap_fk_to_ik, snap_ik_to_fk
from jeffy.setups.tools.rig_base import RigBase
from jeffy.setups.tools.spaces import Spaces

TOL = 1e-3
ARM = {"start": "L_shoulder_JNT", "mid": "L_elbow_JNT", "end": "L_wrist_JNT"}
LEG = {"start": "L_hip_JNT", "mid": "L_knee_JNT", "end": "L_ankle_JNT"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def pos(node):
    return cmds.xform(node, query=True, worldSpace=True, translation=True)


def wm(node):
    return cmds.xform(node, query=True, worldSpace=True, matrix=True)


def close(a, b, tol=TOL):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def assert_close(a, b, what, tol=TOL):
    assert close(a, b, tol), "%s: %s != %s" % (what, [round(v, 4) for v in a], [round(v, 4) for v in b])


def assert_no_pop(before, tol=TOL):
    for joint, matrix in before.items():
        assert_close(wm(joint), matrix, "%s moved" % joint, tol)


#: Maya creates these default nodes the first time an IK handle exists (not ours)
MAYA_DEFAULTS = {"ikRPsolver", "ikSCsolver", "ikSplineSolver", "hikSolver"}


def scene_nodes():
    return set(cmds.ls()) - MAYA_DEFAULTS


def assert_no_constraints():
    found = cmds.ls(type="constraint")
    assert not found, "constraint nodes found: %s" % found


def base():
    skeleton.build_biped()
    return RigBase.build(root_joint="C_root_JNT", name="hero")


def arm(**options):
    values = dict(ARM)
    values.update(options)
    return IkFkLimb.build(name="arm", **values)


# ---------------------------------------------------------------------------
# Rig Base
# ---------------------------------------------------------------------------
def test_rig_base_build_scale_and_delete():
    skeleton.build_biped()
    before = skeleton.world_matrices()
    nodes_before = scene_nodes()
    rig = RigBase.build(root_joint="C_root_JNT", name="hero")
    assert_no_pop(before)
    assert_no_constraints()
    assert cmds.objExists("hero_RIG")
    assert cmds.listRelatives("C_root_JNT", parent=True) == ["hero_skeleton_GRP"]
    assert scene.find_setup("C_global_CTL") == rig
    assert scene.find_setup("C_root_JNT") == rig

    cmds.setAttr("C_global_CTL.globalScale", 2.0)
    assert_close(pos("L_wrist_JNT"), [v * 2 for v in before["L_wrist_JNT"][12:15]], "global scale")
    cmds.setAttr("C_global_CTL.globalScale", 1.0)
    cmds.setAttr("C_root_CTL.translateX", 10)
    assert_close(pos("C_pelvis_JNT"), [10, 100, 0], "root moves the skeleton")

    rig.delete()
    assert not cmds.listRelatives("C_root_JNT", parent=True)
    assert_no_pop(before)
    leftovers = sorted(scene_nodes() - nodes_before)
    assert not leftovers, "left after delete: %s" % leftovers


def test_build_without_rig_base_fails():
    skeleton.build_biped()
    try:
        FkChain.build(start="L_clavicle_JNT")
    except Exception as error:  # SetupError
        assert "Rig Base" in str(error)
    else:
        raise AssertionError("building without a Rig Base should fail")


# ---------------------------------------------------------------------------
# FK Chain
# ---------------------------------------------------------------------------
def test_fk_chain_clavicle_mirror():
    base()
    before = skeleton.world_matrices()
    setup = FkChain.build(start="L_clavicle_JNT")
    assert_no_pop(before)
    assert_no_constraints()
    assert setup.mirror is not None and setup.mirror.side == "R"
    assert cmds.objExists("L_clavicleFK_CTL") and cmds.objExists("R_clavicleFK_CTL")

    cmds.setAttr("L_clavicleFK_CTL.rotateZ", 30)
    assert_close(wm("L_clavicle_JNT")[:12], [v for v in wm("L_clavicleFK_CTL")[:12]], "joint follows control")
    assert not close(pos("L_shoulder_JNT"), before["L_shoulder_JNT"][12:15])


def test_fk_chain_master_and_stretch():
    base()
    before = skeleton.world_matrices()
    FkChain.build(start="C_neck_JNT", end="C_head_JNT", name="neck", master=True, stretch=True, game_safe=True)
    assert_no_pop(before)
    rest = pos("C_head_JNT")
    cmds.setAttr("C_neckMaster_CTL.rotateZ", 20)
    assert not close(pos("C_head_JNT"), rest), "master bends the chain"
    cmds.setAttr("C_neckMaster_CTL.rotateZ", 0)
    cmds.setAttr("C_neckFK_CTL.length", 2.0)
    assert mathlib.distance(pos("C_neck_JNT"), pos("C_head_JNT")) > 15, "length stretches"
    assert close(cmds.getAttr("C_neck_JNT.scale")[0], (1, 1, 1)), "game safe: no scale"


# ---------------------------------------------------------------------------
# IK/FK Limb
# ---------------------------------------------------------------------------
def test_ikfk_arm_no_pop_ik_fk():
    base()
    before = skeleton.world_matrices()
    limb = arm()
    assert_no_pop(before)
    assert_no_constraints()
    assert limb.mirror is not None
    assert cmds.getAttr("L_armSettings_CTL.ikFk") == 1.0
    # IK within reach: the wrist follows the IK control
    cmds.setAttr("L_armIK_CTL.translate", -6, -10, 5)
    assert_close(pos("L_wrist_JNT"), pos("L_armIK_CTL"), "wrist on the IK control")
    # FK: the shoulder joint takes the FK control's rotation
    cmds.setAttr("L_armSettings_CTL.ikFk", 0)
    cmds.setAttr("L_shoulderFK_CTL.rotateY", 25)
    assert_close(wm("L_shoulder_JNT")[:12], wm("L_shoulderFK_CTL")[:12], "FK drives the shoulder")


def test_ikfk_stretch_soft_pin():
    base()
    arm()
    shoulder = pos("L_shoulder_JNT")
    chain = mathlib.distance(shoulder, pos("L_elbow_JNT")) + mathlib.distance(pos("L_elbow_JNT"), pos("L_wrist_JNT"))
    cmds.setAttr("L_armIK_CTL.translateX", 30)
    target = pos("L_armIK_CTL")
    reach = mathlib.distance(shoulder, pos("L_wrist_JNT"))
    assert abs(reach - chain) < 0.05, "no stretch: the arm stops at its length (%s vs %s)" % (reach, chain)
    cmds.setAttr("L_armIK_CTL.stretch", 1)
    assert_close(pos("L_wrist_JNT"), target, "stretch reaches the control", 0.01)
    assert cmds.getAttr("L_shoulder_JNT.scaleX") > 1.1, "film mode: the bind joint scales along the bone"
    cmds.setAttr("L_armIK_CTL.stretch", 0)
    cmds.setAttr("L_armIK_CTL.translateX", 0)
    cmds.setAttr("L_armIK_CTL.softness", 0.5)
    rest_reach = mathlib.distance(shoulder, pos("L_wrist_JNT"))
    assert rest_reach < chain, "soft IK"
    cmds.setAttr("L_armIK_CTL.softness", 0)
    cmds.setAttr("L_armIK_CTL.pin", 1)
    assert_close(pos("L_elbow_JNT"), pos("L_armPole_CTL"), "pin puts the elbow on the pole", 0.01)


def test_ikfk_game_safe_translate_only():
    base()
    arm(game_safe=True)
    cmds.setAttr("L_armIK_CTL.translateX", 30)
    cmds.setAttr("L_armIK_CTL.stretch", 1)
    assert_close(pos("L_wrist_JNT"), pos("L_armIK_CTL"), "stretch reaches the control", 0.01)
    for joint in ARM.values():
        assert close(cmds.getAttr(joint + ".scale")[0], (1, 1, 1)), "%s scaled in game safe mode" % joint


def test_ikfk_snap_both_ways():
    base()
    arm()
    cmds.setAttr("L_armIK_CTL.translate", -8, -12, 9)
    cmds.setAttr("L_armIK_CTL.rotate", 10, 30, -20)
    cmds.setAttr("L_armPole_CTL.translateY", 15)
    ik_pose = dict((j, wm(j)) for j in ARM.values())
    snap_fk_to_ik("L_armIK_CTL")
    assert cmds.getAttr("L_armSettings_CTL.ikFk") == 0.0
    for joint, matrix in ik_pose.items():
        assert_close(wm(joint), matrix, "FK snapped on IK (%s)" % joint, 0.01)
    cmds.setAttr("L_elbowFK_CTL.rotateZ", -20)
    fk_pose = dict((j, wm(j)) for j in ARM.values())
    snap_ik_to_fk("L_armSettings_CTL")
    assert cmds.getAttr("L_armSettings_CTL.ikFk") == 1.0
    # a 2 bone IK has no upper arm roll of its own: positions, the bone directions and the whole wrist match
    for joint, matrix in fk_pose.items():
        assert_close(pos(joint), matrix[12:15], "IK snapped on FK (%s position)" % joint, 0.01)
    assert_close(wm("L_wrist_JNT"), fk_pose["L_wrist_JNT"], "IK snapped on FK (wrist)", 0.01)


def test_ikfk_no_flip_leg():
    base()
    before = skeleton.world_matrices()
    IkFkLimb.build(name="leg", knee="no-flip", **LEG)
    assert_no_pop(before)
    assert not cmds.objExists("L_legPole_CTL")
    knee = pos("L_knee_JNT")
    cmds.setAttr("L_legIK_CTL.rotateY", 40)
    moved = pos("L_knee_JNT")
    assert not close(knee, moved), "the knee follows the foot"
    cmds.setAttr("L_legIK_CTL.rotateY", 0)
    cmds.setAttr("L_legIK_CTL.kneeTwist", 30)
    assert not close(knee, pos("L_knee_JNT")), "kneeTwist aims the knee"


def test_attach_order_and_global_scale():
    base()
    wrist = pos("L_wrist_JNT")
    arm()  # built before the clavicle: attaches to the root for now
    FkChain.build(start="L_clavicle_JNT")  # the arm re-attaches to the clavicle
    rest = pos("L_shoulder_JNT")
    cmds.setAttr("L_armSettings_CTL.ikFk", 0)
    cmds.setAttr("L_clavicleFK_CTL.rotateZ", 25)
    moved = pos("L_shoulder_JNT")
    assert not close(rest, moved), "the arm follows the clavicle"
    assert_close(pos("L_shoulderFK_CTL"), moved, "FK controls follow the clavicle")
    cmds.setAttr("L_clavicleFK_CTL.rotateZ", 0)
    cmds.setAttr("C_global_CTL.globalScale", 2.0)
    assert_close(pos("L_wrist_JNT"), [v * 2 for v in wrist], "global scale (FK)")
    cmds.setAttr("L_armSettings_CTL.ikFk", 1)
    assert_close(pos("L_wrist_JNT"), [v * 2 for v in wrist], "global scale (IK)")


# ---------------------------------------------------------------------------
# Spaces / rebuild / delete
# ---------------------------------------------------------------------------
def test_default_spaces_and_seamless_switch():
    base()
    FkChain.build(start="L_clavicle_JNT")
    arm()
    labels = attach.space_labels("L_armIK_CTL")
    assert labels[:2] == ["root", "world"] and "parent" in labels, labels
    cmds.setAttr("C_root_CTL.translateX", 20)
    before = wm("L_armIK_CTL")
    attach.switch("L_armIK_CTL", "world")
    assert_close(wm("L_armIK_CTL"), before, "seamless switch")
    cmds.setAttr("C_root_CTL.translateX", 0)
    assert_close(wm("L_armIK_CTL"), before, "world space ignores the root")
    assert attach.space_labels("L_shoulderFK_CTL")[0] == "parent"


def test_spaces_layer_rebuild_and_delete():
    base()
    FkChain.build(start="L_clavicle_JNT")
    limb = arm()
    Spaces.build(control="L_armIK_CTL", targets=["C_global_CTL", "L_clavicleFK_CTL"], labels="world,clav")
    assert attach.space_labels("L_armIK_CTL") == ["world", "clav"]
    assert attach.space_labels("R_armIK_CTL") == ["world", "clav"], "mirrored layer"
    new = limb.rebuild(options={"pin": False})
    assert not cmds.attributeQuery("pin", node="L_armIK_CTL", exists=True)
    assert attach.space_labels("L_armIK_CTL") == ["world", "clav"], "layer rebuilt"
    assert new.mirror is not None
    spaces = [s for s in scene.all_setups() if s.TYPE == "spaces" and s.side == "L"][0]
    spaces.delete()
    assert attach.space_labels("L_armIK_CTL")[0] == "root", "defaults are back"


def test_delete_everything_restores_skeleton():
    skeleton.build_biped()
    before = skeleton.world_matrices()
    nodes_before = scene_nodes()
    rig = RigBase.build(root_joint="C_root_JNT", name="hero")
    FkChain.build(start="L_clavicle_JNT")
    arm()
    IkFkLimb.build(name="leg", knee="no-flip", **LEG)
    Spaces.build(control="L_armIK_CTL", targets=["C_global_CTL"])
    cmds.setAttr("L_armIK_CTL.translateY", -20)
    rig.delete()
    assert not scene.all_setups()
    assert_no_pop(before)
    leftovers = sorted(scene_nodes() - nodes_before)
    assert not leftovers, "left after delete: %s" % leftovers


def test_guides_preview_build_and_rebuild():
    base()
    from jeffy.setups.core import guides

    found = IkFkLimb.preview(ARM, {}, name="arm")
    assert set(found) == {"pole", "settings"}
    pole_guide = found["pole"]
    moved = [40.0, 120.0, -60.0]
    cmds.xform(pole_guide, worldSpace=True, translation=moved)
    limb = IkFkLimb.create(ARM, {"mirror": False}, name="arm")
    assert not guides.find("ikfk_limb", "arm", "L"), "guides are deleted after the build"
    pole = pos("L_armPole_CTL")
    assert abs(pole[1] - 145) > 15, "the pole uses the moved guide (%s)" % pole
    limb = limb.rebuild(options={"stretch": False})
    assert_close(pos("L_armPole_CTL"), pole, "rebuild keeps the guide")


def test_undo_build_and_delete():
    cmds.undoInfo(state=True, infinity=True)
    skeleton.build_biped()
    before = skeleton.world_matrices()
    nodes_before = scene_nodes()
    from jeffy.core import decorators

    with decorators.undo_chunk("build"):
        RigBase.build(root_joint="C_root_JNT", name="hero")
    with decorators.undo_chunk("build arm"):
        arm()
    cmds.setAttr("L_armIK_CTL.translateY", -15)
    cmds.undo()  # the move
    cmds.undo()  # the arm
    assert not cmds.objExists("L_armIK_CTL") and not cmds.objExists("R_armIK_CTL")
    assert_no_pop(before)
    cmds.undo()  # the rig base
    assert not scene.all_setups()
    assert_no_pop(before)
    leftovers = sorted(scene_nodes() - nodes_before)
    assert not leftovers, "left after undo: %s" % leftovers
    cmds.redo()
    cmds.redo()
    assert cmds.objExists("L_armIK_CTL")
    cmds.undoInfo(state=False)


def test_spaces_orient_mode_custom_attribute():
    base()
    FkChain.build(start="L_clavicle_JNT", mirror=False)
    IkFkLimb.build(name="arm", mirror=False, **ARM)
    Spaces.build(control="L_shoulderFK_CTL", targets=["L_clavicleFK_CTL", "C_global_CTL"], mode="orient",
                 attr="follow", labels="clavicle,world", mirror=False)
    assert attach.space_labels("L_shoulderFK_CTL") == ["clavicle", "world"]
    assert cmds.attributeQuery("follow", node="L_shoulderFK_CTL", exists=True)
    assert not cmds.attributeQuery("space", node="L_shoulderFK_CTL", exists=True)
    cmds.setAttr("L_armSettings_CTL.ikFk", 0)
    attach.switch("L_shoulderFK_CTL", "world")
    rotation = wm("L_shoulderFK_CTL")[:12]
    cmds.setAttr("L_clavicleFK_CTL.rotateZ", 30)
    assert_close(wm("L_shoulderFK_CTL")[:12], rotation, "orient space: rotation stays in world")
    assert_close(pos("L_shoulderFK_CTL"), pos("L_shoulder_JNT"), "orient space: position follows the clavicle")
    layer =[s for s in scene.all_setups() if s.TYPE == "spaces"][0]
    layer.delete()
    assert cmds.attributeQuery("space", node="L_shoulderFK_CTL", exists=True), "default enum is back"
    assert not cmds.attributeQuery("follow", node="L_shoulderFK_CTL", exists=True)


def test_right_side_arm_works():
    base()
    arm()
    cmds.setAttr("R_armIK_CTL.translate", 6, -10, 5)
    assert_close(pos("R_wrist_JNT"), pos("R_armIK_CTL"), "right wrist on its IK control")
    snap_fk_to_ik("R_armIK_CTL")
    assert_close(pos("R_wrist_JNT"), pos("R_armIK_CTL"), "right FK snapped on IK")


def test_rebuild_rig_base_keeps_setups():
    base()
    FkChain.build(start="L_clavicle_JNT")
    arm()
    Spaces.build(control="L_armIK_CTL", targets=["C_global_CTL", "C_root_CTL"], labels="world,root")
    rig = scene.rigs()[0]
    new = rig.rebuild(options={"size": 2.0})
    types = sorted(s.TYPE + ":" + (s.side or "") for s in scene.all_setups())
    assert types == sorted(["rig_base:C", "fk_chain:L", "fk_chain:R", "ikfk_limb:L", "ikfk_limb:R",
                            "spaces:L", "spaces:R"]), types
    assert new.option("size") == 2.0
    assert attach.space_labels("L_armIK_CTL") == ["world", "root"]


def test_belt_panels_in_maya():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from jeffy.ui.qt import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["belt"])
    from jeffy.ui.setup_belt import common, window

    common.confirm = lambda *_args: True  # no dialogs in tests
    skeleton.build_biped()
    before = skeleton.world_matrices()
    belt = window.SetupBeltWindow()
    rig_panel = belt.panels["rig_base"]
    rig_panel.slot_fields["root_joint"].set_value("C_root_JNT")
    rig_panel.name_edit.setText("hero")
    rig_panel.build()
    assert scene.rigs(), rig_panel.status.text()
    limb = belt.panels["ikfk_limb"]
    limb.fill_from(limb.slot_fields["start"], ["L_shoulder_JNT", "L_elbow_JNT", "L_wrist_JNT"])
    limb.name_edit.setText("arm")
    limb.set_options({"knee": "pole", "mirror": True})
    limb.build()
    assert cmds.objExists("L_armIK_CTL") and cmds.objExists("R_armIK_CTL"), limb.status.text()
    assert_no_pop(before)
    # edit -> rebuild with an option changed
    belt.edit_setup(scene.find_setup("L_armIK_CTL"))
    assert limb.build_button.text() == "Rebuild"
    limb.set_options({"knee": "no-flip"})
    limb.build()
    assert not cmds.objExists("L_armPole_CTL") and not cmds.objExists("R_armPole_CTL"), limb.status.text()
    assert cmds.attributeQuery("kneeTwist", node="L_armIK_CTL", exists=True)
    # setups list
    belt.refresh_setups()
    assert belt.setups_panel.tree.topLevelItemCount() == 1
    limb.delete()
    assert not cmds.objExists("L_armIK_CTL") and not cmds.objExists("R_armIK_CTL")
    assert_no_pop(before)
    belt.close()
    del app


def test_any_joint_orientation():
    """Y down the bone, Z up, rotations left unfrozen: the setups must not care."""
    skeleton.build_biped(mirror=False)
    cmds.joint("L_clavicle_JNT", edit=True, orientJoint="yzx", secondaryAxisOrient="zup", children=True,
               zeroScaleOrient=True)
    cmds.setAttr("L_elbow_JNT.rotate", 5, -12, 20)  # not frozen into the joint orient
    cmds.setAttr("L_wrist_JNT.rotateX", 30)
    before = skeleton.world_matrices()
    RigBase.build(root_joint="C_root_JNT", name="hero")
    FkChain.build(start="L_clavicle_JNT", mirror=False)
    IkFkLimb.build(name="arm", mirror=False, **ARM)
    assert_no_pop(before)
    cmds.setAttr("L_armIK_CTL.translate", -6, -10, 5)
    assert_close(pos("L_wrist_JNT"), pos("L_armIK_CTL"), "wrist on the IK control")
    cmds.setAttr("L_armIK_CTL.pin", 1)
    assert_close(pos("L_elbow_JNT"), pos("L_armPole_CTL"), "pin", 0.01)
    cmds.setAttr("L_armIK_CTL.pin", 0)
    ik_pose = dict((j, wm(j)) for j in ARM.values())
    snap_fk_to_ik("L_armIK_CTL")
    for joint, matrix in ik_pose.items():
        assert_close(wm(joint), matrix, "FK snapped on IK (%s)" % joint, 0.01)
