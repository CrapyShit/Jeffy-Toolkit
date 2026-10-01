"""DAG / hierarchy helpers."""

from maya import cmds

from jeffy.core import naming


def exists(node):
    return bool(node) and cmds.objExists(node)


def long_name(node):
    result = cmds.ls(node, long=True) or []
    return result[0] if result else None


def node_type(node):
    return cmds.nodeType(node)


def is_type(node, type_name):
    """True when ``node`` is (or inherits from) ``type_name``."""
    return bool(cmds.objectType(node, isAType=type_name))


def is_shape(node):
    return is_type(node, "shape")


def is_joint(node):
    return cmds.nodeType(node) == "joint"


def get_shapes(node, types=None, intermediate=False, full_path=True):
    """Shapes of a transform (non intermediate by default)."""
    if is_shape(node):
        return [node]
    shapes = cmds.listRelatives(node, shapes=True, fullPath=full_path) or []
    if not intermediate:
        shapes = [s for s in shapes if not cmds.getAttr(s + ".intermediateObject")]
    if types:
        types = [types] if isinstance(types, str) else types
        shapes = [s for s in shapes if cmds.nodeType(s) in types]
    return shapes


def get_shape(node, types=None):
    shapes = get_shapes(node, types=types)
    return shapes[0] if shapes else None


def get_orig_shapes(node):
    """Intermediate (``Orig``) shapes of a deformed object."""
    shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
    return [s for s in shapes if cmds.getAttr(s + ".intermediateObject")]


def get_transform(node):
    """Transform of a shape (or the node itself if it is a transform)."""
    if is_shape(node):
        return cmds.listRelatives(node, parent=True, fullPath=True)[0]
    return node


def get_parent(node):
    parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
    return parents[0] if parents else None


def get_children(node, node_types=None, full_path=False):
    kwargs = {"children": True, "fullPath": full_path}
    if node_types:
        kwargs["type"] = node_types
    return cmds.listRelatives(node, **kwargs) or []


def get_descendants(node, node_types=None, full_path=False):
    """All descendants in depth first order (parents before children)."""
    kwargs = {"allDescendents": True, "fullPath": True}
    if node_types:
        kwargs["type"] = node_types
    nodes = cmds.listRelatives(node, **kwargs) or []
    nodes = sorted(nodes, key=lambda n: (n.count("|"), n))
    if not full_path:
        nodes = [naming.short_name(n) for n in nodes]
    return nodes


def get_hierarchy(node, node_types=None, include_self=True):
    """Node + transform descendants ordered depth first (parents first)."""
    if isinstance(node_types, str):
        node_types = [node_types]
    result = []

    def walk(current):
        if not node_types or cmds.nodeType(current) in node_types:
            result.append(current)
        children = cmds.listRelatives(current, children=True, fullPath=True) or []
        for child in children:
            if cmds.objectType(child, isAType="transform"):
                walk(child)

    root = long_name(node)
    walk(root)
    if not include_self and result and result[0] == root:
        result = result[1:]
    return result


def get_root(node):
    current = long_name(node)
    while True:
        parent = get_parent(current)
        if not parent:
            return current
        current = parent


def get_chain(start, end=None):
    """Joints from ``start`` down to ``end`` (or to the first leaf).

    Follows the first child at every level when ``end`` is not given.
    Raises ``ValueError`` if ``end`` is not a descendant of ``start``.
    """
    start_long = long_name(start)
    if end:
        end_long = long_name(end)
        if not end_long.startswith(start_long + "|") and end_long != start_long:
            raise ValueError("%s is not below %s" % (end, start))
        chain = [end_long]
        current = end_long
        while current != start_long:
            current = get_parent(current)
            chain.append(current)
        return list(reversed(chain))
    chain = [start_long]
    current = start_long
    while True:
        children = cmds.listRelatives(current, children=True, type="joint", fullPath=True) or []
        if not children:
            break
        current = children[0]
        chain.append(current)
    return chain


def parent(node, new_parent=None):
    """Parent (or unparent when ``new_parent`` is None). Returns new name."""
    current = get_parent(node)
    if new_parent:
        if current and long_name(current) == long_name(new_parent):
            return node
        return cmds.parent(node, new_parent)[0]
    if not current:
        return node
    return cmds.parent(node, world=True)[0]


def create_group(name, parent_node=None, match=None, empty=True):
    """Create an empty transform optionally parented and matched to a node."""
    group = cmds.createNode("transform", name=name, skipSelect=True)
    if match:
        cmds.matchTransform(group, match, position=True, rotation=True, scale=False)
    if parent_node:
        group = cmds.parent(group, parent_node)[0]
    return group


def insert_parent(node, name, keep_world=True):
    """Insert a new transform between ``node`` and its parent.

    The new group is placed exactly at the node's world transform so the node
    ends up with identity local values (a *zero group*).
    """
    group = cmds.createNode("transform", name=name, skipSelect=True)
    parent_node = get_parent(node)
    if parent_node:
        group = cmds.parent(group, parent_node, relative=True)[0]
    if keep_world:
        cmds.matchTransform(group, node, position=True, rotation=True, scale=True)
        rotate_order = cmds.getAttr(node + ".rotateOrder")
        cmds.setAttr(group + ".rotateOrder", rotate_order)
    cmds.parent(node, group)
    return group


def get_mobject(node):
    from maya.api import OpenMaya as om

    selection = om.MSelectionList()
    selection.add(node)
    return selection.getDependNode(0)


def get_dag_path(node):
    from maya.api import OpenMaya as om

    selection = om.MSelectionList()
    selection.add(node)
    return selection.getDagPath(0)


def uuid(node):
    result = cmds.ls(node, uuid=True) or []
    return result[0] if result else None


def from_uuid(value):
    result = cmds.ls(value, long=True) or []
    return result[0] if result else None


def top_level_nodes(include_cameras=False):
    """Top level DAG nodes, without the default cameras."""
    result = []
    for node in cmds.ls(assemblies=True, long=True) or []:
        cameras = cmds.listRelatives(node, shapes=True, type="camera") or []
        if cameras and (not include_cameras or cmds.camera(node, query=True, startupCamera=True)):
            continue
        result.append(node)
    return result
