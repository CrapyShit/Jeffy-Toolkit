"""Blendshape tools: create, add, extract, mirror, flip, split, transfer...

Mirroring and splitting are done with Jeffy's own symmetry maps, so they
work on any symmetric mesh and produce new target meshes you can inspect::

    from jeffy.deformers import blendshape as bs
    bs.mirror_target("head_GEO", "L_smile_GEO", name="R_smile_GEO")
    bs.split_target("head_GEO", "smile_GEO", falloff=2.0)   # -> L_ / R_ meshes
    bs.extract_targets("head_BSH")                            # rebuild meshes
"""

from maya import cmds

from jeffy.core import dag, fileio, logger, naming
from jeffy.deformers import utils as deformer_utils
from jeffy.geometry import mesh as mesh_tools
from jeffy.geometry import symmetry

LOG = logger.get_logger("blendshape")


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def find_blendshapes(mesh):
    return deformer_utils.list_deformers(mesh, types=["blendShape"])


def get_targets(blendshape):
    """``[(index, alias), ...]`` of every weight of a blendshape."""
    aliases = cmds.aliasAttr(blendshape, query=True) or []
    result = []
    for alias, attr in zip(aliases[::2], aliases[1::2]):
        if attr.startswith("weight["):
            result.append((int(attr[7:-1]), alias))
    indices = cmds.getAttr(blendshape + ".weight", multiIndices=True) or []
    known = set(i for i, _a in result)
    result.extend((i, "weight%d" % i) for i in indices if i not in known)
    return sorted(result)


def target_index(blendshape, target):
    if isinstance(target, int):
        return target
    for index, alias in get_targets(blendshape):
        if alias == target:
            return index
    raise ValueError("%s has no target %s" % (blendshape, target))


def next_index(blendshape):
    indices = cmds.getAttr(blendshape + ".weight", multiIndices=True) or []
    return (max(indices) + 1) if indices else 0


def base_geometry(blendshape):
    return cmds.blendShape(blendshape, query=True, geometry=True)[0]


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------
def create(base, targets=None, name=None, front_of_chain=True):
    """Create a blendshape (local origin) on ``base`` with optional targets."""
    targets = targets or []
    name = name or naming.short_name(base) + "_" + naming.suffix("blendshape")
    kwargs = {"name": naming.unique_name(name), "origin": "local"}
    if front_of_chain:
        kwargs["frontOfChain"] = True
    return cmds.blendShape(list(targets) + [base], **kwargs)[0]


def add_target(blendshape, target, weight=0.0, alias=None, inbetween=None):
    """Add a target mesh (or an in-between at ``inbetween`` 0..1)."""
    base = base_geometry(blendshape)
    if inbetween is not None:
        index = target_index(blendshape, alias) if alias else next_index(blendshape) - 1
        cmds.blendShape(blendshape, edit=True, inBetween=True, target=(base, index, target, inbetween))
        return index
    index = next_index(blendshape)
    cmds.blendShape(blendshape, edit=True, target=(base, index, target, 1.0))
    cmds.setAttr("%s.weight[%d]" % (blendshape, index), weight)
    if alias:
        cmds.aliasAttr(alias, "%s.weight[%d]" % (blendshape, index))
    return index


def add_targets_from_selection():
    """Select targets then the base mesh last: adds them to its blendshape."""
    selection = cmds.ls(selection=True, transforms=True) or []
    if len(selection) < 2:
        raise ValueError("Select target meshes then the base mesh")
    base = selection[-1]
    existing = find_blendshapes(base)
    blendshape = existing[0] if existing else create(base)
    for target in selection[:-1]:
        add_target(blendshape, target, alias=naming.strip_namespace(target))
    return blendshape


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
def extract_target(blendshape, target, name=None, parent=None):
    """Duplicate the base mesh with only ``target`` at 1 (other weights 0)."""
    index = target_index(blendshape, target)
    alias = dict(get_targets(blendshape)).get(index, "target%d" % index)
    targets = get_targets(blendshape)
    saved = {}
    for i, _alias in targets:
        plug = "%s.weight[%d]" % (blendshape, i)
        saved[plug] = cmds.getAttr(plug)
    base = cmds.listRelatives(base_geometry(blendshape), parent=True)[0]
    envelope = cmds.getAttr(blendshape + ".envelope")
    other_deformers = [d for d in deformer_utils.list_deformers(base) if d != blendshape]
    other_envelopes = {d: cmds.getAttr(d + ".envelope") for d in other_deformers
                       if cmds.attributeQuery("envelope", node=d, exists=True)}
    try:
        for plug in saved:
            if cmds.getAttr(plug, settable=True):
                cmds.setAttr(plug, 0)
        for deformer in other_envelopes:
            if cmds.getAttr(deformer + ".envelope", settable=True):
                cmds.setAttr(deformer + ".envelope", 0)
        cmds.setAttr(blendshape + ".envelope", 1)
        target_plug = "%s.weight[%d]" % (blendshape, index)
        if cmds.getAttr(target_plug, settable=True):
            cmds.setAttr(target_plug, 1)
        result = mesh_tools.duplicate_clean(base, name=name or alias, parent=parent)
    finally:
        for plug, value in saved.items():
            if cmds.getAttr(plug, settable=True):
                cmds.setAttr(plug, value)
        cmds.setAttr(blendshape + ".envelope", envelope)
        for deformer, value in other_envelopes.items():
            if cmds.getAttr(deformer + ".envelope", settable=True):
                cmds.setAttr(deformer + ".envelope", value)
    return result


def extract_targets(blendshape, connect=False, spacing=None):
    """Extract every target as a mesh, laid out next to the base.

    With ``connect=True`` the extracted meshes are plugged back as the
    targets' input geometry (so sculpting them updates the blendshape).
    """
    base = cmds.listRelatives(base_geometry(blendshape), parent=True)[0]
    bbox = cmds.exactWorldBoundingBox(base)
    width = spacing or (bbox[3] - bbox[0]) * 1.2
    group = cmds.createNode("transform", name=naming.unique_name(naming.short_name(blendshape) + "_targets_GRP"),
                            skipSelect=True)
    meshes = []
    for i, (index, alias) in enumerate(get_targets(blendshape)):
        mesh = extract_target(blendshape, index, name=alias, parent=group)
        cmds.move(width * (i + 1), 0, 0, mesh, relative=True)
        if connect:
            shape = dag.get_shape(mesh)
            plug = "%s.inputTarget[0].inputTargetGroup[%d].inputTargetItem[6000].inputGeomTarget" % (
                blendshape, index)
            cmds.connectAttr(shape + ".worldMesh[0]", plug, force=True)
        meshes.append(mesh)
    return meshes


# ---------------------------------------------------------------------------
# Symmetry: mirror / flip / split
# ---------------------------------------------------------------------------
def mirror_target(base, target, name=None, axis="x", tolerance=1e-3):
    """Create a new mesh with the deltas of ``target`` mirrored across ``axis``."""
    base_points = mesh_tools.get_points(base, world=False)
    target_points = mesh_tools.get_points(target, world=False)
    if len(base_points) != len(target_points):
        raise ValueError("Base and target have different vertex counts")
    mirror_map = symmetry.build_mirror_map(base_points, axis, tolerance)
    unmatched, _ok = symmetry.symmetry_report(base_points, mirror_map, axis)
    if unmatched:
        LOG.warning("%d vertices have no mirror match (kept as is)", len(unmatched))
    new_points = symmetry.mirror_target(base_points, target_points, mirror_map, axis)
    name = name or naming.mirror_name(naming.short_name(target))
    if name == naming.short_name(target):
        name += "_mirrored"
    result = mesh_tools.duplicate_clean(target, name=name)
    mesh_tools.set_points(result, new_points, world=False)
    return result


def symmetrize_target(base, target, axis="x", direction=symmetry.POSITIVE_TO_NEGATIVE, name=None,
                      tolerance=1e-3):
    """New mesh where one side of the target deltas is copied to the other."""
    base_points = mesh_tools.get_points(base, world=False)
    target_points = mesh_tools.get_points(target, world=False)
    mirror_map = symmetry.build_mirror_map(base_points, axis, tolerance)
    mirrored = symmetry.mirror_target(base_points, target_points, mirror_map, axis)
    source_side = 1 if direction == symmetry.POSITIVE_TO_NEGATIVE else -1
    new_points = []
    for i, point in enumerate(base_points):
        side = symmetry.side_of(point, axis)
        new_points.append(mirrored[i] if side == -source_side else target_points[i])
    result = mesh_tools.duplicate_clean(target, name=name or naming.short_name(target) + "_sym")
    mesh_tools.set_points(result, new_points, world=False)
    return result


def split_target(base, target, axis="x", falloff=1.0, names=None):
    """Split a symmetric target into left/right meshes with a smooth falloff.

    Returns ``(positive_side_mesh, negative_side_mesh)``. Default names are
    ``L_<target>`` / ``R_<target>`` (character left is +X).
    """
    base_points = mesh_tools.get_points(base, world=False)
    target_points = mesh_tools.get_points(target, world=False)
    weights = symmetry.split_weights(base_points, axis, falloff)
    positive = symmetry.split_target(base_points, target_points, weights)
    negative = symmetry.split_target(base_points, target_points, [1.0 - w for w in weights])
    short = naming.short_name(target)
    names = names or ("L_" + short, "R_" + short)
    meshes = []
    for name, points in zip(names, (positive, negative)):
        mesh = mesh_tools.duplicate_clean(target, name=name)
        mesh_tools.set_points(mesh, points, world=False)
        meshes.append(mesh)
    return tuple(meshes)


def flip_target_native(blendshape, target, axis="x"):
    """Flip a target in place using Maya's blendShape symmetry (2017+)."""
    index = target_index(blendshape, target)
    cmds.blendShape(blendshape, edit=True, flipTarget=[(0, index)], symmetryAxis=axis, symmetrySpace=1)


def mirror_target_native(blendshape, target, axis="x", direction=0):
    """Mirror a target in place using Maya's blendShape symmetry (2017+)."""
    index = target_index(blendshape, target)
    cmds.blendShape(blendshape, edit=True, mirrorTarget=[(0, index)], mirrorDirection=direction,
                    symmetryAxis=axis, symmetrySpace=1)


# ---------------------------------------------------------------------------
# Transfer / misc
# ---------------------------------------------------------------------------
def transfer_blendshapes(source_base, target_mesh, blendshape=None):
    """Re-create the targets of ``source_base`` on a mesh of different
    topology using a temporary wrap deformer."""
    blendshape = blendshape or find_blendshapes(source_base)[0]
    temp = mesh_tools.duplicate_clean(target_mesh, name=naming.short_name(target_mesh) + "_wrapTmp")
    wrap, wrap_base = deformer_utils.create_wrap(source_base, temp)
    new_targets = []
    targets = get_targets(blendshape)
    saved = {i: cmds.getAttr("%s.weight[%d]" % (blendshape, i)) for i, _a in targets}
    try:
        for index, alias in targets:
            for i, _a in targets:
                if cmds.getAttr("%s.weight[%d]" % (blendshape, i), settable=True):
                    cmds.setAttr("%s.weight[%d]" % (blendshape, i), 1.0 if i == index else 0.0)
            new_targets.append(mesh_tools.duplicate_clean(temp, name=alias + "_transfer"))
    finally:
        for i, value in saved.items():
            if cmds.getAttr("%s.weight[%d]" % (blendshape, i), settable=True):
                cmds.setAttr("%s.weight[%d]" % (blendshape, i), value)
        cmds.delete([n for n in (wrap, wrap_base, temp) if cmds.objExists(n)])
    new_bs = create(target_mesh, name=naming.short_name(target_mesh) + "_" + naming.suffix("blendshape"))
    for mesh, (_index, alias) in zip(new_targets, targets):
        add_target(new_bs, mesh, alias=alias)
    cmds.delete(new_targets)
    return new_bs


def reset_target_delta(blendshape, target):
    index = target_index(blendshape, target)
    cmds.blendShape(blendshape, edit=True, resetTargetDelta=(0, index))


def connect_target(blendshape, target, driver_plug, driver_min=0.0, driver_max=1.0):
    """Drive a target from any attribute range with a ``remapValue``."""
    from jeffy.core import nodes

    index = target_index(blendshape, target)
    value = nodes.remap(driver_plug, driver_min, driver_max, 0.0, 1.0)
    cmds.connectAttr(value, "%s.weight[%d]" % (blendshape, index), force=True)
    return value


def export_weights(blendshape, path):
    """Export the base weights and per-target weights (painted maps)."""
    count = mesh_tools.vertex_count(base_geometry(blendshape))
    data = {"type": "jeffy_blendshape_weights", "version": fileio.FORMAT_VERSION, "vertex_count": count,
            "base": deformer_utils.get_weight_list(blendshape, "%s.inputTarget[0].baseWeights" % blendshape, count),
            "targets": {}}
    for index, alias in get_targets(blendshape):
        plug = "%s.inputTarget[0].inputTargetGroup[%d].targetWeights" % (blendshape, index)
        data["targets"][alias] = deformer_utils.get_weight_list(blendshape, plug, count)
    return fileio.write_json(path, data)


def import_weights(blendshape, path):
    data = fileio.read_json(path)
    deformer_utils.set_weight_list("%s.inputTarget[0].baseWeights" % blendshape, data["base"])
    for alias, values in data["targets"].items():
        try:
            index = target_index(blendshape, alias)
        except ValueError:
            continue
        deformer_utils.set_weight_list("%s.inputTarget[0].inputTargetGroup[%d].targetWeights" % (blendshape, index),
                                       values)
