"""Twist: twist joints along the segments of an IK/FK Limb or an FK Chain.

The tool creates the twist joints (under the segment's first joint, so they
export with the skeleton) and drives them:

* ``counter`` (upper arm / thigh): the twist joints near the shoulder do not
  roll with it; the roll grows toward the elbow,
* ``forward`` (forearm / shin): the roll of the end joint (wrist) spreads from
  the elbow to the wrist.

Skin to the twist joints. A segment that has a Ribbon is refused (the ribbon
twists already).
"""

from maya import cmds

from jeffy.core import mathlib, matrix, naming
from jeffy.joints import tools as joint_tools
from jeffy.setups.core import attach, scene
from jeffy.setups.core.base import Setup
from jeffy.setups.core.schema import NODE, Option, SetupError, Slot
from jeffy.setups.tools import common

MODES = ("counter", "forward", "off")


@scene.register
class Twist(Setup):
    TYPE = "twist"
    LABEL = "Twist"
    CATEGORY = "layer"
    ORDER = 70
    DESCRIPTION = ("Twist joints along an IK/FK Limb or an FK Chain (created under each segment's first joint). "
                   "First segment: counter twist (shoulder / hip roll fades in toward the elbow). Other segments: "
                   "the end joint's roll spreads along the bone (forearm). Skin to the twist joints.")
    SLOTS = (Slot("base", "Setup", kind=NODE, tip="Any control of an IK/FK Limb or an FK Chain"),)
    OPTIONS = (
        Option("count", "Joints per segment", 3, minimum=1, maximum=20),
        Option("first", "First segment", "counter", choices=MODES,
               tip="counter: the joint's own roll fades in along the bone (upper arm, thigh).\n"
                   "forward: the next joint's roll spreads along the bone.\noff: no twist joints."),
        Option("others", "Other segments", "forward", choices=MODES,
               tip="forward: the end joint's roll spreads along the bone (forearm, shin)."),
    )
    BASE_TYPES = ("ikfk_limb", "fk_chain")

    @classmethod
    def resolve_name_side(cls, slots, options, name=None, side=None):
        base = cls.find_base(slots)
        name = naming.legalize(str(name or (base.name + "Twist")).strip()).strip("_")
        return name, (side if side and side != "auto" else base.side)

    @classmethod
    def validate(cls, slots, options):
        base = cls.find_base(slots)
        if len(common.chain_outputs(base)) < 2:
            raise SetupError("%s has a single joint: nothing to twist" % base.describe())
        for layer in base.layers():
            if layer.TYPE in ("ribbon", "twist"):
                raise SetupError("%s already has %s. Delete it first (a Ribbon twists already)."
                                 % (base.describe(), layer.describe()))

    @classmethod
    def rig_lookup_node(cls, slots):
        return slots.get("base")

    def build_setup(self):
        base = self.base
        pairs = common.chain_outputs(base)
        parent = attach.parent_target(base)
        count = self.option("count")
        for segment in range(len(pairs) - 1):
            mode = self.option("first") if segment == 0 else self.option("others")
            if mode == "off":
                continue
            (joint_a, out_a), (joint_b, out_b) = pairs[segment], pairs[segment + 1]
            label = common.label(joint_a)
            own_roll = common.bone_frame(self._name(label, "RollFrame", "AM"), out_a, out_b)
            if mode == "counter":
                frames = (common.bone_frame(self._name(label, "NoRollFrame", "AM"), out_a, out_b, up_node=parent),
                          own_roll)
            else:
                frames = (own_roll, common.bone_frame(self._name(label, "EndRollFrame", "AM"), out_a, out_b,
                                                      up_node=out_b))
            rotation_rest = matrix.get_world_matrix(joint_a)
            start, end = common.position(joint_a), common.position(joint_b)
            radius = cmds.getAttr(joint_a + ".radius") * 0.6 if cmds.nodeType(joint_a) == "joint" else 0.5
            for index in range(1, count + 1):
                weight = (index - 0.5) / count
                part = "%s%02d" % (label + "Twist", index)
                rotation = common.blend_matrices(self._name(part, "Rot", "BM"), frames[0], frames[1], weight,
                                                 translate=0.0)
                position = common.blend_matrices(self._name(part, "Pos", "BM"), out_a + ".worldMatrix[0]",
                                                 out_b + ".worldMatrix[0]", weight, rotate=0.0)
                final = common.blend_matrices(self._name(part, "", "BM"), rotation, position, 1.0, rotate=0.0)
                joint = joint_tools.create_joint(naming.compose(part, self.side, "joint"), parent=joint_a,
                                                 position=mathlib.lerp_vector(start, end, weight), radius=radius)
                matrix.set_joint_orient_from_matrix(joint, rotation_rest)
                rest = matrix.get_world_matrix(joint)
                driven = common.offset_plug(self._name(part, "Offset", "MM"), final, rest, common.plug_matrix(final))
                self.add_output("s%d_%d" % (segment, index), driven, joint=joint, label=part)

    def _name(self, label, part, suffix):
        return naming.compose(label + part, self.side, suffix)
