"""Leg component: IK/FK leg with reverse foot, stretch, soft IK and twist."""

from jeffy.autorig import components
from jeffy.autorig.components.base import Component
from jeffy.core import mathlib
from jeffy.rig import foot, ikfk, space_switch, twist


@components.register
class LegComponent(Component):
    TYPE = "leg"
    DESCRIPTION = "IK/FK leg with reverse foot (roll, bank, twists), stretch, soft IK, knee pin and twist."
    DEFAULT_NAME = "leg"
    DEFAULT_SIDE = "L"
    MIRRORABLE = True
    GUIDES = [
        ("hip", (9.0, 95.0, 0.0), None),
        ("knee", (9.0, 52.0, 3.0), "hip"),
        ("ankle", (9.0, 9.0, -3.0), "knee"),
        ("ball", (9.0, 2.0, 9.0), "ankle"),
        ("toe", (9.0, 2.0, 17.0), "ball"),
        ("heel", (9.0, 0.0, -7.0), "ankle"),
        ("foot_in", (5.0, 0.0, 6.0), "ankle"),
        ("foot_out", (13.0, 0.0, 6.0), "ankle"),
    ]
    SETTINGS = {
        "twist_joints": 2,
        "stretch": True,
        "soft_ik": True,
        "default_ik": True,
        "pole_distance": 1.0,
    }

    def build_skeleton(self, parent):
        hip, knee, ankle, ball, toe = (self.position(label) for label in ("hip", "knee", "ankle", "ball", "toe"))
        upper = self.create_joint("upper", hip, parent=parent)
        lower = self.create_joint("lower", knee, parent=upper)
        foot_joint = self.create_joint("foot", ankle, parent=lower)
        ball_joint = self.create_joint("ball", ball, parent=foot_joint)
        toe_joint = self.create_joint("toe", toe, parent=ball_joint)
        upper, lower = self.orient_chain([upper, lower], up_mode="plane")
        foot_joint, ball_joint, toe_joint = self.orient_chain([foot_joint, ball_joint, toe_joint], up_mode="world",
                                                              world_up=(0.0, 1.0, 0.0))
        self.joints = [upper, lower, foot_joint, ball_joint, toe_joint]
        self.bind_joints = [upper, lower, foot_joint, ball_joint]

    def build_rig(self):
        upper, lower, foot_joint, ball_joint, toe_joint = self.joints
        hip, knee, ankle = (self.position(label) for label in ("hip", "knee", "ankle"))
        size = (mathlib.distance(hip, knee) + mathlib.distance(knee, ankle)) * 0.1
        _rig_parent, parent_joint = self.parent_nodes()

        limb = ikfk.build_ikfk_limb(
            self.joints,
            name=self.name,
            side=self.side,
            parent=parent_joint or self.controls_group,
            control_parent=self.controls_group,
            systems_parent=self.systems_group,
            size=size,
            stretch=bool(self.setting("stretch")),
            soft=bool(self.setting("soft_ik")),
            pole_distance=float(self.setting("pole_distance")),
            default_mode=1.0 if self.setting("default_ik") else 0.0,
            settings_offset=(0.0, size * 1.5, 0.0),
            orient_end=False,
            ik_count=3,
            fk_skip_last=True,
        )
        self.limb = limb
        ik_joints = limb["ik_joints"]
        ik_ctl = limb["ik"]["ik_control"]
        foot.build_reverse_foot(ik_ctl.node, limb["ik"]["end"], ik_joints[2], ik_joints[3], ik_joints[4],
                                self.position("heel"), self.position("foot_in"), self.position("foot_out"),
                                name=self.name + "Foot", side=self.side)

        count = int(self.setting("twist_joints"))
        if count > 0:
            upper_twist = twist.create_twist_joints(upper, lower, count=count, side=self.side,
                                                    name=self.name + "UpperTwist", mode="reverse",
                                                    reference=parent_joint) if parent_joint else []
            lower_twist = twist.create_twist_joints(lower, foot_joint, count=count, side=self.side,
                                                    name=self.name + "LowerTwist", mode="forward")
            self.bind_joints.extend(upper_twist + lower_twist)

        self.register_controls(limb["fk"]["controls"] + [ik_ctl, limb["ik"]["pole_control"], limb["settings"]])
        self.add_output("foot", foot_joint, foot_joint)
        self.add_output("ball", ball_joint, ball_joint)
        self.add_output("toe", toe_joint, toe_joint)

    def post_build(self, context):
        rig_parent, _joint = self.parent_nodes()
        structure = context.structure
        ik_ctl = self.limb["ik"]["ik_control"].node
        pole = self.limb["ik"]["pole_control"]
        spaces = [("world", structure.global_ctl), ("root", structure.local_ctl),
                  ("cog", context.output_node("C_spine.cog")), ("hips", rig_parent)]
        space_switch.create(ik_ctl, [(k, v) for k, v in spaces if v])
        if pole:
            space_switch.create(pole.node, [(k, v) for k, v in (("world", structure.global_ctl), ("foot", ik_ctl),
                                                                  ("hips", rig_parent)) if v])
