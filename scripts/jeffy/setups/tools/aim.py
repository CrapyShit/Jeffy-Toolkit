"""Aim: eyes (2 or more) and other look-at parts.

::

    L_eyesTarget_CTL          master target (space: head / world / root)
      L_eyeTarget_CTL         one target per eye
    L_eyeFK_CTL               per eye, aims at its target; rotate it on top (FK override)

Each eye's FK control follows the head at rest and aims at its target by its
``aim`` attribute (0: plain FK, 1: aim). The eye joint follows its FK control.
"""

from maya import cmds

from jeffy.core import attributes, mathlib, matrix, naming, transform
from jeffy.setups.core import guides as guides_module
from jeffy.setups.core import scene
from jeffy.setups.core import tag as tag_module
from jeffy.setups.core.base import Setup
from jeffy.setups.core.schema import JOINTS, SIZE_OPTION, Option, SetupError, Slot
from jeffy.setups.tools import common

DIRECTIONS = {"+z": (0.0, 0.0, 1.0), "-z": (0.0, 0.0, -1.0), "+x": (1.0, 0.0, 0.0), "-x": (-1.0, 0.0, 0.0)}


@scene.register
class Aim(Setup):
    TYPE = "aim"
    LABEL = "Aim"
    CATEGORY = "build"
    ORDER = 40
    DESCRIPTION = ("Eyes (or any look-at joints): a master target with one target per joint, an FK control per "
                   "joint on top of the aim ('aim' 0..1). Preview to place the target.")
    SLOTS = (
        Slot("joints", "Eyes", kind=JOINTS, tip="The eye joints (2 or more), or any joints that look at a target"),
    )
    OPTIONS = (
        Option("direction", "Look direction", "+z", choices=tuple(DIRECTIONS),
               tip="World direction the character looks at (the targets go there)"),
        Option("distance", "Target distance", 10.0, minimum=0.01, maximum=1000.0,
               tip="Default target distance, in eye spacings (or move the target guide)"),
        SIZE_OPTION,
    )
    GUIDES = ("target",)
    MIRRORABLE = False

    @classmethod
    def resolve_name_side(cls, slots, options, name=None, side=None):
        joints = slots.get("joints") or []
        sides = set(naming.parse(joint)["side"] for joint in joints)
        if not side or side == "auto":
            side = sides.pop() if len(sides) == 1 and None not in sides else naming.SIDE_CENTER
        if not name:
            label = common.label(joints[0]) if joints else "aim"
            name = label + "s" if len(joints) > 1 else label
        return naming.legalize(str(name).strip()).strip("_"), side

    @classmethod
    def validate(cls, slots, options):
        if not slots.get("joints"):
            raise SetupError("Load the eye joints")

    @classmethod
    def driven_joints(cls, slots):
        return list(slots["joints"])

    @classmethod
    def default_guides(cls, slots, options, side):
        points = [common.position(joint) for joint in slots["joints"]]
        center = mathlib.centroid(points)
        spacing = max(mathlib.distance(points[0], points[-1]) if len(points) > 1 else 0.0, _eye_size(slots))
        return {"target": mathlib.add(center, mathlib.scale(DIRECTIONS[options["direction"]],
                                                             spacing * options["distance"]))}

    @classmethod
    def guide_size(cls, slots, options):
        return _eye_size(slots) * 2.0

    def attach_joint(self):
        joints = self.slot_nodes("joints")
        return (cmds.listRelatives(joints[0], parent=True, fullPath=True) or [None])[0] if joints else None

    # ------------------------------------------------------------------
    def build_setup(self):
        options = self.options
        joints = self.slot_nodes("joints")
        points = [common.position(joint) for joint in joints]
        center = mathlib.centroid(points)
        target_point = guides_module.position(self.guides.get("target"))
        size = _eye_size({"joints": joints}) * options["size"]
        offset = mathlib.sub(target_point, center)

        master = self.control("target", self.name + "Target", shape="rectangle" if len(joints) > 1 else "circle",
                              size=max(size * 2.5, mathlib.distance(points[0], points[-1]) * 0.75), axis="z",
                              position=target_point, lock=("s", "v"))
        rest_follow = self.group("Head", parent=self.systems_group)  # follows the parent (head) at rest
        self.add_anchor(rest_follow)
        self.add_anchor(master.zero, master.node, kind="parent", spaces=("parent", "world", "root"), default="parent")

        rest_nodes = []
        for joint, point in zip(joints, points):
            label = common.label(joint)
            side = naming.parse(joint)["side"] or self.side
            target = self.control("target_" + label + side, label + "Target", shape="circle", size=size, axis="z",
                                  parent=master.node, position=mathlib.add(point, offset), lock=("r", "s", "v"),
                                  secondary=True, side=side)
            target.set_parent_tag(master.node)
            rest = common.world_matrix(joint)
            fk = self.control("fk_" + label + side, label + "FK", shape="circle", size=size * 1.3,
                              axis=common.bone_axis(joint).lstrip("-"), world_matrix=rest, lock=("t", "s", "v"),
                              side=side)
            aim_value = attributes.add_attr(fk.node, "aim", "float", default=1.0, minimum=0.0, maximum=1.0)
            # rest frame following the head
            follow = common.offset_plug(naming.compose(label + "Rest", self.side, "MM"),
                                        rest_follow + ".worldMatrix[0]", rest,
                                        matrix.get_world_matrix(rest_follow))
            # aim frame: the joint's axis toward its target, up from the head
            aim_axis, up_axis = _axes(rest, mathlib.sub(mathlib.add(point, offset), point))
            aimed = cmds.createNode("aimMatrix", name=naming.unique_name(naming.compose(label + "Aim", self.side,
                                                                                        "aim_matrix")),
                                    skipSelect=True)
            cmds.connectAttr(follow, aimed + ".inputMatrix")
            cmds.connectAttr(target.node + ".worldMatrix[0]", aimed + ".primaryTargetMatrix")
            cmds.setAttr(aimed + ".primaryInputAxis", *aim_axis)
            cmds.setAttr(aimed + ".primaryMode", 1)
            cmds.setAttr(aimed + ".secondaryInputAxis", *up_axis)
            cmds.setAttr(aimed + ".secondaryMode", 2)
            cmds.connectAttr(follow, aimed + ".secondaryTargetMatrix")
            cmds.setAttr(aimed + ".secondaryTargetVector", *up_axis)
            # the aim axis is the joint axis closest to the target: offset it so the rest pose is exact
            aimed_plug = common.offset_plug(naming.compose(label + "AimRest", self.side, "MM"),
                                            aimed + ".outputMatrix", rest, common.plug_matrix(aimed + ".outputMatrix"))
            mixed = common.blend_matrices(naming.compose(label + "Aim", self.side, "BM"), follow, aimed_plug,
                                          aim_value, translate=0.0)
            local = cmds.createNode("multMatrix", name=naming.unique_name(fk.zero + "_follow_MM"), skipSelect=True)
            cmds.connectAttr(mixed, local + ".matrixIn[0]")
            cmds.connectAttr(matrix.parent_inverse_plug(fk.zero), local + ".matrixIn[1]")
            transform.reset(fk.zero)
            cmds.connectAttr(local + ".matrixSum", fk.zero + ".offsetParentMatrix", force=True)
            self.add_output(label + side, fk.node + ".worldMatrix[0]", joint=joint, label=label + side)
            rest_nodes.append(follow.split(".")[0])
        tag_module.set_nodes(self.tag, "rest_frames", rest_nodes)


def _eye_size(slots):
    joints = slots["joints"]
    child = common.child_joint(joints[0])
    if child:
        return max(common.length(joints[0], child), 1e-3)
    points = [common.position(joint) for joint in joints]
    spacing = mathlib.distance(points[0], points[-1]) if len(points) > 1 else 1.0
    return max(spacing * 0.3, 1e-3)


def _axes(rest, direction):
    """Local axis of ``rest`` pointing along ``direction`` and a perpendicular local axis (vectors)."""
    axes = [mathlib.normalize(axis) for axis in mathlib.axes(rest)[:3]]
    direction = mathlib.normalize(direction)
    index = max(range(3), key=lambda i: abs(mathlib.dot(axes[i], direction)))
    sign = 1.0 if mathlib.dot(axes[index], direction) >= 0 else -1.0
    aim = [0.0, 0.0, 0.0]
    aim[index] = sign
    up = [0.0, 0.0, 0.0]
    up[(index + 1) % 3] = 1.0
    return aim, up
