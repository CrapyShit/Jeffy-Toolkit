"""Transform helpers: matching, offset groups, freezing, mirroring..."""

from maya import cmds

from jeffy.core import attributes, dag, mathlib, matrix, naming


def get_position(node):
    """World position of a node or the centre of components (``mesh.vtx[3]``)."""
    if "." in node:
        points = get_component_positions(node)
        return mathlib.centroid(points)
    return tuple(cmds.xform(node, query=True, worldSpace=True, rotatePivot=True))


def get_component_positions(components):
    """World positions of every (flattened) component."""
    flat = cmds.ls(components, flatten=True) or []
    positions = []
    for comp in flat:
        values = cmds.xform(comp, query=True, worldSpace=True, translation=True)
        for i in range(0, len(values), 3):
            positions.append(tuple(values[i:i + 3]))
    return positions


def get_center(nodes):
    """Centre of the bounding box of nodes/components."""
    points = []
    for node in nodes:
        if "." in node:
            points.extend(get_component_positions(node))
        else:
            points.append(get_position(node))
    mins, maxs = mathlib.bounding_box(points)
    return mathlib.midpoint(mins, maxs)


def set_position(node, position):
    cmds.xform(node, worldSpace=True, translation=position)


def match(node, target, translate=True, rotate=True, scale=False):
    """Snap ``node`` onto ``target`` (works for joints too)."""
    cmds.matchTransform(node, target, position=translate, rotation=rotate, scale=scale)


def distance(a, b):
    return mathlib.distance(get_position(a), get_position(b))


def reset(nodes, translate=True, rotate=True, scale=True):
    """Set transforms back to identity, skipping locked/connected channels."""
    if isinstance(nodes, str):
        nodes = [nodes]
    values = []
    if translate:
        values += [("tx", 0), ("ty", 0), ("tz", 0)]
    if rotate:
        values += [("rx", 0), ("ry", 0), ("rz", 0)]
    if scale:
        values += [("sx", 1), ("sy", 1), ("sz", 1)]
    for node in nodes:
        for attr, value in values:
            if attributes.is_settable(node, attr):
                cmds.setAttr("%s.%s" % (node, attr), value)


def freeze(nodes, translate=True, rotate=True, scale=True):
    cmds.makeIdentity(nodes, apply=True, translate=translate, rotate=rotate, scale=scale, normal=0,
                      preserveNormals=True)


def is_identity(node, tolerance=1e-4):
    return mathlib.is_identity(cmds.getAttr(node + ".matrix"), tolerance)


# ---------------------------------------------------------------------------
# Offset (zero) groups
# ---------------------------------------------------------------------------
def add_offset_groups(node, suffixes=("ZRO",), names=None):
    """Insert groups above ``node`` so it ends up with zero local transforms.

    Returns the created groups from top to bottom. ``names`` may override the
    generated names (``<node>_<suffix>``).
    """
    if isinstance(suffixes, str):
        suffixes = [suffixes]
    base = naming.short_name(node)
    groups = []
    for i, sfx in enumerate(suffixes):
        name = names[i] if names else "%s_%s" % (base, sfx)
        groups.append(dag.insert_parent(node, naming.unique_name(name)))
    # insert_parent puts each new group directly above the node, so the
    # creation order is bottom -> top; return top -> bottom.
    groups.reverse()
    if cmds.nodeType(node) == "joint":
        # joints keep their orientation in jointOrient - move it to the group
        cmds.setAttr(node + ".jointOrient", 0, 0, 0)
        cmds.setAttr(node + ".rotate", 0, 0, 0)
    return groups


def bake_to_offset_parent_matrix(nodes):
    """Move the local transform into ``offsetParentMatrix`` and zero TRS.

    The modern (Maya 2020+) alternative to zero groups.
    """
    if isinstance(nodes, str):
        nodes = [nodes]
    for node in nodes:
        world = matrix.get_world_matrix(node)
        parent_world = cmds.getAttr(node + ".parentMatrix[0]")
        new_offset = mathlib.mult(world, mathlib.inverse(parent_world))
        matrix.set_matrix_attr(node + ".offsetParentMatrix", new_offset)
        reset(node)
        if cmds.nodeType(node) == "joint":
            cmds.setAttr(node + ".jointOrient", 0, 0, 0)


def unbake_offset_parent_matrix(nodes):
    """Move ``offsetParentMatrix`` back into translate/rotate/scale."""
    if isinstance(nodes, str):
        nodes = [nodes]
    for node in nodes:
        world = matrix.get_world_matrix(node)
        matrix.set_matrix_attr(node + ".offsetParentMatrix", mathlib.identity())
        matrix.set_world_matrix(node, world)


# ---------------------------------------------------------------------------
# Creation helpers
# ---------------------------------------------------------------------------
def create_locator(name, position=None, match_node=None, parent=None, size=1.0):
    locator = cmds.spaceLocator(name=name)[0]
    shape = dag.get_shape(locator)
    cmds.setAttr(shape + ".localScale", size, size, size)
    if match_node:
        match(locator, match_node)
    elif position is not None:
        set_position(locator, position)
    if parent:
        locator = cmds.parent(locator, parent)[0]
    return locator


def locators_at(nodes, name="loc", size=1.0, orient=True):
    """One locator per node/component (``orient`` copies the rotation)."""
    result = []
    for node in nodes:
        loc = create_locator(naming.unique_name("%s_%s" % (naming.strip_namespace(node).split(".")[0], name)),
                             size=size)
        if "." in node:
            set_position(loc, get_position(node))
        else:
            match(loc, node, rotate=orient)
        result.append(loc)
    return result


def locator_at_center(nodes, name="center_LOC"):
    loc = create_locator(naming.unique_name(name))
    set_position(loc, get_center(nodes))
    return loc


# ---------------------------------------------------------------------------
# Aiming / mirroring
# ---------------------------------------------------------------------------
def aim_at(node, target, aim_axis="x", up_axis="y", world_up=(0, 1, 0), up_object=None):
    """Rotate ``node`` so ``aim_axis`` points to ``target`` (no constraint)."""
    origin = get_position(node)
    up_point = get_position(up_object) if up_object else None
    mtx = matrix.matrix_from_points(origin, get_position(target), up_point, aim_axis, up_axis, world_up)
    current_scale = mathlib.get_scale(matrix.get_world_matrix(node))
    x, y, z, t = mathlib.axes(mtx)
    mtx = mathlib.from_axes(mathlib.scale(x, current_scale[0]), mathlib.scale(y, current_scale[1]),
                            mathlib.scale(z, current_scale[2]), t)
    matrix.set_world_matrix(node, mtx, translate=False, scale=False)


def mirror(node, target=None, axis="x", mode="behavior"):
    """Mirror the world transform of ``node`` onto ``target``.

    When ``target`` is omitted the mirrored node is found by name
    (``L_`` <-> ``R_``); if none exists ``node`` itself is mirrored.
    """
    target = target or naming.find_mirror_node(node) or node
    mirrored = matrix.mirror_world_matrix(node, axis=axis, mode=mode)
    matrix.set_world_matrix(target, mirrored)
    return target


def snap_pivot(node, target):
    position = get_position(target)
    cmds.xform(node, worldSpace=True, pivots=position)


def center_pivot(nodes):
    cmds.xform(nodes, centerPivots=True)


def copy_rotate_order(source, targets):
    order = cmds.getAttr(source + ".rotateOrder")
    for target in [targets] if isinstance(targets, str) else targets:
        cmds.setAttr(target + ".rotateOrder", order)
