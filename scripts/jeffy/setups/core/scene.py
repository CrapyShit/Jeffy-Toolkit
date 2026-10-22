"""Tool registry and scene queries (which setups exist, who drives a joint...)."""

import collections

from maya import cmds

from jeffy.core import naming
from jeffy.setups.core import tag as tag_module

#: setup type -> tool class (filled by :func:`register`)
REGISTRY = collections.OrderedDict()
OUTPUT_JOINT_ATTR = "jeffyJoint"


def register(cls):
    """Class decorator registering a setup tool."""
    REGISTRY[cls.TYPE] = cls
    return cls


def load_tools():
    """Import every built-in tool (they register themselves)."""
    import jeffy.setups.tools  # noqa: F401

    return REGISTRY


def tool_class(setup_type):
    load_tools()
    return REGISTRY.get(setup_type)


def wrap(tag):
    """The :class:`~jeffy.setups.core.base.Setup` object of a tag."""
    if not tag_module.is_tag(tag):
        return None
    cls = tool_class(tag_module.setup_type(tag))
    if cls is None:
        from jeffy.setups.core.base import Setup

        cls = Setup
    return cls(tag)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def all_setups(rig=None, setup_type=None):
    """Every setup in the scene (optionally of one rig / one type)."""
    result = []
    for tag in tag_module.all_tags():
        setup = wrap(tag)
        if setup is None:
            continue
        if setup_type and setup.TYPE != setup_type:
            continue
        if rig is not None and setup.TYPE != "rig_base":
            owner = setup.rig
            if owner is None or owner.tag != rig.tag:
                continue
        elif rig is not None and setup.tag != rig.tag:
            continue
        result.append(setup)
    return result


def rigs():
    return all_setups(setup_type="rig_base")


def _transform(node):
    if cmds.objectType(node, isAType="shape"):
        return (cmds.listRelatives(node, parent=True, fullPath=True) or [node])[0]
    return node


def find_setup(node):
    """The setup a node belongs to: its tag, a control, a group, an output or a driven joint."""
    if not node or not cmds.objExists(node):
        return None
    if tag_module.is_tag(node):
        return wrap(node)
    current = _transform(node)
    # the node itself or a parent (controls, outputs, setup groups)
    walker = current
    while walker:
        linked = tag_module.linked_tag(walker)
        if linked:
            return wrap(linked)
        walker = (cmds.listRelatives(walker, parent=True, fullPath=True) or [None])[0]
    # ZRO / OFF groups: the control below them
    if cmds.objectType(current, isAType="transform"):
        for child in cmds.listRelatives(current, allDescendents=True, type="transform", fullPath=True) or []:
            linked = tag_module.linked_tag(child)
            if linked:
                return wrap(linked)
    output = output_driving(current)
    if output:
        return wrap(tag_module.linked_tag(output))
    return None


def output_driving(joint):
    """Output transform driving ``joint`` (or ``None``)."""
    if not cmds.objExists(joint):
        return None
    for plug in cmds.listConnections(joint + ".message", source=False, destination=True, plugs=True) or []:
        node, _, attr = plug.partition(".")
        if attr == OUTPUT_JOINT_ATTR:
            return node
    return None


def setup_driving(joint):
    output = output_driving(joint)
    return wrap(tag_module.linked_tag(output)) if output else None


def ancestors(node):
    """Parents of ``node`` from the closest up (long names)."""
    result = []
    current = (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]
    while current:
        result.append(current)
        current = (cmds.listRelatives(current, parent=True, fullPath=True) or [None])[0]
    return result


def is_ancestor(ancestor, node):
    if not ancestor or not node:
        return False
    target = cmds.ls(ancestor, long=True) or []
    if not target:
        return False
    chain = [cmds.ls(node, long=True)[0]] + ancestors(node)
    return target[0] in chain


def find_rig(joint=None):
    """The rig base a joint belongs to.

    The rig whose root joint is above (or is) the joint wins. With no match,
    the only rig of the scene is used. ``None`` when there is no rig (or
    several and none matches).
    """
    candidates = rigs()
    if not candidates:
        return None
    if joint and cmds.objExists(joint):
        for rig in candidates:
            root = rig.slot_node("root_joint")
            if root and is_ancestor(root, joint):
                return rig
    if len(candidates) == 1:
        return candidates[0]
    unrooted = [rig for rig in candidates if not rig.slot_node("root_joint")]
    return unrooted[0] if len(unrooted) == 1 else None


def short(node):
    return naming.short_name(node) if node else node
