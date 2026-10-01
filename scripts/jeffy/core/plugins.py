"""Plugin and Maya version helpers."""

from maya import cmds

MATRIX_NODES = "matrixNodes"
QUAT_NODES = "quatNodes"
LOOKDEV_KIT = "lookdevKit"
FBX = "fbxmaya"


def ensure_plugin(name):
    """Load a plugin if needed. Returns ``True`` when it is available."""
    try:
        if not cmds.pluginInfo(name, query=True, loaded=True):
            cmds.loadPlugin(name, quiet=True)
        return True
    except RuntimeError:
        return False


def ensure_matrix_plugins():
    ensure_plugin(MATRIX_NODES)
    ensure_plugin(QUAT_NODES)


def maya_version():
    """Return the Maya version as an ``int`` (``2024``)."""
    try:
        return int(cmds.about(apiVersion=True)) // 10000
    except Exception:
        return 0


def has_node_type(node_type):
    """True when a node type exists (e.g. ``'uvPin'``, ``'blendMatrix'``)."""
    try:
        return node_type in (cmds.allNodeTypes() or [])
    except Exception:
        return False


def supports_offset_parent_matrix():
    """``offsetParentMatrix`` exists on transforms since Maya 2020."""
    return maya_version() >= 2020
