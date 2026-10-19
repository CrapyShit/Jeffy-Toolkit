# ruff: noqa: F811 - pytest fixtures imported from test_rig_builds
"""Flexible rig (antCGi course) builders checked against the course setups.

These tests build each setup in the scene-aware fake Maya and assert the same wiring,
node operations and behaviour (networks are evaluated numerically).
"""

import pytest

import fakemaya
from test_rig_builds import cmds, driver, geometry, make_arm, run  # noqa: F401


def _targets(cmds, node, kind):
    cons = cmds.listRelatives(node, children=True, type=kind) or []
    assert cons, "%s has no %s" % (node, kind)
    return getattr(cmds, kind)(cons[0], query=True, targetList=True), cons[0]


def _weights(cmds, constraint, kind):
    aliases = getattr(cmds, kind)(constraint, query=True, weightAliasList=True)
    return [driver(cmds, "%s.%s" % (constraint, a)) for a in aliases]


def make_leg(cmds, prefix="L_"):
    names = ["thigh", "knee", "ankle", "ball", "toe"]
    offsets = [(10.0, 50.0, 0.0), (0.0, -22.0, 1.0), (0.0, -22.0, -1.0), (0.0, -3.0, 5.0), (0.0, 0.0, 4.0)]
    joints, parent = [], None
    for name, offset in zip(names, offsets):
        joint = cmds.createNode("joint", name=prefix + name + "_JNT", parent=parent)
        cmds.setAttr(joint + ".translate", *offset)
        joints.append(joint)
        parent = joint
    return joints


# ---------------------------------------------------------------------------
def test_structure(cmds):
    from jeffy.rig.flexible import structure

    result = structure.create("Robot", 10)
    top, master = result["top"], result["master"].node
    for key in ("skeleton", "models", "deformers"):
        assert cmds.listRelatives(result[key], parent=True)[0] == top
    for key in ("controls", "systems"):
        assert cmds.listRelatives(result[key], parent=True)[0] == master
    assert driver(cmds, result["skeleton"] + ".visibility") == master + ".Skeleton"
    assert driver(cmds, result["models"] + ".visibility") == master + ".Geometry"
    assert driver(cmds, result["systems"] + ".visibility") == master + ".Rig_Systems"
    assert cmds.getAttr(master + ".Geometry") is True or cmds.getAttr(master + ".Geometry") == 1
    assert structure.find()["deformers_switch"] == master + ".Deformers"


def test_limb_matches_course(cmds):
    from jeffy.rig.flexible import limb

    arm = make_arm(cmds, names=("L_shoulder_JNT", "L_elbow_JNT", "L_wrist_JNT"))
    result = limb.build_limb(arm, name="arm", side="L")
    glob, switch, rev = result["global"].node, result["switch"], result["reverse"]
    assert cmds.getAttr(switch) == 1.0
    for bind, ik, fk in zip(arm, result["ik_joints"], result["fk_joints"]):
        targets, con = _targets(cmds, bind, "parentConstraint")
        assert targets == [ik, fk]
        assert _weights(cmds, con, "parentConstraint") == [switch, rev]
    for fk, ctl in zip(result["fk_joints"], result["fk_controls"]):
        assert _targets(cmds, fk, "parentConstraint")[0] == [ctl.node]
    assert _targets(cmds, result["ik_joints"][2], "orientConstraint")[0] == [result["ik_control"].node]
    assert cmds.getAttr(result["ik_control"].node + ".rotateOrder") == 1
    handle = result["handle"]
    assert cmds.listRelatives(handle, parent=True)[0] == result["ik_control"].node
    assert _targets(cmds, handle, "poleVectorConstraint")[0] == [result["pole"].node]
    assert driver(cmds, result["ik_control"].zero + ".visibility") == switch
    assert driver(cmds, result["fk_controls"][0].zero + ".visibility") == rev
    assert _targets(cmds, result["group"], "pointConstraint")[0] == [result["root"].node]
    assert _targets(cmds, result["global"].zero, "pointConstraint")[0] == [arm[2]]
    # stretch: condition (GT) of current/rest, divide, on IK scaleX
    cond, ratio = result["stretch_condition"], result["stretch_ratio"]
    assert cmds.getAttr(cond + ".operation") == 2 and cmds.getAttr(ratio + ".operation") == 2
    for joint in result["ik_joints"][:2]:
        assert driver(cmds, joint + ".scaleX") == cond + ".outColorR"
    assert fakemaya.evaluate(cmds, result["ik_joints"][0] + ".scaleX") == pytest.approx(1.0)
    # rest length comes from the scale chain inside the rig
    assert fakemaya.evaluate(cmds, result["stretch_ratio"] + ".input2X") == pytest.approx(10.0)
    assert glob in limb.find_limb(result["ik_control"].node) or limb.find_limb(glob) == glob


def test_bind_helpers(cmds):
    from jeffy.rig.flexible import limb
    from jeffy.ui import actions

    arm = make_arm(cmds, names=("L_shoulder_JNT", "L_elbow_JNT", "L_wrist_JNT"))
    result = limb.build_limb(arm, name="arm", side="L")
    cmds.select(result["global"].node)
    helpers = run(actions.add_flexible_bind_helpers)
    assert len(helpers) == 2
    assert cmds.listRelatives(helpers[0], parent=True)[0] == arm[0]
    assert cmds.listRelatives(helpers[1], parent=True)[0] == arm[1]
    for helper, index in zip(helpers, (1, 2)):
        targets, con = _targets(cmds, helper, "pointConstraint")
        assert targets == [result["ik_joints"][index], result["fk_joints"][index]]
        assert _weights(cmds, con, "pointConstraint") == [result["switch"], result["reverse"]]


def test_spine(cmds):
    from jeffy.ui import actions

    pelvis = cmds.createNode("joint", name="C_pelvis_JNT")
    chain, parent = [], pelvis
    for i in range(4):
        joint = cmds.createNode("joint", name="C_spine%02d_JNT" % (i + 1), parent=parent)
        cmds.setAttr(joint + ".translate", 0.0, 8.0, 0.0)
        chain.append(joint)
        parent = joint
    cmds.select(pelvis, chain[0], chain[-1])
    result = run(actions.build_flexible_spine)
    controls = result["controls"]
    assert len(controls) == 4
    assert _targets(cmds, chain[0], "parentConstraint")[0] == [result["cog"].node]
    for joint, ctl in zip(chain[1:], controls[1:]):
        assert _targets(cmds, joint, "parentConstraint")[0] == [ctl.node]
    assert _targets(cmds, pelvis, "parentConstraint")[0] == [result["hips"].node]
    assert cmds.listRelatives(result["hips"].zero, parent=True)[0] == result["cog"].node
    assert cmds.listRelatives(controls[2].zero, parent=True)[0] == controls[1].node


def test_fingers(cmds):
    from jeffy.ui import actions

    wrist = cmds.createNode("joint", name="L_wrist_JNT")
    roots = []
    for finger in ("index", "middle"):
        parent = wrist
        for i in range(4):
            joint = cmds.createNode("joint", name="L_%s%02d_JNT" % (finger, i + 1), parent=parent)
            cmds.setAttr(joint + ".translate", 1.0, 0.0, 0.0)
            if i == 0:
                roots.append(joint)
            parent = joint
    cmds.select(roots)
    result = run(actions.build_flexible_fingers)
    assert _targets(cmds, result["group"], "parentConstraint")[0] == [wrist]
    for root in roots:
        assert len(result["controls"][root]) == 4  # tips included
    assert cmds.ls("L_index01_CTL")


def test_ribbon_matches_course(geometry):
    from jeffy.rig.flexible import limb, ribbon

    cmds = geometry
    arm = make_arm(cmds, names=("L_shoulder_JNT", "L_elbow_JNT", "L_wrist_JNT"))
    limb_result = limb.build_limb(arm, name="arm", side="L")
    holder = limb_result["global"].node
    result = ribbon.build_ribbon_limb(arm[0], arm[1], arm[2], name="arm", side="L", holder=holder,
                                      crease_fix=True)
    root, upper, middle, lower, end = result["control_joints"]
    offsets = result["offsets"]
    assert len(result["follicles"]) == 9 and len(result["bind_joints"]) == 9
    assert _targets(cmds, offsets[0], "parentConstraint")[0] == [arm[0]]
    assert _targets(cmds, offsets[2], "parentConstraint")[0] == [arm[1]]
    assert _targets(cmds, offsets[4], "pointConstraint")[0] == [arm[2]]
    assert _targets(cmds, offsets[1], "pointConstraint")[0] == [root, middle]
    assert _targets(cmds, offsets[3], "pointConstraint")[0] == [end, middle]
    upper_aim, lower_aim = result["aims"]
    targets, con = _targets(cmds, upper_aim, "aimConstraint")
    assert targets == [middle]
    targets, con = _targets(cmds, lower_aim, "aimConstraint")
    assert targets == [middle]
    surface_shape = cmds.listRelatives(result["surface"], shapes=True)[0]
    assert cmds._node(surface_shape).data["inserted"] == [[0.493, 0.507]]
    # blendshape layer in front of the skin, wired to the holder
    blend = result["blendshape"]
    assert cmds._node(blend).data["front"] is True
    assert driver(cmds, blend + ".weight[0]") == holder + ".TwistBlend"
    assert driver(cmds, blend + ".weight[1]") == holder + ".SineBlend"
    assert driver(cmds, result["sine"] + ".amplitude") == holder + ".SineAmplitude"
    assert driver(cmds, result["sine"] + ".wavelength") == holder + ".SineWavelength"
    assert driver(cmds, result["sine"] + ".offset") == holder + ".SineOffset"
    assert driver(cmds, result["sine_handle"] + ".rotateY") == holder + ".SineOrientation"
    assert driver(cmds, result["twist"] + ".endAngle") == holder + ".TwistOffset"
    assert cmds.getAttr(holder + ".SineAmplitude") == 1.0 and cmds.getAttr(holder + ".SineWavelength") == 5.0
    assert cmds.getAttr(result["sine"] + ".dropoff") == 1
    for offset in (offsets[1], offsets[2], offsets[3]):
        assert driver(cmds, offset + ".visibility") == holder + ".Toon_Controls"
    # crease fix
    fix = result["crease_fix"]
    handles = fix["handles"]
    assert cmds.listRelatives(handles[0], parent=True)[0] == root
    assert cmds.listRelatives(handles[1], parent=True)[0] == middle
    skin = cmds._node(result["skin"])
    influences = [cmds._by_id(i).name for i in skin.data["influences"]]
    assert influences[:5] == [root, upper, middle, lower, end]
    assert fix["elbow_fix"] in influences and fix["wrist_fix"] in influences
    assert cmds.getAttr(result["skin"] + ".envelope") == 1.0
    extra = fix["extra_joint"]
    assert cmds.listRelatives(extra, parent=True)[0] == result["bind_joints"][3]
    assert _targets(cmds, extra, "pointConstraint")[0] == [result["bind_joints"][4]]


def test_ribbon_action_uses_structure_and_limb(geometry):
    from jeffy.core.decorators import ToolError
    from jeffy.ui import actions

    cmds = geometry
    run(actions.create_flexible_structure)
    arm = make_arm(cmds, names=("L_shoulder_JNT", "L_elbow_JNT", "L_wrist_JNT"))
    cmds.select(arm[0], arm[-1])
    limb_result = run(actions.build_flexible_limb)
    cmds.select(arm)
    result = run(actions.build_flexible_ribbon)
    assert result["holder"] == limb_result["global"].node  # the limb's global control holds the attributes
    assert driver(cmds, result["ribbon_group"] + ".visibility").endswith(".Deformers")
    assert cmds.listRelatives(result["group"], parent=True)[0] == "deformers"
    assert cmds.listRelatives(limb_result["group"], parent=True)[0] == "systems"
    cmds.select(result["controls"][0].node)
    with pytest.raises(ToolError):  # crease fix already added by default
        run(actions.add_flexible_crease_fix)


@pytest.mark.parametrize("side", ["L", "R"])
def test_reverse_foot_matches_course(cmds, side):
    from jeffy.rig.flexible import limb
    from jeffy.ui import actions

    leg = make_leg(cmds, side + "_")
    limb_result = limb.build_limb(leg, name="leg", side=side)
    ik_ctl = limb_result["ik_control"].node
    ik = limb_result["ik_joints"]
    locators = []
    for name, pos in (("heel", (10, 0, -3)), ("inner", (8, 0, 4)), ("outer", (12, 0, 4))):
        loc = cmds.spaceLocator(name=name + "_LOC")[0]
        cmds.xform(loc, worldSpace=True, translation=pos)
        locators.append(loc)
    cmds.select([ik_ctl, ik[2], ik[3], ik[4]] + locators)
    result = run(actions.build_flexible_foot)
    p = result["pivots"]
    order = ["root", "heel", "inner", "outer", "end", "ball", "ankle"]
    assert cmds.listRelatives(p["root"], parent=True)[0] == ik_ctl
    for a, b in zip(order, order[1:]):
        assert cmds.listRelatives(p[b], parent=True)[0] == p[a]
    assert cmds.listRelatives(p["toe"], parent=True)[0] == p["end"]
    assert cmds.listRelatives(limb_result["handle"], parent=True)[0] == p["ankle"]
    assert cmds.listRelatives(limb_result["stretch_end"], parent=True)[0] == p["ankle"]
    assert cmds.listRelatives(result["handles"]["ball"], parent=True)[0] == p["ball"]
    assert cmds.listRelatives(result["handles"]["toe"], parent=True)[0] == p["toe"]
    defaults = {a: cmds.getAttr(ik_ctl + "." + a) for a in ("ToeFlex", "RollBack", "RollEnd", "BankAmount",
                                                           "ToeStraightAngle")}
    assert defaults == {"ToeFlex": 9, "RollBack": 3, "RollEnd": 90, "BankAmount": 5, "ToeStraightAngle": 8}
    assert driver(cmds, p["heel"] + ".rotateY") == ik_ctl + ".HeelTwist"
    assert driver(cmds, p["end"] + ".rotateY") == ik_ctl + ".ToeTwist"
    assert driver(cmds, p["toe"] + ".rotateX") == ik_ctl + ".ToeTap"

    def value(plug):
        return fakemaya.evaluate(cmds, plug)

    # roll: the course formula
    for roll in (-10, -3, 0, 4, 8, 10, 12, 14, 20):
        cmds._node(ik_ctl).values["Roll"] = float(roll)
        ball = (roll if roll <= 8 else 8 - 2 * (roll - 8)) * 9 if roll > 0 else 0
        assert value(p["heel"] + ".rotateX") == pytest.approx(min(roll, 0) * 3)
        assert value(p["ball"] + ".rotateX") == pytest.approx(max(ball, 0))
        assert value(p["end"] + ".rotateX") == pytest.approx(min(max(roll - 8, 0) * 15, 90))
    # bank: inner for positive, outer for negative (swapped on the right side)
    first, second = (p["outer"], p["inner"]) if side == "R" else (p["inner"], p["outer"])
    cmds._node(ik_ctl).values["Bank"] = 2.0
    assert value(first + ".rotateZ") == pytest.approx(10.0) and value(second + ".rotateZ") == pytest.approx(0.0)
    cmds._node(ik_ctl).values["Bank"] = -1.0
    assert value(first + ".rotateZ") == pytest.approx(0.0) and value(second + ".rotateZ") == pytest.approx(-5.0)


def test_flex_shapes_in_library():
    from jeffy.controls import library

    names = library.CATEGORIES["Flexible Rig"]
    assert len(names) == 10
    for name in names:
        library.validate(library.get_shape(name))
