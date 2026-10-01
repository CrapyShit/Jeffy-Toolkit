"""Jaw component: jaw joint with a control around the chin."""

from maya import cmds

from jeffy.autorig import components
from jeffy.autorig.components.base import Component
from jeffy.controls.control import Control
from jeffy.core import mathlib


@components.register
class JawComponent(Component):
    TYPE = "jaw"
    DESCRIPTION = "Jaw joint driven by a control (pivot at the jaw hinge)."
    DEFAULT_NAME = "jaw"
    GUIDES = [
        ("jaw", (0.0, 163.0, 4.0), None),
        ("chin", (0.0, 155.0, 12.0), "jaw"),
    ]
    SETTINGS = {}

    def build_skeleton(self, parent):
        joints = self.create_chain(["", "end"], [self.position("jaw"), self.position("chin")], parent=parent,
                                   up_mode="world", world_up=(0.0, 1.0, 0.0))
        self.jaw, self.jaw_end = joints
        self.bind_joints = [self.jaw]

    def build_rig(self):
        length = mathlib.distance(self.position("jaw"), self.position("chin"))
        ctl = Control.create(self.name, side=self.side, shape="u_shape", size=length * 0.45, axis="y",
                             parent=self.controls_group, match=self.jaw, shape_offset=(length, 0.0, 0.0),
                             lock=("s", "v"))
        cmds.parentConstraint(ctl.node, self.jaw, maintainOffset=True)
        self.register_controls([ctl])
        self.add_output("jaw", ctl.node, self.jaw)
