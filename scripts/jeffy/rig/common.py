"""Small helpers shared by the rig building blocks."""

from maya import cmds

from jeffy.core import attributes, dag, mathlib, naming, nodes

AXIS_NAMES = ("x", "y", "z")


def primary_axis(child):
    """Signed axis (``'x'``, ``'-x'`` ...) a child joint is translated along."""
    translate = cmds.getAttr(child + ".translate")[0]
    index = max(range(3), key=lambda i: abs(translate[i]))
    sign = "-" if translate[index] < 0 else ""
    return sign + AXIS_NAMES[index]


def axis_attr(axis, attr="translate"):
    """``('x', 'translate')`` -> ``'translateX'``."""
    return attr + axis.lstrip("+-").upper()


def segment_length(child, axis=None):
    """Rest length of a joint segment (absolute translation along ``axis``)."""
    axis = axis or primary_axis(child)
    return abs(cmds.getAttr("%s.%s" % (child, axis_attr(axis))))


def axis_sign(child, axis=None):
    axis = axis or primary_axis(child)
    return -1.0 if cmds.getAttr("%s.%s" % (child, axis_attr(axis))) < 0 else 1.0


def world_scale_plug(node, name=None):
    """Plug giving the uniform world scale of ``node`` (``decomposeMatrix``).

    Measuring the scale of a node inside the rig (instead of wiring the
    global scale attribute everywhere) makes stretch setups scale proof.
    """
    dm = nodes.decompose_matrix(node + ".worldMatrix[0]", name=name)
    return dm + ".outputScaleX"


def create_group(name, parent=None, match=None, position=None, visible=True, lock=False):
    group = dag.create_group(naming.unique_name(name), parent_node=parent, match=match)
    if position is not None:
        cmds.xform(group, worldSpace=True, translation=position)
    if not visible:
        cmds.setAttr(group + ".visibility", 0)
    if lock:
        attributes.lock_hide(group)
    return group


def create_locator(name, parent=None, match=None, position=None, visible=False):
    locator = cmds.spaceLocator(name=naming.unique_name(name))[0]
    if parent:
        locator = cmds.parent(locator, parent, relative=True)[0]
    if match:
        cmds.matchTransform(locator, match, position=True, rotation=True)
    elif position is not None:
        cmds.xform(locator, worldSpace=True, translation=position)
    if not visible:
        cmds.setAttr(locator + ".visibility", 0)
    return locator


def hide(nodes_list):
    if isinstance(nodes_list, str):
        nodes_list = [nodes_list]
    for node in nodes_list:
        if cmds.objExists(node) and not cmds.getAttr(node + ".visibility", lock=True):
            cmds.setAttr(node + ".visibility", 0)


def lock_all(node):
    attributes.lock_hide(node, ("t", "r", "s"), lock=True, hide=True)


def name_for(base, side, node_type, suffix=""):
    return naming.compose(base + suffix, side, node_type)


def constraint_weight_plugs(constraint):
    """Weight attributes of a constraint in target order."""
    command = getattr(cmds, cmds.nodeType(constraint))
    aliases = command(constraint, query=True, weightAliasList=True) or []
    return ["%s.%s" % (constraint, alias) for alias in aliases]


def connect_visibility(source_plug, targets):
    for target in [targets] if isinstance(targets, str) else targets:
        cmds.connectAttr(source_plug, target + ".visibility", force=True)


def mid_position(a, b, t=0.5):
    from jeffy.core import transform

    return mathlib.lerp_vector(transform.get_position(a), transform.get_position(b), t)
