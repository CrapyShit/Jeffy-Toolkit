"""Eyes component: two eye joints with a shared look-at control."""

from jeffy.autorig import components
from jeffy.autorig.components.base import Component
from jeffy.core import mathlib, naming
from jeffy.joints import tools as joint_tools
from jeffy.rig import aim, space_switch


@components.register
class EyesComponent(Component):
    TYPE = "eyes"
    DESCRIPTION = "Eye joints aimed at a master look-at control with per eye offsets."
    DEFAULT_NAME = "eyes"
    GUIDES = [
        ("left", (3.2, 166.0, 9.0), None),
        ("right", (-3.2, 166.0, 9.0), None),
        ("aim", (0.0, 166.0, 40.0), None),
    ]
    SETTINGS = {"world_space": True}

    def build_skeleton(self, parent):
        self.eye_joints = []
        for label, side in (("left", naming.SIDE_LEFT), ("right", naming.SIDE_RIGHT)):
            joint = joint_tools.create_joint(naming.compose("eye", side, "joint"), position=self.position(label),
                                             parent=parent, radius=self.size * 0.5)
            self.eye_joints.append(joint)
        self.bind_joints = list(self.eye_joints)

    def build_rig(self):
        left, right, target = (self.position(label) for label in ("left", "right", "aim"))
        center = mathlib.midpoint(left, right)
        forward = mathlib.normalize(mathlib.sub(target, center))
        rig_parent, _joint = self.parent_nodes()
        result = aim.build_eye_rig(self.eye_joints, name="eyes", side=self.side,
                                   distance=mathlib.distance(center, target), forward=forward,
                                   control_parent=self.controls_group, up_object=rig_parent,
                                   size=mathlib.distance(left, right) * 0.5)
        self.master = result["master"]
        self.register_controls([self.master] + result["controls"])
        self.add_output("aim", self.master.node, None)

    def post_build(self, context):
        if not self.setting("world_space"):
            return
        rig_parent, _joint = self.parent_nodes()
        spaces = [("head", rig_parent), ("world", context.structure.global_ctl)]
        space_switch.create(self.master.node, [(k, v) for k, v in spaces if v])
