"""Component base class for the auto-rigger.

A component owns:

* ``GUIDES`` - its guide markers ``(label, default_position, parent_label)``
  authored for the left/centre side (right side positions are mirrored),
* ``SETTINGS`` - options with default values (stored on the guide root),
* the build steps that create joints, controls and systems,
* ``outputs`` - named attachment points ``{name: (rig_node, joint)}`` that
  child components reference as ``"<side>_<name>.<output>"``.

Subclass it, implement :meth:`build_skeleton` / :meth:`build_rig` and
register the class with :func:`jeffy.autorig.components.register`.
"""

from maya import cmds

from jeffy.autorig import guides
from jeffy.core import attributes, mathlib, naming
from jeffy.joints import orient as orient_tools
from jeffy.joints import tools as joint_tools

COMPONENT_ATTR = "jeffyComponent"


class Component(object):
    TYPE = "base"
    DESCRIPTION = ""
    GUIDES = []
    SETTINGS = {}
    DEFAULT_SIDE = "C"
    DEFAULT_NAME = "component"
    MIRRORABLE = False

    def __init__(self, name=None, side=None, settings=None, positions=None, parent_output="", size=1.0):
        self.name = name or self.DEFAULT_NAME
        self.side = side or self.DEFAULT_SIDE
        self.settings = dict(self.SETTINGS)
        self.settings.update(settings or {})
        self.positions = dict(positions or {})
        self.parent_output = parent_output or ""
        self.size = size
        self.outputs = {}
        self.bind_joints = []
        self.controls = []
        self.context = None
        self.group = None
        self.controls_group = None
        self.systems_group = None

    def __repr__(self):
        return "%s(%r)" % (type(self).__name__, self.full_name)

    # ------------------------------------------------------------------
    # Naming helpers
    # ------------------------------------------------------------------
    @property
    def full_name(self):
        return "%s_%s" % (self.side, self.name)

    @property
    def is_right(self):
        return self.side == naming.SIDE_RIGHT

    def compose(self, label, node_type):
        """``self.compose("Upper", "joint")`` -> ``L_armUpper_JNT``."""
        return naming.compose(self.name + (label[0].upper() + label[1:] if label else ""), self.side, node_type)

    # ------------------------------------------------------------------
    # Guides
    # ------------------------------------------------------------------
    @classmethod
    def guide_definitions(cls, settings=None):
        """Guide definitions - override for setting dependent guides."""
        return list(cls.GUIDES)

    @classmethod
    def default_positions(cls, side, settings=None):
        result = {}
        for label, position, _parent in cls.guide_definitions(settings):
            result[label] = mathlib.reflect(position, "x") if side == naming.SIDE_RIGHT else tuple(position)
        return result

    def create_guide(self):
        positions = self.default_positions(self.side, self.settings)
        positions.update(self.positions)
        return guides.create_component_guide(self.TYPE, self.name, self.side,
                                             self.guide_definitions(self.settings), positions, self.settings,
                                             self.parent_output, self.size)

    @classmethod
    def from_guide(cls, root):
        info = guides.get_info(root)
        return cls(info["name"], info["side"], info["settings"], info["positions"], info["parent"], info["size"])

    def position(self, label):
        if label in self.positions:
            return tuple(self.positions[label])
        return self.default_positions(self.side, self.settings)[label]

    # ------------------------------------------------------------------
    # Orientation helpers (behaviour mirrored on the right side)
    # ------------------------------------------------------------------
    def orient_chain(self, joints, up_mode="plane", world_up=(0.0, 1.0, 0.0), end_mode="parent"):
        """Orient joints aiming down the chain.

        Right side chains aim along ``-x`` and use a mirrored world up vector
        so that left and right are behaviour mirrored (identical rotation
        values produce mirrored motion).
        """
        aim_axis = "-x" if self.is_right else "x"
        if self.is_right and up_mode == "world":
            world_up = mathlib.negate(mathlib.reflect(world_up, "x"))
        oriented = orient_tools.orient_joints(joints, aim_axis=aim_axis, up_axis="y", up_mode=up_mode,
                                              world_up=world_up, end_mode=end_mode)
        return [naming.short_name(j) for j in oriented]

    def create_joint(self, label, position, parent=None, radius=None):
        radius = radius if radius is not None else self.size * 0.5
        joint = joint_tools.create_joint(self.compose(label, "joint"), position=position, parent=parent,
                                         radius=radius)
        return joint

    def create_chain(self, labels, positions, parent=None, up_mode="plane", world_up=(0.0, 1.0, 0.0)):
        joints = []
        current = parent
        for label, position in zip(labels, positions):
            joint = self.create_joint(label, position, current)
            joints.append(joint)
            current = joint
        if len(joints) > 1:
            joints = self.orient_chain(joints, up_mode=up_mode, world_up=world_up)
        return joints

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def parent_nodes(self):
        """``(rig_node, joint)`` this component attaches to."""
        return self.context.resolve(self.parent_output, self)

    def setup_groups(self):
        structure = self.context.structure
        self.group = cmds.createNode("transform", name=naming.unique_name(self.compose("", "group")),
                                     parent=structure.local_ctl, skipSelect=True)
        attributes.set_string(self.group, COMPONENT_ATTR, self.TYPE)
        self.controls_group = cmds.createNode("transform",
                                              name=naming.unique_name(self.compose("Controls", "group")),
                                              parent=self.group, skipSelect=True)
        self.systems_group = cmds.createNode("transform",
                                             name=naming.unique_name(self.compose("Systems", "group")),
                                             parent=structure.systems, skipSelect=True)
        rig_parent, _joint = self.parent_nodes()
        if rig_parent:
            cmds.parentConstraint(rig_parent, self.controls_group, maintainOffset=True)
            cmds.scaleConstraint(rig_parent, self.controls_group, maintainOffset=True)

    def build(self, context):
        """Run every build step. Called by :mod:`jeffy.autorig.builder`."""
        self.context = context
        self.setup_groups()
        _rig_parent, joint_parent = self.parent_nodes()
        self.build_skeleton(joint_parent or context.structure.skeleton)
        self.build_rig()
        for ctl in self.controls:
            attributes.set_string(ctl.node if hasattr(ctl, "node") else ctl, COMPONENT_ATTR, self.full_name)

    def build_skeleton(self, parent):
        """Create bind joints under ``parent`` (fill ``self.bind_joints``)."""
        raise NotImplementedError

    def build_rig(self):
        """Create controls and systems, fill ``self.outputs``."""
        raise NotImplementedError

    def post_build(self, context):
        """Called once every component is built (spaces between components)."""

    # ------------------------------------------------------------------
    def add_output(self, name, rig_node, joint=None):
        self.outputs[name] = (rig_node, joint)

    def register_controls(self, controls):
        for ctl in controls:
            if ctl is not None and ctl not in self.controls:
                self.controls.append(ctl)

    def setting(self, key):
        return self.settings.get(key, self.SETTINGS.get(key))

    def control_size(self, factor=1.0):
        return self.size * factor
