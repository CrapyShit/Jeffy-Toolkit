"""Selection helpers."""

import fnmatch

from maya import cmds

from jeffy.core import naming


def ordered():
    return cmds.ls(orderedSelection=True) or []


def select_hierarchy(nodes=None, node_type="joint", add=False):
    """Select nodes and their descendants of ``node_type`` (None = all)."""
    nodes = nodes or cmds.ls(selection=True) or []
    result = []
    for node in nodes:
        kwargs = {"allDescendents": True, "fullPath": True}
        if node_type:
            kwargs["type"] = node_type
        descendants = cmds.listRelatives(node, **kwargs) or []
        if not node_type or cmds.nodeType(node) == node_type:
            result.append(cmds.ls(node, long=True)[0])
        result.extend(reversed(descendants))
    cmds.select(result, add=add, replace=not add)
    return result


def select_mirror(nodes=None, add=False):
    """Select the left/right counterparts of the selection."""
    nodes = nodes or cmds.ls(selection=True) or []
    mirrored = [m for m in (naming.find_mirror_node(n) for n in nodes) if m]
    if mirrored:
        cmds.select(mirrored, add=add, replace=not add)
    return mirrored


def select_by_pattern(pattern, node_type=None, add=False):
    """Select nodes whose short name matches a wildcard pattern (``*_CTL``)."""
    kwargs = {"long": True}
    if node_type:
        kwargs["type"] = node_type
    nodes = [n for n in cmds.ls(**kwargs) or [] if fnmatch.fnmatchcase(naming.short_name(n), pattern)]
    cmds.select(nodes, add=add, replace=not add)
    return nodes


def select_by_type(node_type, under=None):
    if under:
        nodes = cmds.listRelatives(under, allDescendents=True, type=node_type, fullPath=True) or []
    else:
        nodes = cmds.ls(type=node_type, long=True) or []
    cmds.select(nodes, replace=True)
    return nodes


def select_constraints(nodes=None):
    nodes = nodes or cmds.ls(selection=True) or []
    constraints = []
    for node in nodes:
        constraints.extend(cmds.listRelatives(node, type="constraint") or [])
        constraints.extend(cmds.listConnections(node, type="constraint", source=True, destination=False) or [])
    constraints = list(dict.fromkeys(constraints))
    cmds.select(constraints, replace=True)
    return constraints


def select_skin_joints(meshes=None):
    from jeffy.deformers import skin

    meshes = meshes or cmds.ls(selection=True, transforms=True) or []
    return skin.select_influences(meshes)


def create_quick_set(name, nodes=None):
    """Create (or extend) a quick selection set."""
    nodes = nodes or cmds.ls(selection=True) or []
    if cmds.objExists(name):
        cmds.sets(nodes, addElement=name)
        return name
    return cmds.sets(nodes, name=name, text="gCharacterSet")


def grow_hierarchy(nodes=None):
    """Add parents of the selection to the selection."""
    nodes = nodes or cmds.ls(selection=True) or []
    parents = [p for p in (cmds.listRelatives(n, parent=True) for n in nodes) if p]
    cmds.select([p[0] for p in parents], add=True)
