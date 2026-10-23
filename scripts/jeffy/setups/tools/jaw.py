"""Jaw / Hinge: a chin control you translate.

The chin control lives in the head's space. Moving it:

* down (-Y) opens the jaw (rotation around the jaw's side axis),
* sideways (X) swings it left / right,
* forward / back (Z) slides it forward / back,

each one clamped (``openMax``, ``closeMax``, ``sideMax``, ``forwardMax``,
``backMax`` on the control), plus an ``open`` attribute (degrees) added on
top. Works for any hinge (prop lids, doors) with a chin-like control.
"""

from maya import cmds

from jeffy.core import attributes, mathlib, matrix, naming, nodes
from jeffy.setups.core import scene
from jeffy.setups.core.base import Setup
from jeffy.setups.core.schema import SIZE_OPTION, Option, SetupError, Slot
from jeffy.setups.tools import common


@scene.register
class Jaw(Setup):
    TYPE = "jaw"
    LABEL = "Jaw / Hinge"
    CATEGORY = "build"
    ORDER = 50
    DESCRIPTION = ("A chin control you translate: down opens the jaw, sideways swings it, forward / back slides "
                   "it, all clamped, plus an 'open' attribute. Also for prop hinges.")
    SLOTS = (
        Slot("jaw", "Jaw", tip="The jaw (hinge) joint"),
        Slot("chin", "Chin", optional=True, tip="Chin / jaw end joint, where the control goes (default: the jaw's "
                                                "child)"),
    )
    OPTIONS = (
        Option("open_max", "Open max", 35.0, minimum=0.0, maximum=180.0, tip="Degrees"),
        Option("close_max", "Close max", 5.0, minimum=0.0, maximum=90.0, tip="Degrees past closed (overbite)"),
        Option("side_max", "Side max", 12.0, minimum=0.0, maximum=90.0, tip="Degrees"),
        Option("forward_max", "Forward max", 0.15, minimum=0.0, maximum=2.0, tip="In jaw lengths"),
        Option("back_max", "Back max", 0.05, minimum=0.0, maximum=2.0, tip="In jaw lengths"),
        SIZE_OPTION,
    )
    MIRRORABLE = False

    @classmethod
    def validate(cls, slots, options):
        chin = slots.get("chin") or common.child_joint(slots["jaw"])
        if not chin:
            raise SetupError("%s has no child joint: load the chin joint" % slots["jaw"])
        if slots.get("chin") and not scene.is_ancestor(slots["jaw"], slots["chin"]):
            raise SetupError("Chin (%s) must be below Jaw (%s)" % (slots["chin"], slots["jaw"]))

    @classmethod
    def driven_joints(cls, slots):
        return [slots["jaw"]]

    def build_setup(self):
        options = self.options
        jaw = self.slot_node("jaw")
        chin_joint = self.slot_node("chin") or common.child_joint(jaw)
        pivot, chin = common.position(jaw), common.position(chin_joint)
        length = max(mathlib.distance(pivot, chin), 1e-3)
        forward = mathlib.sub(chin, pivot)
        forward = (forward[0], 0.0, forward[2])
        forward = mathlib.normalize(forward) if mathlib.length(forward) > 1e-6 else (0.0, 0.0, 1.0)
        up = (0.0, 1.0, 0.0)
        side = mathlib.normalize(mathlib.cross(up, forward))
        frame = mathlib.from_axes(side, up, forward, pivot)  # X side (open axis), Y up, Z forward

        head = self.group("Head")
        self.add_anchor(head)
        ctl = self.control("chin", self.name + "Chin", shape="cube", size=length * 0.12 * options["size"], axis="y",
                           position=chin, lock=("r", "s", "v"))
        self.add_anchor(ctl.zero)  # follows the head, translate drives the jaw
        node = ctl.node
        attributes.add_separator(node, "jaw")
        open_attr = attributes.add_attr(node, "open", "float", default=0.0)
        limits = {}
        for attr, value in (("openMax", options["open_max"]), ("closeMax", options["close_max"]),
                            ("sideMax", options["side_max"]), ("forwardMax", options["forward_max"] * length),
                            ("backMax", options["back_max"] * length)):
            limits[attr] = attributes.add_attr(node, attr, "float", default=value, minimum=0.0, keyable=False,
                                               channel_box=True)
            cmds.setAttr(limits[attr], value)
        degrees_per_unit = options["open_max"] / (length * 0.5) if options["open_max"] else 30.0 / length

        name = self._n
        opening = nodes.add(nodes.multiply(node + ".translateY", -degrees_per_unit, name=name("OpenMove", "MDL")),
                            open_attr, name=name("Open", "ADL"))
        open_angle = nodes.clamp(opening, nodes.negate(limits["closeMax"], name=name("Close", "MDL")),
                                 limits["openMax"], name=name("Open", "CLP"))
        side_angle = nodes.clamp(nodes.multiply(node + ".translateX", degrees_per_unit, name=name("Side", "MDL")),
                                 nodes.negate(limits["sideMax"], name=name("SideMin", "MDL")), limits["sideMax"],
                                 name=name("Side", "CLP"))
        slide = nodes.clamp(node + ".translateZ", nodes.negate(limits["backMax"], name=name("Back", "MDL")),
                            limits["forwardMax"], name=name("Slide", "CLP"))
        extra = cmds.createNode("composeMatrix", name=naming.unique_name(name("Motion", "CM")), skipSelect=True)
        cmds.connectAttr(open_angle, extra + ".inputRotateX")
        cmds.connectAttr(side_angle, extra + ".inputRotateY")
        cmds.connectAttr(slide, extra + ".inputTranslateZ")
        cmds.setAttr(extra + ".inputRotateOrder", 1)  # yzx: open, then swing

        rest = common.world_matrix(jaw)
        pose = cmds.createNode("multMatrix", name=naming.unique_name(name("Pose", "MM")), skipSelect=True)
        matrix.set_matrix_attr(pose + ".matrixIn[0]", mathlib.mult(rest, mathlib.inverse(frame)))
        cmds.connectAttr(extra + ".outputMatrix", pose + ".matrixIn[1]")
        matrix.set_matrix_attr(pose + ".matrixIn[2]", mathlib.mult(frame, mathlib.inverse(
            matrix.get_world_matrix(head))))
        cmds.connectAttr(head + ".worldMatrix[0]", pose + ".matrixIn[3]")
        self.add_output("jaw", pose + ".matrixSum", joint=jaw, label=common.label(jaw))

    def _n(self, label, suffix):
        return naming.compose(self.name + label, self.side, suffix)
