"""Fleshy Lids: eyelids that follow the eye (a layer on an Aim setup).

Give the eye joint and the upper / lower lid joints (one per lid, or a row
along each lid). Every lid joint turns around the eye's centre:

* by the eye's own rotation, scaled by ``eyeFollow`` (up / down) and
  ``sideFollow`` (left / right) on the lid's control,
* by the lid control itself (rotate it to open / close the lid).
"""

from maya import cmds

from jeffy.core import attributes, mathlib, matrix, naming, nodes, transform
from jeffy.setups.core import scene
from jeffy.setups.core import tag as tag_module
from jeffy.setups.core.base import Setup
from jeffy.setups.core.schema import JOINTS, NODE, SIZE_OPTION, Option, SetupError, Slot
from jeffy.setups.tools import common


@scene.register
class FleshyLids(Setup):
    TYPE = "lids"
    LABEL = "Fleshy Lids"
    CATEGORY = "layer"
    ORDER = 85
    DESCRIPTION = ("Eyelids that follow the eye (a layer on an Aim setup): one or several joints per lid turn "
                   "around the eye by 'eyeFollow' / 'sideFollow', plus a control per lid to open and close it.")
    SLOTS = (
        Slot("base", "Aim setup", kind=NODE, tip="Any control of the eyes' Aim setup"),
        Slot("eye", "Eye", tip="The eye joint (one of the Aim setup's joints)"),
        Slot("upper", "Upper lid", kind=JOINTS, tip="Upper lid joint(s)"),
        Slot("lower", "Lower lid", kind=JOINTS, optional=True, tip="Lower lid joint(s)"),
    )
    OPTIONS = (
        Option("upper_follow", "Upper follow", 0.6, minimum=0.0, maximum=1.0, tip="Default eyeFollow of the upper lid"),
        Option("lower_follow", "Lower follow", 0.3, minimum=0.0, maximum=1.0, tip="Default eyeFollow of the lower lid"),
        Option("side_follow", "Side follow", 0.2, minimum=0.0, maximum=1.0, tip="Default sideFollow of both lids"),
        SIZE_OPTION,
    )
    BASE_TYPES = ("aim",)

    @classmethod
    def resolve_name_side(cls, slots, options, name=None, side=None):
        eye = slots.get("eye")
        parsed = naming.parse(eye) if eye else {"name": "eye", "side": None}
        name = naming.legalize(str(name or ((parsed["name"] or "eye") + "Lids")).strip()).strip("_")
        if not side or side == "auto":
            side = parsed["side"] or naming.SIDE_CENTER
        return name, side

    @classmethod
    def validate(cls, slots, options):
        base = cls.find_base(slots)
        if slots["eye"] not in base.slot_nodes("joints"):
            raise SetupError("%s is not one of %s's joints" % (slots["eye"], base.describe()))
        for joint in (slots.get("upper") or []) + (slots.get("lower") or []):
            if joint == slots["eye"]:
                raise SetupError("The eye cannot be a lid joint")

    @classmethod
    def driven_joints(cls, slots):
        return list(slots.get("upper") or []) + list(slots.get("lower") or [])

    @classmethod
    def rig_lookup_node(cls, slots):
        return slots.get("base")

    def build_setup(self):
        options = self.options
        base = self.base
        eye = self.slot_node("eye")
        index = base.slot_nodes("joints").index(eye)
        rest_frame = tag_module.get_nodes(base.tag, "rest_frames")[index] + ".matrixSum"
        eye_output = scene.output_driving(eye)
        eye_rest = common.world_matrix(eye)
        size = max(common.segment_length(eye), 0.5) * 2.0 * options["size"]

        # the eye's rotation since rest, in its own axes
        inverse = nodes.inverse_matrix(rest_frame, name=self._n("EyeRestInv", "UTL"))
        relative = nodes.mult_matrix([eye_output + ".worldMatrix[0]", inverse], name=self._n("EyeDelta", "MM"))
        delta = nodes.decompose_matrix(relative, name=self._n("EyeDelta", "DM"))
        axes = [mathlib.normalize(axis) for axis in mathlib.axes(eye_rest)[:3]]
        pitch = max(range(3), key=lambda i: abs(axes[i][0]))  # axis closest to the world side (X)
        yaw = max((i for i in range(3) if i != pitch), key=lambda i: abs(axes[i][1]))  # closest to world up

        for key, follow_default in (("upper", options["upper_follow"]), ("lower", options["lower_follow"])):
            joints = self.slot_nodes(key)
            if not joints:
                continue
            label = self.name + key[0].upper() + key[1:]
            ctl = self.control(key, label, shape="half_circle", size=size, axis="z", world_matrix=eye_rest,
                               lock=("t", "s", "v"), secondary=True)
            eye_control = base.controls.get("fk_" + common.label(eye) + (naming.parse(eye)["side"] or base.side))
            if eye_control:
                ctl.set_parent_tag(eye_control)
            follow_attr = attributes.add_attr(ctl.node, "eyeFollow", "float", default=follow_default, minimum=0.0,
                                              maximum=1.0)
            side_attr = attributes.add_attr(ctl.node, "sideFollow", "float", default=options["side_follow"],
                                            minimum=0.0, maximum=1.0)
            # the control's ZRO follows the eye's rest frame (the head)
            local = cmds.createNode("multMatrix", name=naming.unique_name(ctl.zero + "_follow_MM"), skipSelect=True)
            cmds.connectAttr(rest_frame, local + ".matrixIn[0]")
            cmds.connectAttr(matrix.parent_inverse_plug(ctl.zero), local + ".matrixIn[1]")
            transform.reset(ctl.zero)
            cmds.connectAttr(local + ".matrixSum", ctl.zero + ".offsetParentMatrix", force=True)
            # eye rotation scaled per axis
            compose = cmds.createNode("composeMatrix", name=naming.unique_name(self._n(key + "Follow", "CM")),
                                      skipSelect=True)
            for axis_index, axis in enumerate("XYZ"):
                weight = {pitch: follow_attr, yaw: side_attr}.get(axis_index)
                if weight is None:
                    continue
                scaled = nodes.multiply("%s.outputRotate%s" % (delta, axis), weight,
                                        name=self._n(key + "Follow" + axis, "MDL"))
                cmds.connectAttr(scaled, "%s.inputRotate%s" % (compose, axis))
            for joint in joints:
                rest = common.world_matrix(joint)
                pose = cmds.createNode("multMatrix", name=naming.unique_name(naming.compose(
                    common.label(joint) + "Pose", self.side, "MM")), skipSelect=True)
                matrix.set_matrix_attr(pose + ".matrixIn[0]", mathlib.mult(rest, mathlib.inverse(eye_rest)))
                cmds.connectAttr(compose + ".outputMatrix", pose + ".matrixIn[1]")
                cmds.connectAttr(ctl.node + ".worldMatrix[0]", pose + ".matrixIn[2]")
                self.add_output(common.label(joint), pose + ".matrixSum", joint=joint, label=common.label(joint))

    def _n(self, label, suffix):
        return naming.compose(self.name + label, self.side, suffix)
