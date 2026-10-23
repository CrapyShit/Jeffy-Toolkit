"""Edge Ribbon in real Maya: blendShape follow, no double transformation, jaw follow, master, rebuild, game safe."""

import skeleton
from maya import cmds
from test_setups_stage1 import assert_close, assert_no_constraints, assert_no_pop, pos

from jeffy.setups.core import scene
from jeffy.setups.tools.edge_ribbon import EdgeRibbon
from jeffy.setups.tools.jaw import Jaw
from jeffy.setups.tools.rig_base import RigBase

MOUTH = (0.0, 158.0, 11.0)
LIFT = 0.5


def rig():
    skeleton.build_biped(mirror=False, face=True)
    before = skeleton.world_matrices()
    RigBase.build(root_joint="C_root_JNT", name="hero")
    Jaw.build(jaw="C_jaw_JNT", chin="C_chin_JNT")
    return before


def mouth_mesh(name="face_GEO", blend=True, skin=True):
    """A tube facing forward: its middle edge ring is a round 'lip' loop (radius 3)."""
    mesh = cmds.polyCylinder(name=name, radius=3, height=1, subdivisionsAxis=16, subdivisionsHeight=2,
                             axis=(0, 0, 1), constructionHistory=False)[0]
    cmds.xform(mesh, translation=MOUTH)
    loop = ring_edges(mesh, MOUTH[2])
    if blend:
        target = cmds.duplicate(mesh, name=name + "Smile")[0]
        for vertex in ring_vertices(target, MOUTH[2]):
            if cmds.pointPosition(vertex, world=True)[1] > MOUTH[1] + 0.1:
                cmds.move(0, LIFT, 0, vertex, relative=True, worldSpace=True)
        cmds.blendShape(target, mesh, name=name + "_BS")
        cmds.delete(target)
    if skin:
        cmds.skinCluster("C_head_JNT", "C_jaw_JNT", mesh, toSelectedBones=True, name=name + "_SKN")
        cmds.skinPercent(name + "_SKN", mesh + ".vtx[*]", transformValue=[("C_head_JNT", 1.0)])
    return mesh, loop


def ring_vertices(mesh, z):
    return [v for v in cmds.ls(mesh + ".vtx[*]", flatten=True) if abs(cmds.pointPosition(v, world=True)[2] - z) < 1e-3]


def ring_edges(mesh, z):
    result = []
    for edge in cmds.ls(mesh + ".e[*]", flatten=True):
        vertices = cmds.ls(cmds.polyListComponentConversion(edge, toVertex=True), flatten=True)
        if all(abs(cmds.pointPosition(v, world=True)[2] - z) < 1e-3 for v in vertices):
            result.append(edge)
    return result


def top_vertex(mesh):
    return max(ring_vertices(mesh, MOUTH[2]), key=lambda v: cmds.pointPosition(v, world=True)[1])


def skin_ring_to(setup, mesh):
    """Add the bind joints to the mesh's skin, each ring vertex fully on its nearest bind joint."""
    skin = mesh + "_SKN"
    joints = setup.bind_joints()
    for joint in joints:
        cmds.skinCluster(skin, edit=True, addInfluence=joint, weight=0.0)
    for vertex in ring_vertices(mesh, MOUTH[2]):
        point = cmds.pointPosition(vertex, world=True)
        nearest = min(joints, key=lambda j: sum((a - b) ** 2 for a, b in zip(pos(j), point)))
        cmds.skinPercent(skin, vertex, transformValue=[(nearest, 1.0)], zeroRemainingInfluences=True)
    return skin


def test_edge_ribbon_follows_blendshape_without_double_transform():
    before = rig()
    mesh, loop = mouth_mesh()
    lips = EdgeRibbon.build(base="C_jawChin_CTL", edges=loop)
    assert lips.name == "lips" and lips.side == "C", (lips.name, lips.side)
    assert_no_constraints()
    assert_no_pop(before)
    names = sorted(scene.short(c) for c in lips.controls.values())
    for expected in ("C_lipsUpper_CTL", "C_lipsLower_CTL", "L_lipsCorner_CTL", "R_lipsCorner_CTL",
                     "L_lipsUpper_CTL", "C_lipsMaster_CTL"):
        assert expected in names, (expected, names)
    assert len(lips.bind_joints()) == 20

    # the controls follow the blendShape, their channels stay at 0
    upper = "C_lipsUpper_CTL"
    rest = pos(upper)
    cmds.setAttr(mesh + "_BS.w[0]", 1)
    assert_close(pos(upper), (rest[0], rest[1] + LIFT, rest[2]), "the upper lip control follows the blendShape", 0.05)
    assert cmds.getAttr(upper + ".translateY") == 0
    cmds.setAttr(mesh + "_BS.w[0]", 0)

    # skin, connect, then the blendShape moves the lips once
    skin_ring_to(lips, mesh)
    assert lips.connect_skin() == 20
    top = top_vertex(mesh)
    top_rest = cmds.pointPosition(top, world=True)
    cmds.setAttr(mesh + "_BS.w[0]", 1)
    assert_close(cmds.pointPosition(top, world=True), (top_rest[0], top_rest[1] + LIFT, top_rest[2]),
                 "no double transformation", 0.02)
    # and the control still moves the lip on top
    cmds.setAttr(upper + ".translateY", 1)
    moved = cmds.pointPosition(top, world=True)[1]
    assert moved > top_rest[1] + LIFT + 0.7, ("the control moves the lip on top", moved - top_rest[1])
    cmds.setAttr(upper + ".translateY", 0)
    # the whole rig moves: the lips come along, still moved once by the blendShape
    root = lips.rig.controls["root"]
    cmds.setAttr(root + ".translateX", 10)
    assert_close(cmds.pointPosition(top, world=True), (top_rest[0] + 10, top_rest[1] + LIFT, top_rest[2]),
                 "the lips follow the rig", 0.02)
    cmds.setAttr(root + ".translateX", 0)


def test_edge_ribbon_jaw_follow_and_master():
    rig()
    _mesh, loop = mouth_mesh()
    lips = EdgeRibbon.build(base="C_jawChin_CTL", edges=loop)
    upper, lower, corner = "C_lipsUpper_CTL", "C_lipsLower_CTL", "L_lipsCorner_CTL"
    assert cmds.getAttr(upper + ".jawFollow") == 0.0
    assert cmds.getAttr(lower + ".jawFollow") == 1.0
    assert cmds.getAttr(corner + ".jawFollow") == 0.5
    rests = dict((node, pos(node)) for node in (upper, lower, corner))
    cmds.setAttr("C_jawChin_CTL.translateY", -2)
    assert_close(pos(upper), rests[upper], "jawFollow 0: the upper lip stays")
    drop_lower = rests[lower][1] - pos(lower)[1]
    drop_corner = rests[corner][1] - pos(corner)[1]
    assert drop_lower > 0.3, ("the lower lip follows the jaw", drop_lower)
    assert 0.0 < drop_corner < drop_lower, ("corners follow half way", drop_corner, drop_lower)
    cmds.setAttr("C_jawChin_CTL.translateY", 0)

    # the master moves every control
    cmds.setAttr("C_lipsMaster_CTL.translateX", 1)
    for node in (upper, lower, corner):
        assert_close(pos(node), (rests[node][0] + 1, rests[node][1], rests[node][2]), "master moves " + node)
    cmds.setAttr("C_lipsMaster_CTL.translateX", 0)
    # its outline follows the blendShape
    shape = cmds.listRelatives("C_lipsMaster_CTL", shapes=True)[0]
    tops = lambda: max(p[1] for p in cmds.getAttr(shape + ".cv[*]"))  # noqa: E731
    before = tops()
    cmds.setAttr("face_GEO_BS.w[0]", 1)
    assert tops() > before + LIFT * 0.5, ("the outline follows the lips", tops() - before)
    assert lips.TYPE == "edge_ribbon"


def test_edge_ribbon_rebuild_keeps_weights_and_delete_restores():
    rig()
    mesh, loop = mouth_mesh()
    rest_points = [cmds.pointPosition(v, world=True) for v in cmds.ls(mesh + ".vtx[*]", flatten=True)]
    lips = EdgeRibbon.build(base="C_jawChin_CTL", edges=loop)
    skin = skin_ring_to(lips, mesh)
    lips.connect_skin()
    top = top_vertex(mesh)
    weights_before = cmds.skinPercent(skin, top, query=True, value=True, ignoreBelow=1e-6)
    lips = lips.rebuild(options={"joint_count": 20, "width": 0.4})
    joint_influences = [j for j in cmds.skinCluster(skin, query=True, influence=True) if "lips" in j]
    assert len(joint_influences) == 20, joint_influences
    assert cmds.skinPercent(skin, top, query=True, value=True, ignoreBelow=1e-6) == weights_before
    connected = cmds.listConnections(skin + ".bindPreMatrix", source=True, destination=False) or []
    assert len(connected) == 20, "bindPreMatrix wired again after the rebuild"
    top_rest = cmds.pointPosition(top, world=True)
    cmds.setAttr(mesh + "_BS.w[0]", 1)
    assert_close(cmds.pointPosition(top, world=True), (top_rest[0], top_rest[1] + LIFT, top_rest[2]),
                 "still no double transform", 0.02)
    cmds.setAttr(mesh + "_BS.w[0]", 0)

    lips.delete()
    assert not [j for j in cmds.skinCluster(skin, query=True, influence=True) if "lips" in j]
    after = [cmds.pointPosition(v, world=True) for v in cmds.ls(mesh + ".vtx[*]", flatten=True)]
    for a, b in zip(rest_points, after):
        assert_close(a, b, "the mesh is back as it was")
    assert cmds.objExists(mesh + "_BS"), "the user's blendShape stays"


def test_edge_ribbon_creates_blendshape_and_removes_it():
    rig()
    mesh, loop = mouth_mesh(blend=False, skin=False)
    lips = EdgeRibbon.build(base="C_jawChin_CTL", edges=loop, master=False)
    created = cmds.ls(cmds.listHistory(mesh), type="blendShape")
    assert created, "an empty blendShape was added"
    assert "C_lipsMaster_CTL" not in [scene.short(c) for c in lips.controls.values()]
    lips.delete()
    assert not cmds.ls(cmds.listHistory(mesh), type="blendShape"), "the empty blendShape is removed again"
    assert not cmds.ls("*lips*", type="transform")


def test_edge_ribbon_game_safe_offsets():
    rig()
    mesh, loop = mouth_mesh()
    lips = EdgeRibbon.build(base="C_jawChin_CTL", edges=loop, game_safe=True, master=False)
    for joint in lips.bind_joints():
        assert cmds.listRelatives(joint, parent=True)[0] == "C_head_JNT", joint
    skin_ring_to(lips, mesh)
    assert lips.connect_skin() == 0
    assert not cmds.listConnections(mesh + "_SKN.bindPreMatrix", source=True, destination=False)
    top = top_vertex(mesh)
    top_rest = cmds.pointPosition(top, world=True)
    joint_rest = dict((j, pos(j)) for j in lips.bind_joints())
    cmds.setAttr(mesh + "_BS.w[0]", 1)
    assert_close(cmds.pointPosition(top, world=True), (top_rest[0], top_rest[1] + LIFT, top_rest[2]),
                 "game safe: no double transform", 0.02)
    for joint, value in joint_rest.items():
        assert_close(pos(joint), value, "game safe joints stay at rest without control motion", 0.01)
    cmds.setAttr("C_lipsUpper_CTL.translateY", 1)
    assert cmds.pointPosition(top, world=True)[1] > top_rest[1] + LIFT + 0.7


def test_edge_ribbon_open_chain_mirrors():
    rig()
    plane = cmds.polyPlane(name="brow_GEO", width=12, height=4, subdivisionsX=12, subdivisionsY=4, axis=(0, 0, 1),
                           constructionHistory=False)[0]
    cmds.xform(plane, translation=(0, 170, 10))
    chain = []
    for edge in cmds.ls(plane + ".e[*]", flatten=True):
        points = [cmds.pointPosition(v, world=True) for v in
                  cmds.ls(cmds.polyListComponentConversion(edge, toVertex=True), flatten=True)]
        if all(abs(p[1] - 170) < 1e-3 and 1.5 < p[0] < 5.5 for p in points):
            chain.append(edge)
    brow = EdgeRibbon.build(base="C_jawChin_CTL", edges=chain, name="brow", control_count=3, joint_count=5)
    assert brow.side == "L"
    other = brow.mirror
    assert other is not None and other.side == "R"
    assert cmds.objExists("R_brow01_CTL") and cmds.objExists("L_brow01_CTL")
    assert_close(pos("R_brow01_CTL"), (-pos("L_brow01_CTL")[0],) + tuple(pos("L_brow01_CTL")[1:]),
                 "mirrored control")
    assert all(name.startswith("R_") for name in (scene.short(j) for j in other.bind_joints()))
