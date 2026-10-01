"""Root component - the root joint driven by the rig's local control."""

from maya import cmds

from jeffy.autorig import components
from jeffy.autorig.components.base import Component


@components.register
class RootComponent(Component):
    TYPE = "root"
    DESCRIPTION = "Root joint following the global/local controls."
    DEFAULT_NAME = "root"
    GUIDES = [("root", (0.0, 0.0, 0.0), None)]
    SETTINGS = {"create_joint": True}

    def build_skeleton(self, parent):
        if not self.setting("create_joint"):
            return
        joint = self.create_joint("", self.position("root"), parent=parent, radius=self.size)
        self.bind_joints = [joint]

    def build_rig(self):
        local = self.context.structure.local_ctl
        joint = self.bind_joints[0] if self.bind_joints else None
        if joint:
            cmds.parentConstraint(local, joint, maintainOffset=True)
            cmds.scaleConstraint(local, joint, maintainOffset=True)
        self.add_output("root", local, joint)
        self.add_output("global", self.context.structure.global_ctl, joint)
