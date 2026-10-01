"""Joint orientation tools.

:func:`orient_joints` is a full featured replacement for *Orient Joint*:

* any aim / up axis combination, including negative axes,
* up vector from the world, an object, the chain plane (auto detects the
  bending plane, perfect for arms/legs/fingers) or the current orientation,
* children keep their world position (and orientation when not oriented),
* end joints can take the parent orientation, the world orientation or be
  left untouched.
"""

import contextlib

from maya import cmds

from jeffy.core import dag, mathlib, matrix, transform

UP_MODES = ("world", "plane", "object", "keep")
END_MODES = ("parent", "world", "keep")


@contextlib.contextmanager
def detached_children(joint):
    """Temporarily unparent every child of ``joint`` (world kept)."""
    children = [c for c in cmds.listRelatives(joint, children=True, fullPath=True) or []
                if cmds.objectType(c, isAType="transform")]
    uuids = cmds.ls(children, uuid=True) or []
    for child in children:
        cmds.parent(child, world=True)
    try:
        yield
    finally:
        for uid in uuids:
            nodes = cmds.ls(uid, long=True)
            if nodes:
                cmds.parent(nodes[0], joint)


def _child_joints(joint):
    return cmds.listRelatives(joint, children=True, type="joint", fullPath=True) or []


def _sorted_by_depth(joints):
    longs = cmds.ls(joints, long=True, type="joint") or []
    return sorted(longs, key=lambda n: n.count("|"))


def _plane_up(joint, child, previous_normal):
    """Bending plane normal around ``joint`` (consistent along the chain)."""
    j_pos = transform.get_position(joint)
    c_pos = transform.get_position(child)
    candidates = []
    grandchildren = _child_joints(child)
    if grandchildren:
        candidates.append(mathlib.cross(mathlib.sub(c_pos, j_pos),
                                        mathlib.sub(transform.get_position(grandchildren[0]), c_pos)))
    parent = dag.get_parent(joint)
    if parent and cmds.nodeType(parent) == "joint":
        p_pos = transform.get_position(parent)
        candidates.append(mathlib.cross(mathlib.sub(j_pos, p_pos), mathlib.sub(c_pos, j_pos)))
    for normal in candidates:
        if mathlib.length(normal) > 1e-6:
            normal = mathlib.normalize(normal)
            if previous_normal is not None and mathlib.dot(normal, previous_normal) < 0:
                normal = mathlib.negate(normal)
            return normal
    return previous_normal


def orient_joints(
    joints,
    aim_axis="x",
    up_axis="y",
    up_mode="world",
    world_up=(0.0, 1.0, 0.0),
    up_object=None,
    end_mode="parent",
    hierarchy=False,
):
    """Orient joints so ``aim_axis`` points to their first child joint.

    :param up_mode: ``world`` (use ``world_up``), ``plane`` (chain bending
        plane normal), ``object`` (toward ``up_object``) or ``keep`` (keep the
        current direction of ``up_axis``).
    :param end_mode: what to do with joints without children: ``parent``
        (zero orient - same as the parent), ``world`` or ``keep``.
    :param hierarchy: also orient every descendant joint.
    """
    if up_mode not in UP_MODES:
        raise ValueError("up_mode must be one of %s" % (UP_MODES,))
    if end_mode not in END_MODES:
        raise ValueError("end_mode must be one of %s" % (END_MODES,))
    if isinstance(joints, str):
        joints = [joints]
    targets = list(joints)
    if hierarchy:
        for joint in joints:
            targets.extend(cmds.listRelatives(joint, allDescendents=True, type="joint", fullPath=True) or [])
    targets = _sorted_by_depth(set(cmds.ls(targets, long=True) or []))
    uuids = cmds.ls(targets, uuid=True) or []

    up_name = up_axis.lstrip("+-").lower()
    previous_normal = None
    for uid in uuids:
        joint = cmds.ls(uid, long=True)[0]
        children = _child_joints(joint)
        if children:
            child = children[0]
            position = transform.get_position(joint)
            aim_vector = mathlib.sub(transform.get_position(child), position)
            if mathlib.length(aim_vector) < 1e-6:
                continue
            if up_mode == "world":
                up_vector = world_up
            elif up_mode == "object":
                if not up_object:
                    raise ValueError("up_object is required for up_mode='object'")
                up_vector = mathlib.sub(transform.get_position(up_object), position)
            elif up_mode == "plane":
                previous_normal = _plane_up(joint, child, previous_normal)
                up_vector = previous_normal if previous_normal is not None else world_up
            else:  # keep
                axes = mathlib.axes(matrix.get_world_matrix(joint))
                up_vector = axes[mathlib.AXIS_INDEX[up_name]]
                if up_axis.startswith("-"):
                    up_vector = mathlib.negate(up_vector)
            target = mathlib.aim_matrix(position, aim_vector, up_vector, aim_axis, up_axis)
            with detached_children(joint):
                matrix.set_joint_orient_from_matrix(joint, target)
        else:
            if end_mode == "keep":
                continue
            with detached_children(joint):
                if end_mode == "parent":
                    cmds.setAttr(joint + ".jointOrient", 0, 0, 0)
                    cmds.setAttr(joint + ".rotate", 0, 0, 0)
                    cmds.setAttr(joint + ".rotateAxis", 0, 0, 0)
                else:
                    world = mathlib.set_translation(mathlib.identity(), transform.get_position(joint))
                    matrix.set_joint_orient_from_matrix(joint, world)
    return [cmds.ls(uid, long=True)[0] for uid in uuids]


def orient_to_world(joints):
    """Make joints world aligned (identity world rotation)."""
    if isinstance(joints, str):
        joints = [joints]
    for joint in _sorted_by_depth(joints):
        with detached_children(joint):
            world = mathlib.set_translation(mathlib.identity(), transform.get_position(joint))
            matrix.set_joint_orient_from_matrix(joint, world)


def orient_like_parent(joints):
    if isinstance(joints, str):
        joints = [joints]
    for joint in _sorted_by_depth(joints):
        with detached_children(joint):
            cmds.setAttr(joint + ".jointOrient", 0, 0, 0)
            cmds.setAttr(joint + ".rotate", 0, 0, 0)


def rotate_axes(joints, rotation=(90.0, 0.0, 0.0)):
    """Rotate the local axes of joints by ``rotation`` (degrees, local space).

    Handy for quick fixes like flipping an up axis by 180 degrees around X.
    Children keep their world transforms.
    """
    if isinstance(joints, str):
        joints = [joints]
    offset = mathlib.euler_to_matrix(rotation, "xyz")
    for joint in _sorted_by_depth(joints):
        world = matrix.get_world_matrix(joint)
        rotated = mathlib.mult(offset, mathlib.orthonormalize(world))
        rotated = mathlib.set_translation(rotated, mathlib.get_translation(world))
        with detached_children(joint):
            matrix.set_joint_orient_from_matrix(joint, rotated)


def freeze_rotations(joints):
    """Move rotate values into jointOrient (keeps world orientation)."""
    if isinstance(joints, str):
        joints = [joints]
    for joint in _sorted_by_depth(joints):
        world = matrix.get_world_matrix(joint)
        with detached_children(joint):
            matrix.set_joint_orient_from_matrix(joint, world)


def is_planar(joints, tolerance=1e-3):
    """True when every joint lies in the plane of the first, middle and last."""
    points = [transform.get_position(j) for j in joints]
    if len(points) < 4:
        return True
    planar = mathlib.planarize(points)
    return all(mathlib.distance(a, b) < tolerance for a, b in zip(points, planar))
