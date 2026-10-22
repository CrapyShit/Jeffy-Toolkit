"""The setup tag: one hidden ``network`` node per setup.

The tag is how setups find each other. It stores:

* type, version, name, side, options and guide positions (strings / JSON),
* the slots (joints the user gave), as message lists (rename proof) and as
  names (used to rebuild after a delete),
* the controls, outputs, driven joints and every node the build created,
* links to the rig base, the parent setup (for layers: the base setup) and
  the mirrored setup.

Every control and output of a setup has a ``jeffySetup`` message attribute
connected from its tag, so any of them leads back to the setup.
"""

import json

from maya import cmds

from jeffy.core import attributes, naming

TYPE_ATTR = "jeffySetupType"
VERSION_ATTR = "jeffySetupVersion"
NAME_ATTR = "jeffySetupName"
SIDE_ATTR = "jeffySetupSide"
LINK_ATTR = "jeffySetup"  # on controls / outputs / groups: message from the tag

TAG_SUFFIX = "SETUP"


# ---------------------------------------------------------------------------
# Creation / queries
# ---------------------------------------------------------------------------
def create(setup_type, name, side, version=1):
    tag = cmds.createNode("network", name=naming.unique_name(naming.compose(name, side, TAG_SUFFIX)),
                          skipSelect=True)
    attributes.set_string(tag, TYPE_ATTR, setup_type)
    attributes.set_string(tag, NAME_ATTR, name)
    attributes.set_string(tag, SIDE_ATTR, side or "")
    attributes.add_attr(tag, VERSION_ATTR, "int", default=version, keyable=False)
    for attr in (TYPE_ATTR, VERSION_ATTR):
        cmds.setAttr("%s.%s" % (tag, attr), lock=True)
    return tag


def is_tag(node):
    return bool(node) and cmds.objExists(node) and cmds.attributeQuery(TYPE_ATTR, node=node, exists=True)


def all_tags():
    """Every setup tag in the scene (namespaces included), in creation order."""
    result = []
    for pattern in ("*.%s" % TYPE_ATTR, "*:*.%s" % TYPE_ATTR):
        for node in cmds.ls(pattern, objectsOnly=True) or []:
            if node not in result:
                result.append(node)
    return result


def setup_type(tag):
    return attributes.get_string(tag, TYPE_ATTR)


def name_of(tag):
    return attributes.get_string(tag, NAME_ATTR)


def side_of(tag):
    return attributes.get_string(tag, SIDE_ATTR) or None


# ---------------------------------------------------------------------------
# JSON values
# ---------------------------------------------------------------------------
def set_data(tag, key, value):
    attr = "jeffy_" + key
    attributes.set_string(tag, attr, json.dumps(value, sort_keys=True))


def get_data(tag, key, default=None):
    text = attributes.get_string(tag, "jeffy_" + key, "")
    if not text:
        return default
    try:
        return json.loads(text)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Message lists
# ---------------------------------------------------------------------------
def _plug(tag, key):
    return "%s.jeffyMsg_%s" % (tag, key)


def set_nodes(tag, key, nodes):
    """Store ``nodes`` (ordered, ``None`` keeps an empty index) on ``tag``."""
    attr = "jeffyMsg_" + key
    plug = _plug(tag, key)
    if cmds.attributeQuery(attr, node=tag, exists=True):
        for index in cmds.getAttr(plug, multiIndices=True) or []:
            element = "%s[%d]" % (plug, index)
            for source in cmds.listConnections(element, source=True, destination=False, plugs=True) or []:
                cmds.disconnectAttr(source, element)
            cmds.removeMultiInstance(element, **{"break": True})  # "break" is a Python keyword
    else:
        attributes.add_attr(tag, attr, "message", multi=True)
    for index, node in enumerate(nodes):
        if node and cmds.objExists(node):
            cmds.connectAttr(node + ".message", "%s[%d]" % (plug, index), force=True)


def add_nodes(tag, key, nodes):
    """Append ``nodes`` to a message list."""
    attr = "jeffyMsg_" + key
    plug = _plug(tag, key)
    if not cmds.attributeQuery(attr, node=tag, exists=True):
        attributes.add_attr(tag, attr, "message", multi=True)
    indices = cmds.getAttr(plug, multiIndices=True) or []
    index = (max(indices) + 1) if indices else 0
    for node in nodes:
        if node and cmds.objExists(node):
            cmds.connectAttr(node + ".message", "%s[%d]" % (plug, index), force=True)
            index += 1


def get_nodes(tag, key, keep_empty=False):
    """Nodes of a message list, in index order (long names stay unique)."""
    attr = "jeffyMsg_" + key
    if not cmds.attributeQuery(attr, node=tag, exists=True):
        return []
    plug = _plug(tag, key)
    indices = cmds.getAttr(plug, multiIndices=True) or []
    if not indices:
        return []
    result = [None] * (max(indices) + 1) if keep_empty else []
    for index in indices:
        sources = cmds.listConnections("%s[%d]" % (plug, index), source=True, destination=False) or []
        if keep_empty:
            result[index] = sources[0] if sources else None
        elif sources:
            result.append(sources[0])
    return result


def set_node(tag, key, node):
    set_nodes(tag, key, [node] if node else [])


def get_node(tag, key):
    nodes = get_nodes(tag, key)
    return nodes[0] if nodes else None


# ---------------------------------------------------------------------------
# Links from controls / outputs back to the tag
# ---------------------------------------------------------------------------
def link(tag, node):
    """Connect ``tag.message`` to ``node.jeffySetup`` (any node of the setup)."""
    if not cmds.attributeQuery(LINK_ATTR, node=node, exists=True):
        cmds.addAttr(node, longName=LINK_ATTR, attributeType="message")
    cmds.connectAttr(tag + ".message", "%s.%s" % (node, LINK_ATTR), force=True)


def linked_tag(node):
    """The tag a node is linked to (or ``None``)."""
    if not cmds.objExists(node) or not cmds.attributeQuery(LINK_ATTR, node=node, exists=True):
        return None
    sources = cmds.listConnections("%s.%s" % (node, LINK_ATTR), source=True, destination=False) or []
    return sources[0] if sources else None
