"""NURBS curve helpers."""

from maya import cmds
from maya.api import OpenMaya as om

from jeffy.core import dag, mathlib, naming, nodes, transform


def _fn_curve(curve):
    shape = dag.get_shape(curve, types="nurbsCurve") if cmds.nodeType(curve) != "nurbsCurve" else curve
    if not shape:
        raise ValueError("%s is not a nurbs curve" % curve)
    return om.MFnNurbsCurve(dag.get_dag_path(shape))


def curve_from_points(points, name="curve_CRV", degree=3, through=True):
    """Create a curve from positions.

    ``through=True`` creates the curve through the points (edit points),
    otherwise the points are used as CVs.
    """
    points = [tuple(p) for p in points]
    degree = min(degree, len(points) - 1)
    if degree < 1:
        raise ValueError("Need at least two points")
    if through and degree > 1:
        curve = cmds.curve(name=naming.unique_name(name), degree=degree, editPoint=points)
    else:
        curve = cmds.curve(name=naming.unique_name(name), degree=degree, point=points)
    naming.fix_shape_names([curve])
    return curve


def curve_from_nodes(node_list, name="curve_CRV", degree=3, through=False):
    return curve_from_points([transform.get_position(n) for n in node_list], name, degree, through)


def curve_from_edges(edges, name="curve_CRV", degree=3):
    """Create a curve from an edge loop/selection (``polyToCurve``)."""
    result = cmds.polyToCurve(edges, form=2, degree=degree, conformToSmoothMeshPreview=False)
    curve = cmds.rename(result[0], naming.unique_name(name))
    cmds.delete(curve, constructionHistory=True)
    return curve


def get_cv_positions(curve, world=True):
    shape = dag.get_shape(curve) if cmds.nodeType(curve) != "nurbsCurve" else curve
    flat = cmds.xform(shape + ".cv[*]", query=True, worldSpace=world, objectSpace=not world, translation=True)
    return [tuple(flat[i:i + 3]) for i in range(0, len(flat), 3)]


def cv_count(curve):
    return _fn_curve(curve).numCVs


def length(curve):
    return _fn_curve(curve).length()


def param_at_length(curve, distance):
    return _fn_curve(curve).findParamFromLength(distance)


def point_at_param(curve, param, world=True):
    point = _fn_curve(curve).getPointAtParam(param, om.MSpace.kWorld if world else om.MSpace.kObject)
    return (point.x, point.y, point.z)


def closest_param(curve, point, world=True):
    _point, param = _fn_curve(curve).closestPoint(om.MPoint(*point),
                                                  space=om.MSpace.kWorld if world else om.MSpace.kObject)
    return param


def params_along(curve, count, by_length=True):
    """``count`` parameters spread along the curve (evenly by arc length)."""
    fn = _fn_curve(curve)
    if count == 1:
        fractions = [0.5]
    else:
        fractions = mathlib.distribute(count, 0.0, 1.0)
    if by_length:
        total = fn.length()
        return [fn.findParamFromLength(min(total, f * total)) for f in fractions]
    start, end = fn.knotDomain
    return [start + (end - start) * f for f in fractions]


def positions_along(curve, count, by_length=True):
    return [point_at_param(curve, p) for p in params_along(curve, count, by_length)]


def rebuild(curve, spans=4, degree=3, keep_range=0):
    """Rebuild a curve in place (uniform parameterisation 0..1 by default)."""
    cmds.rebuildCurve(curve, constructionHistory=False, replaceOriginal=True, rebuildType=0, endKnots=1,
                      keepRange=keep_range, keepControlPoints=False, keepEndPoints=True, keepTangents=False,
                      spans=spans, degree=degree)
    return curve


def reverse(curve):
    cmds.reverseCurve(curve, constructionHistory=False, replaceOriginal=True)
    return curve


def create_connector_line(start, end, name="connector_CRV", parent=None, template=True):
    """Linear curve that always connects two transforms (e.g. pole vector line).

    The CVs are driven by the world positions of ``start`` and ``end``; the
    curve does not inherit transforms so it can live anywhere in the rig.
    """
    curve = cmds.curve(name=naming.unique_name(name), degree=1, point=[(0, 0, 0), (0, 0, 0)])
    naming.fix_shape_names([curve])
    shape = dag.get_shape(curve)
    for index, node in enumerate((start, end)):
        dm = nodes.decompose_matrix(node + ".worldMatrix[0]", name="%s_%s_DM" % (naming.short_name(curve), index))
        cmds.connectAttr(dm + ".outputTranslate", "%s.controlPoints[%d]" % (shape, index))
    if parent:
        curve = cmds.parent(curve, parent)[0]
    cmds.setAttr(curve + ".inheritsTransform", 0)
    for attr in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"):
        cmds.setAttr("%s.%s" % (curve, attr), lock=True)
    if template:
        cmds.setAttr(shape + ".overrideEnabled", 1)
        cmds.setAttr(shape + ".overrideDisplayType", 1)
    return curve


def attach_to_curve(node, curve, param=None, percent=True, use_tangent=False, up_object=None, name=None):
    """Attach a transform to a curve with ``pointOnCurveInfo``.

    ``param`` is a 0..1 fraction when ``percent`` is on. When ``use_tangent``
    is on an aimConstraint-like orientation is built with a ``motionPath``.
    Returns the info (or motionPath) node.
    """
    shape = dag.get_shape(curve)
    if param is None:
        param = closest_param(curve, transform.get_position(node))
        if percent:
            fn = _fn_curve(curve)
            start, end = fn.knotDomain
            param = (param - start) / (end - start) if end != start else 0.0
    base = name or naming.short_name(node)
    if use_tangent:
        path = cmds.createNode("motionPath", name=naming.unique_name(base + "_MP"), skipSelect=True)
        cmds.connectAttr(shape + ".worldSpace[0]", path + ".geometryPath")
        cmds.setAttr(path + ".fractionMode", percent)
        cmds.setAttr(path + ".uValue", param)
        cmds.setAttr(path + ".follow", 1)
        if up_object:
            cmds.setAttr(path + ".worldUpType", 1)  # object up
            cmds.connectAttr(up_object + ".worldMatrix[0]", path + ".worldUpMatrix")
        cmds.connectAttr(path + ".allCoordinates", node + ".translate")
        cmds.connectAttr(path + ".rotate", node + ".rotate")
        cmds.connectAttr(node + ".rotateOrder", path + ".rotateOrder")
        return path
    info = cmds.createNode("pointOnCurveInfo", name=naming.unique_name(base + "_POCI"), skipSelect=True)
    cmds.connectAttr(shape + ".worldSpace[0]", info + ".inputCurve")
    cmds.setAttr(info + ".turnOnPercentage", percent)
    cmds.setAttr(info + ".parameter", param)
    parent = dag.get_parent(node)
    if parent:
        mm = nodes.compose_matrix(translate=info + ".position")
        local = nodes.mult_matrix([mm, parent + ".worldInverseMatrix[0]"])
        dm = nodes.decompose_matrix(local)
        cmds.connectAttr(dm + ".outputTranslate", node + ".translate", force=True)
    else:
        cmds.connectAttr(info + ".position", node + ".translate", force=True)
    return info


def curve_from_joints(joints, name="curve_CRV", degree=3, spans=None):
    """Curve through joint positions, optionally rebuilt to ``spans`` spans."""
    curve = curve_from_points([transform.get_position(j) for j in joints], name, degree, through=True)
    if spans:
        rebuild(curve, spans=spans, degree=degree)
    return curve
