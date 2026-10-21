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
    # leg + toe handles; the ankle already follows the foot through the IK
    # tool's orient constraint, so no ankle -> ball handle fights it
    handles = cmds.ls(type="ikHandle")
    assert len(handles) == 2, handles
    assert cmds.listRelatives(ankle, children=True, type="orientConstraint")


def make_leg(cmds, side="L", x=2.0, prefix="", with_reverse=True):
    """hip > knee > ankle > ball > toe, plus a reverse chain heel > toe tip > ball > ankle."""
    names = ("hip", "knee", "ankle", "ball", "toe")
    offsets = ((x, 10.0, 0.0), (0.0, -5.0, 0.3), (0.0, -4.5, -0.3), (0.0, -0.4, 1.0), (0.0, 0.0, 1.0))
    joints = []
    parent = None
    for name, offset in zip(names, offsets):
        joint = cmds.createNode("joint", name="%s_%s%s_JNT" % (side, prefix, name), parent=parent)
        cmds.setAttr(joint + ".translate", *offset)
        joints.append(joint)
        parent = joint
    if not with_reverse:
        return joints, None
    group = cmds.createNode("transform", name="%s_Ctrl" % side)
    reverse = []
    parent = group
    for i, pos in enumerate(((x, 0.0, -0.5), (x, 0.0, 2.0), (x, 0.1, 1.0), (x, 0.5, 0.0))):
        joint = cmds.createNode("joint", name="%s_reversefoot%02d" % (side, i + 1), parent=parent)
        cmds.xform(joint, worldSpace=True, translation=pos)
        reverse.append(joint)
        parent = joint
    return joints, reverse


@pytest.mark.parametrize("mirror", [True, False])
def test_reverse_foot_from_chain(cmds, mirror):
    from jeffy.ui import actions

    legs = {}
    for side, x in (("L", 2.0), ("R", -2.0)):
        joints, reverse = make_leg(cmds, side, x)
        cmds.select(joints[0], joints[2])
        run(actions.build_ik)
        ik_ctl = [n for n in cmds.ls("%s_*IK_CTL" % side) if "Pole" not in n][0]
        legs[side] = (joints, reverse, ik_ctl)

    joints, reverse, ik_ctl = legs["L"]
    cmds.select(ik_ctl, reverse[0])
    run(actions.build_reverse_foot_from_chain, mirror)

    for side in ("L", "R") if mirror else ("L",):
        joints, reverse, ik_ctl = legs[side]
        assert cmds.attributeQuery("roll", node=ik_ctl, exists=True)
        # the chain hangs under the bank pivots, under the IK control
        inner = cmds.listRelatives(reverse[0], parent=True)[0]
        outer = cmds.listRelatives(cmds.listRelatives(inner, parent=True)[0], parent=True)[0]
        assert "Inner" in inner and "Outer" in outer
        assert cmds.listRelatives(cmds.listRelatives(outer, parent=True)[0], parent=True)[0] == ik_ctl
        # heel, toe tip and ball joints are rotated by the roll network
        for joint in reverse[:3]:
            assert driver(cmds, joint + ".rotate").endswith(".outputRotate"), joint
        # the leg IK target follows the reverse ankle, the toe handle the toe tap pivot
        assert [c for c in cmds.listRelatives(reverse[3], children=True) or [] if "End" in c]
        toe_handles = [h for h in cmds.ls(type="ikHandle") if "Toe" in h and h.startswith(side)]
        assert toe_handles and "ToeTap" in cmds.listRelatives(toe_handles[0], parent=True)[0]
    assert cmds.attributeQuery("roll", node=legs["R"][2], exists=True) == mirror
    assert_no_offset_parent_cycles(cmds)


def test_reverse_foot_finds_the_ik_ankle(cmds):
    from jeffy.rig import foot

    _bind, reverse = make_leg(cmds, "L", 2.0)
    ik_joints, _none = make_leg(cmds, "L", 2.0, prefix="IK", with_reverse=False)
    assert foot.find_foot_joints(reverse, 0.1) == (ik_joints[2], ik_joints[3], ik_joints[4])


def test_reverse_foot_ambiguous_ankle_raises(cmds):
    from jeffy.rig import foot

    _joints, reverse = make_leg(cmds, "L", 2.0)
    make_leg(cmds, "L", 2.0, prefix="FK", with_reverse=False)
    with pytest.raises(ValueError, match="Several ankle joints"):
        foot.find_foot_joints(reverse, 0.1)


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


def test_spline_ikfk(geometry):
    cmds = geometry
    from jeffy.ui import actions

    root = cmds.createNode("joint", name="C_hips_JNT")
    chain = make_chain(cmds, 6, name="spine", parent=root)
    cmds.select(chain[0], chain[-1])
    run(actions.build_spline_ikfk, 3)
    assert len(cmds.ls(type="ikHandle")) == 1

    settings = [n for n in cmds.ls("*Settings*_CTL") if cmds.attributeQuery("ikFk", node=n, exists=True)]
    assert len(settings) == 1

    # every curve point is driven; every IK control (middle too) owns tangents
    ik_controls = sorted(n for n in cmds.ls("*IK0*_CTL"))
    assert len(ik_controls) == 3, ik_controls
    curve = [c for c in cmds.ls(type="nurbsCurve") if "IK" not in c and "Guide" not in c]
    for index in range(7):
        assert any(driver(cmds, "%s.controlPoints[%d]" % (shape, index)) for shape in curve), index
    middle_tangents = cmds.listRelatives(ik_controls[1], allDescendents=True, type="transform") or []
    assert len([t for t in middle_tangents if t.endswith("_LOC")]) == 2, middle_tangents
    for ctl in ik_controls:
        assert cmds.attributeQuery("tangentLength", node=ctl, exists=True)

    # bind joints blend between the FK and IK chains; FK controls drive the FK chain
    for bind in chain:
        targets = constraint_targets(cmds, bind)
        assert len(targets) == 2 and "_FK" in targets[0] and "_IK" in targets[1], targets
        assert driver(cmds, bind + ".scale")
    fk_controls = cmds.ls("*FK*_CTL")
    assert len(fk_controls) == len(chain), fk_controls

    assert_no_offset_parent_cycles(cmds)


def assert_no_offset_parent_cycles(cmds, depth=6):
    """No node's offsetParentMatrix may be computed from its own parent matrices
    (Maya reports a cycle, e.g. ``Cycle on 'pelvisFK_BM.outputMatrix'``)."""
    for node in cmds.ls("*"):
        if not cmds.objExists(node + ".offsetParentMatrix"):
            continue
        frontier = [node + ".offsetParentMatrix"]
        for _level in range(depth):
            upstream = []
            for plug in frontier:
                target = plug if "." in plug and plug.split(".")[0] == node else plug.split(".")[0]
                upstream.extend(cmds.listConnections(target, source=True, destination=False, plugs=True) or [])
            for plug in upstream:
                owner, attr = plug.split(".", 1)
                assert not (owner == node and attr.startswith(("parentInverseMatrix", "parentMatrix"))), \
                    "%s.offsetParentMatrix depends on its own %s" % (node, attr)
            frontier = [p for p in upstream if p.split(".")[0] != node]


def test_cycle_checker_catches_own_parent_matrix(cmds):
    """The pattern behind ``Cycle on 'pelvisFK_BM.outputMatrix'``."""
    group = cmds.createNode("transform", name="grp")
    zero = cmds.createNode("transform", name="zero", parent=group)
    mm = cmds.createNode("multMatrix", name="mm")
    pick = cmds.createNode("pickMatrix", name="pm")
    cmds.connectAttr(zero + ".parentInverseMatrix[0]", mm + ".matrixIn[1]")
    cmds.connectAttr(mm + ".matrixSum", pick + ".inputMatrix")
    cmds.connectAttr(pick + ".outputMatrix", zero + ".offsetParentMatrix")
    with pytest.raises(AssertionError):
        assert_no_offset_parent_cycles(cmds)


def test_matrix_tools_have_no_offset_parent_cycles(cmds):
    from jeffy.rig import matrix_constraints, space_switch

    parent = cmds.createNode("transform", name="parent_GRP")
    driven = cmds.createNode("transform", name="driven", parent=parent)
    zero = cmds.createNode("transform", name="ctl_ZRO", parent=parent)
    ctl = cmds.createNode("transform", name="ctl_CTL", parent=zero)
    targets = [cmds.createNode("transform", name=n) for n in ("a_GRP", "b_GRP")]
    matrix_constraints.matrix_constraint(targets[0], driven)
    space_switch.create(ctl, [("a", targets[0]), ("b", targets[1])], driven=zero, method="matrix")
    assert_no_offset_parent_cycles(cmds)


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


@pytest.mark.parametrize("with_holder", [False, True])
def test_finger_ikfk(cmds, with_holder):
    from jeffy.ui import actions

    hand = cmds.createNode("joint", name="L_hand_JNT")
    holder = cmds.createNode("transform", name="L_hand_CTL") if with_holder else None
    chains = []
    for finger in ("index", "middle"):
        joints = make_chain(cmds, 4, name=finger, step=1.0, parent=hand)
        joints = [cmds.rename(j, j.replace("C_", "L_")) for j in joints]
        cmds.setAttr(joints[1] + ".jointOrient", 0.0, 0.0, -10.0)
        chains.append(joints)
    cmds.select([c[0] for c in chains] + ([holder] if holder else []))
    run(actions.build_finger_ikfk)

    assert len(cmds.ls(type="ikHandle")) == 2
    for joints in chains:
        for bind in joints:
            targets = constraint_targets(cmds, bind)
            assert len(targets) == 2 and "_FK" in targets[0] and "_IK" in targets[1], targets
        finger = "index" if "index" in joints[0] else "middle"
        ik_ctl = [n for n in cmds.ls("L_%sIK*_CTL" % finger)]
        assert ik_ctl, cmds.ls("*_CTL")
        assert cmds.attributeQuery("space", node=ik_ctl[0], exists=True)
        if holder:
            assert cmds.attributeQuery(finger + "IkFk", node=holder, exists=True)


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


@pytest.mark.parametrize("api, expected", [(20240000, "multDoubleLinear"), (20260000, "multDL")])
def test_renamed_node_types(cmds, monkeypatch, api, expected):
    from jeffy.core import nodes

    monkeypatch.setattr(cmds, "about", lambda apiVersion=False, **_k: api if apiVersion else str(api // 10000))
    assert nodes.node_type("multDoubleLinear") == expected
    assert nodes.node_type("multiplyDivide") == "multiplyDivide"
