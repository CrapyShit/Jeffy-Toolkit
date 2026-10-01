"""Scene tools for NURBS curve shapes: create, replace, mirror, scale, save..."""

import os

from maya import cmds

from jeffy.controls import library
from jeffy.core import color, dag, fileio, mathlib, naming


# ---------------------------------------------------------------------------
# Creation / data
# ---------------------------------------------------------------------------
def _create_curve(curve, name):
    points = [tuple(p) for p in curve["points"]]
    degree = curve.get("degree", 1)
    periodic = bool(curve.get("periodic", False)) and degree > 1
    if periodic:
        points = points + points[:degree]
    knots = library.knots_for(len(points), degree, periodic)
    return cmds.curve(name=name, degree=degree, point=points, knot=knots, periodic=periodic)


def create_curves(curves, name="curve"):
    """Create a transform holding one nurbsCurve shape per curve dict."""
    library.validate(curves)
    transform = None
    for curve in curves:
        node = _create_curve(curve, name if transform is None else name + "_tmp")
        if transform is None:
            transform = node
            continue
        shape = dag.get_shapes(node)[0]
        cmds.parent(shape, transform, relative=True, shape=True)
        cmds.delete(node)
    naming.fix_shape_names([transform])
    return transform


def create_shape(shape="circle", name="curve", size=1.0, axis="y", offset=(0.0, 0.0, 0.0)):
    curves = library.transform_shape(library.get_shape(shape), size=size, axis=axis, offset=offset)
    return create_curves(curves, name)


def curve_shapes(node):
    return dag.get_shapes(node, types="nurbsCurve")


def get_cvs(node):
    return ["%s.cv[*]" % shape for shape in curve_shapes(node)]


def _cv_positions(shape, world=False):
    flat = cmds.xform(shape + ".cv[*]", query=True, worldSpace=world, objectSpace=not world, translation=True)
    return [tuple(flat[i:i + 3]) for i in range(0, len(flat), 3)]


def get_shape_data(node, world=False):
    """Serializable curve data of every nurbsCurve shape under ``node``."""
    data = []
    for shape in curve_shapes(node):
        degree = cmds.getAttr(shape + ".degree")
        form = cmds.getAttr(shape + ".form")
        spans = cmds.getAttr(shape + ".spans")
        points = _cv_positions(shape, world)
        periodic = form == 2
        if periodic:
            points = points[:spans]
        data.append({"points": points, "degree": degree, "periodic": periodic})
    return data


def set_shape_data(node, curves, keep_color=True, keep_line_width=True):
    """Replace the curve shapes of ``node`` with ``curves`` (object space)."""
    old_shapes = curve_shapes(node)
    old_color = color.get_color(node) if keep_color else None
    width = None
    if keep_line_width and old_shapes and cmds.attributeQuery("lineWidth", node=old_shapes[0], exists=True):
        width = cmds.getAttr(old_shapes[0] + ".lineWidth")
    temp = create_curves(curves, naming.short_name(node) + "_shapeTmp")
    new_shapes = dag.get_shapes(temp)
    if old_shapes:
        cmds.delete(old_shapes)
    for shape in new_shapes:
        cmds.parent(shape, node, relative=True, shape=True)
    cmds.delete(temp)
    naming.fix_shape_names([node])
    if old_color is not None:
        color.set_color(node, old_color)
    if width is not None:
        set_line_width(node, width)
    return curve_shapes(node)


def replace_shape(nodes, shape="circle", size=None, axis="y"):
    """Swap the shape of controls keeping colour (``size=None`` keeps size)."""
    if isinstance(nodes, str):
        nodes = [nodes]
    for node in nodes:
        scale = size
        if scale is None:
            scale = _shape_radius(node) or 1.0
        curves = library.transform_shape(library.get_shape(shape), size=scale, axis=axis)
        set_shape_data(node, curves)


def _shape_radius(node):
    points = []
    for curve in get_shape_data(node):
        points.extend(curve["points"])
    if not points:
        return None
    return max(mathlib.length(p) for p in points) or None


def copy_shape(source, targets, world=False):
    """Copy the curve shapes of ``source`` to ``targets``.

    With ``world=True`` the copied shape keeps its world space placement,
    otherwise it is copied in object space (relative to each target).
    """
    if isinstance(targets, str):
        targets = [targets]
    data = get_shape_data(source, world=False)
    for target in targets:
        set_shape_data(target, data)
        if world:
            for src_shape, dst_shape in zip(curve_shapes(source), curve_shapes(target)):
                positions = _cv_positions(src_shape, world=True)
                for i, pos in enumerate(positions):
                    cmds.xform("%s.cv[%d]" % (dst_shape, i), worldSpace=True, translation=pos)


def mirror_shape(source, target=None, axis="x"):
    """Mirror the world space CVs of ``source`` onto ``target``.

    The target's shape topology is replaced by the source's if they differ.
    When ``target`` is None the mirrored node is found by name.
    """
    target = target or naming.find_mirror_node(source)
    if not target:
        raise ValueError("No mirror target found for %s" % source)
    src_shapes = curve_shapes(source)
    dst_shapes = curve_shapes(target)
    same = len(src_shapes) == len(dst_shapes) and all(
        cmds.getAttr(a + ".spans") == cmds.getAttr(b + ".spans")
        and cmds.getAttr(a + ".degree") == cmds.getAttr(b + ".degree")
        for a, b in zip(src_shapes, dst_shapes)
    )
    if not same:
        set_shape_data(target, get_shape_data(source))
        dst_shapes = curve_shapes(target)
    for src, dst in zip(src_shapes, dst_shapes):
        positions = _cv_positions(src, world=True)
        for i, pos in enumerate(positions):
            cmds.xform("%s.cv[%d]" % (dst, i), worldSpace=True, translation=mathlib.reflect(pos, axis))
    return target


def mirror_shapes(nodes, axis="x"):
    """Mirror shapes of every node onto its ``L``/``R`` counterpart."""
    done = []
    for node in nodes:
        target = naming.find_mirror_node(node)
        if target and target not in done:
            mirror_shape(node, target, axis)
            done.append(target)
    return done


# ---------------------------------------------------------------------------
# Editing
# ---------------------------------------------------------------------------
def _pivot(node):
    return cmds.xform(node, query=True, worldSpace=True, rotatePivot=True)


def scale_shapes(nodes, factor):
    """Scale CVs around the object's pivot (``factor`` float or xyz tuple)."""
    if isinstance(nodes, str):
        nodes = [nodes]
    if isinstance(factor, (int, float)):
        factor = (factor, factor, factor)
    for node in nodes:
        cvs = get_cvs(node)
        if cvs:
            cmds.scale(factor[0], factor[1], factor[2], cvs, relative=True, pivot=_pivot(node), objectSpace=True)


def rotate_shapes(nodes, rotation):
    """Rotate CVs in object space around the pivot, e.g. ``(90, 0, 0)``."""
    if isinstance(nodes, str):
        nodes = [nodes]
    for node in nodes:
        cvs = get_cvs(node)
        if cvs:
            cmds.rotate(rotation[0], rotation[1], rotation[2], cvs, relative=True, objectSpace=True,
                        pivot=_pivot(node))


def translate_shapes(nodes, offset, object_space=True):
    if isinstance(nodes, str):
        nodes = [nodes]
    for node in nodes:
        cvs = get_cvs(node)
        if cvs:
            cmds.move(offset[0], offset[1], offset[2], cvs, relative=True, objectSpace=object_space,
                      worldSpace=not object_space)


def set_line_width(nodes, width):
    """Curve line thickness (Maya 2022+ ``lineWidth``; -1 = preference)."""
    if isinstance(nodes, str):
        nodes = [nodes]
    for node in nodes:
        for shape in curve_shapes(node):
            if cmds.attributeQuery("lineWidth", node=shape, exists=True):
                cmds.setAttr(shape + ".lineWidth", width)


def set_always_on_top(nodes, state=True):
    if isinstance(nodes, str):
        nodes = [nodes]
    for node in nodes:
        for shape in curve_shapes(node):
            cmds.setAttr(shape + ".alwaysDrawOnTop", state)


def _absorb_shapes(node, target):
    """Move the curve shapes of ``node`` under ``target`` keeping world placement."""
    if dag.get_parent(node) != dag.long_name(target):
        node = cmds.parent(node, target)[0]
    cmds.makeIdentity(node, apply=True, translate=True, rotate=True, scale=True)
    for shape in curve_shapes(node):
        cmds.parent(shape, target, relative=True, shape=True)
    if not cmds.listRelatives(node, children=True):
        cmds.delete(node)


def combine(nodes):
    """Parent every curve shape under the first transform (world kept)."""
    if not nodes:
        return None
    target = nodes[0]
    for node in nodes[1:]:
        _absorb_shapes(node, target)
    naming.fix_shape_names([target])
    return target


def text_curves(text, name="text_CTL", font="Arial"):
    """Create curves from a string, combined under one transform."""
    created = cmds.textCurves(text=text, font=font, name=name + "_tmp")[0]
    shapes = cmds.listRelatives(created, allDescendents=True, type="nurbsCurve", fullPath=True) or []
    letters = []
    for shape in shapes:
        parent = cmds.listRelatives(shape, parent=True, fullPath=True)[0]
        if parent not in letters:
            letters.append(parent)
    transform = cmds.createNode("transform", name=name, skipSelect=True)
    uuids = cmds.ls(letters, uuid=True) or []
    for uid in uuids:
        letter = cmds.ls(uid, long=True)[0]
        _absorb_shapes(letter, transform)
    if cmds.objExists(created):
        cmds.delete(created)
    cmds.xform(transform, centerPivots=True)
    naming.fix_shape_names([transform])
    return transform


# ---------------------------------------------------------------------------
# Library IO
# ---------------------------------------------------------------------------
def save_to_library(node, name=None):
    """Save the (object space) shape of ``node`` as a reusable library shape."""
    name = naming.legalize(name or naming.strip_namespace(node))
    path = os.path.join(library.user_library_dir(), name + ".json")
    fileio.write_json(path, {"name": name, "curves": get_shape_data(node)})
    return path


def delete_from_library(name):
    path = os.path.join(library.user_library_dir(), name + ".json")
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False


def export_shapes(path, nodes):
    """Write shapes + colours of nodes to a JSON file (keyed by short name)."""
    data = {}
    for node in nodes:
        entry = {"curves": get_shape_data(node)}
        node_color = color.get_color(node)
        if node_color is not None:
            entry["color"] = node_color
        data[naming.strip_namespace(node)] = entry
    return fileio.write_json(path, {"version": fileio.FORMAT_VERSION, "type": "shapes", "shapes": data})


def import_shapes(path, nodes=None, namespace=""):
    """Apply shapes from :func:`export_shapes` to matching scene nodes."""
    data = fileio.read_json(path)["shapes"]
    applied = []
    wanted = set(naming.strip_namespace(n) for n in nodes) if nodes else None
    for name, entry in data.items():
        if wanted is not None and name not in wanted:
            continue
        full = "%s:%s" % (namespace, name) if namespace else name
        if not cmds.objExists(full):
            continue
        set_shape_data(full, entry["curves"], keep_color=False)
        if "color" in entry:
            value = entry["color"]
            color.set_color(full, tuple(value) if isinstance(value, list) else value)
        applied.append(full)
    return applied
