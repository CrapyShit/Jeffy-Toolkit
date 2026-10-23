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


def build_biped(mirror=True, long_neck=False, tail=False, face=False, fingers=False):
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
    if long_neck:
        neck = joint("C_neck01_JNT", (0, 148, 0), chest)
        neck = joint("C_neck02_JNT", (0, 152, 0.5), neck)
        neck = joint("C_neck03_JNT", (0, 156, 1), neck)
    else:
        neck = joint("C_neck_JNT", (0, 150, 0), chest)
    head = joint("C_head_JNT", (0, 160, 1), neck)
    joint("C_headEnd_JNT", (0, 180, 1), head)
    if tail:
        previous = pelvis
        for index in range(6):
            previous = joint("C_tail%02d_JNT" % (index + 1), (0, 98 - index * 2, -6 - index * 7), previous)
    orient(pelvis, "zup")

    clavicle = joint("L_clavicle_JNT", (2, 145, 2), chest)
    shoulder = joint("L_shoulder_JNT", (15, 145, -1), clavicle)
    elbow = joint("L_elbow_JNT", (40, 144, -4), shoulder)
    wrist = joint("L_wrist_JNT", (64, 145, -1), elbow)
    joint("L_hand_JNT", (72, 145, -1), wrist)
    orient(clavicle, "yup")
    if fingers:
        add_fingers("L_wrist_JNT", "L")

    hip = joint("L_hip_JNT", (9, 97, 0), pelvis)
    knee = joint("L_knee_JNT", (9, 52, 3), hip)
    ankle = joint("L_ankle_JNT", (9, 9, -2), knee)
    ball = joint("L_ball_JNT", (9, 1, 10), ankle)
    joint("L_toe_JNT", (9, 1, 18), ball)
    orient(hip, "zup")

    if face:
        add_face()
    if mirror:
        for start in (clavicle, hip):
            cmds.mirrorJoint(start, mirrorYZ=True, mirrorBehavior=True, searchReplace=("L_", "R_"))
    return root


def world_matrices(joints=None):
    """``{joint: world matrix}`` of every joint (for pop checks)."""
    joints = joints or cmds.ls(type="joint")
    return dict((j, cmds.xform(j, query=True, worldSpace=True, matrix=True)) for j in joints)


def add_face(head="C_head_JNT"):
    """Eyes, lids and a jaw under the head (call after build_biped)."""
    for side, x in (("L", 3.0), ("R", -3.0)):
        eye = joint("%s_eye_JNT" % side, (x, 166, 8), head)
        joint("%s_eyeEnd_JNT" % side, (x, 166, 10), eye)
        joint("%s_upperLid_JNT" % side, (x, 166, 8), head)
        joint("%s_lowerLid_JNT" % side, (x, 166, 8), head)
        for index, offset in enumerate((-1.0, 0.0, 1.0)):
            joint("%s_upperLid%02d_JNT" % (side, index + 1), (x + offset, 167.2, 9.4), head)
    jaw = joint("C_jaw_JNT", (0, 162, 4), head)
    joint("C_chin_JNT", (0, 154, 11), jaw)
    cmds.joint(jaw, edit=True, orientJoint="xyz", secondaryAxisOrient="yup", children=True, zeroScaleOrient=True)


def add_fingers(wrist="L_wrist_JNT", side="L"):
    """Thumb (no metacarpal) and index / middle / ring / pinky with metacarpals."""
    sign = 1.0 if side == "L" else -1.0
    roots = []
    thumb = joint("%s_thumb01_JNT" % side, (sign * 66, 144, 3), wrist)
    roots.append(thumb)
    previous = thumb
    for index, point in enumerate(((68, 143.5, 5.5), (70.5, 143, 7), (73, 142.5, 8))):
        previous = joint("%s_thumb%02d_JNT" % (side, index + 2), (sign * point[0], point[1], point[2]), previous)
    for row, (name, z) in enumerate((("index", 2.5), ("middle", 0.5), ("ring", -1.5), ("pinky", -3.5))):
        meta = joint("%s_%sMeta_JNT" % (side, name), (sign * 66, 145, z * 0.5), wrist)
        roots.append(meta)
        previous = meta
        for index in range(4):
            previous = joint("%s_%s%02d_JNT" % (side, name, index + 1),
                             (sign * (74 + index * 3.0), 145 - index * 0.4 - row * 0.2, z), previous)
    for root in roots:
        cmds.joint(root, edit=True, orientJoint="xyz", secondaryAxisOrient="yup", children=True,
                   zeroScaleOrient=True)
    return roots
