"""Arm component: clavicle + IK/FK arm with stretch, soft IK, pin and twist."""

from maya import cmds

from jeffy.autorig import components
from jeffy.autorig.components.base import Component
from jeffy.controls.control import Control
from jeffy.core import mathlib
from jeffy.rig import ikfk, space_switch, twist


@components.register
class ArmComponent(Component):
    TYPE = "arm"
    DESCRIPTION = "Clavicle and IK/FK arm (stretch, soft IK, elbow pin, twist joints, spaces)."
    DEFAULT_NAME = "arm"
    DEFAULT_SIDE = "L"
    MIRRORABLE = True
    GUIDES = [
        ("clavicle", (2.0, 145.0, 1.0), None),
        ("shoulder", (17.0, 145.0, -2.0), "clavicle"),
        ("elbow", (43.0, 145.0, -5.0), "shoulder"),
        ("wrist", (67.0, 145.0, -2.0), "elbow"),
        ("hand_end", (77.0, 145.0, -2.0), "wrist"),
    ]
    SETTINGS = {
        "twist_joints": 2,
        "stretch": True,
        "soft_ik": True,
        "default_ik": False,
        "pole_distance": 1.0,
        "ik_world_orient": True,
    }

    def build_skeleton(self, parent):
        clav_pos, shoulder, elbow, wrist, hand_end = (
            self.position(label) for label in ("clavicle", "shoulder", "elbow", "wrist", "hand_end"))
        self.clavicle = self.create_joint("clavicle", clav_pos, parent=parent)
        chain = self.create_chain(["upper", "lower", "hand", "handEnd"], [shoulder, elbow, wrist, hand_end],
                                  parent=self.clavicle, up_mode="plane")
        self.clavicle = self.orient_chain([self.clavicle], up_mode="world", world_up=(0.0, 1.0, 0.0))[0]
        self.upper, self.lower, self.hand, self.hand_end = chain
        self.bind_joints = [self.clavicle, self.upper, self.lower, self.hand]

    def build_rig(self):
        shoulder, elbow, wrist = (self.position(label) for label in ("shoulder", "elbow", "wrist"))
        arm_length = mathlib.distance(shoulder, elbow) + mathlib.distance(elbow, wrist)
        size = arm_length * 0.12
        clav_length = mathlib.distance(self.position("clavicle"), shoulder)

        clavicle = Control.create("clavicle", side=self.side, shape="pin_circle", size=clav_length * 0.5,
                                  axis="y", parent=self.controls_group, match=self.clavicle)
        cmds.parentConstraint(clavicle.node, self.clavicle, maintainOffset=True)

        offset = (0.0, size * 1.5, 0.0)
        limb = ikfk.build_ikfk_limb(
            [self.upper, self.lower, self.hand],
            name=self.name,
            side=self.side,
            parent=self.clavicle,
            control_parent=self.controls_group,
            systems_parent=self.systems_group,
            size=size,
            stretch=bool(self.setting("stretch")),
            soft=bool(self.setting("soft_ik")),
            pole_distance=float(self.setting("pole_distance")),
            orient_ik_control="world" if self.setting("ik_world_orient") else "joint",
            default_mode=1.0 if self.setting("default_ik") else 0.0,
            settings_offset=offset,
        )
        self.limb = limb
        self.clavicle_ctl = clavicle

        count = int(self.setting("twist_joints"))
        if count > 0:
            upper = twist.create_twist_joints(self.upper, self.lower, count=count, side=self.side,
                                              name=self.name + "UpperTwist", mode="reverse",
                                              reference=self.clavicle)
            lower = twist.create_twist_joints(self.lower, self.hand, count=count, side=self.side,
                                              name=self.name + "LowerTwist", mode="forward")
            self.bind_joints.extend(upper + lower)

        ik_ctl = limb["ik"]["ik_control"]
        pole = limb["ik"]["pole_control"]
        self.register_controls([clavicle] + limb["fk"]["controls"] + [ik_ctl, pole, limb["settings"]])
        self.add_output("hand", self.hand, self.hand)
        self.add_output("clavicle", clavicle.node, self.clavicle)
        self.add_output("shoulder", self.upper, self.upper)

    def post_build(self, context):
        rig_parent, _joint = self.parent_nodes()
        structure = context.structure
        ik_ctl = self.limb["ik"]["ik_control"].node
        pole = self.limb["ik"]["pole_control"]
        spaces = [
            ("world", structure.global_ctl),
            ("root", structure.local_ctl),
            ("cog", context.output_node("C_spine.cog")),
            ("chest", rig_parent),
            ("head", context.output_node("C_neck.head")),
        ]
        space_switch.create(ik_ctl, [(k, v) for k, v in spaces if v])
        if pole:
            space_switch.create(pole.node, [(k, v) for k, v in (("world", structure.global_ctl), ("hand", ik_ctl),
                                                                  ("chest", rig_parent)) if v])
        fk_root = self.limb["fk"]["controls"][0]
        space_switch.create(fk_root.node, [(k, v) for k, v in (("shoulder", self.clavicle_ctl.node),
                                                                 ("chest", rig_parent),
                                                                 ("world", structure.global_ctl)) if v],
                            attr="follow", mode="orient")
