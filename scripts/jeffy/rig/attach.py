"""Attach transforms to meshes, surfaces and curves (rivets, follicles, uvPin).

::

    from jeffy.rig import attach
    attach.attach_to_geometry("L_brow_ZRO", "head_GEO")          # follicle rivet
    attach.attach_to_geometry("L_brow_ZRO", "head_GEO", method="uvPin")
    attach.rivets_on_selection()                                 # select components
"""

from maya import cmds

from jeffy.core import dag, mathlib, matrix, naming, transform
from jeffy.geometry import mesh as mesh_tools
from jeffy.geometry import surfaces

METHODS = ("follicle", "uvPin")


def _geo_shape(geo):
    if cmds.objectType(geo, isAType="shape"):
        return geo
    shapes = dag.get_shapes(geo, types=["mesh", "nurbsSurface"])
    if not shapes:
        raise ValueError("%s is not a mesh or nurbs surface" % geo)
    return shapes[0]


def closest_uv(geo, position):
    """Normalized UV of the closest point on a mesh (UV set) or surface."""
    shape = _geo_shape(geo)
    if cmds.nodeType(shape) == "mesh":
        return mesh_tools.closest_uv(shape, position)
    return surfaces.closest_uv(shape, position, normalized=True)


def create_follicle(geo, u, v, name="follicle", parent=None):
    """Create a follicle stuck to ``geo`` at ``(u, v)``; returns the transform."""
    shape = _geo_shape(geo)
    follicle_shape = cmds.createNode("follicle", name=naming.unique_name(name + "Shape"), skipSelect=True)
    follicle = cmds.listRelatives(follicle_shape, parent=True)[0]
    follicle = cmds.rename(follicle, naming.unique_name(name))
    follicle_shape = dag.get_shapes(follicle)[0]
    if cmds.nodeType(shape) == "mesh":
        cmds.connectAttr(shape + ".outMesh", follicle_shape + ".inputMesh")
    else:
        cmds.connectAttr(shape + ".local", follicle_shape + ".inputSurface")
    cmds.connectAttr(shape + ".worldMatrix[0]", follicle_shape + ".inputWorldMatrix")
    cmds.connectAttr(follicle_shape + ".outTranslate", follicle + ".translate")
    cmds.connectAttr(follicle_shape + ".outRotate", follicle + ".rotate")
    cmds.setAttr(follicle_shape + ".parameterU", u)
    cmds.setAttr(follicle_shape + ".parameterV", v)
    cmds.setAttr(follicle_shape + ".visibility", 0)
    cmds.setAttr(follicle + ".inheritsTransform", 0)
    for attr in ("tx", "ty", "tz", "rx", "ry", "rz"):
        cmds.setAttr("%s.%s" % (follicle, attr), lock=True)
    if parent:
        follicle = cmds.parent(follicle, parent)[0]
    return follicle


def create_uv_pin(geo, coordinates, name="uvPin"):
    """Create a ``uvPin`` node (Maya 2020+) with several coordinates.

    Returns ``(node, [outputMatrix plugs])``. The output matrices are in
    world space (the world geometry is used as input).
    """
    shape = _geo_shape(geo)
    pin = cmds.createNode("uvPin", name=naming.unique_name(name), skipSelect=True)
    if cmds.nodeType(shape) == "mesh":
        cmds.connectAttr(shape + ".worldMesh[0]", pin + ".deformedGeometry")
    else:
        cmds.connectAttr(shape + ".worldSpace[0]", pin + ".deformedGeometry")
        cmds.setAttr(pin + ".normalizedIsoParms", 1)
    outputs = []
    for index, (u, v) in enumerate(coordinates):
        cmds.setAttr("%s.coordinate[%d].coordinateU" % (pin, index), u)
        cmds.setAttr("%s.coordinate[%d].coordinateV" % (pin, index), v)
        outputs.append("%s.outputMatrix[%d]" % (pin, index))
    return pin, outputs


def attach_to_geometry(node, geo, method="follicle", u=None, v=None, maintain_offset=True, parent_to=False,
                       name=None):
    """Make ``node`` follow ``geo`` at the closest point (or given ``u, v``).

    * ``follicle`` - creates a follicle; the node is parent constrained to it
      (or parented under it with ``parent_to=True``).
    * ``uvPin`` - drives the node's ``offsetParentMatrix`` (no constraint).

    Returns the follicle transform or the uvPin node.
    """
    if method not in METHODS:
        raise ValueError("method must be one of %s" % (METHODS,))
    if u is None or v is None:
        u, v = closest_uv(geo, transform.get_position(node))
    base = name or naming.short_name(node)
    if method == "follicle":
        follicle = create_follicle(geo, u, v, name=base + "_FOL")
        if parent_to:
            cmds.parent(node, follicle)
        else:
            cmds.parentConstraint(follicle, node, maintainOffset=maintain_offset)
        return follicle

    pin, outputs = create_uv_pin(geo, [(u, v)], name=base + "_UVP")
    world = matrix.get_world_matrix(node)
    mm = cmds.createNode("multMatrix", name=naming.unique_name(base + "_pin_MM"), skipSelect=True)
    if maintain_offset:
        # node world relative to the pin matrix at bind time
        pin_matrix = cmds.getAttr(outputs[0])
        offset = mathlib.mult(world, mathlib.inverse(pin_matrix))
        matrix.set_matrix_attr(mm + ".matrixIn[0]", offset)
    cmds.connectAttr(outputs[0], mm + ".matrixIn[1]")
    cmds.connectAttr(node + ".parentInverseMatrix[0]", mm + ".matrixIn[2]")
    transform.reset(node)
    cmds.connectAttr(mm + ".matrixSum", node + ".offsetParentMatrix", force=True)
    return pin


def rivets_on_selection(method="follicle", name="rivet"):
    """Create a locator rivet for each selected component group / object.

    Select components (vertices/edges/faces) on a mesh: one rivet at their
    centre. Select objects then a mesh last: each object gets attached.
    """
    selection = cmds.ls(selection=True) or []
    if not selection:
        raise ValueError("Select components, or objects followed by a mesh")
    components = [s for s in selection if "." in s]
    rivets = []
    if components:
        by_mesh = {}
        for comp in components:
            by_mesh.setdefault(comp.split(".")[0], []).append(comp)
        for geo, comps in by_mesh.items():
            position = mathlib.centroid(transform.get_component_positions(comps))
            locator = cmds.spaceLocator(name=naming.unique_name("%s_%s_LOC" % (naming.short_name(geo), name)))[0]
            cmds.xform(locator, worldSpace=True, translation=position)
            attach_to_geometry(locator, geo, method=method, maintain_offset=False, parent_to=method == "follicle")
            rivets.append(locator)
        return rivets
    geo = selection[-1]
    for node in selection[:-1]:
        attach_to_geometry(node, geo, method=method)
        rivets.append(node)
    return rivets


def follicles_along_surface(surface, count, name="ribbon", v=0.5, parent=None):
    """Evenly spaced follicles along the U direction of a surface."""
    follicles = []
    for i, u in enumerate(mathlib.distribute(count, 0.0, 1.0)):
        follicles.append(create_follicle(surface, u, v, name="%s%02d_FOL" % (name, i + 1), parent=parent))
    return follicles
