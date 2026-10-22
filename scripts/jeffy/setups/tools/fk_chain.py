"""FK Chain: one control per joint from Start to End.

Use it for clavicles, simple chains, props, and as the base of fingers and
toes. Options: spaces on the top control (orient isolation), a master control
that bends the whole chain, FK stretch (``length``), a control on the last
joint or not.

::

    L_clavicleControls_GRP
      L_clavicleRoot_GRP                     follows the parent setup / spaces
        L_clavicleMaster_ZRO > OFF > CTL     (option) bends every control
        L_clavicleFK_ZRO > OFF > CTL
          L_nextFK_ZRO > OFF > CTL ...
"""

from jeffy.core import attributes
from jeffy.setups.core import scene
from jeffy.setups.core.base import Setup
from jeffy.setups.core.schema import GAME_SAFE_OPTION, SIZE_OPTION, Option, Slot
from jeffy.setups.tools import common

SHAPES = ("circle", "square", "octagon", "cube", "sphere", "diamond")
SPACE_ROLES = ("parent", "cog", "chest", "hips", "head", "root", "world")


@scene.register
class FkChain(Setup):
    TYPE = "fk_chain"
    LABEL = "FK Chain"
    CATEGORY = "build"
    ORDER = 10
    DESCRIPTION = ("One control per joint from Start to End (leave End empty for a single joint). For clavicles, "
                   "simple chains, props, fingers and toes.")
    SLOTS = (
        Slot("start", "Start", tip="First joint of the chain"),
        Slot("end", "End", optional=True, tip="Last joint of the chain (empty: only the Start joint)"),
    )
    OPTIONS = (
        Option("spaces", "Top control spaces", "orient", choices=("orient", "parent", "none"),
               tip="orient: the chain stays attached to its parent but its rotation can follow another space "
                   "(parent, COG, chest, root, world...).\nparent: the whole chain can follow another space.\n"
                   "none: it always follows its parent."),
        Option("master", "Master control", False, tip="An extra control at the start whose rotation bends every "
                                                     "control of the chain (curl)"),
        Option("stretch", "Stretch (length)", False,
               tip="A 'length' attribute on each control moves the next one along the bone"),
        Option("end_control", "Control on the last joint", True,
               tip="Off: the last joint (a tip) just follows the control before it"),
        Option("translate", "Translatable", False, tip="Leave the translate channels of the controls unlocked"),
        Option("shape", "Shape", "circle", choices=SHAPES),
        SIZE_OPTION,
        GAME_SAFE_OPTION,
    )
    SCALE_STRETCH = True

    @classmethod
    def validate(cls, slots, options):
        common.chain(slots["start"], slots.get("end"))

    @classmethod
    def driven_joints(cls, slots):
        return common.chain(slots["start"], slots.get("end"))

    # ------------------------------------------------------------------
    def build_setup(self):
        joints = common.chain(self.slot_node("start"), self.slot_node("end"))
        options = self.options
        lengths = [common.length(a, b) for a, b in zip(joints, joints[1:])]
        if not lengths:
            lengths = [common.segment_length(joints[0])]
        unit = (sum(lengths) / len(lengths)) if any(lengths) else 1.0
        size = unit * 0.3 * options["size"]

        root = self.group("Root", parent=self.controls_group, match=joints[0])
        locks = ["s", "v"] + ([] if options["translate"] else ["t"])
        count = len(joints) if (options["end_control"] or len(joints) == 1) else len(joints) - 1

        master = None
        if options["master"] and count > 1:
            master = self.control("master", self.name + "Master", shape="square", size=size * 1.6,
                                  axis=_shape_axis(common.bone_axis(joints[0])), parent=root, match=joints[0],
                                  lock=("t", "s", "v"), secondary=True)

        fk = []
        parent = root
        for index, joint in enumerate(joints[:count]):
            child = joints[index + 1] if index + 1 < len(joints) else None
            ctl = self.control("fk%d" % index, common.label(joint) + "FK", shape=options["shape"], size=size,
                               axis=_shape_axis(common.bone_axis(joint, child)), parent=parent, match=joint,
                               lock=locks)
            if fk:
                ctl.set_parent_tag(fk[-1].node)
            fk.append(ctl)
            parent = ctl.node

        if options["stretch"] or master:
            for index, ctl in enumerate(fk):
                length_plug = None
                if options["stretch"] and index > 0:
                    previous = fk[index - 1].node
                    length_plug = attributes.add_attr(previous, "length", "float", default=1.0, minimum=0.001)
                common.compose_zero(ctl.zero, length_plug=length_plug,
                                    pre_rotate_plug=(master.node + ".rotate") if master else None,
                                    rotate_order_plug=(master.node + ".rotateOrder") if master else None)

        # outputs (the tip follows the last control when it has none)
        for index, joint in enumerate(joints):
            if index < len(fk):
                plug = fk[index].node + ".worldMatrix[0]"
            else:
                tip = self.group(common.label(joint) + "Tip", parent=fk[-1].node, match=joint, visible=False)
                if options["stretch"]:
                    length_plug = attributes.add_attr(fk[-1].node, "length", "float", default=1.0, minimum=0.001)
                    common.compose_zero(tip, length_plug=length_plug)
                plug = tip + ".worldMatrix[0]"
            child_key = "j%d" % (index + 1) if index + 1 < len(joints) else None
            self.add_output("j%d" % index, plug, joint=joint, stretch_child=child_key, label=common.label(joint))

        if options["spaces"] == "none":
            self.add_anchor(root)
        else:
            self.add_anchor(root, fk[0].node, kind=options["spaces"], spaces=SPACE_ROLES, default="parent")


def _shape_axis(bone_axis):
    """Control shapes face the bone axis (``-x`` faces the same way as ``x``)."""
    return bone_axis.lstrip("-")
