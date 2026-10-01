"""Standard rig hierarchy with global scale and display switches.

::

    character_RIG
    |-- geometry_GRP
    |-- skeleton_GRP
    |-- controls_GRP
    |   `-- C_global_ZRO > C_global_CTL > C_local_ZRO > C_local_CTL
    |-- systems_GRP        (hidden by default)
    `-- extras_GRP
"""

from maya import cmds

from jeffy.controls.control import Control
from jeffy.core import attributes, naming

RIG_ATTR = "jeffyRig"
DISPLAY_TYPES = ["normal", "template", "reference"]


class RigStructure(object):
    """Accessors for the groups/controls of a rig hierarchy."""

    KEYS = ("rig", "geometry", "skeleton", "controls", "systems", "extras", "global_ctl", "local_ctl")

    def __init__(self, rig):
        self.rig = rig

    def _member(self, key):
        return (attributes.get_message(self.rig, "jeffy_" + key) or [None])[0]

    @property
    def geometry(self):
        return self._member("geometry")

    @property
    def skeleton(self):
        return self._member("skeleton")

    @property
    def controls(self):
        return self._member("controls")

    @property
    def systems(self):
        return self._member("systems")

    @property
    def extras(self):
        return self._member("extras")

    @property
    def global_ctl(self):
        return self._member("global_ctl")

    @property
    def local_ctl(self):
        return self._member("local_ctl")

    @property
    def name(self):
        return attributes.get_string(self.rig, RIG_ATTR)

    @property
    def scale_plug(self):
        return self.global_ctl + ".globalScale"

    def as_dict(self):
        return {key: getattr(self, key) for key in self.KEYS}


def create(name="character", size=10.0):
    """Create the rig hierarchy and return a :class:`RigStructure`."""
    rig = cmds.createNode("transform", name=naming.unique_name("%s_RIG" % name), skipSelect=True)
    attributes.set_string(rig, RIG_ATTR, name)
    groups = {}
    for key in ("geometry", "skeleton", "controls", "systems", "extras"):
        groups[key] = cmds.createNode("transform", name=naming.unique_name("%s_GRP" % key), parent=rig,
                                      skipSelect=True)

    global_ctl = Control.create("global", side="C", shape="master", size=size, parent=groups["controls"],
                                lock=("v",), color_value="yellow")
    local_ctl = Control.create("local", side="C", shape="circle_arrows", size=size * 0.8,
                               parent=global_ctl.node, lock=("v", "s"), color_value="light_yellow")
    local_ctl.set_parent_tag(global_ctl.node)

    gctl = global_ctl.node
    attributes.add_separator(gctl, "rig")
    scale_plug = attributes.add_attr(gctl, "globalScale", "float", default=1.0, minimum=0.001)
    for axis in "XYZ":
        cmds.connectAttr(scale_plug, "%s.scale%s" % (gctl, axis))
    attributes.lock_hide(gctl, ("sx", "sy", "sz"))

    attributes.add_separator(gctl, "display")
    _display_switch(gctl, "geometry", groups["geometry"], default_type=2)
    _display_switch(gctl, "skeleton", groups["skeleton"], default_type=0, visible=False)
    vis = attributes.add_attr(gctl, "controlsVis", "bool", default=True, keyable=False, channel_box=True)
    cmds.connectAttr(vis, groups["controls"] + ".visibility")
    vis = attributes.add_attr(gctl, "systemsVis", "bool", default=False, keyable=False, channel_box=True)
    cmds.connectAttr(vis, groups["systems"] + ".visibility")
    vis = attributes.add_attr(gctl, "extrasVis", "bool", default=True, keyable=False, channel_box=True)
    cmds.connectAttr(vis, groups["extras"] + ".visibility")

    for key, node in list(groups.items()) + [("global_ctl", gctl), ("local_ctl", local_ctl.node)]:
        attributes.add_message(rig, "jeffy_" + key, node)
    for group in groups.values():
        attributes.lock_hide(group, ("t", "r", "s"), hide=False)
    attributes.lock_hide(rig, ("t", "r", "s"), hide=False)
    return RigStructure(rig)


def _display_switch(ctl, label, group, default_type=0, visible=True):
    vis = attributes.add_attr(ctl, label + "Vis", "bool", default=visible, keyable=False, channel_box=True)
    display = attributes.add_attr(ctl, label + "Display", "enum", enum_names=DISPLAY_TYPES, default=default_type,
                                  keyable=False, channel_box=True)
    cmds.connectAttr(vis, group + ".visibility")
    cmds.setAttr(group + ".overrideEnabled", 1)
    cmds.connectAttr(display, group + ".overrideDisplayType")


def find(name=None):
    """Return existing :class:`RigStructure` objects (optionally by name)."""
    result = []
    for node in cmds.ls("*.%s" % RIG_ATTR, "*:*.%s" % RIG_ATTR, objectsOnly=True) or []:
        structure = RigStructure(node)
        if name is None or structure.name == name:
            result.append(structure)
    return result


def get_or_create(name="character", size=10.0):
    existing = find(name)
    return existing[0] if existing else create(name, size)
