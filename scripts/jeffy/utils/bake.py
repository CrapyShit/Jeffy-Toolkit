"""Baking and game export helpers."""

import os

from maya import cmds, mel

from jeffy.core import dag, naming, plugins

TRANSFORM_ATTRS = ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ", "scaleX", "scaleY",
                   "scaleZ")


def frame_range():
    return cmds.playbackOptions(query=True, minTime=True), cmds.playbackOptions(query=True, maxTime=True)


def bake(nodes, start=None, end=None, attributes=TRANSFORM_ATTRS, sample=1.0, euler_filter=True,
         simulation=True):
    """Bake attributes of nodes over a frame range (default: playback range)."""
    if not nodes:
        return []
    default_start, default_end = frame_range()
    start = default_start if start is None else start
    end = default_end if end is None else end
    cmds.bakeResults(nodes, simulation=simulation, time=(start, end), sampleBy=sample,
                     attribute=list(attributes), disableImplicitControl=True, preserveOutsideKeys=True,
                     sparseAnimCurveBake=False, removeBakedAttributeFromLayer=False, bakeOnOverrideLayer=False,
                     minimizeRotation=True)
    if euler_filter:
        curves = cmds.listConnections(nodes, type="animCurve", source=True, destination=False) or []
        rotation_curves = [c for c in curves if cmds.nodeType(c) == "animCurveTA"]
        if rotation_curves:
            cmds.filterCurve(rotation_curves, filter="euler")
    return nodes


def delete_constraints(nodes):
    constraints = []
    for node in nodes:
        constraints.extend(cmds.listRelatives(node, type="constraint", fullPath=True) or [])
        for con in cmds.listConnections(node, type="constraint", source=True, destination=False) or []:
            if con not in constraints:
                constraints.append(con)
    constraints = [c for c in set(constraints) if cmds.objExists(c)]
    if constraints:
        cmds.delete(constraints)
    return constraints


def bake_skeleton(root, start=None, end=None, delete_constraint_nodes=True):
    """Bake every joint under ``root`` then remove the constraints driving them."""
    joints = [root] + (cmds.listRelatives(root, allDescendents=True, type="joint", fullPath=True) or [])
    bake(joints, start, end)
    if delete_constraint_nodes:
        delete_constraints(joints)
    return joints


def create_export_skeleton(root, prefix="", suffix="", parent=None, joint_filter=None):
    """Duplicate a joint hierarchy (joints only) constrained to the original.

    The copy follows the rig and can be baked/exported without touching it.
    ``joint_filter`` (callable) can skip joints (e.g. helper joints).
    Returns ``{original: copy}``.
    """
    mapping = {}
    joints = [dag.long_name(root)] + (cmds.listRelatives(root, allDescendents=True, type="joint", fullPath=True)
                                      or [])
    joints = sorted(joints, key=lambda j: j.count("|"))
    for joint in joints:
        if joint_filter and not joint_filter(joint):
            continue
        short = naming.strip_namespace(joint)
        copy = cmds.createNode("joint", name=naming.unique_name(prefix + short + suffix), skipSelect=True)
        cmds.matchTransform(copy, joint, position=True, rotation=True)
        cmds.makeIdentity(copy, apply=True, rotate=True)
        for attr in ("radius", "rotateOrder"):
            cmds.setAttr("%s.%s" % (copy, attr), cmds.getAttr("%s.%s" % (joint, attr)))
        parent_joint = dag.get_parent(joint)
        while parent_joint and parent_joint not in mapping:
            parent_joint = dag.get_parent(parent_joint)
        if parent_joint:
            copy = cmds.parent(copy, mapping[parent_joint])[0]
        elif parent:
            copy = cmds.parent(copy, parent)[0]
        mapping[joint] = copy
    for joint, copy in mapping.items():
        cmds.parentConstraint(joint, copy, maintainOffset=True)
        cmds.scaleConstraint(joint, copy, maintainOffset=True)
    return mapping


def export_fbx(nodes, path, start=None, end=None, animation=True, bake_animation=True, up_axis="y"):
    """Export nodes to FBX with sensible game settings."""
    if not plugins.ensure_plugin(plugins.FBX):
        raise RuntimeError("The FBX plugin (fbxmaya) is not available")
    default_start, default_end = frame_range()
    start = default_start if start is None else start
    end = default_end if end is None else end
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    mel.eval("FBXResetExport")
    mel.eval("FBXExportSmoothingGroups -v true")
    mel.eval("FBXExportSkins -v true")
    mel.eval("FBXExportShapes -v true")
    mel.eval("FBXExportInputConnections -v false")
    mel.eval("FBXExportUpAxis %s" % up_axis)
    mel.eval("FBXExportAnimationOnly -v false")
    if animation:
        mel.eval("FBXExportBakeComplexAnimation -v %s" % ("true" if bake_animation else "false"))
        mel.eval("FBXExportBakeComplexStart -v %d" % int(start))
        mel.eval("FBXExportBakeComplexEnd -v %d" % int(end))
        mel.eval("FBXExportBakeComplexStep -v 1")
    else:
        mel.eval("FBXExportBakeComplexAnimation -v false")
    cmds.select(nodes, replace=True)
    mel.eval('FBXExport -f "%s" -s' % path.replace("\\", "/"))
    return path


def bake_and_export(root, meshes, path, start=None, end=None):
    """Game export in one go: export skeleton -> bake -> FBX -> clean up."""
    mapping = create_export_skeleton(root)
    new_root = mapping[dag.long_name(root)]
    try:
        bake_skeleton(new_root, start, end)
        export_fbx([new_root] + list(meshes or []), path, start, end)
    finally:
        if cmds.objExists(new_root):
            cmds.delete(new_root)
    return path
