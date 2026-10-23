"""Deleting or rebuilding a setup never deletes Maya's shared nodes (IK solvers), so other IK handles live on."""

import skeleton
from maya import cmds

from jeffy.setups.core import scene
from jeffy.setups.core import tag as tag_module
from jeffy.setups.core.base import SHARED_TYPES
from jeffy.setups.tools.ikfk_limb import IkFkLimb
from jeffy.setups.tools.rig_base import RigBase
from jeffy.setups.tools.spline import SplineIkFk


def test_rebuilding_the_first_ik_setup_keeps_other_ik_handles():
    skeleton.build_biped(mirror=False)
    RigBase.build(root_joint="C_root_JNT", name="hero")
    # the spine is the scene's first IK: Maya creates its shared IK solvers during this build
    spine = SplineIkFk.build(start="C_spine01_JNT", end="C_chest_JNT", pelvis="C_pelvis_JNT", mode="spine")
    owned = tag_module.get_nodes(spine.tag, "owned")
    assert not [node for node in owned if cmds.nodeType(node) in SHARED_TYPES], "solvers are never owned"
    IkFkLimb.build(name="arm", start="L_shoulder_JNT", mid="L_elbow_JNT", end="L_wrist_JNT", mirror=False)
    IkFkLimb.build(name="leg", start="L_hip_JNT", mid="L_knee_JNT", end="L_ankle_JNT", mirror=False)
    handles = sorted(cmds.ls(type="ikHandle"))
    assert len(handles) == 3, handles

    spine = scene.find_setup("C_spineCog_CTL").rebuild(options={"ik_controls": 4})
    assert sorted(cmds.ls(type="ikHandle")) == handles, "a rebuild keeps the other setups' IK handles"
    scene.find_setup("L_armIK_CTL").delete()
    assert len(cmds.ls(type="ikHandle")) == 2, cmds.ls(type="ikHandle")
    spine.delete()
    assert cmds.ls(type="ikHandle") == ["L_leg_IKH"], cmds.ls(type="ikHandle")
    # the leg's IK still works
    rest = cmds.xform("L_knee_JNT", query=True, worldSpace=True, translation=True)
    cmds.setAttr("L_legIK_CTL.translateY", 10)
    assert cmds.xform("L_knee_JNT", query=True, worldSpace=True, translation=True) != rest
