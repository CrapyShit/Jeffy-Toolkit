"""Rig Base: the rig's top groups and its Global and Root controls.

::

    character_RIG
      C_global_ZRO > OFF > C_global_CTL      world space role, globalScale, visibility switches
        C_root_ZRO > OFF > C_root_CTL        root space role (the main mover)
      character_controls_GRP                 every setup's controls
      character_systems_GRP                  every setup's systems (hidden)
      character_skeleton_GRP                 your skeleton (optional), follows the Global control
      character_geometry_GRP                 your meshes

Build it first: the other tools find it from their joints.
"""

from maya import cmds

from jeffy.core import attributes, mathlib, matrix, naming, transform
from jeffy.setups.core import attach, scene
from jeffy.setups.core import tag as tag_module
from jeffy.setups.core.base import Setup
from jeffy.setups.core.schema import SIZE_OPTION, Option, SetupError, Slot

GROUP_KEYS = ("controls", "systems", "skeleton", "geometry")
DISPLAY_TYPES = ("normal", "template", "reference")


@scene.register
class RigBase(Setup):
    TYPE = "rig_base"
    LABEL = "Rig Base"
    CATEGORY = "base"
    ORDER = 0
    DESCRIPTION = ("The rig's top groups, a Global control (global scale, visibility and display switches) and a "
                   "Root control. Build it first: every other tool puts its controls and systems inside it.")
    SLOTS = (
        Slot("root_joint", "Root joint", optional=True,
             tip="Top joint of your skeleton (optional). It follows the Root control and can move into the "
                 "rig's skeleton group."),
    )
    OPTIONS = (
        Option("move_skeleton", "Put skeleton in rig", True,
               tip="Parent the root joint under the rig's skeleton group (joint values do not change). It goes "
                   "back where it was when the Rig Base is deleted."),
        SIZE_OPTION,
    )
    MIRRORABLE = False
    HAS_GROUPS = False

    @classmethod
    def resolve_name_side(cls, slots, options, name=None, side=None):
        name = naming.legalize(str(name or "character").strip()).strip("_") or "character"
        return name, naming.SIDE_CENTER

    @classmethod
    def validate(cls, slots, options):
        root = slots.get("root_joint")
        if not root:
            return
        for rig in scene.rigs():
            other = rig.slot_node("root_joint")
            if other and (scene.is_ancestor(other, root) or scene.is_ancestor(root, other)):
                raise SetupError("%s is already part of %s" % (naming.short_name(root), rig.describe()))

    @classmethod
    def driven_joints(cls, slots):
        return [slots["root_joint"]] if slots.get("root_joint") else []

    # ------------------------------------------------------------------
    def build_setup(self):
        name = self.name
        root_joint = self.slot_node("root_joint")
        size = _skeleton_radius(root_joint) * self.option("size")

        top = cmds.createNode("transform", name=naming.unique_name("%s_RIG" % name), skipSelect=True)
        tag_module.link(self.tag, top)
        tag_module.set_node(self.tag, "group_top", top)
        groups = {}
        for key in GROUP_KEYS:
            group = cmds.createNode("transform", name=naming.unique_name("%s_%s_GRP" % (name, key)), skipSelect=True)
            groups[key] = cmds.parent(group, top, relative=True)[0]
            tag_module.set_node(self.tag, "group_" + key, groups[key])
            tag_module.link(self.tag, groups[key])

        glob = self.control("global", "global", shape="master", size=size, axis="y", parent=top,
                            position=(0.0, 0.0, 0.0), lock=("v",), role="world")
        root = self.control("root", "root", shape="circle", size=size * 0.75, axis="y", parent=glob.node,
                            position=(0.0, 0.0, 0.0), lock=("s", "v"), role="root")
        root.set_parent_tag(glob.node)
        self._global_attributes(glob.node, groups)
        # the skeleton group carries the Global control (and its scale): every joint scales with the rig,
        # driven or not, and the bind joints keep a scale of 1
        self.follow(groups["skeleton"], glob.node, label="global")

        self.add_output("root", root.node + ".worldMatrix[0]")
        if root_joint:
            if self.option("move_skeleton"):
                parent = (cmds.listRelatives(root_joint, parent=True, fullPath=True) or [None])[0]
                tag_module.set_data(self.tag, "skeleton_parent", parent)
                if parent != cmds.ls(groups["skeleton"], long=True)[0]:
                    root_joint = cmds.parent(root_joint, groups["skeleton"])[0]
            offset = cmds.createNode("multMatrix", name=naming.unique_name("%s_rootJoint_MM" % name),
                                     skipSelect=True)
            matrix.set_matrix_attr(offset + ".matrixIn[0]", matrix.offset_matrix(root_joint, root.node))
            cmds.connectAttr(root.node + ".worldMatrix[0]", offset + ".matrixIn[1]")
            self.add_output("rootJoint", offset + ".matrixSum", joint=root_joint)

    def _global_attributes(self, glob, groups):
        attributes.add_separator(glob, "scale")
        scale = attributes.add_attr(glob, "globalScale", "float", default=1.0, minimum=0.001)
        for axis in "XYZ":
            cmds.connectAttr(scale, "%s.scale%s" % (glob, axis))
        attributes.lock_hide(glob, ("s",), lock=False, hide=True)

        attributes.add_separator(glob, "display")
        switches = (("controls", "controlsVis", True), ("skeleton", "jointsVis", True),
                    ("geometry", "geometryVis", True), ("systems", "systemsVis", False))
        for key, attr, default in switches:
            plug = attributes.add_attr(glob, attr, "bool", default=default, keyable=False, channel_box=True)
            cmds.setAttr(plug, default)
            cmds.connectAttr(plug, groups[key] + ".visibility")
        for key, attr, default in (("skeleton", "jointsDisplay", 2), ("geometry", "geometryDisplay", 0)):
            plug = attributes.add_attr(glob, attr, "enum", enum_names=DISPLAY_TYPES, default=default, keyable=False,
                                       channel_box=True)
            cmds.setAttr(plug, default)
            cmds.setAttr(groups[key] + ".overrideEnabled", 1)
            cmds.connectAttr(plug, groups[key] + ".overrideDisplayType")

    # ------------------------------------------------------------------
    def rig_group(self, key):
        """``controls``, ``systems``, ``skeleton``, ``geometry`` or ``top``."""
        return tag_module.get_node(self.tag, "group_" + key)

    def members(self):
        """Every other setup of this rig."""
        return [setup for setup in scene.all_setups(rig=self) if setup.tag != self.tag]

    def after_release(self):
        root_joint = self.slot_node("root_joint")
        if not root_joint or not cmds.objExists(root_joint):
            return
        original = tag_module.get_data(self.tag, "skeleton_parent")
        current = (cmds.listRelatives(root_joint, parent=True, fullPath=True) or [None])[0]
        skeleton = self.rig_group("skeleton")
        if current and skeleton and current == (cmds.ls(skeleton, long=True) or [None])[0]:
            if original and cmds.objExists(original):
                cmds.parent(root_joint, original)
            else:
                cmds.parent(root_joint, world=True)

    def rebuild(self, options=None, slots=None, guides=None, name=None, side=None):
        """Rebuild the Rig Base and every setup of the rig."""
        bases, layers = [], []
        for member in self.members():
            if member.CATEGORY == "layer":
                continue
            if not member.is_mirror_secondary():
                bases.append(member.spec())
            for layer in member.all_layers():
                if not layer.is_mirror_secondary():
                    layers.append(layer.spec())
        specs = bases + layers
        spec = self.spec()
        spec["options"].update(options or {})
        spec["slots"].update(slots or {})
        self.delete()
        new = RigBase.create(spec["slots"], spec["options"], name=name or spec["name"])
        for member_spec in specs:
            scene.tool_class(member_spec["type"]).create(member_spec["slots"], member_spec["options"],
                                                         name=member_spec["name"], side=member_spec["side"],
                                                         guides=member_spec["guides"], rig=new)
        attach.refresh_rig(new)
        return new


def _skeleton_radius(root_joint):
    """Control radius from the skeleton's size (all joints of the scene without a root joint)."""
    if root_joint:
        joints = [root_joint] + (cmds.listRelatives(root_joint, allDescendents=True, type="joint",
                                                    fullPath=True) or [])
    else:
        joints = cmds.ls(type="joint", long=True) or []
    if not joints:
        return 1.0
    points = [transform.get_position(joint) for joint in joints]
    low, high = mathlib.bounding_box(points)
    width = max(high[0] - low[0], high[2] - low[2])
    height = high[1] - low[1]
    return max(width * 0.55, height * 0.3, 1e-3)
