"""Mesh helpers (OpenMaya 2.0 for speed)."""

import re

from maya import cmds
from maya.api import OpenMaya as om

from jeffy.core import dag, naming


def _mesh_shape(mesh):
    if cmds.nodeType(mesh) == "mesh":
        return mesh
    shapes = dag.get_shapes(mesh, types="mesh")
    if not shapes:
        raise ValueError("%s has no mesh shape" % mesh)
    return shapes[0]


def _fn_mesh(mesh):
    return om.MFnMesh(dag.get_dag_path(_mesh_shape(mesh)))


def _space(world):
    return om.MSpace.kWorld if world else om.MSpace.kObject


def get_points(mesh, world=True):
    """Vertex positions as a list of tuples."""
    points = _fn_mesh(mesh).getPoints(_space(world))
    return [(p.x, p.y, p.z) for p in points]


def set_points(mesh, points, world=False, undoable=False):
    """Set vertex positions.

    The API call is *not undoable*: by default use it on freshly created
    meshes (e.g. new blendshape targets). With ``undoable=True`` positions
    are set per vertex through ``cmds.xform`` (slower but undoable).
    """
    if undoable:
        shape = _mesh_shape(mesh)
        current = get_points(mesh, world)
        for i, (old, new) in enumerate(zip(current, points)):
            if any(abs(a - b) > 1e-7 for a, b in zip(old, new)):
                cmds.xform("%s.vtx[%d]" % (shape, i), worldSpace=world, objectSpace=not world, translation=new)
        return
    array = om.MPointArray()
    for p in points:
        array.append(om.MPoint(p[0], p[1], p[2]))
    _fn_mesh(mesh).setPoints(array, _space(world))


def vertex_count(mesh):
    return _fn_mesh(mesh).numVertices


def face_count(mesh):
    return _fn_mesh(mesh).numPolygons


def same_topology(mesh_a, mesh_b):
    a, b = _fn_mesh(mesh_a), _fn_mesh(mesh_b)
    return a.numVertices == b.numVertices and a.numPolygons == b.numPolygons and a.numEdges == b.numEdges


def get_neighbors(mesh):
    """``neighbors[i]`` = list of vertex indices connected to vertex ``i``."""
    iterator = om.MItMeshVertex(dag.get_dag_path(_mesh_shape(mesh)))
    result = []
    while not iterator.isDone():
        result.append(list(iterator.getConnectedVertices()))
        iterator.next()
    return result


def get_face_vertices(mesh):
    """List of vertex index lists per face."""
    fn = _fn_mesh(mesh)
    return [list(fn.getPolygonVertices(i)) for i in range(fn.numPolygons)]


def closest_point(mesh, point, world=True):
    """``(position, face_index)`` of the closest point on the mesh surface."""
    result, face = _fn_mesh(mesh).getClosestPoint(om.MPoint(*point), _space(world))
    return (result.x, result.y, result.z), face


def closest_normal(mesh, point, world=True):
    _point, normal, _face = _fn_mesh(mesh).getClosestPointAndNormal(om.MPoint(*point), _space(world))
    return (normal.x, normal.y, normal.z)


def closest_uv(mesh, point, world=True, uv_set=None):
    """UV coordinates of the closest point on the mesh."""
    fn = _fn_mesh(mesh)
    uv_set = uv_set or fn.currentUVSetName()
    result = fn.getUVAtPoint(om.MPoint(*point), _space(world), uv_set)
    return result[0], result[1]


def closest_vertex(mesh, point, world=True):
    """Index of the vertex closest to ``point``."""
    fn = _fn_mesh(mesh)
    _pos, face = closest_point(mesh, point, world)
    points = fn.getPoints(_space(world))
    target = om.MPoint(*point)
    best = None
    best_dist = None
    for index in fn.getPolygonVertices(face):
        dist = points[index].distanceTo(target)
        if best is None or dist < best_dist:
            best, best_dist = index, dist
    return best


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------
_INDEX_RE = re.compile(r"\[(\d+)(?::(\d+))?\]")


def to_vertices(components):
    """Convert any component selection to flattened vertex names."""
    converted = cmds.polyListComponentConversion(components, toVertex=True) or []
    return cmds.ls(converted, flatten=True) or []


def vertex_indices(components):
    """``{mesh_shape_or_transform: [indices]}`` from a component selection."""
    result = {}
    for vertex in to_vertices(components):
        node, _, rest = vertex.partition(".")
        match = _INDEX_RE.search(rest)
        if match:
            result.setdefault(node, []).append(int(match.group(1)))
    return result


def selected_vertices():
    return vertex_indices(cmds.ls(selection=True) or [])


def compress_indices(indices):
    """``[1, 2, 3, 7]`` -> ``['1:3', '7']`` (for compact component lists)."""
    indices = sorted(set(indices))
    ranges = []
    start = prev = None
    for index in indices:
        if start is None:
            start = prev = index
        elif index == prev + 1:
            prev = index
        else:
            ranges.append((start, prev))
            start = prev = index
    if start is not None:
        ranges.append((start, prev))
    return ["%d:%d" % (a, b) if a != b else "%d" % a for a, b in ranges]


def component_list(mesh, indices, component="vtx"):
    return ["%s.%s[%s]" % (mesh, component, r) for r in compress_indices(indices)]


# ---------------------------------------------------------------------------
# Duplication / cleanup
# ---------------------------------------------------------------------------
def duplicate_clean(mesh, name=None, parent=None):
    """Duplicate the current (deformed) state of a mesh without history,
    intermediate shapes, locked channels or set memberships."""
    name = naming.unique_name(name or naming.short_name(mesh) + "_dup")
    dup = cmds.duplicate(mesh, name=name, returnRootsOnly=True)[0]
    for shape in dag.get_orig_shapes(dup):
        cmds.delete(shape)
    for attr in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz", "v"):
        cmds.setAttr("%s.%s" % (dup, attr), lock=False, keyable=True)
    children = [c for c in cmds.listRelatives(dup, children=True, fullPath=True) or []
                if cmds.objectType(c, isAType="transform")]
    if children:
        cmds.delete(children)
    if parent:
        dup = cmds.parent(dup, parent)[0]
    elif dag.get_parent(dup):
        dup = cmds.parent(dup, world=True)[0]
    naming.fix_shape_names([dup])
    return dup


def delete_history(meshes, non_deformer_only=True):
    """Delete construction history (keeping skin/blendshapes by default)."""
    if isinstance(meshes, str):
        meshes = [meshes]
    for mesh in meshes:
        if non_deformer_only:
            cmds.bakePartialHistory(mesh, prePostDeformers=True)
        else:
            cmds.delete(mesh, constructionHistory=True)


def delete_unused_orig_shapes(meshes):
    """Delete intermediate shapes that have no outgoing connections."""
    deleted = []
    for mesh in meshes:
        for shape in dag.get_orig_shapes(mesh):
            if not cmds.listConnections(shape, source=False, destination=True):
                cmds.delete(shape)
                deleted.append(shape)
    return deleted
