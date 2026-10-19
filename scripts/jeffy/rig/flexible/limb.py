"""Course style IK/FK limb with distance based stretch (videos 2, 3 and 5).

Built like the course scenes:

* the bind chain is driven by duplicated ``IK`` and ``FK`` chains through parent
  constraints (no offset) whose weights come from ``IK_FK_Switch`` (on a global
  control that follows the end joint) and a ``reverse`` node,
* a third duplicated ``scale`` chain measures the rest length; stretch compares
  the root control -> IK control distance with it (``condition`` greater than +
  ``multiplyDivide`` divide) and scales the IK joints on X,
* the systems group follows the root control's position only,
* :func:`add_bind_helpers` adds non-rotating elbow/wrist bind joints that follow
  the IK/FK positions (clean stretch + bend weighting without a ribbon).

Extra joints after the third (ball, toe) are duplicated and blended too, with
FK controls; the IK only solves the first three (use the flexible reverse foot
for the rest).

::

    from jeffy.rig.flexible import limb
    result = limb.build_limb(["L_upArm_JNT", "L_foreArm_JNT", "L_hand_JNT"], name="arm", side="L")
    limb.add_bind_helpers(result)
"""

from maya import cmds

from jeffy.core import attributes, mathlib, naming, transform
from jeffy.joints import tools as joint_tools
from jeffy.rig import common as rig_common
from jeffy.rig.flexible import common

SWITCH = "IK_FK_Switch"


def _duplicate(joints, tag, parent):
    chain = joint_tools.duplicate_chain(joints[0], joints[-1], search="_JNT", replace="_%s_JNT" % tag,
                                        parent=parent)
    return [naming.short_name(j) for j in chain]


def build_limb(joints, name="limb", side=None, control_parent=None, systems_parent=None, size=1.0,
               stretch=True, pole_distance=0.0, ik_orient="joint", global_offset=None, shapes=None):
    """Build the course IK/FK limb on ``joints`` (bind chain root -> end, 3 or more).

    :param pole_distance: 0 places the pole control on the middle joint like the
        course; larger values push it out along the bend (x chain length)
    :param ik_orient: ``joint`` (IK control aligned to the end joint, as in the
        course) or ``world``
    :param global_offset: world offset of the global (switch) control from the
        end joint; defaults to ``size * 1.5`` up
    :returns: dict with ``global``, ``root``, ``ik_control``, ``pole``,
        ``fk_controls``, ``ik_joints``, ``fk_joints``, ``scale_joints``,
        ``handle``, ``switch``, ``reverse``, ``group`` and the stretch nodes
    """
    joints = [naming.short_name(j) for j in joints]
    if len(joints) < 3:
        raise ValueError("A limb needs at least three joints")
    shapes = dict({"global": "gear", "root": "square", "ik": "cube", "pole": "octahedron", "fk": "circle"},
                  **(shapes or {}))
    base = name
    grp = common.group(base + "Systems", side, parent=systems_parent, visible=False)
    root_pos = transform.get_position(joints[0])
    cmds.xform(grp, worldSpace=True, pivots=root_pos)

    ik_joints = _duplicate(joints, "IK", grp)
    fk_joints = _duplicate(joints, "FK", grp)
    scale_joints = _duplicate(joints[:3], "SCL", grp)

    # controls -------------------------------------------------------------
    icons = common.group(base + "Controls", side, parent=control_parent)
    root = common.control(base + "Root", side, shapes["root"], size * 1.2, "x", parent=icons, match=joints[0],
                          lock=("r", "s", "v"))
    fk_targets = joints[:3] + joints[3:-1]
    fk_controls = []
    parent = root.node
    for joint, fk_joint in zip(fk_targets, fk_joints):
        label = naming.parse(joint)["name"] or naming.strip_namespace(joint)
        ctl = common.control(label + "FK", side, shapes["fk"], size, "x", parent=parent, match=joint)
        cmds.parentConstraint(ctl.node, fk_joint, maintainOffset=False)
        fk_controls.append(ctl)
        parent = ctl.node

    end = joints[2]
    ik_ctl = common.control(base + "IK", side, shapes["ik"], size, "x", parent=icons, match=end,
                            match_rotation=(ik_orient == "joint"), lock=("s", "v"))
    cmds.setAttr(ik_ctl.node + ".rotateOrder", 1)  # yzx, as in the course
    positions = [transform.get_position(j) for j in joints[:3]]
    if pole_distance:
        pole_pos = mathlib.pole_vector_position(positions[0], positions[1], positions[2], pole_distance)
    else:
        pole_pos = positions[1]
    pole = common.control(base + "Pole", side, shapes["pole"], size * 0.4, "y", parent=icons, match=joints[1],
                          lock=("r", "s", "v"))
    cmds.xform(pole.zero, worldSpace=True, translation=pole_pos)

    glob = common.control(base, side, shapes["global"], size * 0.5, "y", parent=icons,
                          position=mathlib.add(positions[2], global_offset or (0.0, size * 1.5, 0.0)),
                          lock=("t", "r", "s", "v"))
    switch = attributes.add_attr(glob.node, SWITCH, "float", default=1.0, minimum=0.0, maximum=1.0)
    cmds.pointConstraint(end, glob.zero, maintainOffset=True)
    reverse = common.node("reverse", base + "IkFk", side, "reverse")
    cmds.connectAttr(switch, reverse + ".inputX")
    rev = reverse + ".outputX"

    # blend the bind chain ---------------------------------------------------
    for bind, ik_joint, fk_joint in zip(joints, ik_joints, fk_joints):
        common.blend_constraint(cmds.parentConstraint, (ik_joint, fk_joint), bind, (switch, rev))

    # IK ---------------------------------------------------------------------
    handle, effector = cmds.ikHandle(startJoint=ik_joints[0], endEffector=ik_joints[2], solver="ikRPsolver",
                                     name=naming.unique_name(naming.compose(base, side, "ik_handle")))
    cmds.rename(effector, naming.unique_name(naming.compose(base, side, "effector")))
    handle = cmds.parent(handle, ik_ctl.node)[0]
    cmds.poleVectorConstraint(pole.node, handle)
    cmds.orientConstraint(ik_ctl.node, ik_joints[2], maintainOffset=(ik_orient != "joint"))
    cmds.setAttr(handle + ".visibility", 0)

    # visibility -------------------------------------------------------------
    for ctl in (ik_ctl, pole):
        cmds.connectAttr(switch, ctl.zero + ".visibility")
    cmds.connectAttr(rev, fk_controls[0].zero + ".visibility")

    result = {"global": glob, "root": root, "ik_control": ik_ctl, "pole": pole, "fk_controls": fk_controls,
              "joints": joints, "ik_joints": ik_joints, "fk_joints": fk_joints, "scale_joints": scale_joints,
              "handle": handle, "switch": switch, "reverse": rev, "group": grp, "controls_group": icons}

    if stretch:
        result.update(add_stretch(result, base, side))

    cmds.pointConstraint(root.node, grp, maintainOffset=False)
    common.lock_free([c.zero for c in fk_controls] + [ik_ctl.zero, pole.zero])
    common.lock_free(glob.zero, ("r", "s"))

    common.store(glob.node, "bind", joints)
    common.store(glob.node, "ik", ik_joints)
    common.store(glob.node, "fk", fk_joints)
    common.store(glob.node, "nodes", [ik_ctl.node, pole.node, root.node, reverse, grp])
    return result


def add_stretch(result, base, side):
    """Distance based IK stretch on ``scaleX`` (course video 3)."""
    scale_joints = result["scale_joints"]
    upper = common.node("distanceBetween", base + "Upper", side, "distance")
    lower = common.node("distanceBetween", base + "Lower", side, "distance")
    cmds.connectAttr(scale_joints[0] + ".worldMatrix[0]", upper + ".inMatrix1")
    cmds.connectAttr(scale_joints[1] + ".worldMatrix[0]", upper + ".inMatrix2")
    cmds.connectAttr(scale_joints[1] + ".worldMatrix[0]", lower + ".inMatrix1")
    cmds.connectAttr(scale_joints[2] + ".worldMatrix[0]", lower + ".inMatrix2")
    full = common.node("addDoubleLinear", base + "FullLength", side)
    cmds.connectAttr(upper + ".distance", full + ".input1")
    cmds.connectAttr(lower + ".distance", full + ".input2")

    end = rig_common.create_locator(naming.compose(base + "StretchEnd", side, "locator"),
                                    parent=result["ik_control"].node, match=result["joints"][2])
    current = common.node("distanceBetween", base + "Stretch", side, "distance")
    cmds.connectAttr(result["root"].node + ".worldMatrix[0]", current + ".inMatrix1")
    cmds.connectAttr(end + ".worldMatrix[0]", current + ".inMatrix2")

    ratio = common.node("multiplyDivide", base + "Stretch", side, "multiply_divide", operation=2)
    cmds.connectAttr(current + ".distance", ratio + ".input1X")
    cmds.connectAttr(full + ".output", ratio + ".input2X")
    condition = common.node("condition", base + "Stretch", side, "condition", operation=2)
    cmds.connectAttr(current + ".distance", condition + ".firstTerm")
    cmds.connectAttr(full + ".output", condition + ".secondTerm")
    cmds.connectAttr(ratio + ".outputX", condition + ".colorIfTrueR")
    cmds.setAttr(condition + ".colorIfFalseR", 1.0)
    for joint in result["ik_joints"][:2]:
        cmds.connectAttr(condition + ".outColorR", joint + ".scaleX", force=True)
    return {"stretch_end": end, "stretch_condition": condition, "stretch_ratio": ratio, "rest_length": full,
            "current_length": current}


def find_limb(node):
    """Global control of the flexible limb ``node`` belongs to (or ``None``)."""
    owner = common.find_meta_owner(node, "bind")
    if owner:
        return naming.short_name(owner)
    for candidate in cmds.listConnections(node + ".message", source=False, destination=True) or []:
        if cmds.attributeQuery(common.META_PREFIX + "bind", node=candidate, exists=True):
            return candidate
    return None


def add_bind_helpers(limb, mid_index=1, end_index=2):
    """Non-rotating bind joints at the middle and end joint (course video 5).

    ``limb`` is a :func:`build_limb` result or its global control. Each helper is
    a copy of the joint, parented one level up (elbow helper under the
    shoulder, wrist helper under the elbow), point constrained to the IK and FK
    joints with the switch weights: it follows the position but never rotates,
    so stretch and bends can be weighted separately. Returns the new joints.
    """
    if isinstance(limb, dict):
        glob = limb["global"].node
    else:
        glob = find_limb(limb) or limb
    bind, ik_joints, fk_joints = (common.fetch(glob, key) for key in ("bind", "ik", "fk"))
    if not bind:
        raise ValueError("%s is not a flexible limb control" % glob)
    switch = "%s.%s" % (glob, SWITCH)
    reverse = cmds.listConnections(switch, source=False, destination=True, type="reverse")[0] + ".outputX"
    helpers = []
    for index in (mid_index, end_index):
        joint = bind[index]
        parsed = naming.parse(joint)
        label = (parsed["name"] or naming.strip_namespace(joint)) + "Bind"
        helper = cmds.duplicate(joint, parentOnly=True, name=naming.unique_name(naming.compose(label, parsed["side"],
                                                                                                "joint")))[0]
        helper = cmds.parent(helper, bind[index - 1])[0]
        for axis in "XYZ":
            cmds.setAttr("%s.rotate%s" % (helper, axis), 0)
        common.blend_constraint(cmds.pointConstraint, (ik_joints[index], fk_joints[index]), helper,
                                (switch, reverse))
        helpers.append(naming.short_name(helper))
    return helpers
