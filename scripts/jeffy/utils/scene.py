"""Scene cleanup and rig finalisation helpers."""

from maya import cmds, mel

from jeffy.controls.control import is_control
from jeffy.core import attributes, dag, logger

LOG = logger.get_logger("scene")

PROTECTED_NAMESPACES = ("UI", "shared")
TURTLE_NODES = ("TurtleDefaultBakeLayer", "TurtleBakeLayerManager", "TurtleRenderOptions", "TurtleUIOptions")


# ---------------------------------------------------------------------------
# Namespaces
# ---------------------------------------------------------------------------
def list_namespaces():
    """Every namespace (deepest first) except Maya's internal ones."""
    namespaces = cmds.namespaceInfo(":", listOnlyNamespaces=True, recurse=True) or []
    namespaces = [ns for ns in namespaces if ns not in PROTECTED_NAMESPACES]
    return sorted(namespaces, key=lambda ns: ns.count(":"), reverse=True)


def remove_namespaces(namespaces=None):
    """Merge namespaces into the root namespace (references are skipped)."""
    removed = []
    referenced = set()
    for ref in cmds.ls(type="reference") or []:
        try:
            referenced.add(cmds.referenceQuery(ref, namespace=True).lstrip(":"))
        except RuntimeError:
            continue
    for namespace in namespaces or list_namespaces():
        if namespace in referenced or not cmds.namespace(exists=namespace):
            continue
        try:
            cmds.namespace(removeNamespace=namespace, mergeNamespaceWithRoot=True)
            removed.append(namespace)
        except RuntimeError as error:
            LOG.warning("Could not remove namespace %s: %s", namespace, error)
    return removed


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
def delete_unknown_nodes():
    nodes = cmds.ls(type=["unknown", "unknownDag", "unknownTransform"]) or []
    deleted = []
    for node in nodes:
        if not cmds.objExists(node):
            continue
        try:
            cmds.lockNode(node, lock=False)
            cmds.delete(node)
            deleted.append(node)
        except RuntimeError:
            LOG.warning("Could not delete %s", node)
    return deleted


def remove_unknown_plugins():
    removed = []
    for plugin in cmds.unknownPlugin(query=True, list=True) or []:
        try:
            cmds.unknownPlugin(plugin, remove=True)
            removed.append(plugin)
        except RuntimeError:
            LOG.warning("Could not remove unknown plugin %s", plugin)
    return removed


def delete_turtle_nodes():
    deleted = []
    for node in TURTLE_NODES:
        if cmds.objExists(node):
            cmds.lockNode(node, lock=False)
            cmds.delete(node)
            deleted.append(node)
    if cmds.pluginInfo("Turtle", query=True, loaded=True):
        try:
            cmds.unloadPlugin("Turtle", force=True)
        except RuntimeError:
            pass
    return deleted


def delete_unused_nodes():
    """Delete unused render/utility nodes (Hypershade's cleanup)."""
    mel.eval("MLdeleteUnused")


def delete_display_layers():
    layers = [layer for layer in cmds.ls(type="displayLayer") or [] if layer != "defaultLayer"
              and not cmds.referenceQuery(layer, isNodeReferenced=True)]
    if layers:
        cmds.delete(layers)
    return layers


def import_references():
    imported = []
    for ref in cmds.ls(type="reference") or []:
        if ref == "sharedReferenceNode" or ref.endswith("sharedReferenceNode"):
            continue
        try:
            path = cmds.referenceQuery(ref, filename=True)
            cmds.file(path, importReference=True)
            imported.append(path)
        except RuntimeError:
            continue
    return imported


def find_empty_groups(root=None):
    nodes = cmds.listRelatives(root, allDescendents=True, type="transform", fullPath=True) if root else \
        cmds.ls(type="transform", long=True)
    result = []
    for node in nodes or []:
        if cmds.nodeType(node) != "transform" or is_control(node):
            continue
        if cmds.listRelatives(node, children=True):
            continue
        if cmds.listConnections(node, source=True, destination=True):
            continue
        result.append(node)
    return result


def delete_empty_groups(root=None):
    deleted = []
    while True:
        empty = find_empty_groups(root)
        if not empty:
            return deleted
        cmds.delete(empty)
        deleted.extend(empty)


def clean_scene():
    """Run every safe cleanup step and return a report dict."""
    return {
        "unknown_nodes": delete_unknown_nodes(),
        "unknown_plugins": remove_unknown_plugins(),
        "turtle": delete_turtle_nodes(),
    }


# ---------------------------------------------------------------------------
# Rig finalisation
# ---------------------------------------------------------------------------
def lock_rig(root, lock=True, hide_history=True):
    """Lock transform channels of every non-control node under ``root``.

    With ``hide_history`` the utility nodes are set to *not historically
    interesting* so they disappear from the channel box INPUTS section.
    """
    nodes = [root] + (cmds.listRelatives(root, allDescendents=True, type="transform", fullPath=True) or [])
    for node in nodes:
        if is_control(node):
            continue
        for attr in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"):
            plug = "%s.%s" % (node, attr)
            if cmds.objExists(plug) and not cmds.listConnections(plug, source=True, destination=False):
                cmds.setAttr(plug, lock=lock)
    if hide_history:
        set_historical_interest(root, 0 if lock else 1)


def set_historical_interest(root, value=0):
    nodes = cmds.listHistory(root, allConnections=True) or []
    for node in nodes:
        if cmds.objExists(node + ".isHistoricallyInteresting") and not cmds.objectType(node, isAType="dagNode"):
            try:
                cmds.setAttr(node + ".isHistoricallyInteresting", value)
            except RuntimeError:
                continue


def set_joint_display(root, visible=False, draw_style=None):
    joints = [root] + (cmds.listRelatives(root, allDescendents=True, type="joint", fullPath=True) or [])
    for joint in joints:
        if draw_style is not None:
            cmds.setAttr(joint + ".drawStyle", draw_style)
        if not cmds.getAttr(joint + ".visibility", lock=True) and not cmds.listConnections(
                joint + ".visibility", source=True, destination=False):
            cmds.setAttr(joint + ".visibility", visible)


def scene_report():
    """Quick statistics about the scene."""
    return {
        "joints": len(cmds.ls(type="joint") or []),
        "meshes": len(cmds.ls(type="mesh", noIntermediate=True) or []),
        "skin_clusters": len(cmds.ls(type="skinCluster") or []),
        "blendshapes": len(cmds.ls(type="blendShape") or []),
        "constraints": len(cmds.ls(type="constraint") or []),
        "expressions": len(cmds.ls(type="expression") or []),
        "utility_nodes": len(cmds.ls(type=["multiplyDivide", "plusMinusAverage", "condition", "reverse",
                                           "blendColors", "remapValue", "clamp", "multDoubleLinear",
                                           "addDoubleLinear", "multMatrix", "decomposeMatrix"]) or []),
        "namespaces": len(list_namespaces()),
        "top_nodes": len(dag.top_level_nodes()),
    }


def add_rig_info(node, **info):
    """Store arbitrary info strings on a node (author, version, date...)."""
    for key, value in info.items():
        attributes.set_string(node, "info_" + key, str(value))
