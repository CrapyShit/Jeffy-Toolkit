"""Skin cluster tools: binding, weight IO, copy/mirror, cleanup and editing.

Highlights::

    from jeffy.deformers import skin
    skin.export_weights("body_GEO", "/path/body.json")
    skin.import_weights("body_GEO", "/path/body.json")       # index or position
    skin.copy_skin("body_GEO", ["shirt_GEO", "pants_GEO"])
    skin.mirror_skin("body_GEO")                              # +X -> -X
    skin.limit_influences("body_GEO", 4)
    skin.rebind_at_current_pose("body_GEO")                   # after moving joints
    skin.smooth_weights(cmds.ls(sl=True))                     # selected vertices
"""

from maya import cmds
from maya.api import OpenMaya as om
from maya.api import OpenMayaAnim as oma

from jeffy.core import dag, fileio, logger, mathlib, naming
from jeffy.deformers import weights as wmath
from jeffy.geometry import mesh as mesh_tools
from jeffy.geometry.spatial import SpatialHash

LOG = logger.get_logger("skin")

BIND_METHODS = {"closest": 0, "hierarchy": 1, "heatmap": 2, "geodesic": 3}
SKIN_METHODS = {"linear": 0, "dual_quaternion": 1, "blended": 2}
FILE_TYPE = "jeffy_skin_weights"


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def _shape(node):
    if cmds.objectType(node, isAType="shape"):
        return node
    shapes = dag.get_shapes(node, types=["mesh", "nurbsCurve", "nurbsSurface", "lattice"])
    return shapes[0] if shapes else None


def find_skin_cluster(node):
    """The skinCluster deforming ``node`` (transform or shape) or ``None``."""
    shape = _shape(node)
    if not shape:
        return None
    for skin in cmds.ls(cmds.listHistory(shape, pruneDagObjects=True) or [], type="skinCluster") or []:
        geometry = cmds.skinCluster(skin, query=True, geometry=True) or []
        if any(dag.long_name(g) == dag.long_name(shape) for g in geometry):
            return skin
    return None


def require_skin(node):
    skin = find_skin_cluster(node)
    if not skin:
        raise ValueError("%s has no skinCluster" % node)
    return skin


def get_influences(skin):
    return cmds.skinCluster(skin, query=True, influence=True) or []


def get_skinned_meshes(joints=None):
    """Meshes deformed by a skinCluster (optionally influenced by ``joints``)."""
    result = []
    for skin in cmds.ls(type="skinCluster") or []:
        if joints:
            influences = set(get_influences(skin))
            if not influences.intersection(joints):
                continue
        for geo in cmds.skinCluster(skin, query=True, geometry=True) or []:
            transform = cmds.listRelatives(geo, parent=True)[0]
            if transform not in result:
                result.append(transform)
    return result


def _logical_indices(skin):
    """``{influence_long_name: logical index}`` from the ``matrix`` plugs."""
    result = {}
    for index in cmds.getAttr(skin + ".matrix", multiIndices=True) or []:
        sources = cmds.listConnections("%s.matrix[%d]" % (skin, index), source=True, destination=False) or []
        if sources:
            result[dag.long_name(sources[0])] = index
    return result


# ---------------------------------------------------------------------------
# Binding
# ---------------------------------------------------------------------------
def bind(meshes, joints, max_influences=4, method="closest", skinning="linear", drop_off=4.0, name=None,
         heatmap_falloff=0.68):
    """Bind meshes to joints. Returns the created skinClusters."""
    if isinstance(meshes, str):
        meshes = [meshes]
    result = []
    for mesh in meshes:
        existing = find_skin_cluster(mesh)
        if existing:
            LOG.warning("%s is already skinned (%s)", mesh, existing)
            result.append(existing)
            continue
        kwargs = {
            "toSelectedBones": True,
            "bindMethod": BIND_METHODS[method],
            "skinMethod": SKIN_METHODS[skinning],
            "normalizeWeights": 1,
            "maximumInfluences": max_influences,
            "obeyMaxInfluences": True,
            "dropoffRate": drop_off,
            "name": name or naming.short_name(mesh) + "_" + naming.suffix("skin_cluster"),
        }
        if method == "heatmap":
            kwargs["heatmapFalloff"] = heatmap_falloff
        result.append(cmds.skinCluster(list(joints) + [mesh], **kwargs)[0])
    return result


def unbind(meshes, keep_history=False):
    if isinstance(meshes, str):
        meshes = [meshes]
    for mesh in meshes:
        skin = find_skin_cluster(mesh)
        if skin:
            cmds.skinCluster(skin, edit=True, unbindKeepHistory=keep_history, unbind=not keep_history)


def set_skinning_method(meshes, method="linear"):
    for mesh in [meshes] if isinstance(meshes, str) else meshes:
        skin = find_skin_cluster(mesh)
        if skin:
            cmds.setAttr(skin + ".skinningMethod", SKIN_METHODS[method])


# ---------------------------------------------------------------------------
# Weight access
# ---------------------------------------------------------------------------
def _components(shape):
    path = dag.get_dag_path(shape)
    node_type = cmds.nodeType(shape)
    if node_type == "mesh":
        count = om.MFnMesh(path).numVertices
        comp_type = om.MFn.kMeshVertComponent
    elif node_type == "nurbsCurve":
        count = om.MFnNurbsCurve(path).numCVs
        comp_type = om.MFn.kCurveCVComponent
    else:
        raise ValueError("Unsupported geometry type %s (mesh and nurbsCurve only)" % node_type)
    fn_comp = om.MFnSingleIndexedComponent()
    component = fn_comp.create(comp_type)
    fn_comp.setCompleteData(count)
    return path, component, count


def _skinned_shape(skin):
    return cmds.skinCluster(skin, query=True, geometry=True)[0]


def get_weights(skin):
    """Return ``(flat_weights, influence_names, vertex_count)``."""
    shape = _skinned_shape(skin)
    path, component, count = _components(shape)
    fn = oma.MFnSkinCluster(dag.get_mobject(skin))
    values, _influence_count = fn.getWeights(path, component)
    names = [p.partialPathName() for p in fn.influenceObjects()]
    return list(values), names, count


def set_weights(skin, flat, vertices=None, undoable=True):
    """Write weights (flat, ordered like :func:`get_weights` influences).

    With ``vertices`` only those rows are written (``flat`` still holds all
    vertices). ``undoable=False`` uses ``MFnSkinCluster.setWeights`` - much
    faster for whole meshes but not undoable.
    """
    shape = _skinned_shape(skin)
    fn = oma.MFnSkinCluster(dag.get_mobject(skin))
    influence_paths = fn.influenceObjects()
    count = len(influence_paths)
    vertex_total = len(flat) // count
    if not undoable:
        path, component, _count = _components(shape)
        if vertices is not None:
            fn_comp = om.MFnSingleIndexedComponent()
            component = fn_comp.create(om.MFn.kMeshVertComponent if cmds.nodeType(shape) == "mesh"
                                       else om.MFn.kCurveCVComponent)
            fn_comp.addElements(list(vertices))
            subset = []
            for v in vertices:
                subset.extend(flat[v * count:(v + 1) * count])
            flat = subset
        indices = om.MIntArray()
        for i in range(count):
            indices.append(i)
        values = om.MDoubleArray()
        for value in flat:
            values.append(value)
        fn.setWeights(path, component, indices, values, False)
        return

    logical = [fn.indexForInfluenceObject(p) for p in influence_paths]
    normalize_state = cmds.getAttr(skin + ".normalizeWeights")
    cmds.setAttr(skin + ".normalizeWeights", 0)
    try:
        for v in (range(vertex_total) if vertices is None else vertices):
            row = flat[v * count:(v + 1) * count]
            for i, weight in zip(logical, row):
                cmds.setAttr("%s.weightList[%d].weights[%d]" % (skin, v, i), weight)
    finally:
        cmds.setAttr(skin + ".normalizeWeights", normalize_state)


# ---------------------------------------------------------------------------
# Import / export
# ---------------------------------------------------------------------------
def export_weights(mesh, path=None, include_positions=True):
    """Export skin weights to JSON. Returns the file path."""
    skin = require_skin(mesh)
    flat, influences, count = get_weights(skin)
    shape = _skinned_shape(skin)
    data = {
        "type": FILE_TYPE,
        "version": fileio.FORMAT_VERSION,
        "mesh": naming.strip_namespace(mesh),
        "skin_cluster": naming.strip_namespace(skin),
        "vertex_count": count,
        "influences": [naming.strip_namespace(i) for i in influences],
        "skinning_method": cmds.getAttr(skin + ".skinningMethod"),
        "max_influences": cmds.getAttr(skin + ".maxInfluences"),
        "maintain_max_influences": cmds.getAttr(skin + ".maintainMaxInfluences"),
        "weights": wmath.to_sparse(flat, len(influences), [naming.strip_namespace(i) for i in influences]),
    }
    if cmds.getAttr(skin + ".skinningMethod") == 2 and cmds.nodeType(shape) == "mesh":
        fn = oma.MFnSkinCluster(dag.get_mobject(skin))
        dag_path, component, _count = _components(shape)
        data["blend_weights"] = list(fn.getBlendWeights(dag_path, component))
    if include_positions and cmds.nodeType(shape) == "mesh":
        data["positions"] = mesh_tools.get_points(shape, world=True)
    path = path or "%s/%s_skin.json" % (fileio.scene_dir(), naming.strip_namespace(mesh))
    return fileio.write_json(path, data, precision=6)


def _resolve_influence(name, remap=None):
    if remap and name in remap:
        name = remap[name]
    if cmds.objExists(name):
        return name
    matches = cmds.ls("*:" + name) or cmds.ls("*:*:" + name) or []
    return matches[0] if matches else None


def import_weights(mesh, path, method="auto", remap=None, undoable=False):
    """Import weights saved by :func:`export_weights`.

    :param method: ``index`` (same topology), ``position`` (closest stored
        vertex in world space) or ``auto`` (index when vertex counts match)
    :param remap: ``{"old_joint": "new_joint"}`` influence renames
    The mesh is bound automatically when it has no skinCluster.
    """
    data = fileio.read_json(path)
    if data.get("type") != FILE_TYPE:
        raise ValueError("%s is not a Jeffy skin weights file" % path)
    stored = data["influences"]
    resolved = []
    missing = []
    for name in stored:
        node = _resolve_influence(name, remap)
        resolved.append(node)
        if not node:
            missing.append(name)
    if missing:
        LOG.warning("Missing influences (weights redistributed): %s", ", ".join(missing))
    available = [n for n in resolved if n]
    if not available:
        raise ValueError("None of the stored influences exist in the scene")

    skin = find_skin_cluster(mesh)
    if not skin:
        skin = bind(mesh, available, max_influences=data.get("max_influences", 4))[0]
    else:
        current = set(dag.long_name(i) for i in get_influences(skin))
        to_add = [n for n in available if dag.long_name(n) not in current]
        if to_add:
            add_influences(mesh, to_add)

    shape = _skinned_shape(skin)
    vertex_count = _components(shape)[2]
    source_flat = wmath.from_sparse(data["weights"], stored, data["vertex_count"])

    use_index = method == "index" or (method == "auto" and vertex_count == data["vertex_count"])
    if not use_index:
        if "positions" not in data:
            raise ValueError("The weight file has no positions - cannot import by position")
        grid = SpatialHash(data["positions"])
        targets = mesh_tools.get_points(shape, world=True)
        mapping = [grid.nearest(p)[0] for p in targets]
        source_flat = wmath.remap_vertices(source_flat, len(stored), mapping)
    elif vertex_count != data["vertex_count"]:
        raise ValueError("Vertex count differs (%d vs %d) - use method='position'"
                         % (vertex_count, data["vertex_count"]))

    _current, skin_influences, _count = get_weights(skin)
    skin_short = [naming.strip_namespace(i) for i in skin_influences]
    resolved_short = {stored[i]: naming.strip_namespace(n) for i, n in enumerate(resolved) if n}
    renamed = [resolved_short.get(name, "__missing__%s" % name) for name in stored]
    new_flat = wmath.reorder_influences(source_flat, renamed, skin_short)
    new_flat = wmath.normalize(new_flat, len(skin_short))
    set_weights(skin, new_flat, undoable=undoable)
    if "skinning_method" in data:
        cmds.setAttr(skin + ".skinningMethod", data["skinning_method"])
    return skin


def export_selected(folder=None):
    """Export weights of every selected skinned mesh into ``folder``."""
    folder = folder or fileio.scene_dir()
    paths = []
    for node in cmds.ls(selection=True, transforms=True) or []:
        if find_skin_cluster(node):
            paths.append(export_weights(node, "%s/%s_skin.json" % (folder, naming.strip_namespace(node))))
    return paths


def import_selected(folder=None, method="auto"):
    import os

    folder = folder or fileio.scene_dir()
    done = []
    for node in cmds.ls(selection=True, transforms=True) or []:
        path = os.path.join(folder, "%s_skin.json" % naming.strip_namespace(node))
        if os.path.isfile(path):
            import_weights(node, path, method=method)
            done.append(node)
    return done


# ---------------------------------------------------------------------------
# Copy / mirror
# ---------------------------------------------------------------------------
INFLUENCE_ASSOCIATION = ["label", "oneToOne", "closestJoint"]


def copy_skin(source, targets, surface="closestPoint", influence=None, uv_space=None):
    """Copy skinning from ``source`` to ``targets`` (binding them if needed)."""
    if isinstance(targets, str):
        targets = [targets]
    source_skin = require_skin(source)
    influences = get_influences(source_skin)
    result = []
    for target in targets:
        target_skin = find_skin_cluster(target)
        if not target_skin:
            target_skin = bind(target, influences, max_influences=cmds.getAttr(source_skin + ".maxInfluences"))[0]
        else:
            add_influences(target, influences)
        kwargs = {
            "sourceSkin": source_skin,
            "destinationSkin": target_skin,
            "noMirror": True,
            "surfaceAssociation": surface,
            "influenceAssociation": influence or INFLUENCE_ASSOCIATION,
        }
        if uv_space:
            kwargs["uvSpace"] = uv_space
        cmds.copySkinWeights(**kwargs)
        cmds.setAttr(target_skin + ".skinningMethod", cmds.getAttr(source_skin + ".skinningMethod"))
        result.append(target_skin)
    return result


def mirror_skin(meshes, axis="x", positive_to_negative=True, surface="closestPoint", influence=None,
                label_joints=True):
    """Mirror weights across an axis on each mesh (``copySkinWeights``).

    With ``label_joints`` influences are labelled from their names first so
    the *label* association finds left/right pairs reliably.
    """
    if isinstance(meshes, str):
        meshes = [meshes]
    mode = {"x": "YZ", "y": "XZ", "z": "XY"}[axis.lower()]
    for mesh in meshes:
        skin = require_skin(mesh)
        if label_joints:
            from jeffy.joints import tools as joint_tools

            joint_tools.label_joints(cmds.ls(get_influences(skin), type="joint"))
        cmds.copySkinWeights(sourceSkin=skin, destinationSkin=skin, mirrorMode=mode,
                             mirrorInverse=not positive_to_negative, surfaceAssociation=surface,
                             influenceAssociation=influence or INFLUENCE_ASSOCIATION)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
def prune(meshes, threshold=0.01):
    for mesh in [meshes] if isinstance(meshes, str) else meshes:
        skin = require_skin(mesh)
        cmds.skinPercent(skin, _skinned_shape(skin), pruneWeights=threshold)


def normalize(meshes):
    for mesh in [meshes] if isinstance(meshes, str) else meshes:
        skin = require_skin(mesh)
        cmds.skinPercent(skin, _skinned_shape(skin), normalize=True)


def limit_influences(meshes, max_influences=4, undoable=True):
    """Keep only the N largest weights per vertex and lock the max."""
    for mesh in [meshes] if isinstance(meshes, str) else meshes:
        skin = require_skin(mesh)
        flat, influences, _count = get_weights(skin)
        count = len(influences)
        over = wmath.vertices_over_limit(flat, count, max_influences)
        if over:
            new_flat = wmath.limit_influences(flat, count, max_influences)
            set_weights(skin, new_flat, vertices=over, undoable=undoable)
        cmds.setAttr(skin + ".maxInfluences", max_influences)
        cmds.setAttr(skin + ".maintainMaxInfluences", 1)


def remove_unused_influences(meshes):
    """Remove influences that have no weight on any vertex."""
    removed = []
    for mesh in [meshes] if isinstance(meshes, str) else meshes:
        skin = require_skin(mesh)
        weighted = set(cmds.skinCluster(skin, query=True, weightedInfluence=True) or [])
        for influence in get_influences(skin):
            if influence not in weighted:
                cmds.skinCluster(skin, edit=True, removeInfluence=influence)
                removed.append(influence)
    return removed


def add_influences(mesh, joints):
    """Add influences with zero weight."""
    skin = require_skin(mesh)
    existing = set(dag.long_name(i) for i in get_influences(skin))
    for joint in joints:
        if dag.long_name(joint) in existing:
            continue
        cmds.skinCluster(skin, edit=True, addInfluence=joint, weight=0.0, lockWeights=True)
        cmds.setAttr(joint + ".lockInfluenceWeights", 0)


def set_influences_locked(joints, locked=True):
    for joint in joints:
        if cmds.attributeQuery("lockInfluenceWeights", node=joint, exists=True):
            cmds.setAttr(joint + ".lockInfluenceWeights", locked)


def rebind_at_current_pose(meshes):
    """Reset the bind pose to the current joint pose, keeping weights.

    Use after moving joints in a skinned rig: the mesh returns to its
    original shape with the joints where they are now.
    """
    for mesh in [meshes] if isinstance(meshes, str) else meshes:
        skin = require_skin(mesh)
        for influence, index in _logical_indices(skin).items():
            inverse = cmds.getAttr(influence + ".worldInverseMatrix[0]")
            cmds.setAttr("%s.bindPreMatrix[%d]" % (skin, index), *inverse, type="matrix")
        poses = cmds.listConnections(skin + ".bindPose", source=True, destination=False) or []
        for pose in poses:
            cmds.dagPose(get_influences(skin), reset=True, name=pose)


def go_to_bind_pose(meshes=None):
    """Restore the bind pose of the given (or all) skinned meshes."""
    skins = [require_skin(m) for m in ([meshes] if isinstance(meshes, str) else meshes)] if meshes else \
        cmds.ls(type="skinCluster") or []
    for skin in skins:
        for pose in cmds.listConnections(skin + ".bindPose", source=True, destination=False) or []:
            cmds.dagPose(pose, restore=True)


# ---------------------------------------------------------------------------
# Vertex level editing
# ---------------------------------------------------------------------------
_CLIPBOARD = {}


def _vertex_selection(components=None):
    components = components or cmds.ls(selection=True) or []
    mapping = mesh_tools.vertex_indices(components)
    result = []
    for node, indices in mapping.items():
        transform = node if not cmds.objectType(node, isAType="shape") else cmds.listRelatives(node, parent=True)[0]
        result.append((transform, sorted(set(indices))))
    return result


def copy_vertex_weights(component=None):
    """Store the (averaged) weights of the selected vertices."""
    selection = _vertex_selection([component] if component else None)
    if not selection:
        raise ValueError("Select vertices")
    mesh, indices = selection[0]
    skin = require_skin(mesh)
    flat, influences, _count = get_weights(skin)
    count = len(influences)
    averaged = wmath.average_rows([flat[v * count:(v + 1) * count] for v in indices])
    _CLIPBOARD.clear()
    _CLIPBOARD.update({naming.strip_namespace(n): w for n, w in zip(influences, averaged) if w > 1e-6})
    return dict(_CLIPBOARD)


def paste_vertex_weights(components=None):
    """Apply the stored weights to the selected vertices."""
    if not _CLIPBOARD:
        raise ValueError("Copy vertex weights first")
    for mesh, indices in _vertex_selection(components):
        skin = require_skin(mesh)
        flat, influences, _count = get_weights(skin)
        short = [naming.strip_namespace(n) for n in influences]
        missing = [n for n in _CLIPBOARD if n not in short]
        if missing:
            add_influences(mesh, [_resolve_influence(n) for n in missing if _resolve_influence(n)])
            flat, influences, _count = get_weights(skin)
            short = [naming.strip_namespace(n) for n in influences]
        count = len(short)
        row = wmath.normalize_row([_CLIPBOARD.get(n, 0.0) for n in short])
        for v in indices:
            flat[v * count:(v + 1) * count] = row
        set_weights(skin, flat, vertices=indices)


def average_vertex_weights(components=None):
    """Give every selected vertex the average of their weights."""
    for mesh, indices in _vertex_selection(components):
        skin = require_skin(mesh)
        flat, influences, _count = get_weights(skin)
        count = len(influences)
        row = wmath.average_rows([flat[v * count:(v + 1) * count] for v in indices])
        for v in indices:
            flat[v * count:(v + 1) * count] = row
        set_weights(skin, flat, vertices=indices)


def smooth_weights(components=None, iterations=2, strength=0.5, respect_locks=True):
    """Smooth weights of the selected vertices over the mesh connectivity."""
    for mesh, indices in _vertex_selection(components):
        skin = require_skin(mesh)
        flat, influences, _count = get_weights(skin)
        locked = []
        if respect_locks:
            locked = [i for i, n in enumerate(influences)
                      if cmds.attributeQuery("lockInfluenceWeights", node=n, exists=True)
                      and cmds.getAttr(n + ".lockInfluenceWeights")]
        neighbors = mesh_tools.get_neighbors(mesh)
        new_flat = wmath.smooth(flat, len(influences), neighbors, vertices=indices, iterations=iterations,
                                strength=strength, locked=locked)
        set_weights(skin, new_flat, vertices=indices)


def move_weights(mesh, source, target, components=None, amount=1.0):
    """Move weights from one influence to another (all or selected vertices)."""
    skin = require_skin(mesh)
    add_influences(mesh, [target])
    flat, influences, count = get_weights(skin)
    longs = [dag.long_name(i) for i in influences]
    source_index = longs.index(dag.long_name(source))
    target_index = longs.index(dag.long_name(target))
    vertices = None
    if components:
        selection = _vertex_selection(components)
        vertices = selection[0][1] if selection else None
    new_flat = wmath.move_weights(flat, len(influences), source_index, target_index, vertices, amount)
    set_weights(skin, new_flat, vertices=vertices, undoable=vertices is not None)


def select_influenced_vertices(joint, mesh=None):
    meshes = [mesh] if mesh else get_skinned_meshes([joint])
    cmds.select(clear=True)
    for item in meshes:
        skin = find_skin_cluster(item)
        if skin and joint in get_influences(skin):
            cmds.skinCluster(skin, edit=True, selectInfluenceVerts=joint)


def select_influences(meshes):
    joints = []
    for mesh in [meshes] if isinstance(meshes, str) else meshes:
        skin = find_skin_cluster(mesh)
        if skin:
            joints.extend(i for i in get_influences(skin) if i not in joints)
    cmds.select(joints, replace=True)
    return joints


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
def combine_skinned(meshes, name="combined_GEO"):
    """Combine skinned meshes keeping skinning (``polyUniteSkinned``)."""
    result = cmds.polyUniteSkinned(meshes, constructionHistory=False, mergeUVSets=1)
    return cmds.rename(result[0], naming.unique_name(name))


def skin_info(mesh):
    """Dictionary with statistics about a skinned mesh."""
    skin = require_skin(mesh)
    flat, influences, count = get_weights(skin)
    inf_count = len(influences)
    max_setting = cmds.getAttr(skin + ".maxInfluences")
    return {
        "skin_cluster": skin,
        "vertices": count,
        "influences": inf_count,
        "max_influences_setting": max_setting,
        "max_influences_used": wmath.max_influences_used(flat, inf_count),
        "vertices_over_limit": len(wmath.vertices_over_limit(flat, inf_count, max_setting)),
        "skinning_method": cmds.getAttr(skin + ".skinningMethod"),
        "unused_influences": inf_count - len(cmds.skinCluster(skin, query=True, weightedInfluence=True) or []),
    }


def closest_joint(position, joints):
    return min(joints, key=lambda j: mathlib.distance(position, cmds.xform(j, query=True, worldSpace=True,
                                                                           translation=True)))
