"""Mesh edge selections given to setup tools (edge loops and chains).

An edges slot holds component names (``face_GEO.e[120:131]``). These helpers
check them, put their vertices in order along the loop and find the mirrored
edges on the other side of the mesh.
"""

from maya import cmds
from maya.api import OpenMaya as om

from jeffy.core import naming
from jeffy.setups.core.schema import SetupError

EDGE_MASK = 32


def expand(edges):
    """Every edge of ``edges`` as its own name (``mesh.e[3]``)."""
    if not edges:
        return []
    try:
        return cmds.filterExpand(edges, selectionMask=EDGE_MASK, expand=True) or []
    except (RuntimeError, ValueError, TypeError):
        return []


def compact(edges):
    """Edge names merged into ranges (``mesh.e[3:9]``)."""
    selection = om.MSelectionList()
    for edge in expand(edges):
        selection.add(edge)
    return list(selection.getSelectionStrings())


def is_edges(values):
    """Are all ``values`` mesh edges?"""
    values = list(values or [])
    return bool(values) and all(expand([value]) for value in values)


def _dag_and_ids(edges):
    selection = om.MSelectionList()
    for edge in expand(edges):
        selection.add(edge)
    mesh, ids = None, set()
    for index in range(selection.length()):
        dag, component = selection.getComponent(index)
        if component.isNull() or component.apiType() != om.MFn.kMeshEdgeComponent:
            raise SetupError("Select mesh edges only")
        if mesh is None:
            mesh = dag
        elif dag.fullPathName() != mesh.fullPathName():
            raise SetupError("All the edges must be on the same mesh")
        ids.update(om.MFnSingleIndexedComponent(component).getElements())
    if mesh is None:
        raise SetupError("No edges given")
    return mesh, ids


def mesh_of(edges):
    """``(transform, shape)`` of the mesh the edges are on (short unique names)."""
    dag, _ids = _dag_and_ids(edges)
    shape = dag.fullPathName()
    if cmds.nodeType(shape) != "mesh":
        shape = (cmds.listRelatives(shape, shapes=True, noIntermediate=True, fullPath=True, type="mesh") or [shape])[0]
    transform = cmds.listRelatives(shape, parent=True, fullPath=True)[0]
    return cmds.ls(transform)[0], cmds.ls(shape)[0]


def ordered_loop(edges):
    """``(vertex ids, world points, closed)`` along the loop or chain.

    A closed loop starts at its left-most point (+X) and goes up first; an
    open chain runs from +X to -X.
    """
    dag, ids = _dag_and_ids(edges)
    if len(ids) < 2:
        raise SetupError("Select at least 2 connected edges")
    iterator = om.MItMeshEdge(dag)
    neighbours = {}
    for edge in ids:
        iterator.setIndex(edge)
        a, b = iterator.vertexId(0), iterator.vertexId(1)
        neighbours.setdefault(a, []).append(b)
        neighbours.setdefault(b, []).append(a)
    if any(len(found) > 2 for found in neighbours.values()):
        raise SetupError("The edges branch: select one single loop or chain")
    ends = [vertex for vertex, found in neighbours.items() if len(found) == 1]
    if len(ends) not in (0, 2):
        raise SetupError("The edges must form one continuous loop or chain")
    closed = not ends

    start = ends[0] if ends else next(iter(neighbours))
    order, seen, current = [start], {start}, start
    while True:
        following = [vertex for vertex in neighbours[current] if vertex not in seen]
        if not following:
            break
        current = following[0]
        order.append(current)
        seen.add(current)
    if len(order) != len(neighbours):
        raise SetupError("The edges are not all connected")

    points = om.MFnMesh(dag).getPoints(om.MSpace.kWorld)
    if closed:
        first = max(range(len(order)), key=lambda i: (points[order[i]].x, -i))
        order = order[first:] + order[:first]
        if points[order[1]].y < points[order[-1]].y:
            order = [order[0]] + order[1:][::-1]
    elif points[order[0]].x < points[order[-1]].x:
        order.reverse()
    return order, [(points[v].x, points[v].y, points[v].z) for v in order], closed


def side_of(edges):
    """``L`` / ``R`` / ``C`` from where the loop is (its centre's X)."""
    _ids, points, _closed = ordered_loop(edges)
    xs = [point[0] for point in points]
    centre = sum(xs) / len(xs)
    span = max(max(xs) - min(xs), max(p[1] for p in points) - min(p[1] for p in points), 1e-6)
    if centre > span * 0.05 and min(xs) > -span * 0.05:
        return naming.SIDE_LEFT
    if centre < -span * 0.05 and max(xs) < span * 0.05:
        return naming.SIDE_RIGHT
    return naming.SIDE_CENTER


def mirror(edges):
    """The edges on the other side of the mesh (across world X), compacted."""
    dag, ids = _dag_and_ids(edges)
    mesh = om.MFnMesh(dag)
    points = mesh.getPoints(om.MSpace.kWorld)
    xs = [p.x for p in points]
    tolerance = max(max(xs) - min(xs), 1e-6) * 0.01
    cache = {}

    def mirrored_vertex(vertex):
        if vertex in cache:
            return cache[vertex]
        point = points[vertex]
        target = om.MPoint(-point.x, point.y, point.z)
        _closest, face = mesh.getClosestPoint(target, om.MSpace.kWorld)
        found = min(mesh.getPolygonVertices(face), key=lambda v: points[v].distanceTo(target))
        if points[found].distanceTo(target) > tolerance:
            raise SetupError("The mesh is not symmetrical around vertex %d: no mirrored edges found" % vertex)
        cache[vertex] = found
        return found

    edge_iterator = om.MItMeshEdge(dag)
    vertex_iterator = om.MItMeshVertex(dag)
    transform = mesh_of(edges)[0]
    result = []
    for edge in sorted(ids):
        edge_iterator.setIndex(edge)
        a = mirrored_vertex(edge_iterator.vertexId(0))
        b = mirrored_vertex(edge_iterator.vertexId(1))
        vertex_iterator.setIndex(a)
        match = None
        for candidate in vertex_iterator.getConnectedEdges():
            edge_iterator.setIndex(candidate)
            if b in (edge_iterator.vertexId(0), edge_iterator.vertexId(1)):
                match = candidate
                break
        if match is None:
            raise SetupError("No mirrored edge for %s.e[%d]" % (transform, edge))
        result.append("%s.e[%d]" % (transform, match))
    return compact(result)
