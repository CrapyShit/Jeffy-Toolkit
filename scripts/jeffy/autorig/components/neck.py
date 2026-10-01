"""Neck + head component with head orientation spaces."""

from maya import cmds

from jeffy.autorig import components
from jeffy.autorig.components.base import Component
from jeffy.controls.control import Control
from jeffy.core import mathlib
from jeffy.rig import fk, space_switch


@components.register
class NeckComponent(Component):
    TYPE = "neck"
    DESCRIPTION = "FK neck and head control (head can follow neck, chest or world)."
    DEFAULT_NAME = "neck"
    GUIDES = [
        ("neck", (0.0, 148.0, -2.0), None),
        ("head", (0.0, 160.0, 1.0), "neck"),
        ("head_end", (0.0, 180.0, 1.0), "head"),
    ]
    SETTINGS = {"neck_joints": 2, "head_spaces": True}

    def build_skeleton(self, parent):
        count = max(1, int(self.setting("neck_joints")))
        neck, head, head_end = (self.position(label) for label in ("neck", "head", "head_end"))
        positions = [mathlib.lerp_vector(neck, head, i / float(count)) for i in range(count)]
        labels = ["%02d" % (i + 1) for i in range(count)] + ["head", "headEnd"]
        joints = self.create_chain(labels, positions + [head, head_end], parent=parent, up_mode="world",
                                   world_up=(0.0, 0.0, 1.0))
        self.neck_joints = joints[:count]
        self.head_joint = joints[count]
        self.head_end = joints[count + 1]
        self.bind_joints = self.neck_joints + [self.head_joint]

    def build_rig(self):
        neck, head, head_end = (self.position(label) for label in ("neck", "head", "head_end"))
        neck_length = mathlib.distance(neck, head)
        head_length = mathlib.distance(head, head_end)
        result = fk.build_fk_chain(self.neck_joints, name=self.name, side=self.side, shape="circle",
                                   size=max(neck_length * 0.6, head_length * 0.35), axis="x",
                                   parent=self.controls_group)
        neck_controls = result["controls"]
        head_ctl = Control.create("head", side=self.side, shape="circle", size=head_length * 0.6, axis="x",
                                  parent=neck_controls[-1].node, match=self.head_joint, offsets=("zero", "space"),
                                  shape_offset=(head_length * 0.5, 0.0, 0.0), color_value="yellow")
        head_ctl.set_parent_tag(neck_controls[-1].node)
        cmds.parentConstraint(head_ctl.node, self.head_joint, maintainOffset=True)
        cmds.scaleConstraint(head_ctl.node, self.head_joint, maintainOffset=True)
        self.neck_controls = neck_controls
        self.head_ctl = head_ctl
        self.register_controls(neck_controls + [head_ctl])
        self.add_output("head", head_ctl.node, self.head_joint)
        self.add_output("neck", neck_controls[0].node, self.neck_joints[0])

    def post_build(self, context):
        if not self.setting("head_spaces"):
            return
        rig_parent, _joint = self.parent_nodes()
        spaces = [("neck", self.neck_controls[-1].node), ("chest", rig_parent),
                  ("world", context.structure.global_ctl)]
        space_switch.create(self.head_ctl.node, [(label, node) for label, node in spaces if node],
                            attr="follow", mode="orient")
