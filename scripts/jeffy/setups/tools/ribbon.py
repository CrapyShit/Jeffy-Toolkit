"""Ribbon: bendy segments with their own deform joints, on an IK/FK Limb or an FK Chain.

For every segment (shoulder > elbow, elbow > wrist...) a NURBS ribbon follows
the setup's outputs; ``uvPin`` nodes ride on it and drive new deform joints
(5 per segment by default). On top of the limb you get:

* a **bend** control in the middle of each segment,
* a **joint bend** control at each inner joint (elbow / knee) moving both
  ribbons around it,
* twist spread along each segment (the first one from the parent: the
  shoulder roll fades in toward the elbow),
* ``volume`` (film): the deform joints get thinner when the segment stretches.

``bendyVis`` and ``volume`` are added to the limb's settings control. Skin
your mesh to the ribbon joints instead of the limb joints.
"""

import math

from maya import cmds

from jeffy.core import attributes, mathlib, matrix, naming, nodes, transform
from jeffy.joints import tools as joint_tools
from jeffy.setups.core import attach, scene
from jeffy.setups.core import tag as tag_module
from jeffy.setups.core.base import Setup
from jeffy.setups.core.schema import GAME_SAFE_OPTION, NODE, SIZE_OPTION, Option, SetupError, Slot
from jeffy.setups.tools import common

KNOTS_U = [0.0, 0.0, 0.0, 1.0, 2.0, 2.0, 2.0]
HOLDER_ATTRS = ("bendyVis", "volume")


@scene.register
class Ribbon(Setup):
    TYPE = "ribbon"
    LABEL = "Ribbon"
    CATEGORY = "layer"
    ORDER = 60
    DESCRIPTION = ("Bendy limbs: a ribbon per segment of an IK/FK Limb or FK Chain drives its own deform joints, "
                   "with bend controls, twist spread along the bones and volume. Skin to the ribbon joints.")
    SLOTS = (Slot("base", "Setup", kind=NODE, tip="Any control of an IK/FK Limb or an FK Chain"),)
    OPTIONS = (
        Option("joints", "Joints per segment", 5, minimum=2, maximum=30),
        Option("bend_controls", "Bend controls", True, tip="A bend control in the middle of each segment and at "
                                                           "each inner joint (elbow / knee)"),
        Option("twist", "First segment twist", "from parent", choices=("from parent", "follow joint"),
               tip="from parent: the shoulder / hip roll fades in along the segment (counter twist).\n"
                   "follow joint: the whole segment rolls with its joint."),
        Option("volume", "Volume", True, tip="'volume' attribute: the joints thin out when the segment stretches "
                                             "(not in game safe mode)"),
        SIZE_OPTION,
        GAME_SAFE_OPTION,
    )
    BASE_TYPES = ("ikfk_limb", "fk_chain")

    @classmethod
    def resolve_name_side(cls, slots, options, name=None, side=None):
        base = cls.find_base(slots)
        name = naming.legalize(str(name or (base.name + "Ribbon")).strip()).strip("_")
        return name, (side if side and side != "auto" else base.side)

    @classmethod
    def validate(cls, slots, options):
        base = cls.find_base(slots)
        if len(common.chain_outputs(base)) < 2:
            raise SetupError("%s has a single joint: a ribbon needs two joints or more" % base.describe())
        for layer in base.layers():
            if layer.TYPE in ("ribbon", "twist"):
                raise SetupError("%s already has %s. Delete it first (a Ribbon twists already)."
                                 % (base.describe(), layer.describe()))

    @classmethod
    def rig_lookup_node(cls, slots):
        return slots.get("base")

    # ------------------------------------------------------------------
    def build_setup(self):
        options = self.options
        base = self.base
        pairs = common.chain_outputs(base)
        joints = [joint for joint, _output in pairs]
        outputs = [output for _joint, output in pairs]
        points = [common.position(joint) for joint in joints]
        total = sum(mathlib.distance(a, b) for a, b in zip(points, points[1:]))
        size = total * options["size"]
        game_safe = options["game_safe"]

        holder = base.controls.get("settings") or base.controls.get("fk0") or list(base.controls.values())[0]
        tag_module.set_node(self.tag, "holder", holder)
        attributes.add_separator(holder, "ribbon")
        bendy_vis = attributes.add_attr(holder, "bendyVis", "bool", default=True, keyable=False, channel_box=True)
        cmds.setAttr(bendy_vis, True)
        volume = None
        if options["volume"] and not game_safe:
            volume = attributes.add_attr(holder, "volume", "float", default=1.0, minimum=0.0, maximum=1.0)

        # inner joint controls (elbow / knee)
        drivers = {}
        for index in range(1, len(joints) - 1):
            between = common.blend_matrices(self._n(common.label(joints[index]) + "BendSpace", "BM"),
                                             outputs[index] + ".worldMatrix[0]",
                                             outputs[index - 1] + ".worldMatrix[0]", 0.5, translate=0.0)
            if options["bend_controls"]:
                ctl = self._follow_control("joint%d" % index, common.label(joints[index]) + "Bend", between,
                                           size * 0.07, bendy_vis)
                drivers[index] = ctl + ".worldMatrix[0]"
            else:
                drivers[index] = between

        reference = _width_reference(points, joints[0])
        parent = attach.parent_target(base)
        joints_group = None
        if not game_safe:
            rig = self.rig
            joints_group = self.group("Joints", parent=rig.rig_group("skeleton") if rig is not None else None)
        count = options["joints"]

        for segment in range(len(joints) - 1):
            label = common.label(joints[segment])
            if segment == 0:
                if options["twist"] == "from parent":
                    start = common.bone_frame(self._n(label + "RibbonStart", "AM"), outputs[0], outputs[1],
                                              up_node=parent)
                else:
                    start = outputs[0] + ".worldMatrix[0]"
            else:
                start = drivers[segment]
            end = drivers.get(segment + 1, outputs[segment + 1] + ".worldMatrix[0]")
            if segment + 1 == len(joints) - 1:
                end = outputs[segment + 1] + ".worldMatrix[0]"
            middle = common.blend_matrices(self._n(label + "RibbonMid", "BM"), start, end, 0.5)
            if options["bend_controls"]:
                middle = self._follow_control("bend%d" % segment, label + "Bend", middle, size * 0.09,
                                              bendy_vis) + ".worldMatrix[0]"
            columns = [start, common.blend_matrices(self._n(label + "RibbonQ1", "BM"), start, middle, 0.5), middle,
                       common.blend_matrices(self._n(label + "RibbonQ3", "BM"), middle, end, 0.5), end]
            shape = self._surface(label, columns, reference, mathlib.distance(points[segment], points[segment + 1]))
            self._joints(segment, label, joints[segment], start, end, shape, count, joints_group, volume)

    def _n(self, label, suffix):
        return naming.compose(label, self.side, suffix)

    def _follow_control(self, key, label, plug, size, visibility):
        """Control whose ZRO follows a matrix plug (created at the plug's rest pose)."""
        ctl = self.control(key, label, shape="circle", size=size, axis="x",
                           world_matrix=mathlib.orthonormalize(common.plug_matrix(plug)), lock=("s", "v"),
                           secondary=True)
        local = cmds.createNode("multMatrix", name=naming.unique_name(ctl.zero + "_follow_MM"), skipSelect=True)
        cmds.connectAttr(plug, local + ".matrixIn[0]")
        cmds.connectAttr(matrix.parent_inverse_plug(ctl.zero), local + ".matrixIn[1]")
        transform.reset(ctl.zero)
        cmds.connectAttr(local + ".matrixSum", ctl.zero + ".offsetParentMatrix", force=True)
        cmds.connectAttr(visibility, ctl.zero + ".visibility")
        return ctl.node

    def _surface(self, label, columns, reference, length):
        """Degree 3 x 1 surface whose CVs ride on the column matrices (world space)."""
        rests = [common.plug_matrix(plug) for plug in columns]
        direction = mathlib.normalize(mathlib.sub(mathlib.get_translation(rests[-1]),
                                                  mathlib.get_translation(rests[0])))
        width = mathlib.normalize(mathlib.sub(reference, mathlib.scale(direction, mathlib.dot(reference,
                                                                                              direction))))
        half = mathlib.scale(width, length * 0.12)
        points = []
        for rest in rests:
            center = mathlib.get_translation(rest)
            points.extend([mathlib.add(center, half), mathlib.sub(center, half)])
        shape = cmds.surface(degreeU=3, degreeV=1, knotU=KNOTS_U, knotV=[0.0, 1.0], point=points)
        surface = cmds.listRelatives(shape, parent=True)[0]
        surface = cmds.rename(surface, naming.unique_name(naming.compose(label + "Ribbon", self.side, "surface")))
        surface = cmds.parent(surface, self.systems_group)[0]
        shape = cmds.listRelatives(surface, shapes=True, fullPath=True)[0]
        cmds.setAttr(surface + ".inheritsTransform", 0)
        for column, (plug, rest) in enumerate(zip(columns, rests)):
            for row in (0, 1):
                local = mathlib.transform_point(points[column * 2 + row], mathlib.inverse(rest))
                follow = cmds.createNode("pointMatrixMult", name=naming.unique_name(
                    "%s_cv%d%d_PMM" % (naming.strip_namespace(surface), column, row)), skipSelect=True)
                cmds.setAttr(follow + ".inPoint", *local)
                cmds.connectAttr(plug, follow + ".inMatrix")
                cmds.connectAttr(follow + ".output", "%s.controlPoints[%d]" % (shape, column * 2 + row))
        return shape

    def _joints(self, segment, label, bind_joint, start, end, shape, count, joints_group, volume):
        pin = cmds.createNode("uvPin", name=naming.unique_name(naming.compose(label + "Ribbon", self.side, "uv_pin")),
                              skipSelect=True)
        cmds.connectAttr(shape + ".worldSpace[0]", pin + ".deformedGeometry")
        child = common.child_joint(bind_joint)
        bone_index = common.bone_axis_index(bind_joint, child)[0] if child else 0
        squash = None
        if volume:
            distance = cmds.createNode("distanceBetween", name=naming.unique_name(
                naming.compose(label + "RibbonLength", self.side, "distance")), skipSelect=True)
            cmds.connectAttr(start, distance + ".inMatrix1")
            cmds.connectAttr(end, distance + ".inMatrix2")
            scale = nodes.decompose_matrix(start, name=naming.compose(label + "RibbonScale", self.side, "DM"))
            current = nodes.divide(distance + ".distance", scale + ".outputScaleX")
            rest_length = max(cmds.getAttr(distance + ".distance") / (cmds.getAttr(scale + ".outputScaleX") or 1.0),
                              1e-6)
            ratio = nodes.divide(rest_length, nodes.clamp(current, 1e-6, 1e12))
            squash = nodes.power(ratio, 0.5)  # sqrt(rest / current)
        rotation = mathlib.orthonormalize(matrix.get_world_matrix(bind_joint))
        radius = cmds.getAttr(bind_joint + ".radius") * 0.5
        for index in range(count):
            u = float(index) / count
            cmds.setAttr("%s.coordinate[%d].coordinateU" % (pin, index), u)
            cmds.setAttr("%s.coordinate[%d].coordinateV" % (pin, index), 0.5)
            plug = "%s.outputMatrix[%d]" % (pin, index)
            rest = common.plug_matrix(plug)
            part = "%s%02d" % (self.name, segment * count + index + 1)
            parent = bind_joint if joints_group is None else joints_group
            joint = joint_tools.create_joint(naming.compose(part, self.side, "joint"), parent=parent,
                                             position=mathlib.get_translation(rest), radius=radius)
            joint_world = list(rotation)
            joint_world[12:15] = mathlib.get_translation(rest)
            matrix.set_joint_orient_from_matrix(joint, joint_world)
            driven = common.offset_plug(naming.compose(part + "Offset", self.side, "MM"), plug,
                                        matrix.get_world_matrix(joint), rest)
            if squash is not None:
                profile = math.sin(math.pi * u)
                if profile > 1e-4:
                    amount = nodes.multiply(nodes.multiply(nodes.subtract(squash, 1.0), volume), profile)
                    factor = nodes.add(amount, 1.0)
                    compose = cmds.createNode("composeMatrix", name=naming.unique_name(
                        naming.compose(part + "Volume", self.side, "CM")), skipSelect=True)
                    for axis_index, axis in enumerate("XYZ"):
                        target = "%s.inputScale%s" % (compose, axis)
                        if axis_index == bone_index:
                            cmds.setAttr(target, 1.0)
                        else:
                            cmds.connectAttr(factor, target)
                    scaled = cmds.createNode("multMatrix", name=naming.unique_name(
                        naming.compose(part + "Volume", self.side, "MM")), skipSelect=True)
                    cmds.connectAttr(compose + ".outputMatrix", scaled + ".matrixIn[0]")
                    cmds.connectAttr(driven, scaled + ".matrixIn[1]")
                    driven = scaled + ".matrixSum"
            self.add_output("s%d_%d" % (segment, index), driven, joint=joint, label=part)

    def before_delete(self):
        holder = tag_module.get_node(self.tag, "holder")
        if holder and cmds.objExists(holder):
            for attr in HOLDER_ATTRS + ("sep_ribbon",):
                if cmds.attributeQuery(attr, node=holder, exists=True):
                    cmds.setAttr("%s.%s" % (holder, attr), lock=False)
                    cmds.deleteAttr(holder, attribute=attr)


def _width_reference(points, first_joint):
    """Vector across the ribbons: the chain's bend plane normal (or a joint axis when straight)."""
    if len(points) >= 3:
        normal = mathlib.cross(mathlib.sub(points[1], points[0]), mathlib.sub(points[2], points[1]))
        if mathlib.length(normal) > 1e-6:
            return mathlib.normalize(normal)
    world = matrix.get_world_matrix(first_joint)
    direction = mathlib.normalize(mathlib.sub(points[1], points[0]))
    axes = [mathlib.normalize(axis) for axis in mathlib.axes(world)[:3]]
    return min(axes, key=lambda axis: abs(mathlib.dot(axis, direction)))
