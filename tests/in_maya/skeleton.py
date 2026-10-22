"""Test skeletons for the headless Maya tests (real Maya only)."""

from maya import cmds


def joint(name, position, parent=None):
    node = cmds.createNode("joint", name=name, skipSelect=True)
    if parent:
        node = cmds.parent(node, parent)[0]
    cmds.xform(node, worldSpace=True, translation=position)
    return node


def orient(root, secondary="yup"):
    cmds.joint(root, edit=True, orientJoint="xyz", secondaryAxisOrient=secondary, children=True,
               zeroScaleOrient=True)


def build_biped(mirror=True):
    """A small biped in centimetres (root at the origin, X down every chain).

    ``C_root > C_pelvis > C_spine01 > C_spine02 > C_chest > C_neck > C_head``,
    ``L_clavicle > L_shoulder > L_elbow > L_wrist > L_hand`` under the chest,
    ``L_hip > L_knee > L_ankle > L_ball > L_toe`` under the pelvis, mirrored
    to ``R_``.
    """
    cmds.file(new=True, force=True)
    root = joint("C_root_JNT", (0, 0, 0))
    pelvis = joint("C_pelvis_JNT", (0, 100, 0), root)
    spine1 = joint("C_spine01_JNT", (0, 110, 0.5), pelvis)
    spine2 = joint("C_spine02_JNT", (0, 122, 1), spine1)
    chest = joint("C_chest_JNT", (0, 135, 0.5), spine2)
    neck = joint("C_neck_JNT", (0, 150, 0), chest)
    head = joint("C_head_JNT", (0, 160, 1), neck)
    joint("C_headEnd_JNT", (0, 180, 1), head)
    orient(pelvis, "zup")

    clavicle = joint("L_clavicle_JNT", (2, 145, 2), chest)
    shoulder = joint("L_shoulder_JNT", (15, 145, -1), clavicle)
    elbow = joint("L_elbow_JNT", (40, 144, -4), shoulder)
    wrist = joint("L_wrist_JNT", (64, 145, -1), elbow)
    joint("L_hand_JNT", (72, 145, -1), wrist)
    orient(clavicle, "yup")

    hip = joint("L_hip_JNT", (9, 97, 0), pelvis)
    knee = joint("L_knee_JNT", (9, 52, 3), hip)
    ankle = joint("L_ankle_JNT", (9, 9, -2), knee)
    ball = joint("L_ball_JNT", (9, 1, 10), ankle)
    joint("L_toe_JNT", (9, 1, 18), ball)
    orient(hip, "zup")

    if mirror:
        for start in (clavicle, hip):
            cmds.mirrorJoint(start, mirrorYZ=True, mirrorBehavior=True, searchReplace=("L_", "R_"))
    return root


def world_matrices(joints=None):
    """``{joint: world matrix}`` of every joint (for pop checks)."""
    joints = joints or cmds.ls(type="joint")
    return dict((j, cmds.xform(j, query=True, worldSpace=True, matrix=True)) for j in joints)
