"""Reverse foot setup (roll, bank, twists, toe tap).

Pivot hierarchy (each pivot has an oriented ``ZRO`` group above it)::

    ik control
    `-- heel > toe tip > outer bank > inner bank
                                       |-- ball   > ankle target + ball IK
                                       `-- toeTap > toe IK

Attributes added on the IK control: ``roll``, ``rollBreak``,
``rollStraight``, ``bank``, ``heelTwist``, ``toeTwist``, ``ballTwist`` and
``toeTap``.

The roll follows the classic "rolling foot": negative values pivot on the
heel, positive values lift the heel around the ball until ``rollBreak``,
then blend onto the toe tip until ``rollStraight``.
"""

from maya import cmds

from jeffy.core import attributes, mathlib, matrix, naming, nodes, plugins, transform
from jeffy.rig import common


def foot_frame(heel, toe, up=(0.0, 1.0, 0.0)):
    """Orientation matrix for the pivots: Z forward (heel -> toe), Y up."""
    forward = mathlib.sub(toe, heel)
    forward = mathlib.normalize((forward[0], 0.0, forward[2])) if abs(up[1]) > 0.5 else mathlib.normalize(forward)
    if mathlib.length(forward) < 1e-6:
        forward = (0.0, 0.0, 1.0)
    x_axis = mathlib.normalize(mathlib.cross(up, forward))
    y_axis = mathlib.normalize(mathlib.cross(forward, x_axis))
    return mathlib.from_axes(x_axis, y_axis, forward)


def _pivot(name, side, position, frame, parent):
    zero = common.create_group(naming.compose(name + "Piv", side, "zero"), parent=parent)
    world = mathlib.set_translation(frame, position)
    matrix.set_world_matrix(zero, world, scale=False)
    return cmds.createNode("transform", name=naming.unique_name(naming.compose(name + "Piv", side, "group")),
                           parent=zero, skipSelect=True)


def _foot_handles(ankle, ball, toe, ball_parent, toe_parent, name, side):
    """Single chain IK handles keeping the ball and toe on their pivots.

    When the leg IK already orient constrains the ankle to its end target
    (the IK tools do by default), the ankle follows the foot through that
    constraint and no ankle -> ball handle is made: both would drive the
    ankle rotation.
    """
    ball_handle = None
    if not cmds.listRelatives(ankle, children=True, type="orientConstraint"):
        ball_handle = cmds.ikHandle(startJoint=ankle, endEffector=ball, solver="ikSCsolver",
                                    name=naming.unique_name(naming.compose(name + "Ball", side, "ik_handle")))[0]
        ball_handle = cmds.parent(ball_handle, ball_parent)[0]
    toe_handle = cmds.ikHandle(startJoint=ball, endEffector=toe, solver="ikSCsolver",
                               name=naming.unique_name(naming.compose(name + "Toe", side, "ik_handle")))[0]
    toe_handle = cmds.parent(toe_handle, toe_parent)[0]
    common.hide([h for h in (ball_handle, toe_handle) if h])
    return ball_handle, toe_handle


def _foot_attributes(ctl, roll_break=30.0, roll_straight=60.0):
    """Add the foot attributes to ``ctl``; returns ``{name: plug}``."""
    if cmds.attributeQuery("roll", node=ctl, exists=True):
        raise ValueError("%s already has a reverse foot (it has a 'roll' attribute)" % ctl)
    attributes.add_separator(ctl, "foot")
    plugs = {"roll": attributes.add_attr(ctl, "roll", "float", default=0.0),
             "rollBreak": attributes.add_attr(ctl, "rollBreak", "float", default=roll_break, minimum=0.0),
             "rollStraight": attributes.add_attr(ctl, "rollStraight", "float", default=roll_straight,
                                                 minimum=0.0)}
    for attr in ("bank", "heelTwist", "toeTwist", "ballTwist", "toeTap"):
        plugs[attr] = attributes.add_attr(ctl, attr, "float", default=0.0)
    return plugs


def _roll_network(plugs, name, side):
    """Split ``roll`` into heel / ball / toe angles (rolling foot).

    Negative roll pivots on the heel; positive lifts the heel around the
    ball until ``rollBreak``, then blends onto the toe tip until
    ``rollStraight``.
    """
    roll = plugs["roll"]
    base = name + "Roll"
    heel = nodes.clamp(roll, -180.0, 0.0, name=naming.compose(base + "Heel", side, "clamp"))
    toe_blend = nodes.remap(roll, plugs["rollBreak"], plugs["rollStraight"], 0.0, 1.0,
                            name=naming.compose(base + "ToeBlend", side, "remap"))
    ball = nodes.multiply(nodes.clamp(roll, 0.0, plugs["rollBreak"]), nodes.reverse(toe_blend),
                          name=naming.compose(base + "Ball", side, "utility"))
    toe = nodes.multiply(roll, toe_blend, name=naming.compose(base + "Toe", side, "utility"))
    return {"heel": heel, "ball": ball, "toe": toe}


def build_reverse_foot(ik_control, end_target, ankle, ball, toe, heel_pos, inner_pos, outer_pos, name="foot",
                       side=None, roll_break=30.0, roll_straight=60.0):
    """Build a reverse foot under ``ik_control``.

    :param end_target: the node the leg IK aims for (``ik.build_ik`` returns
        it as ``end``); it is re-parented under the ball pivot.
    :param ankle, ball, toe: IK joints of the foot (ankle is the leg end)
    :param heel_pos, inner_pos, outer_pos: world positions of the pivots
    :returns: dict with ``pivots``, ``ball_handle``, ``toe_handle``
    """
    ankle_pos = transform.get_position(ankle)
    ball_pos = transform.get_position(ball)
    toe_pos = transform.get_position(toe)
    ground = min(heel_pos[1], toe_pos[1])
    toe_tip = (toe_pos[0], ground, toe_pos[2])
    frame = foot_frame(heel_pos, toe_tip)
    x_axis = mathlib.axes(frame)[0]
    outward = 1.0 if mathlib.dot(x_axis, mathlib.sub(outer_pos, inner_pos)) >= 0 else -1.0

    heel = _pivot(name + "Heel", side, heel_pos, frame, ik_control)
    toe_piv = _pivot(name + "Toe", side, toe_tip, frame, heel)
    outer = _pivot(name + "Outer", side, outer_pos, frame, toe_piv)
    inner = _pivot(name + "Inner", side, inner_pos, frame, outer)
    ball_piv = _pivot(name + "Ball", side, ball_pos, frame, inner)
    toe_tap = _pivot(name + "ToeTap", side, ball_pos, frame, inner)

    end_target = cmds.parent(end_target, ball_piv)[0]
    cmds.xform(end_target, worldSpace=True, translation=ankle_pos)

    ball_handle, toe_handle = _foot_handles(ankle, ball, toe, ball_piv, toe_tap, name, side)

    plugs = _foot_attributes(ik_control, roll_break, roll_straight)
    rolls = _roll_network(plugs, name, side)
    cmds.connectAttr(rolls["heel"], heel + ".rotateX")
    cmds.connectAttr(rolls["ball"], ball_piv + ".rotateX")
    cmds.connectAttr(rolls["toe"], toe_piv + ".rotateX")
    bank, heel_twist, toe_twist, ball_twist, tap = (plugs[k] for k in ("bank", "heelTwist", "toeTwist",
                                                                       "ballTwist", "toeTap"))
    # bank: positive rolls onto the outer edge
    cmds.connectAttr(nodes.multiply(nodes.clamp(bank, 0.0, 180.0), -outward), outer + ".rotateZ")
    cmds.connectAttr(nodes.multiply(nodes.clamp(bank, -180.0, 0.0), -outward), inner + ".rotateZ")
    # twists and toe tap (positive lifts the toes)
    cmds.connectAttr(heel_twist, heel + ".rotateY")
    cmds.connectAttr(toe_twist, toe_piv + ".rotateY")
    cmds.connectAttr(ball_twist, ball_piv + ".rotateY")
    cmds.connectAttr(nodes.negate(tap), toe_tap + ".rotateX")

    return {
        "pivots": {"heel": heel, "toe": toe_piv, "outer": outer, "inner": inner, "ball": ball_piv,
                   "toe_tap": toe_tap},
        "ball_handle": ball_handle,
        "toe_handle": toe_handle,
        "end_target": end_target,
    }


# ---------------------------------------------------------------------------
# Reverse foot from a reverse joint chain
# ---------------------------------------------------------------------------
def _distance(a, b):
    return mathlib.distance(transform.get_position(a), transform.get_position(b))


def find_end_target(ik_control):
    """The ``...End`` locator the toolkit's IK tools create under the IK control."""
    children = cmds.listRelatives(ik_control, children=True, type="transform") or []
    targets = [c for c in children if "End" in c and cmds.listRelatives(c, shapes=True, type="locator")]
    return targets[0] if targets else None


_FOLLOW_CONSTRAINTS = ("pointConstraint", "parentConstraint", "orientConstraint")


def _upstream_nodes(plugs, depth=4):
    """Nodes feeding ``plugs`` through up to ``depth`` connections."""
    found = []
    frontier = list(plugs)
    for _level in range(depth):
        upstream = []
        for plug in frontier:
            for node in cmds.listConnections(plug, source=True, destination=False) or []:
                node = naming.short_name(node)
                if node not in found:
                    found.append(node)
                    upstream.append(node)
        frontier = upstream
    return found


def _follows(handle, control):
    """True when ``handle`` is under ``control``, constrained to it or driven by it."""
    control = naming.short_name(control)
    long_handle = (cmds.ls(handle, long=True) or [handle])[0]
    long_control = (cmds.ls(control, long=True) or [control])[0]
    if long_handle.startswith(long_control + "|"):
        return True
    for kind in _FOLLOW_CONSTRAINTS:
        for constraint in cmds.listRelatives(handle, children=True, type=kind) or []:
            targets = getattr(cmds, kind)(constraint, query=True, targetList=True) or []
            if control in [naming.short_name(t) for t in targets]:
                return True
    plugs = ["%s.%s" % (handle, a) for a in ("translate", "translateX", "translateY", "translateZ",
                                               "offsetParentMatrix")]
    return control in _upstream_nodes([p for p in plugs if cmds.objExists(p)])


def find_ik_handle(ik_control, near=None):
    """The IK handle that follows ``ik_control`` (the one closest to ``near``)."""
    handles = [h for h in cmds.ls(type="ikHandle") or [] if _follows(h, ik_control)]
    if not handles:
        return None
    if near is not None and len(handles) > 1:
        position = transform.get_position(near)
        handles.sort(key=lambda h: mathlib.distance(transform.get_position(h), position))
    return naming.short_name(handles[0])


def attach_ik_handle(handle, parent):
    """Move ``handle`` under ``parent`` (keeping its world position).

    Point / parent / orient constraints and translate inputs that made it
    follow the IK control are removed; its pole vector constraint stays.
    """
    for kind in _FOLLOW_CONSTRAINTS:
        constraints = cmds.listRelatives(handle, children=True, type=kind) or []
        if constraints:
            cmds.delete(constraints)
    for attr in ("translate", "translateX", "translateY", "translateZ", "offsetParentMatrix"):
        plug = "%s.%s" % (handle, attr)
        for source in cmds.listConnections(plug, source=True, destination=False, plugs=True) or []:
            cmds.disconnectAttr(source, plug)
    for attr in ("translateX", "translateY", "translateZ"):
        cmds.setAttr("%s.%s" % (handle, attr), lock=False)
    position = transform.get_position(handle)
    handle = cmds.parent(handle, parent)[0]
    cmds.xform(handle, worldSpace=True, translation=position)
    return handle


def release_ankle(ankle, keep_under):
    """Delete orient constraints on ``ankle`` whose targets do not move with
    the foot (not under ``keep_under``), so the foot drives the ankle."""
    root = (cmds.ls(keep_under, long=True) or [keep_under])[0]
    for constraint in cmds.listRelatives(ankle, children=True, type="orientConstraint") or []:
        targets = cmds.orientConstraint(constraint, query=True, targetList=True) or []
        longs = [(cmds.ls(t, long=True) or [t])[0] for t in targets]
        if not all(t.startswith(root + "|") for t in longs):
            cmds.delete(constraint)


def find_foot_joints(reverse_chain, tolerance):
    """Base ``(ankle, ball, toe)`` joints sitting on the reverse ankle and ball.

    Several chains can sit on the same spot (bind, IK, FK): joints named
    ``IK`` win, then the only candidate left. Raises when it is ambiguous.
    """
    _heel, toe_tip, rev_ball, rev_ankle = reverse_chain[:4]
    ankle_pos = transform.get_position(rev_ankle)
    ball_pos = transform.get_position(rev_ball)
    skip = set(naming.short_name(j) for j in reverse_chain)
    candidates = []
    for joint in cmds.ls(type="joint") or []:
        if naming.short_name(joint) in skip:
            continue
        if mathlib.distance(transform.get_position(joint), ankle_pos) > tolerance:
            continue
        balls = [c for c in cmds.listRelatives(joint, children=True, type="joint") or []
                 if mathlib.distance(transform.get_position(c), ball_pos) <= tolerance]
        if balls:
            candidates.append((joint, balls[0]))
    if not candidates:
        raise ValueError("No foot joints found under %s / %s: the reverse ankle and ball must sit on the base "
                         "ankle and ball (or select the IK ankle joint)" % (rev_ankle, rev_ball))
    if len(candidates) > 1:
        ik = [c for c in candidates if "IK" in naming.short_name(c[0])]
        if len(ik) == 1:
            candidates = ik
        else:
            raise ValueError("Several ankle joints sit on %s (%s): select the IK ankle joint as the third object"
                             % (rev_ankle, ", ".join(naming.short_name(c[0]) for c in candidates)))
    ankle, ball = candidates[0]
    return ankle, ball, _toe_of(ball, transform.get_position(toe_tip))


def _toe_of(ball, toe_tip_pos):
    toes = cmds.listRelatives(ball, children=True, type="joint") or []
    if not toes:
        raise ValueError("%s has no toe joint under it" % ball)
    return min(toes, key=lambda j: mathlib.distance(transform.get_position(j), toe_tip_pos))


def _orient_frame(joint):
    """World axes rotate values act in (jointOrient x parent), no scale."""
    orient = mathlib.euler_to_matrix(cmds.getAttr(joint + ".jointOrient")[0], "xyz")
    parent = cmds.getAttr(joint + ".parentMatrix[0]")
    return [mathlib.normalize(axis) for axis in mathlib.axes(mathlib.mult(orient, parent))[:3]]


def _drive_rotation(joint, terms, name, side):
    """Rotate ``joint`` around world axes: ``terms`` is ``[(world_axis, angle_plug)]``.

    Works whatever the joint orientation is: each axis is expressed in the
    joint's own frame and turned into a quaternion, so the reverse chain keeps
    the orientation it was built with.
    """
    plugins.ensure_matrix_plugins()
    frame = _orient_frame(joint)
    quats = []
    for index, (axis, angle) in enumerate(terms):
        local = [mathlib.dot(axis, row) for row in frame]
        node = cmds.createNode("axisAngleToQuat", name=naming.unique_name(naming.compose(
            "%s%d" % (name, index), side, "utility")), skipSelect=True)
        cmds.setAttr(node + ".inputAxis", *local)
        cmds.connectAttr(angle, node + ".inputAngle")
        quats.append(node + ".outputQuat")
    quat = quats[0]
    for other in quats[1:]:
        prod = cmds.createNode("quatProd", name=naming.unique_name(naming.compose(name + "Prod", side, "utility")),
                               skipSelect=True)
        cmds.connectAttr(quat, prod + ".input1Quat")
        cmds.connectAttr(other, prod + ".input2Quat")
        quat = prod + ".outputQuat"
    euler = cmds.createNode("quatToEuler", name=naming.unique_name(naming.compose(name + "Euler", side,
                                                                                  "utility")), skipSelect=True)
    cmds.connectAttr(quat, euler + ".inputQuat")
    cmds.connectAttr(joint + ".rotateOrder", euler + ".inputRotateOrder")
    cmds.connectAttr(euler + ".outputRotate", joint + ".rotate", force=True)
    return euler


def build_reverse_foot_from_chain(ik_control, reverse_root, end_target=None, ankle=None, inner_pos=None,
                                  outer_pos=None, name="foot", side=None, roll_break=30.0, roll_straight=60.0,
                                  bank_width=0.3, ik_handle=None):
    """Reverse foot driven by an existing reverse joint chain.

    The chain is ``heel > toe tip > ball > ankle`` (each joint a child of the
    previous one), with the ankle and ball on the base foot joints. The base
    ankle / ball / toe are found from their positions (or pass ``ankle``).

    :param end_target: the ``...End`` locator the leg IK follows (toolkit IK
        tools; found under the IK control by default)
    :param ik_handle: the leg IK handle to move with the foot when there is
        no such locator (default: the handle that follows the IK control -
        parented under it, constrained or connected to it)
    :param inner_pos, outer_pos: bank pivots; default on each side of the
        ball, ``bank_width`` times the foot length apart. They sit under
        ``..._ZRO`` groups: move those to adjust the pivots later.
    :returns: dict with ``reverse_joints``, ``pivots``, ``ball_handle``,
        ``toe_handle``, ``end_target`` and the foot ``joints``
    """
    from jeffy.core import dag
    from jeffy.joints import orient as orient_tools

    chain = [naming.short_name(j) for j in dag.get_chain(reverse_root)]
    if len(chain) < 4:
        raise ValueError("%s: the reverse chain needs 4 joints (heel > toe tip > ball > ankle)" % reverse_root)
    rev_heel, rev_toe, rev_ball, rev_ankle = chain[:4]
    foot_length = max(_distance(rev_heel, rev_toe), 1e-3)
    tolerance = foot_length * 0.05
    if ankle:
        ball = next((c for c in cmds.listRelatives(ankle, children=True, type="joint") or []
                     if _distance(c, rev_ball) <= tolerance), None)
        if not ball:
            raise ValueError("%s has no child joint on the reverse ball %s" % (ankle, rev_ball))
        toe = _toe_of(ball, transform.get_position(rev_toe))
    else:
        ankle, ball, toe = find_foot_joints(chain, tolerance)
    if _distance(ankle, rev_ankle) > tolerance:
        raise ValueError("The reverse ankle %s is not on the ankle %s" % (rev_ankle, ankle))
    if not ik_handle:
        end_target = end_target or find_end_target(ik_control)
        if not end_target:
            ik_handle = find_ik_handle(ik_control, near=ankle)
    if not end_target and not ik_handle:
        raise ValueError("No IK handle follows %s (parented under it, constrained or connected to it)"
                         % ik_control)

    heel_pos = transform.get_position(rev_heel)
    toe_pos = transform.get_position(rev_toe)
    ball_pos = transform.get_position(rev_ball)
    frame = foot_frame(heel_pos, toe_pos)
    x_axis, y_axis = mathlib.axes(frame)[0], mathlib.axes(frame)[1]
    ground = min(heel_pos[1], toe_pos[1])
    if inner_pos is None or outer_pos is None:
        offset = mathlib.scale(x_axis, foot_length * bank_width * 0.5)
        a = mathlib.add((ball_pos[0], ground, ball_pos[2]), offset)
        b = mathlib.sub((ball_pos[0], ground, ball_pos[2]), offset)
        # the outer edge is the one further from the body's centre line
        outer_pos, inner_pos = (a, b) if abs(a[0]) >= abs(b[0]) else (b, a)
    outward = 1.0 if mathlib.dot(x_axis, mathlib.sub(outer_pos, inner_pos)) >= 0 else -1.0

    plugs = _foot_attributes(ik_control, roll_break, roll_straight)

    # bank pivots above the chain, the chain under them
    outer = _pivot(name + "Outer", side, outer_pos, frame, ik_control)
    inner = _pivot(name + "Inner", side, inner_pos, frame, outer)
    if dag.get_parent(rev_heel) != naming.short_name(inner):
        rev_heel = cmds.parent(rev_heel, inner)[0]
    chain = [naming.short_name(j) for j in dag.get_chain(rev_heel)][:4]
    rev_heel, rev_toe, rev_ball, rev_ankle = chain
    # rotate values go to jointOrient (same world pose): the network owns rotate
    orient_tools.freeze_rotations(chain)
    toe_tap = _pivot(name + "ToeTap", side, ball_pos, frame, rev_toe)

    if ik_handle:
        end_target = attach_ik_handle(ik_handle, rev_ankle)
    else:
        end_target = cmds.parent(end_target, rev_ankle)[0]
        cmds.xform(end_target, worldSpace=True, translation=transform.get_position(ankle))
    # an ankle orient constraint to something that does not roll with the
    # foot (e.g. the IK control itself) would fight the foot
    release_ankle(ankle, rev_heel)
    ball_handle, toe_handle = _foot_handles(ankle, ball, toe, rev_ball, toe_tap, name, side)

    rolls = _roll_network(plugs, name, side)
    _drive_rotation(rev_heel, [(x_axis, rolls["heel"]), (y_axis, plugs["heelTwist"])], name + "Heel", side)
    _drive_rotation(rev_toe, [(x_axis, rolls["toe"]), (y_axis, plugs["toeTwist"])], name + "Toe", side)
    _drive_rotation(rev_ball, [(x_axis, rolls["ball"]), (y_axis, plugs["ballTwist"])], name + "Ball", side)
    bank = plugs["bank"]
    cmds.connectAttr(nodes.multiply(nodes.clamp(bank, 0.0, 180.0), -outward), outer + ".rotateZ")
    cmds.connectAttr(nodes.multiply(nodes.clamp(bank, -180.0, 0.0), -outward), inner + ".rotateZ")
    cmds.connectAttr(nodes.negate(plugs["toeTap"]), toe_tap + ".rotateX")

    return {
        "reverse_joints": chain,
        "pivots": {"outer": outer, "inner": inner, "toe_tap": toe_tap},
        "ball_handle": ball_handle,
        "toe_handle": toe_handle,
        "end_target": end_target,
        "ik_handle": ik_handle and end_target,
        "joints": (ankle, ball, toe),
    }


def mirror_name(node):
    """``L_x`` <-> ``R_x`` (also ``_L_`` / ``Left``...) or None."""
    short = naming.short_name(node)
    for left, right in (("L_", "R_"), ("_L_", "_R_"), ("_L", "_R"), ("Left", "Right"), ("left", "right")):
        if left in short:
            return short.replace(left, right, 1)
        if right in short:
            return short.replace(right, left, 1)
    return None


# ---------------------------------------------------------------------------
# One click reverse foot: builds the reverse chain from the foot joints
# ---------------------------------------------------------------------------
def foot_chain(joints):
    """``(ankle, ball, toe, tip)`` from the selected foot joints.

    Pass the ankle alone (ball and toe are its first child joints) or the
    ankle, ball, toe and optionally the toe end. ``tip`` is the toe end, or
    the toe when there is none.
    """
    joints = [naming.short_name(j) for j in joints]
    chain = list(joints)
    while len(chain) < 4:
        children = cmds.listRelatives(chain[-1], children=True, type="joint") or []
        if not children:
            break
        chain.append(naming.short_name(children[0]))
    if len(chain) < 3:
        raise ValueError("Select the ankle, ball and toe joints (or the ankle of a chain ankle > ball > toe)")
    ankle, ball, toe = chain[:3]
    tip = chain[3] if len(chain) > 3 else toe
    return ankle, ball, toe, tip


def ik_counterpart(joint):
    """The IK joint sitting on ``joint`` (IK/FK limbs), or ``joint`` itself."""
    short = naming.short_name(joint)
    if "IK" in short:
        return short
    position = transform.get_position(joint)
    children = [transform.get_position(c) for c in cmds.listRelatives(joint, children=True, type="joint") or []]
    for other in cmds.ls(type="joint") or []:
        name = naming.short_name(other)
        if "IK" not in name or mathlib.distance(transform.get_position(other), position) > 1e-3:
            continue
        other_children = [transform.get_position(c)
                          for c in cmds.listRelatives(other, children=True, type="joint") or []]
        if not children or any(mathlib.distance(a, b) < 1e-3 for a in children for b in other_children):
            return name
    return short


def foot_guides(ankle, ball, tip, heel_back=0.3):
    """Default ``(heel, toe_tip)`` positions: on the ground under the foot.

    The ground is the lowest of the ball and the tip. The heel sits behind
    the ankle by ``heel_back`` times the ankle -> tip length.
    """
    ankle_pos = transform.get_position(ankle)
    ball_pos = transform.get_position(ball)
    tip_pos = transform.get_position(tip)
    ground = min(ball_pos[1], tip_pos[1])
    forward = mathlib.sub(tip_pos, ankle_pos)
    forward = (forward[0], 0.0, forward[2])
    length = mathlib.length(forward)
    forward = mathlib.normalize(forward) if length > 1e-6 else (0.0, 0.0, 1.0)
    heel = mathlib.sub((ankle_pos[0], ground, ankle_pos[2]), mathlib.scale(forward, max(length, 1e-3) * heel_back))
    return heel, (tip_pos[0], ground, tip_pos[2])


def build_reverse_chain(ankle, ball, heel_pos, tip_pos, name="foot", side=None, parent=None):
    """Create ``heel > toe tip > ball > ankle`` joints aligned with the foot
    (Z forward, Y up); returns the joints."""
    from jeffy.joints import tools as joint_tools

    frame = foot_frame(heel_pos, tip_pos)
    joints = []
    current = parent
    for label, position in (("Heel", heel_pos), ("ToeTip", tip_pos), ("Ball", transform.get_position(ball)),
                            ("Ankle", transform.get_position(ankle))):
        joint = joint_tools.create_joint(naming.compose(name + "Rev" + label, side, "joint"), parent=current)
        cmds.xform(joint, worldSpace=True, translation=position)
        matrix.set_joint_orient_from_matrix(joint, frame)
        joints.append(joint)
        current = joint
    return joints


def build_reverse_foot_auto(ik_control, foot_joints, heel_pos=None, inner_pos=None, outer_pos=None, name="foot",
                            side=None, roll_break=30.0, roll_straight=60.0, heel_back=0.3, bank_width=0.3,
                            ik_handle=None):
    """The whole reverse foot from the IK control and the foot joints.

    Creates the reverse joint chain (heel, toe tip, ball, ankle), the bank
    pivots and the roll network, then wires the leg IK and the foot joints
    (see :func:`build_reverse_foot_from_chain`). When ``foot_joints`` are
    bind joints of an IK/FK limb, their IK joints are used.

    :param foot_joints: the ankle, or ankle, ball, toe [, toe end]
    :param heel_pos: default behind the ankle, on the ground
    :returns: the :func:`build_reverse_foot_from_chain` result plus ``guides``
    """
    ankle, ball, _toe, tip = foot_chain(foot_joints)
    ik_ankle = ik_counterpart(ankle)
    if not ik_handle and not find_end_target(ik_control):
        ik_handle = find_ik_handle(ik_control, near=ik_ankle)
        if not ik_handle:  # fail before creating anything
            raise ValueError("No IK handle follows %s (parented under it, constrained or connected to it)"
                             % ik_control)
    default_heel, tip_pos = foot_guides(ankle, ball, tip, heel_back)
    heel_pos = heel_pos or default_heel
    reverse = build_reverse_chain(ankle, ball, heel_pos, tip_pos, name=name, side=side, parent=ik_control)
    result = build_reverse_foot_from_chain(ik_control, reverse[0], ankle=ik_ankle, inner_pos=inner_pos,
                                           outer_pos=outer_pos, name=name, side=side, roll_break=roll_break,
                                           roll_straight=roll_straight, bank_width=bank_width,
                                           ik_handle=ik_handle)
    result["guides"] = {"heel": heel_pos, "toe_tip": tip_pos}
    return result
