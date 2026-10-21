"""Helpers shared by the flexible rig builders."""

from maya import cmds

from jeffy.controls.control import Control
from jeffy.core import attributes, naming, nodes

#: Drawing override colours used by the course rig (left red, right yellow, centre green).
SIDE_COLORS = {"L": (1.0, 0.0, 0.0), "R": (1.0, 1.0, 0.0), "C": (0.0, 1.0, 0.0)}
MASTER_COLOR = (0.0, 1.0, 1.0)
META_PREFIX = "jeffyFlex_"


def side_color(side):
    return SIDE_COLORS.get(side or "C", SIDE_COLORS["C"])


def control(name, side=None, shape="circle", size=1.0, axis="x", parent=None, match=None, position=None,
            match_rotation=True, lock=("v",), color_value=None):
    """Course style control: one zero group above the control, side colour."""
    return Control.create(name, side=side, shape=shape, size=size, axis=axis, parent=parent, match=match,
                          position=position, match_rotation=match_rotation, offsets=("zero",), lock=lock,
                          color_value=color_value or side_color(side))


def group(name, side=None, parent=None, match=None, visible=True):
    node = cmds.createNode("transform", name=naming.unique_name(naming.compose(name, side, "group")),
                           skipSelect=True)
    if parent:
        node = cmds.parent(node, parent, relative=True)[0]
    if match:
        cmds.matchTransform(node, match, position=True, rotation=True)
    if not visible:
        cmds.setAttr(node + ".visibility", 0)
    return node


def lock_free(nodes, attrs=("t", "r", "s")):
    """Lock and hide channels that are not driven (constrained channels stay as they are)."""
    for node in [nodes] if isinstance(nodes, str) else nodes:
        for attr in attributes.expand(attrs):
            plug = "%s.%s" % (node, attr)
            if not cmds.objExists(plug):
                continue
            if cmds.listConnections(plug, source=True, destination=False):
                continue
            cmds.setAttr(plug, lock=True, keyable=False, channelBox=False)


def node(node_type, name, side=None, suffix_key="utility", **attrs):
    created = cmds.createNode(nodes.node_type(node_type),
                              name=naming.unique_name(naming.compose(name, side, suffix_key)), skipSelect=True)
    for attr, value in attrs.items():
        attributes.set_or_connect(value, "%s.%s" % (created, attr))
    return created


def constraint_weights(constraint):
    command = getattr(cmds, cmds.nodeType(constraint))
    aliases = command(constraint, query=True, weightAliasList=True) or []
    return ["%s.%s" % (constraint, alias) for alias in aliases]


def blend_constraint(command, targets, driven, weight_plugs, **kwargs):
    """Constraint to several targets whose weights are driven by ``weight_plugs``."""
    kwargs.setdefault("maintainOffset", False)
    constraint = command(list(targets) + [driven], **kwargs)[0]
    for plug, weight in zip(weight_plugs, constraint_weights(constraint)):
        cmds.connectAttr(plug, weight, force=True)
    return constraint


# ---------------------------------------------------------------------------
# Meta data (ordered message lists on a node)
# ---------------------------------------------------------------------------
def store(node, key, items):
    plug = attributes.add_attr(node, META_PREFIX + key, "message", multi=True)
    for index, item in enumerate(items):
        if item:
            cmds.connectAttr(item + ".message", "%s[%d]" % (plug, index), force=True)
    return plug


def fetch(node, key):
    plug = "%s.%s%s" % (node, META_PREFIX, key)
    if not cmds.objExists(plug):
        return []
    result = []
    for index in cmds.getAttr(plug, multiIndices=True) or []:
        result.extend(cmds.listConnections("%s[%d]" % (plug, index), source=True, destination=False) or [])
    return result


def find_meta_owner(node, key):
    """Walk up from ``node`` until a node carrying ``jeffyFlex_<key>`` is found."""
    current = node
    while current:
        if cmds.attributeQuery(META_PREFIX + key, node=current, exists=True):
            return current
        parents = cmds.listRelatives(current, parent=True, fullPath=True) or []
        current = parents[0] if parents else None
    return None
