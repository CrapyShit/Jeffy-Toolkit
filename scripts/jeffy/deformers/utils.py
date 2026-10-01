"""Generic deformer tools: weights IO/mirror, soft selection clusters, wraps,
lattices, wires, delta mush, deformer order and envelopes."""

from maya import cmds
from maya.api import OpenMaya as om

from jeffy.core import dag, fileio, mathlib, naming
from jeffy.geometry import mesh as mesh_tools
from jeffy.geometry import symmetry

DEFORMER_FILE_TYPE = "jeffy_deformer_weights"


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def list_deformers(node, types=None):
    """Deformers in the history of ``node`` (closest first)."""
    history = cmds.listHistory(node, pruneDagObjects=True, interestLevel=1) or []
    result = [h for h in history if cmds.objectType(h, isAType="geometryFilter")]
    if types:
        types = [types] if isinstance(types, str) else types
        result = [d for d in result if cmds.nodeType(d) in types]
    return result


def deformer_geometry(deformer):
    """``[(geometry_index, shape), ...]`` deformed by ``deformer``."""
    shapes = cmds.deformer(deformer, query=True, geometry=True) or []
    indices = cmds.deformer(deformer, query=True, geometryIndices=True) or list(range(len(shapes)))
    return list(zip(indices, shapes))


def geometry_index(deformer, shape):
    long_shape = dag.long_name(dag.get_shape(shape) or shape)
    for index, geo in deformer_geometry(deformer):
        if dag.long_name(geo) == long_shape:
            return index
    raise ValueError("%s is not deformed by %s" % (shape, deformer))


def _point_count(shape):
    node_type = cmds.nodeType(shape)
    if node_type == "mesh":
        return mesh_tools.vertex_count(shape)
    return len(cmds.ls("%s.cv[*]" % shape, flatten=True) or cmds.ls("%s.pt[*]" % shape, flatten=True) or [])


# ---------------------------------------------------------------------------
# Weight lists
# ---------------------------------------------------------------------------
def get_weight_list(node, plug, count, default=1.0):
    """Values of a (sparse) multi weight attribute as a dense list."""
    del node  # kept for API symmetry
    indices = cmds.getAttr(plug, multiIndices=True) or []
    result = [default] * count
    if not indices:
        return result
    values = cmds.getAttr(plug) or []
    if not isinstance(values, (list, tuple)):
        values = [values]
    for index, value in zip(indices, values):
        if index < count:
            result[index] = value
    return result


def set_weight_list(plug, values):
    """Set a whole multi weight attribute in one call (undoable)."""
    count = len(values)
    if not count:
        return
    cmds.setAttr("%s[0:%d]" % (plug, count - 1), *values, size=count)


def weight_plug(deformer, geo_index=0):
    return "%s.weightList[%d].weights" % (deformer, geo_index)


def get_deformer_weights(deformer, shape=None):
    shape = shape or deformer_geometry(deformer)[0][1]
    index = geometry_index(deformer, shape)
    return get_weight_list(deformer, weight_plug(deformer, index), _point_count(shape))


def set_deformer_weights(deformer, values, shape=None):
    shape = shape or deformer_geometry(deformer)[0][1]
    set_weight_list(weight_plug(deformer, geometry_index(deformer, shape)), values)


def export_deformer_weights(deformer, path):
    data = {"type": DEFORMER_FILE_TYPE, "version": fileio.FORMAT_VERSION, "deformer": naming.short_name(deformer),
            "node_type": cmds.nodeType(deformer), "geometry": []}
    for _index, shape in deformer_geometry(deformer):
        entry = {"shape": naming.strip_namespace(cmds.listRelatives(shape, parent=True)[0]),
                 "weights": get_deformer_weights(deformer, shape)}
        if cmds.nodeType(shape) == "mesh":
            entry["positions"] = mesh_tools.get_points(shape)
        data["geometry"].append(entry)
    return fileio.write_json(path, data, precision=5)


def import_deformer_weights(deformer, path, method="auto"):
    """Import weights; ``method`` ``index``/``position``/``auto`` like skins."""
    from jeffy.geometry.spatial import SpatialHash

    data = fileio.read_json(path)
    if data.get("type") != DEFORMER_FILE_TYPE:
        raise ValueError("%s is not a Jeffy deformer weights file" % path)
    geometry = deformer_geometry(deformer)
    for entry in data["geometry"]:
        target = None
        for _index, shape in geometry:
            if naming.strip_namespace(cmds.listRelatives(shape, parent=True)[0]) == entry["shape"]:
                target = shape
        if target is None and len(geometry) == 1 and len(data["geometry"]) == 1:
            target = geometry[0][1]
        if target is None:
            continue
        values = entry["weights"]
        count = _point_count(target)
        if method == "position" or (method == "auto" and count != len(values)):
            if "positions" not in entry:
                raise ValueError("No stored positions for %s" % entry["shape"])
            grid = SpatialHash(entry["positions"])
            values = [values[grid.nearest(p)[0]] for p in mesh_tools.get_points(target)]
        set_deformer_weights(deformer, values, target)


def copy_deformer_weights(source_deformer, target_deformer, source_shape=None, target_shape=None,
                          surface="closestPoint"):
    source_shape = source_shape or deformer_geometry(source_deformer)[0][1]
    target_shape = target_shape or deformer_geometry(target_deformer)[0][1]
    cmds.copyDeformerWeights(sourceShape=source_shape, destinationShape=target_shape,
                             sourceDeformer=source_deformer, destinationDeformer=target_deformer,
                             surfaceAssociation=surface, noMirror=True)


def mirror_deformer_weights(deformer, shape=None, axis="x", direction=symmetry.POSITIVE_TO_NEGATIVE,
                            tolerance=1e-3):
    """Mirror a deformer's weights across ``axis`` using a symmetry map."""
    shape = shape or deformer_geometry(deformer)[0][1]
    points = mesh_tools.get_points(shape, world=True)
    mirror_map = symmetry.build_mirror_map(points, axis, tolerance)
    values = get_deformer_weights(deformer, shape)
    set_deformer_weights(deformer, symmetry.mirror_weights(values, mirror_map, points, axis, direction), shape)


def flood_weights(deformer, value=1.0, shape=None):
    shape = shape or deformer_geometry(deformer)[0][1]
    set_deformer_weights(deformer, [value] * _point_count(shape), shape)


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------
def soft_selection_weights():
    """``{shape: {vertex_index: weight}}`` from the current soft selection."""
    rich = om.MGlobal.getRichSelection()
    selection = rich.getSelection()
    result = {}
    for i in range(selection.length()):
        try:
            path, component = selection.getComponent(i)
        except RuntimeError:
            continue
        if component.isNull() or not component.hasFn(om.MFn.kMeshVertComponent):
            continue
        fn = om.MFnSingleIndexedComponent(component)
        elements = fn.getElements()
        has_weights = fn.hasWeights
        shape = path.fullPathName()
        for j, index in enumerate(elements):
            weight = fn.weight(j).influence if has_weights else 1.0
            result.setdefault(shape, {})[index] = weight
    return result


def cluster_from_soft_selection(name="soft_CLS"):
    """Create a cluster weighted by the soft selection (select vertices with
    soft select on). The handle is placed at the weighted centre."""
    data = soft_selection_weights()
    if not data:
        raise ValueError("Select vertices (soft selection supported)")
    components = []
    for shape, weights in data.items():
        components.extend(mesh_tools.component_list(shape, list(weights)))
    cluster, handle = cmds.cluster(components, name=naming.unique_name(name))
    total = 0.0
    center = (0.0, 0.0, 0.0)
    for shape, weights in data.items():
        index = geometry_index(cluster, shape)
        plug = weight_plug(cluster, index)
        points = mesh_tools.get_points(shape, world=True)
        for vertex, weight in weights.items():
            cmds.setAttr("%s[%d]" % (plug, vertex), weight)
            center = mathlib.add(center, mathlib.scale(points[vertex], weight))
            total += weight
    if total > 0:
        center = mathlib.scale(center, 1.0 / total)
        cmds.xform(handle, worldSpace=True, pivots=center)
        handle_shape = dag.get_shape(handle)
        if handle_shape and cmds.attributeQuery("origin", node=handle_shape, exists=True):
            cmds.setAttr(handle_shape + ".origin", *center)
    return cluster, handle


def create_cluster(components=None, name="cluster_CLS", relative=False):
    components = components or cmds.ls(selection=True) or []
    if not components:
        raise ValueError("Select components or objects")
    return cmds.cluster(components, name=naming.unique_name(name), relative=relative)


def create_wrap(driver, driven, max_distance=1.0, falloff_mode=0, name=None):
    """Wrap ``driven`` to ``driver`` without using the selection or MEL.

    Returns ``(wrap, base_mesh)``.
    """
    driver_shape = dag.get_shape(driver, types="mesh")
    wrap = cmds.deformer(driven, type="wrap", name=naming.unique_name(name or naming.short_name(driven) + "_wrap"))[0]
    cmds.setAttr(wrap + ".weightThreshold", 0.0)
    cmds.setAttr(wrap + ".maxDistance", max_distance)
    cmds.setAttr(wrap + ".autoWeightThreshold", 1)
    cmds.setAttr(wrap + ".exclusiveBind", 0)
    cmds.setAttr(wrap + ".falloffMode", falloff_mode)
    base = mesh_tools.duplicate_clean(driver, name=naming.short_name(driver) + "Base")
    cmds.setAttr(base + ".visibility", 0)
    base_shape = dag.get_shape(base)
    for long_name, short, kwargs in (
        ("dropoff", "dr", {"defaultValue": 4.0, "minValue": 0.0, "maxValue": 20.0, "keyable": True}),
        ("smoothness", "smt", {"defaultValue": 0.0, "minValue": 0.0, "keyable": True}),
        ("inflType", "ift", {"attributeType": "short", "defaultValue": 2, "minValue": 1, "maxValue": 2}),
    ):
        if not cmds.attributeQuery(long_name, node=driver_shape, exists=True):
            cmds.addAttr(driver_shape, longName=long_name, shortName=short, **kwargs)
    cmds.connectAttr(driver_shape + ".worldMesh[0]", wrap + ".driverPoints[0]")
    cmds.connectAttr(base_shape + ".worldMesh[0]", wrap + ".basePoints[0]")
    cmds.connectAttr(driver_shape + ".inflType", wrap + ".inflType[0]")
    cmds.connectAttr(driver_shape + ".smoothness", wrap + ".smoothness[0]")
    cmds.connectAttr(driver_shape + ".dropoff", wrap + ".dropoff[0]")
    world = cmds.getAttr(driven + ".worldMatrix[0]")
    cmds.setAttr(wrap + ".geomMatrix", *world, type="matrix")
    return wrap, base


def create_lattice(nodes_list=None, divisions=(3, 3, 3), name="lattice", local=True):
    nodes_list = nodes_list or cmds.ls(selection=True) or []
    result = cmds.lattice(nodes_list, divisions=divisions, objectCentered=True, name=naming.unique_name(name),
                          ldivisions=(2, 2, 2) if local else divisions)
    return result


def create_wire(curve, meshes, dropoff=1.0, name="wire"):
    wire = cmds.wire(meshes, wire=curve, name=naming.unique_name(name), dropoffDistance=(0, dropoff))[0]
    return wire


def create_delta_mush(meshes, iterations=10, step=0.5, name=None):
    result = []
    for mesh in [meshes] if isinstance(meshes, str) else meshes:
        result.append(cmds.deltaMush(mesh, smoothingIterations=iterations, smoothingStep=step,
                                     name=naming.unique_name(name or naming.short_name(mesh) + "_deltaMush"))[0])
    return result


def create_tension(meshes, name=None):
    result = []
    for mesh in [meshes] if isinstance(meshes, str) else meshes:
        result.append(cmds.tension(mesh, name=naming.unique_name(name or naming.short_name(mesh) + "_tension"))[0])
    return result


# ---------------------------------------------------------------------------
# Order / envelopes
# ---------------------------------------------------------------------------
def move_to_front(mesh, deformer):
    """Move ``deformer`` to the front of the chain (evaluated first)."""
    deformers = list_deformers(mesh)
    if len(deformers) < 2 or deformers[-1] == deformer:
        return
    cmds.reorderDeformers(deformer, deformers[-1], mesh)
    cmds.reorderDeformers(deformers[-1], deformer, mesh)


def move_to_back(mesh, deformer):
    deformers = list_deformers(mesh)
    if len(deformers) < 2 or deformers[0] == deformer:
        return
    cmds.reorderDeformers(deformers[0], deformer, mesh)


def set_envelopes(mesh, value=1.0, types=None):
    for deformer in list_deformers(mesh, types):
        plug = deformer + ".envelope"
        if cmds.objExists(plug) and cmds.getAttr(plug, settable=True):
            cmds.setAttr(plug, value)


def toggle_deformers(mesh, types=None):
    """Toggle every deformer envelope on/off (based on the first one)."""
    deformers = [d for d in list_deformers(mesh, types) if cmds.objExists(d + ".envelope")]
    if not deformers:
        return None
    state = 0.0 if cmds.getAttr(deformers[0] + ".envelope") > 0 else 1.0
    set_envelopes(mesh, state, types)
    return state
