"""Build the face tools in the scene-aware fake Maya and check the wiring."""

import pytest

from test_rig_builds import assert_no_offset_parent_cycles, cmds, constraint_targets, driver, run  # noqa: F401


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


# ---------------------------------------------------------------------------
# face ribbons, jaw, follows, lip seal, channel drivers
# ---------------------------------------------------------------------------
@pytest.fixture
def face_geo(face, monkeypatch):
    """``face`` plus polyline stand-ins for the ribbon surface helpers."""
    from jeffy.core import mathlib
    from jeffy.geometry import surfaces

    def points_of(node):
        shape = face._node(node)
        if shape.is_transform:
            shape = [c for c in shape.children if c.is_shape][0]
        return shape.data["points"]

    def ribbon_from_points(points, width=1.0, up_vector=(0.0, 0.0, 1.0), name="ribbon_SRF", spans=None,
                           degree=3, normal_axis=None):
        node = face.createNode("nurbsSurface", name=name + "Shape")
        face._node(node).data["points"] = [tuple(p) for p in points]
        return face.listRelatives(node, parent=True)[0]

    def point_at_uv(surface, u, v, normalized=True):
        pts = points_of(surface)
        return mathlib.lerp_vector(pts[0], pts[-1], u)

    monkeypatch.setattr(surfaces, "ribbon_from_points", ribbon_from_points)
    monkeypatch.setattr(surfaces, "point_at_uv", point_at_uv)
    return face


def lip_points(y):
    return [(-2.0 + i * 0.5, y, 3.0) for i in range(9)]


def test_face_ribbon(face_geo):
    from jeffy.rig.face import ribbon

    head = face_geo.createNode("joint", name="C_head_JNT")
    result = ribbon.build_face_ribbon(points=lip_points(0.2), name="upperLip", side="C", num_controls=5,
                                      control_parent=head)
    assert len(result["joints"]) == 9 and len(result["controls"]) == 5
    for ctl in result["controls"]:
        assert face_geo.listRelatives(ctl.zero, parent=True)[0] == result["main"].node
    assert face_geo.ls(type="skinCluster")
    assert ribbon.corner_controls(result["main"].node) == [result["controls"][0].node, result["controls"][-1].node]


def test_jaw_with_lip_follow(face_geo):
    from jeffy.rig.face import jaw, ribbon

    head = face_geo.createNode("joint", name="C_head_JNT")
    jaw_joint = face_geo.createNode("joint", name="C_jaw_JNT", parent=head)
    upper = ribbon.build_face_ribbon(points=lip_points(0.2), name="upperLip", side="C", control_parent=head)
    lower = ribbon.build_face_ribbon(points=lip_points(-0.2), name="lowerLip", side="C", control_parent=head)
    result = jaw.build_jaw(jaw_joint, upper_lip=upper["main"].node, lower_lip=lower["main"].node)
    ctl = result["control"].node
    assert constraint_targets(face_geo, jaw_joint) == [ctl]
    for attr in ("lowerLipFollow", "upperLipFollow", "cornerFollow"):
        assert face_geo.attributeQuery(attr, node=ctl, exists=True), attr
    assert face_geo.getAttr(ctl + ".lowerLipFollow") == 1.0
    # each lip main and each corner sits under a follow group blending head and jaw
    for node in (upper["main"].zero, lower["main"].zero, upper["controls"][0].zero, lower["controls"][-1].zero):
        group = face_geo.listRelatives(node, parent=True)[0]
        assert "Follow" in group, group
        assert constraint_targets(face_geo, group) == ["C_head_JNT", ctl]
    corner = upper["controls"][0].node
    assert driver(face_geo, corner + ".jawFollow") == ctl + ".cornerFollow"
    assert_no_offset_parent_cycles(face_geo)


@pytest.mark.parametrize("mode", ["parent", "orient", "point"])
def test_partial_follow(face, mode):
    from jeffy.ui import actions

    driver_node = face.createNode("transform", name="L_lipCorner_CTL")
    group = face.createNode("transform", name="head_GRP")
    cheek_zero = face.createNode("transform", name="L_cheek_ZRO", parent=group)
    cheek = face.createNode("transform", name="L_cheek_CTL", parent=cheek_zero)
    face.select(driver_node, cheek)
    run(actions.add_partial_follow, 0.3, mode)
    follow_group = face.listRelatives(cheek, parent=True)[0]
    assert "Follow" in follow_group
    kind = {"parent": "parentConstraint", "orient": "orientConstraint", "point": "pointConstraint"}[mode]
    assert face.listRelatives(follow_group, children=True, type=kind)
    assert face.getAttr(cheek + ".follow") == pytest.approx(0.3)


def test_fleshy_eyes_pivot_on_the_eye(face):
    from jeffy.ui import actions

    eye = face.createNode("joint", name="L_eye_JNT")
    face.setAttr(eye + ".translate", 3.0, 1.0, 2.0)
    lid = face.createNode("transform", name="L_upperLidMain_CTL")
    face.xform(lid, worldSpace=True, translation=(3.0, 1.5, 3.0))
    face.select(eye, lid)
    run(actions.add_fleshy_eyes, 0.25)
    group = face.listRelatives(lid, parent=True)[0]
    assert face.listRelatives(group, children=True, type="orientConstraint")
    assert face.getAttr(lid + ".eyeFollow") == pytest.approx(0.25)


def test_lip_seal_on_curve_rigs_and_not_on_ribbons(face_geo):
    from jeffy.rig.face import blink, curve_rig, ribbon

    upper = curve_rig.build_curve_rig(points=lip_points(0.2), name="upperLip", side="C", num_controls=5)
    lower = curve_rig.build_curve_rig(points=lip_points(-0.2), name="lowerLip", side="C", num_controls=5)
    result = blink.build_lip_seal(upper["main"].node, lower["main"].node, side="C")
    assert face_geo.attributeQuery("seal", node=upper["main"].node, exists=True)
    assert face_geo.getAttr(upper["main"].node + ".sealHeight") == pytest.approx(0.5)
    assert set(result["targets"]) == {"upper", "lower"}

    a = ribbon.build_face_ribbon(points=lip_points(1.0), name="browA", side="C")
    b = ribbon.build_face_ribbon(points=lip_points(1.5), name="browB", side="C")
    with pytest.raises(ValueError, match="face ribbon"):
        blink.build_lip_seal(a["main"].node, b["main"].node)


def test_connect_channel_to_target(face, monkeypatch):
    from jeffy.ui import actions

    mesh, node = make_blendshape(face, ["browUp", "browDown"])
    ctl = face.createNode("transform", name="L_brow_CTL")
    monkeypatch.setattr(actions, "_find_blendshape", lambda _node: node)
    face.select(ctl, mesh)
    run(actions.connect_channel_to_target, "translateY", 0.0, -1.0, "browDown")
    assert driver(face, node + ".weight[1]")
