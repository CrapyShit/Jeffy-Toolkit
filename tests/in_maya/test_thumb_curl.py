"""The thumb curls across the palm (its own plane), whatever its joint orientation."""

import skeleton
from maya import cmds
from test_setups_stage1 import pos

from jeffy.core import mathlib
from jeffy.setups.tools.hand import Hand
from jeffy.setups.tools.rig_base import RigBase

FINGERS = ["L_thumb01_JNT", "L_indexMeta_JNT", "L_middleMeta_JNT", "L_ringMeta_JNT", "L_pinkyMeta_JNT"]
THUMB = ["L_thumb01_JNT", "L_thumb02_JNT", "L_thumb03_JNT", "L_thumb04_JNT"]


def _hand(thumb_points=None, secondary="yup"):
    skeleton.build_biped(mirror=False, fingers=True)
    if thumb_points:  # a straight thumb pointing forward and down, like a hand at rest
        for joint in THUMB[1:]:
            cmds.parent(joint, world=True)
        for joint, point in zip(THUMB, thumb_points):
            cmds.xform(joint, worldSpace=True, translation=point)
        for parent, child in zip(THUMB, THUMB[1:]):
            cmds.parent(child, parent)
    cmds.joint(THUMB[0], edit=True, orientJoint="xyz", secondaryAxisOrient=secondary, children=True,
               zeroScaleOrient=True)
    RigBase.build(root_joint="C_root_JNT", name="hero")
    Hand.build(wrist="L_wrist_JNT", fingers=FINGERS, mirror=False)


def _palm_centre():
    bases = [pos(name) for name in ("L_index01_JNT", "L_middle01_JNT", "L_ring01_JNT", "L_pinky01_JNT")]
    return mathlib.midpoint(pos("L_wrist_JNT"), mathlib.centroid(bases)), max(point[1] for point in bases)


def _check(label):
    """A thumb curl brings the tip toward the palm's centre, never over the back of the hand."""
    length = sum(mathlib.distance(pos(a), pos(b)) for a, b in zip(THUMB, THUMB[1:]))
    centre, knuckles = _palm_centre()
    tip = pos(THUMB[-1])
    cmds.setAttr("L_hand_CTL.thumbCurl", 4)
    curled = pos(THUMB[-1])
    cmds.setAttr("L_hand_CTL.thumbCurl", 0)
    closer = mathlib.distance(tip, centre) - mathlib.distance(curled, centre)
    assert closer > length * 0.3, "%s: the thumb curls toward the palm (%.2f of %.2f)" % (label, closer, length)
    assert curled[1] < knuckles, "%s: the thumb stays on the palm side (tip at %.2f, knuckles at %.2f)" % (
        label, curled[1], knuckles)


def test_thumb_curls_across_the_palm():
    _hand()
    _check("skeleton thumb")


def test_straight_thumb_curls_across_the_palm_whatever_its_orientation():
    points = [(66, 144, 3), (67.5, 143, 5.5), (69, 142, 8), (70.5, 141, 10.5)]
    for secondary in ("yup", "zup", "ydown"):
        _hand(points, secondary)
        _check("straight thumb, %s" % secondary)
