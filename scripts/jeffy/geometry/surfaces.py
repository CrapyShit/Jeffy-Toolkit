"""NURBS surface helpers (ribbons)."""

from maya import cmds
from maya.api import OpenMaya as om

from jeffy.core import dag, mathlib, naming, transform


def _fn_surface(surface):
    shape = dag.get_shape(surface, types="nurbsSurface") if cmds.nodeType(surface) != "nurbsSurface" else surface
    if not shape:
        raise ValueError("%s is not a nurbs surface" % surface)
    return om.MFnNurbsSurface(dag.get_dag_path(shape))


def ribbon_from_points(points, width=1.0, up_vector=(0.0, 0.0, 1.0), name="ribbon_SRF", spans=None, degree=3,
                       normal_axis=None):
    """Loft a ribbon surface along ``points``.

    The ribbon width is measured along ``up_vector`` (projected so that it
    stays perpendicular to the chain). U runs along the points, V across.
    """
    points = [tuple(p) for p in points]
    if len(points) < 2:
        raise ValueError("Need at least two points")
    half = width / 2.0
    side_a, side_b = [], []
    for i, point in enumerate(points):
        if i < len(points) - 1:
            direction = mathlib.sub(points[i + 1], point)
        else:
            direction = mathlib.sub(point, points[i - 1])
        side = mathlib.cross(mathlib.normalize(direction), up_vector)
        offset_dir = mathlib.normalize(mathlib.cross(side, mathlib.normalize(direction)))
        if mathlib.length(offset_dir) < 1e-6:
            offset_dir = mathlib.normalize(up_vector)
        side_a.append(mathlib.add(point, mathlib.scale(offset_dir, half)))
        side_b.append(mathlib.sub(point, mathlib.scale(offset_dir, half)))
    curve_degree = min(degree, len(points) - 1)
    curve_a = cmds.curve(degree=curve_degree, editPoint=side_a) if curve_degree > 1 else cmds.curve(
        degree=1, point=side_a)
    curve_b = cmds.curve(degree=curve_degree, editPoint=side_b) if curve_degree > 1 else cmds.curve(
        degree=1, point=side_b)
    surface = cmds.loft(curve_a, curve_b, name=naming.unique_name(name), constructionHistory=False, uniform=True,
                        degree=1, sectionSpans=1, range=False, polygon=0)[0]
    cmds.delete(curve_a, curve_b)
    ensure_u_along_length(surface)
    if spans:
        cmds.rebuildSurface(surface, constructionHistory=False, replaceOriginal=True, rebuildType=0, endKnots=1,
                            keepRange=0, keepControlPoints=False, keepCorners=False, spansU=spans, degreeU=degree,
                            spansV=1, degreeV=1, direction=0)
    naming.fix_shape_names([surface])
    return surface


def ensure_u_along_length(surface):
    """Swap U and V if needed so that U runs along the long side."""
    along_u = mathlib.distance(point_at_uv(surface, 0.0, 0.5), point_at_uv(surface, 1.0, 0.5))
    along_v = mathlib.distance(point_at_uv(surface, 0.5, 0.0), point_at_uv(surface, 0.5, 1.0))
    if along_v > along_u:
        cmds.reverseSurface(surface, direction=3, constructionHistory=False, replaceOriginal=True)
    return surface


def ribbon_from_nodes(node_list, width=1.0, up_vector=(0.0, 0.0, 1.0), name="ribbon_SRF", spans=None):
    return ribbon_from_points([transform.get_position(n) for n in node_list], width, up_vector, name, spans)


def closest_uv(surface, point, normalized=True):
    """Closest ``(u, v)`` on a surface (0..1 when ``normalized``)."""
    fn = _fn_surface(surface)
    _point, u, v = fn.closestPoint(om.MPoint(*point), space=om.MSpace.kWorld)
    if normalized:
        u_start, u_end = fn.knotDomainInU
        v_start, v_end = fn.knotDomainInV
        u = (u - u_start) / (u_end - u_start) if u_end != u_start else 0.0
        v = (v - v_start) / (v_end - v_start) if v_end != v_start else 0.0
    return u, v


def point_at_uv(surface, u, v, normalized=True):
    fn = _fn_surface(surface)
    if normalized:
        u_start, u_end = fn.knotDomainInU
        v_start, v_end = fn.knotDomainInV
        u = u_start + (u_end - u_start) * u
        v = v_start + (v_end - v_start) * v
    point = fn.getPointAtParam(u, v, om.MSpace.kWorld)
    return (point.x, point.y, point.z)
