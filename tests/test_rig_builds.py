"""Build rigs in a scene-aware fake Maya and check the wiring.

These tests run the real UI actions (without the error-swallowing tool
decorator) so a crash anywhere in a build fails the test with a traceback.
"""

import pytest

import fakemaya


@pytest.fixture
def cmds(monkeypatch):
    import importlib
    import pkgutil

    import jeffy
    import jeffy.ui.actions  # noqa: F401 - import every module before patching
    from jeffy import autorig, controls, core, deformers, geometry, joints, rig, utils  # noqa: F401

    for info in pkgutil.walk_packages(jeffy.__path__, "jeffy."):
        if ".ui." in info.name and not info.name.endswith("actions"):
            continue
        importlib.import_module(info.name)
    return fakemaya.install(monkeypatch)


def make_arm(cmds, names=("joint1", "joint2", "joint3"), parent=None, bend=10.0):
    """Shoulder > elbow > wrist, aiming down +X with a slight elbow bend."""
    joints = []
    current = parent
    for i, name in enumerate(names):
        joint = cmds.createNode("joint", name=name, parent=current)
        if i == 0:
            cmds.setAttr(joint + ".translate", 0.0, 10.0, 0.0)
        else:
            cmds.setAttr(joint + ".translate", 5.0, 0.0, 0.0)
        if i == 1:
            cmds.setAttr(joint + ".jointOrient", 0.0, bend, 0.0)
        joints.append(joint)
        current = joint
    return joints


def run(action, *args, **kwargs):
    """Call a @tool action without its try/except wrapper."""
    return action.__wrapped__(*args, **kwargs)


def driver(cmds, plug):
    return fakemaya.driver_of(cmds, plug)


def constraint_targets(cmds, node, kind="parentConstraint"):
    constraints = [c for c in (cmds.listRelatives(node, children=True, type=kind) or [])]
    assert constraints, "%s has no %s" % (node, kind)
    return cmds.parentConstraint(constraints[0], query=True, targetList=True)


@pytest.mark.parametrize("with_parent", [False, True])
def test_ikfk_limb_from_selection(cmds, with_parent):
    from jeffy.ui import actions

    parent = cmds.createNode("joint", name="clavicle") if with_parent else None
    arm = make_arm(cmds, parent=parent)
    cmds.select(arm[0])
    run(actions.build_ikfk)

    # bind joints (the selection) blend between the FK and IK chains
    for bind in arm:
        targets = constraint_targets(cmds, bind)
        assert len(targets) == 2, targets
        assert "_FK" in targets[0] and "_IK" in targets[1], targets
        assert driver(cmds, bind + ".scale"), "%s scale not blended" % bind

    settings = [n for n in cmds.ls("*Settings*_CTL") if cmds.attributeQuery("ikFk", node=n, exists=True)]
    assert len(settings) == 1

    # the IK chain is solved by a handle that follows the IK control
    handles = cmds.ls(type="ikHandle")
    assert len(handles) == 1
    handle = handles[0]
    fk_root, ik_root = constraint_targets(cmds, arm[0])
    # the IK root must be free to rotate (only the solver drives it)
    for axis in "XYZ":
        assert driver(cmds, "%s.rotate%s" % (ik_root, axis)) is None, "IK root rotation is driven"
    point = cmds.listRelatives(handle, children=True, type="pointConstraint")
    assert point, "the IK handle does not follow anything"
    # FK root rotation comes from its control only
    fk_cons = cmds.listRelatives(fk_root, children=True, type="parentConstraint")
    assert len(fk_cons) == 1
    assert len(cmds.parentConstraint(fk_cons[0], query=True, targetList=True)) == 1
    # with a parent joint the duplicated chains follow it
    if with_parent:
        follow = cmds.listRelatives(ik_root, parent=True)[0]
        assert constraint_targets(cmds, follow) == ["clavicle"]


def test_ikfk_limb_rest_pose_values(cmds):
    """At the rest pose the stretch / soft IK network must not move anything."""
    from jeffy.ui import actions

    arm = make_arm(cmds)
    cmds.select(arm[0])
    run(actions.build_ikfk)
    _fk_root, ik_root = constraint_targets(cmds, arm[0])
    ik_joints = [ik_root] + cmds.listRelatives(ik_root, allDescendents=True, type="joint")[::-1]
    ik_joints = [j for j in ik_joints if "_IK" in j]
    assert len(ik_joints) == 3
    for joint in ik_joints[1:]:
        assert driver(cmds, joint + ".translateX"), "%s length is not driven by the stretch network" % joint
        value = fakemaya.evaluate(cmds, joint + ".translateX")
        assert value == pytest.approx(5.0, abs=1e-3), "%s length %s instead of 5" % (joint, value)

    # the IK handle target (soft locator) sits exactly at the IK end
    handle = cmds.ls(type="ikHandle")[0]
    point = cmds.listRelatives(handle, children=True, type="pointConstraint")[0]
    soft_loc = cmds.pointConstraint(point, query=True, targetList=True)[0]
    distance = fakemaya.evaluate(cmds, soft_loc + ".translateX")
    root = cmds.xform(ik_joints[0], query=True, worldSpace=True, translation=True)
    end = cmds.xform(ik_joints[-1], query=True, worldSpace=True, translation=True)
    from jeffy.core import mathlib

    assert distance == pytest.approx(mathlib.distance(root, end), abs=1e-3)

    # switch weights: FK by default, IK when ikFk = 1
    constraint = cmds.listRelatives(arm[1], children=True, type="parentConstraint")[0]
    weights = cmds.parentConstraint(constraint, query=True, weightAliasList=True)
    assert fakemaya.evaluate(cmds, "%s.%s" % (constraint, weights[0])) == 1.0
    assert fakemaya.evaluate(cmds, "%s.%s" % (constraint, weights[1])) == 0.0


# ---------------------------------------------------------------------------
# Every rigging button from the window
# ---------------------------------------------------------------------------
def make_chain(cmds, count=5, name="tail", step=3.0, parent=None):
    joints = []
    current = parent
    for i in range(count):
        joint = cmds.createNode("joint", name="C_%s%02d_JNT" % (name, i + 1), parent=current)
        cmds.setAttr(joint + ".translate", *((0.0, 5.0, 0.0) if i == 0 else (step, 0.0, 0.0)))
        joints.append(joint)
        current = joint
    return joints


def test_fk_chain(cmds):
    from jeffy.ui import actions

    root = cmds.createNode("joint", name="C_hips_JNT")
    chain = make_chain(cmds, 3, parent=root)
    cmds.select(chain[0])
    run(actions.build_fk)
    for joint in chain:
        assert cmds.listRelatives(joint, children=True, type="parentConstraint"), joint
    ctl = cmds.listRelatives(chain[0], children=True, type="parentConstraint")
    zero = [n for n in cmds.ls("*tail01*ZRO*")][0]
    follow = cmds.listRelatives(zero, parent=True)[0]
    assert constraint_targets(cmds, follow) == ["C_hips_JNT"]
    assert ctl


def test_ik_chain_and_reverse_foot(cmds):
    from jeffy.ui import actions

    hip = cmds.createNode("joint", name="L_hip_JNT")
    cmds.setAttr(hip + ".translate", 2.0, 10.0, 0.0)
    knee = cmds.createNode("joint", name="L_knee_JNT", parent=hip)
    cmds.setAttr(knee + ".translate", 0.0, -5.0, 0.3)
    ankle = cmds.createNode("joint", name="L_ankle_JNT", parent=knee)
    cmds.setAttr(ankle + ".translate", 0.0, -4.5, -0.3)
    ball = cmds.createNode("joint", name="L_ball_JNT", parent=ankle)
    cmds.setAttr(ball + ".translate", 0.0, -0.4, 1.0)
    toe = cmds.createNode("joint", name="L_toe_JNT", parent=ball)
    cmds.setAttr(toe + ".translate", 0.0, 0.0, 1.0)
    cmds.select(hip, ankle)
    run(actions.build_ik)
    handle = cmds.ls(type="ikHandle")[0]
    assert cmds.listRelatives(handle, children=True, type="pointConstraint")
    ik_ctl = [n for n in cmds.ls("*IK_CTL") if "Pole" not in n][0]
    locators = []
    for name, pos in (("heel", (2, 0, -0.5)), ("inner", (1.5, 0, 1)), ("outer", (2.5, 0, 1))):
        loc = cmds.spaceLocator(name=name + "_LOC")[0]
        cmds.xform(loc, worldSpace=True, translation=pos)
        locators.append(loc)
    cmds.select([ik_ctl, ankle, ball, toe] + locators)
    run(actions.build_reverse_foot)
    assert len(cmds.ls(type="ikHandle")) == 3


@pytest.fixture
def geometry(cmds, monkeypatch):
    """Pure Python stand-ins for the OpenMaya based curve/surface sampling.

    Curves and ribbon surfaces are treated as polylines through their points,
    which is all the builds need to place controls and follicles.
    """
    from jeffy.core import mathlib
    from jeffy.geometry import curves, surfaces

    def points_of(node):
        shape = cmds._node(node)
        if shape.is_transform:
            shape = [c for c in shape.children if c.is_shape][0]
        return shape.data["points"]

    def along(points, t):
        lengths = [mathlib.distance(a, b) for a, b in zip(points, points[1:])]
        target = sum(lengths) * t
        for (a, b), length in zip(zip(points, points[1:]), lengths):
            if target <= length or length == lengths[-1]:
                return mathlib.lerp_vector(a, b, min(1.0, target / length if length else 0.0))
            target -= length
        return points[-1]

    def positions_along(curve, count, start=0.0, end=1.0):
        return [along(points_of(curve), t) for t in mathlib.distribute(count, start, end)]

    def ribbon_from_points(points, width=1.0, up_vector=(0.0, 0.0, 1.0), name="ribbon_SRF", spans=None,
                           degree=3, normal_axis=None):
        node = cmds.createNode("nurbsSurface", name=name + "Shape")
        cmds._node(node).data["points"] = [tuple(p) for p in points]
        return cmds.listRelatives(node, parent=True)[0]

    monkeypatch.setattr(curves, "positions_along", positions_along)
    monkeypatch.setattr(surfaces, "ribbon_from_points", ribbon_from_points)
    monkeypatch.setattr(surfaces, "point_at_uv", lambda surface, u, v, normalized=True: along(points_of(surface), u))
    return cmds


def test_spline_ik(geometry):
    cmds = geometry
    from jeffy.ui import actions

    root = cmds.createNode("joint", name="C_hips_JNT")
    chain = make_chain(cmds, 6, name="spine", parent=root)
    cmds.select(chain[0], chain[-1])
    run(actions.build_spline)
    assert cmds.ls(type="ikHandle")
    assert driver(cmds, chain[2] + ".translateX")


@pytest.mark.parametrize("per_joint", [True, False])
def test_hybrid_spline(geometry, per_joint):
    cmds = geometry
    from jeffy.ui import actions

    root = cmds.createNode("joint", name="C_hips_JNT")
    chain = make_chain(cmds, 6, name="spine", parent=root)
    cmds.select(chain[0], chain[-1])
    run(actions.build_hybrid_spline, 3, True, True, 1.0, per_joint)
    assert len(cmds.ls(type="ikHandle")) == 1

    ik_controls = sorted(cmds.ls("*splineIK0*_CTL") or cmds.ls("*IK0*_CTL"))
    assert len(ik_controls) == 3, ik_controls
    settings = ik_controls[-1]
    assert cmds.attributeQuery("ikBlend", node=settings, exists=True)
    assert cmds.attributeQuery("ik01", node=settings, exists=True) == per_joint

    # every curve point is driven, controls rotate their tangent points
    curve = [c for c in cmds.ls(type="nurbsCurve") if "IK" not in c and "Guide" not in c]
    for index in range(7):
        assert any(driver(cmds, "%s.controlPoints[%d]" % (shape, index)) for shape in curve), index
    for ctl in ik_controls:
        assert cmds.attributeQuery("tangentLength", node=ctl, exists=True)

    # each bind joint follows its own FK control, FK controls follow the IK chain
    fk_controls = []
    for joint in chain:
        targets = constraint_targets(cmds, joint)
        assert len(targets) == 1 and targets[0].endswith("FK_CTL"), targets
        fk_controls.append(targets[0])
        zero = cmds.listRelatives(cmds.listRelatives(targets[0], parent=True)[0], parent=True)[0]
        assert driver(cmds, zero + ".offsetParentMatrix"), zero
        assert driver(cmds, joint + ".scale")
    # FK controls are a hierarchy, so rotating one moves everything below
    for parent_ctl, child_ctl in zip(fk_controls, fk_controls[1:]):
        assert child_ctl in (cmds.listRelatives(parent_ctl, allDescendents=True) or [])
    # the middle IK control twists the FK layer
    assert any(driver(cmds, cmds.listRelatives(cmds.listRelatives(c, parent=True)[0], parent=True)[0]
                      + ".rotateX") for c in fk_controls[1:])


def test_ribbon(geometry):
    cmds = geometry
    from jeffy.ui import actions

    chain = make_chain(cmds, 2, name="upArm", step=10.0)
    cmds.select(chain[0], chain[1])
    run(actions.build_ribbon)
    controls = cmds.ls("*Bend*_CTL")
    assert len(controls) == 3
    zeros = [cmds.listRelatives(c, parent=True)[0] for c in controls]
    groups = [cmds.listRelatives(z, parent=True)[0] if "OFF" in z else z for z in zeros]
    assert any(cmds.listRelatives(g, children=True, type="parentConstraint") for g in groups)


def test_twist_joints(cmds):
    from jeffy.ui import actions

    arm = make_arm(cmds, names=("L_upper_JNT", "L_lower_JNT", "L_hand_JNT"))
    cmds.select(arm[1], arm[2])
    run(actions.build_twist)
    twist = cmds.ls("*Twist*_JNT")
    assert len(twist) == 3
    for joint in twist:
        assert driver(cmds, joint + ".rotateX")


def test_space_switch_both_methods(cmds):
    from jeffy.controls.control import Control
    from jeffy.ui import actions

    for method in ("constraint", "matrix"):
        ctl = Control.create("hand" + method, side="L", offsets=("zero", "space"))
        a = cmds.createNode("transform", name="chest" + method)
        b = cmds.createNode("transform", name="world" + method)
        cmds.select(ctl.node, a, b)
        run(actions.add_space_switch, method=method)
        assert cmds.attributeQuery("space", node=ctl.node, exists=True)


def test_eye_rig_and_fingers(cmds):
    from jeffy.ui import actions

    head = cmds.createNode("joint", name="C_head_JNT")
    eyes = []
    for side, x in (("L", 1.0), ("R", -1.0)):
        eye = cmds.createNode("joint", name="%s_eye_JNT" % side, parent=head)
        cmds.setAttr(eye + ".translate", x, 1.0, 1.0)
        eyes.append(eye)
    cmds.select(eyes)
    run(actions.build_eye_rig)
    for eye in eyes:
        assert cmds.listRelatives(eye, children=True, type="aimConstraint")

    hand = cmds.createNode("joint", name="L_hand_JNT")
    roots = []
    for finger in ("index", "middle"):
        joints = make_chain(cmds, 4, name=finger, step=1.0, parent=hand)
        joints = [cmds.rename(j, j.replace("C_", "L_")) for j in joints]
        roots.append(joints[0])
    cmds.select(roots)
    run(actions.build_fingers)
    assert cmds.ls("L_index01_CTL") and cmds.ls("L_middle03_CTL"), cmds.ls("*_CTL")


def test_dynamic_chain_drives_selection(cmds):
    from jeffy.ui import actions

    root = cmds.createNode("joint", name="C_hips_JNT")
    chain = make_chain(cmds, 5, parent=root)
    cmds.select(chain[0])
    run(actions.create_dynamic_chain)
    for joint in chain:
        targets = constraint_targets(cmds, joint)
        assert "_DRV" in targets[0] and "_DYN" in targets[1], targets


def test_pose_reader_matrix_constraint_attach(cmds):
    from jeffy.ui import actions

    arm = make_arm(cmds, names=("L_upper_JNT", "L_lower_JNT", "L_hand_JNT"))
    cmds.select(arm[1])
    run(actions.create_pose_reader)
    assert cmds.ls("*reader_LOC")
    a = cmds.createNode("transform", name="driver_GRP")
    b = cmds.createNode("transform", name="driven_GRP")
    cmds.select(a, b)
    run(actions.matrix_constraint)
    assert driver(cmds, b + ".offsetParentMatrix")


def test_rig_structure(cmds):
    from jeffy.ui import actions

    run(actions.create_rig_structure)
    assert cmds.ls("C_global_CTL")


def _templates():
    from jeffy.autorig import templates

    return templates.list_templates()


@pytest.mark.parametrize("template", _templates())
def test_autorig_templates_build(geometry, template):
    from jeffy.autorig import builder, templates

    cmds = geometry
    templates.create(template)
    structure = builder.build("hero")
    assert structure.global_ctl
    # every skin joint is driven: constraint, IK solver or direct connection
    skin_set = [n for n in cmds.nodes if n.type == "objectSet" and "skinJoints" in n.name][0]
    joints = skin_set.data["members"]
    assert joints
    undriven = []
    for joint in joints:
        node = cmds._node(joint)
        constrained = any(c.type in fakemaya.CONSTRAINT_TYPES for c in node.children)
        connected = any(driver(cmds, "%s.%s%s" % (joint, attr, axis))
                        for attr in ("translate", "rotate") for axis in "XYZ")
        if not (constrained or connected or node.data.get("ik_solved_by")):
            undriven.append(joint)
    assert not undriven, "skin joints driven by nothing: %s" % undriven


def test_failed_tool_undoes_its_partial_build(cmds):
    from jeffy.core.decorators import ToolError, tool

    @tool("Crashing Tool")
    def crashing():
        cmds.createNode("transform", name="half_built_GRP")
        raise RuntimeError("boom")

    @tool("Bad Selection")
    def bad_selection():
        raise ToolError("Select joints")

    cmds.undo_stack.append("user work")
    bad_selection()
    assert cmds.undo_stack == ["user work"]  # nothing undone for user errors
    crashing()
    assert "undo: Crashing Tool" in cmds.log
    assert cmds.undo_stack == ["user work"]
    assert any("partial build was undone" in line for line in cmds.log)
