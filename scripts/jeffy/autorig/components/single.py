"""Single control component (props, weapons, accessories, extra bones)."""

from maya import cmds

from jeffy.autorig import components
from jeffy.autorig.components.base import Component
from jeffy.controls.control import Control


@components.register
class SingleComponent(Component):
    TYPE = "control"
    DESCRIPTION = "One control, optionally driving one joint."
    DEFAULT_NAME = "prop"
    GUIDES = [("control", (0.0, 0.0, 0.0), None)]
    SETTINGS = {"shape": "cube", "control_size": 5.0, "create_joint": True}

    def build_skeleton(self, parent):
        self.joint = None
        if self.setting("create_joint"):
            self.joint = self.create_joint("", self.position("control"), parent=parent)
            self.bind_joints = [self.joint]

    def build_rig(self):
        ctl = Control.create(self.name, side=self.side, shape=str(self.setting("shape")),
                             size=float(self.setting("control_size")), parent=self.controls_group,
                             position=self.position("control"), offsets=("zero", "space"))
        if self.joint:
            cmds.parentConstraint(ctl.node, self.joint, maintainOffset=True)
            cmds.scaleConstraint(ctl.node, self.joint, maintainOffset=True)
        self.register_controls([ctl])
        self.add_output("control", ctl.node, self.joint)
