"""Build the face tools in the scene-aware fake Maya and check the wiring."""

import pytest

from test_rig_builds import assert_no_offset_parent_cycles, cmds, driver, run  # noqa: F401 - the cmds fixture


@pytest.fixture
def face(cmds, monkeypatch):  # noqa: F811
    """Stand-ins for the OpenMaya / text based helpers."""
    from jeffy.controls import shapes
    from jeffy.core import mathlib
    from jeffy.deformers import blendshape
    from jeffy.geometry import curves
    from jeffy.rig import attach

    def text_curves(text, name="text_CTL", font="Arial"):
        return cmds.createNode("transform", name=name)

    def positions_along(curve, count, by_length=True):
        shape = cmds._node(curve)
        shape = [c for c in shape.children if c.is_shape][0]
        points = shape.data["points"]
        return [mathlib.lerp_vector(points[0], points[-1], t) for t in mathlib.distribute(count, 0.0, 1.0)]

    monkeypatch.setattr(shapes, "text_curves", text_curves)
    monkeypatch.setattr(curves, "positions_along", positions_along)
    monkeypatch.setattr(attach, "closest_uv", lambda geo, position: (0.5, 0.5))
    real_uv_pin = attach.create_uv_pin

    def create_uv_pin(geo, coordinates, name="uvPin"):
        # the fake scene does not evaluate the pin: give it a rest matrix
        pin, outputs = real_uv_pin(geo, coordinates, name=name)
        for index in range(len(outputs)):
            cmds._node(pin).values["outputMatrix[%d]" % index] = mathlib.identity()
        return pin, outputs

    monkeypatch.setattr(attach, "create_uv_pin", create_uv_pin)
    monkeypatch.setattr(blendshape, "get_targets",
                        lambda bs: [(i, a) for i, a in enumerate(cmds._node(bs).data.get("aliases", []))])
    return cmds


def make_blendshape(cmds, aliases):  # noqa: F811
    base = cmds.createNode("transform", name="head_GEO")
    cmds.createNode("mesh", name="head_GEOShape", parent=base)
    node = cmds.createNode("blendShape", name="face_BSH")
    cmds._node(node).data["aliases"] = list(aliases)
    for index in range(len(aliases)):
        cmds.setAttr("%s.weight[%d]" % (node, index), 0.0)
    return base, node


def test_slider_outputs(face):
    from jeffy.rig.face import sliders

    result = sliders.create_slider("jaw", side="C", mode="square", size=1.0)
    ctl = result["control"].node
    assert set(result["outputs"]) == {"up", "down", "right", "left"}
    for plug in result["outputs"].values():
        assert driver(face, plug)
    assert face._node(ctl).data["limits"]["translationX"] == (-1.0, 1.0)

    one = sliders.create_slider("blink", side="L", mode="vertical", two_sided=False)
    assert set(one["outputs"]) == {"up"}
    assert face.getAttr(one["control"].node + ".tx", lock=True)


def test_pair_targets():
    from jeffy.rig.face import sliders

    pairs = sliders._pair_targets(["browUp", "smile", "browDown", "L_eye_dn", "L_eye_up"])
    assert pairs == [("brow", "browUp", "browDown"), ("smile", "smile", None),
                     ("L_eye", "L_eye_up", "L_eye_dn")]


def test_face_board_from_blendshape(face):
    from jeffy.ui import actions

    mesh, node = make_blendshape(face, ["browUp", "browDown", "smile", "pucker"])
    face.select(node)
    run(actions.face_board_from_blendshape)
    for index in range(4):
        assert driver(face, "%s.weight[%d]" % (node, index)), index
    assert len(face.ls("*Slider_GRP")) == 3


def test_surface_control_cancels_double_transform(face):
    from jeffy.rig.face import surface_controls

    mesh = face.createNode("transform", name="head_GEO")
    face.createNode("mesh", name="head_GEOShape", parent=mesh)
    result = surface_controls.build_surface_control(mesh, (1.0, 10.0, 2.0), name="cheek", side="L")
    ctl = result["control"]
    assert driver(face, ctl.last_offset + ".offsetParentMatrix").endswith(".inverseMatrix")
    assert driver(face, result["joint"] + ".offsetParentMatrix")
    assert driver(face, result["pin"] + ".offsetParentMatrix")
    assert face.xform(result["joint"], query=True, worldSpace=True, translation=True) == pytest.approx(
        [1.0, 10.0, 2.0])
    assert_no_offset_parent_cycles(face)


@pytest.mark.parametrize("with_center", [False, True])
def test_curve_rig_and_blink(face, with_center):
    from jeffy.rig.face import blink, curve_rig

    head = face.createNode("joint", name="C_head_JNT")
    eye = face.createNode("joint", name="L_eye_JNT", parent=head) if with_center else None
    if eye:
        face.setAttr(eye + ".translate", 3.0, 0.0, 2.0)
    upper_points = [(2.0 + i * 0.5, 0.5, 3.0) for i in range(7)]
    lower_points = [(2.0 + i * 0.5, -0.5, 3.0) for i in range(7)]
    upper = curve_rig.build_curve_rig(points=upper_points, name="upperLid", side="L", num_controls=5, center=eye,
                                      joint_parent=head)
    lower = curve_rig.build_curve_rig(points=lower_points, name="lowerLid", side="L", num_controls=5, center=eye,
                                      joint_parent=head)
    assert len(upper["joints"]) == 7 and len(upper["controls"]) == 5
    low_shape = face.listRelatives(upper["low"], shapes=True)[0]
    for i in range(5):
        assert driver(face, "%s.controlPoints[%d]" % (low_shape, i))
    for joint in upper["joints"]:
        if with_center:
            base = face.listRelatives(joint, parent=True)[0]
            assert face.listRelatives(base, children=True, type="aimConstraint")
        else:
            assert driver(face, joint + ".translate") or driver(face, joint + ".translateX")

    result = blink.build_blink(upper["main"].node, lower["main"].node, side="L")
    holder = upper["main"].node
    assert face.attributeQuery("blink", node=holder, exists=True)
    assert face.attributeQuery("blinkHeight", node=holder, exists=True)
    assert set(result["targets"]) == {"upper", "lower"}
    assert len(face.ls(type="blendShape")) == 3


def test_surface_controls_action_on_joints(face):
    from jeffy.ui import actions

    head = face.createNode("joint", name="C_head_JNT")
    joints = []
    for name, x in (("L_cheek_JNT", 2.0), ("R_cheek_JNT", -2.0)):
        joint = face.createNode("joint", name=name, parent=head)
        face.setAttr(joint + ".translate", x, 1.0, 2.0)
        joints.append(joint)
    mesh = face.createNode("transform", name="head_GEO")
    face.createNode("mesh", name="head_GEOShape", parent=mesh)
    face.select(joints + [mesh])
    run(actions.build_surface_controls)
    for joint in joints:
        assert driver(face, joint + ".offsetParentMatrix")
    assert face.ls("L_cheek_CTL") and face.ls("R_cheek_CTL"), face.ls("*_CTL")


def test_connect_slider_action(face, monkeypatch):
    from jeffy.rig.face import sliders
    from jeffy.ui import actions

    mesh, node = make_blendshape(face, ["smile", "frown"])
    slider = sliders.create_slider("mouth", side="C")
    monkeypatch.setattr(actions, "_find_blendshape", lambda _node: node)
    face.select(slider["control"].node, mesh)
    run(actions.connect_face_slider, "down", "frown")
    assert driver(face, node + ".weight[1]").endswith(".down")
