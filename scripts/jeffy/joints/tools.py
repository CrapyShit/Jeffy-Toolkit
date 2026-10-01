"""Joint creation and editing tools."""

from maya import cmds

from jeffy.core import dag, mathlib, naming, transform
from jeffy.joints import orient as orient_tools

DRAW_STYLES = {"bone": 0, "box": 1, "none": 2, "joint": 3}
JOINT_SIDES = {"C": 0, "L": 1, "R": 2}


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------
def create_joint(name, position=None, parent=None, radius=None, match=None, rotate_order=None):
    """Create a single joint (never parented to the selection by accident)."""
    joint = cmds.createNode("joint", name=naming.unique_name(name), skipSelect=True)
    if parent:
        joint = cmds.parent(joint, parent, relative=True)[0]
    if match:
        cmds.matchTransform(joint, match, position=True, rotation=True)
        orient_tools.freeze_rotations(joint)
    elif position is not None:
        cmds.xform(joint, worldSpace=True, translation=position)
    if radius is not None:
        cmds.setAttr(joint + ".radius", radius)
    if rotate_order is not None:
        cmds.setAttr(joint + ".rotateOrder", rotate_order)
    return joint


def create_chain(positions, names=None, name="joint", side=None, parent=None, orient=True, aim_axis="x",
                 up_axis="y", up_mode="plane", world_up=(0, 1, 0), radius=None):
    """Create a parented joint chain through ``positions`` and orient it."""
    joints = []
    current_parent = parent
    for i, position in enumerate(positions):
        if names:
            joint_name = names[i]
        else:
            joint_name = naming.compose("%s%02d" % (name, i + 1), side, "joint")
        joint = create_joint(joint_name, position=position, parent=current_parent, radius=radius)
        joints.append(joint)
        current_parent = joint
    if orient and joints:
        oriented = orient_tools.orient_joints(joints, aim_axis=aim_axis, up_axis=up_axis, up_mode=up_mode,
                                              world_up=world_up)
        joints = [naming.short_name(j) for j in oriented]
    return joints


def joints_at_selection(nodes=None, name="joint", chain=False, center=False, orient=True, radius=None):
    """Create joints on selected objects and/or components.

    * objects: one joint per object (position and rotation matched)
    * components: one joint at the centre of each selected group of
      components, e.g. select edge loops one by one
    * ``center=True``: a single joint at the centre of the whole selection
    * ``chain=True``: joints are parented in selection order
    """
    nodes = nodes or cmds.ls(orderedSelection=True) or []
    if not nodes:
        raise ValueError("Nothing selected")
    if center:
        return [create_joint(naming.compose(name, None, "joint"), position=transform.get_center(nodes),
                             radius=radius)]
    joints = []
    previous = None
    for i, node in enumerate(nodes):
        joint_name = naming.compose("%s%02d" % (name, i + 1), None, "joint")
        if "." in node:
            joint = create_joint(joint_name, position=transform.get_position(node), radius=radius)
        else:
            joint = create_joint(joint_name, match=node, radius=radius)
        if chain and previous:
            joint = cmds.parent(joint, previous)[0]
        joints.append(joint)
        previous = joint
    if chain and orient and len(joints) > 1:
        joints = [naming.short_name(j) for j in orient_tools.orient_joints(joints, up_mode="plane")]
    return joints


def joints_on_curve(curve, count=5, name="curve", side=None, chain=True, orient=True, aim_axis="x", up_axis="y",
                    up_mode="plane", world_up=(0, 1, 0)):
    """Evenly distribute ``count`` joints along a curve (by arc length)."""
    from jeffy.geometry import curves as curve_tools

    positions = curve_tools.positions_along(curve, count)
    if chain:
        return create_chain(positions, name=name, side=side, orient=orient, aim_axis=aim_axis, up_axis=up_axis,
                            up_mode=up_mode, world_up=world_up)
    return [create_joint(naming.compose("%s%02d" % (name, i + 1), side, "joint"), position=p)
            for i, p in enumerate(positions)]


def joints_on_transforms(nodes, name_suffix="JNT", parent_hierarchy=False):
    """Create a joint matching each transform (position + orientation)."""
    joints = []
    mapping = {}
    for node in nodes:
        joint = create_joint("%s_%s" % (naming.strip_namespace(node), name_suffix), match=node)
        joints.append(joint)
        mapping[dag.long_name(node)] = joint
    if parent_hierarchy:
        for node in nodes:
            parent = dag.get_parent(node)
            while parent and parent not in mapping:
                parent = dag.get_parent(parent)
            if parent:
                cmds.parent(mapping[dag.long_name(node)], mapping[parent])
    return joints


def insert_joints(start, count=1, name=None):
    """Insert ``count`` evenly spaced joints between ``start`` and its child."""
    children = cmds.listRelatives(start, children=True, type="joint", fullPath=True) or []
    if not children:
        raise ValueError("%s has no child joint" % start)
    end = children[0]
    end_uuid = cmds.ls(end, uuid=True)[0]
    start_pos = transform.get_position(start)
    end_pos = transform.get_position(end)
    base = name or naming.short_name(start)
    created = []
    parent = start
    radius = cmds.getAttr(start + ".radius")
    for i in range(1, count + 1):
        t = i / float(count + 1)
        joint = create_joint("%s_split%02d" % (base, i), parent=parent, radius=radius)
        cmds.setAttr(joint + ".jointOrient", 0, 0, 0)
        cmds.xform(joint, worldSpace=True, translation=mathlib.lerp_vector(start_pos, end_pos, t))
        created.append(joint)
        parent = joint
    end = cmds.ls(end_uuid, long=True)[0]
    cmds.parent(end, parent)
    return created


def duplicate_chain(start, end=None, search="_JNT", replace="_DUP_JNT", parent=None):
    """Duplicate a joint chain (joints only, no side branches) with new names.

    Names are built by replacing ``search`` with ``replace`` (or appending
    ``replace`` when ``search`` is not found). The copy stays under the
    original parent unless ``parent`` is given. Returns root -> tip.
    """
    chain = dag.get_chain(start, end)
    new_joints = []
    previous = None
    for joint in chain:
        short = naming.short_name(joint)
        new_name = short.replace(search, replace) if search and search in short else short + replace
        dup = cmds.duplicate(joint, parentOnly=True, name=naming.unique_name(new_name))[0]
        if previous:
            dup = cmds.parent(dup, previous)[0]
        elif parent:
            dup = cmds.parent(dup, parent)[0]
        new_joints.append(dup)
        previous = dup
    return [naming.short_name(j) for j in new_joints]


def mirror_joints(roots, axis="x", behavior=True, search="L_", replace="R_"):
    """Mirror joint hierarchies (wrapper around ``mirrorJoint``)."""
    if isinstance(roots, str):
        roots = [roots]
    flag = {"x": "mirrorYZ", "y": "mirrorXZ", "z": "mirrorXY"}[axis.lower()]
    created = []
    for root in roots:
        kwargs = {flag: True, "mirrorBehavior": behavior}
        if search:
            kwargs["searchReplace"] = (search, replace)
        created.extend(cmds.mirrorJoint(root, **kwargs) or [])
    return created


# ---------------------------------------------------------------------------
# Display / attributes
# ---------------------------------------------------------------------------
def set_radius(joints, radius):
    for joint in cmds.ls(joints, type="joint") or []:
        cmds.setAttr(joint + ".radius", radius)


def scale_radius(joints, factor):
    for joint in cmds.ls(joints, type="joint") or []:
        cmds.setAttr(joint + ".radius", cmds.getAttr(joint + ".radius") * factor)


def set_local_axes_visible(nodes, state=None):
    """Show/hide local rotation axes (``state=None`` toggles)."""
    for node in cmds.ls(nodes) or []:
        value = state if state is not None else not cmds.getAttr(node + ".displayLocalAxis")
        cmds.setAttr(node + ".displayLocalAxis", value)


def set_draw_style(joints, style="bone"):
    value = DRAW_STYLES[style] if isinstance(style, str) else style
    for joint in cmds.ls(joints, type="joint") or []:
        cmds.setAttr(joint + ".drawStyle", value)


def set_segment_scale_compensate(joints, value=True):
    for joint in cmds.ls(joints, type="joint") or []:
        cmds.setAttr(joint + ".segmentScaleCompensate", value)


def set_preferred_angles(joints):
    for joint in cmds.ls(joints, type="joint") or []:
        cmds.joint(joint, edit=True, setPreferredAngles=True)


def label_joints(joints):
    """Set joint labels (side/type/other type) from names.

    Labels make ``copySkinWeights``/``mirror skin`` with *label* influence
    association work across sides.
    """
    for joint in cmds.ls(joints, type="joint") or []:
        parsed = naming.parse(joint)
        side = parsed["side"] or naming.side_from_name(joint)
        cmds.setAttr(joint + ".side", JOINT_SIDES.get(side, 3))
        cmds.setAttr(joint + ".type", 18)  # "Other"
        label = naming.strip_namespace(parsed["name"] or naming.short_name(joint))
        cmds.setAttr(joint + ".otherType", label, type="string")


def connect_inverse_scale(joints):
    """Make sure every joint's ``inverseScale`` is driven by its parent's scale."""
    for joint in cmds.ls(joints, type="joint") or []:
        parent = dag.get_parent(joint)
        if parent and cmds.nodeType(parent) == "joint":
            if not cmds.isConnected(parent + ".scale", joint + ".inverseScale"):
                cmds.connectAttr(parent + ".scale", joint + ".inverseScale", force=True)


def zero_end_orients(joints):
    """Zero the jointOrient of end joints (aligned to their parent)."""
    ends = [j for j in cmds.ls(joints, type="joint", long=True) or []
            if not cmds.listRelatives(j, children=True, type="joint")]
    orient_tools.orient_like_parent(ends)
    return ends


# ---------------------------------------------------------------------------
# Queries / hierarchy edits
# ---------------------------------------------------------------------------
def get_end_joints(roots):
    if isinstance(roots, str):
        roots = [roots]
    result = []
    for root in roots:
        joints = [root] + (cmds.listRelatives(root, allDescendents=True, type="joint", fullPath=True) or [])
        result.extend(j for j in joints if not cmds.listRelatives(j, children=True, type="joint"))
    return result


def delete_end_joints(roots):
    ends = get_end_joints(roots)
    if ends:
        cmds.delete(ends)
    return len(ends)


def chain_length(joints):
    positions = [transform.get_position(j) for j in joints]
    return sum(mathlib.distance(a, b) for a, b in zip(positions, positions[1:]))


def planarize_chain(joints):
    """Snap every joint of a chain onto the plane of first, mid and last joints.

    Run :func:`jeffy.joints.orient.orient_joints` with ``up_mode='plane'``
    afterwards for a perfectly planar IK ready chain.
    """
    positions = [transform.get_position(j) for j in joints]
    new_positions = mathlib.planarize(positions)
    uuids = cmds.ls(joints, uuid=True) or []
    for uid, position in zip(uuids, new_positions):
        joint = cmds.ls(uid, long=True)[0]
        with orient_tools.detached_children(joint):
            cmds.xform(joint, worldSpace=True, translation=position)
    return [cmds.ls(uid)[0] for uid in uuids]


def reparent_shapes_to_joints(nodes):
    """Move curve shapes under joints of the same name with a ``_JNT`` suffix
    (handy to make joints selectable through a control curve)."""
    moved = []
    for node in nodes:
        target = naming.short_name(node).rsplit("_", 1)[0] + "_" + naming.suffix("joint")
        if not cmds.objExists(target):
            continue
        for shape in dag.get_shapes(node):
            cmds.parent(shape, target, relative=True, shape=True)
            moved.append(shape)
    return moved
