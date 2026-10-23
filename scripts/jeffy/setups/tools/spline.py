"""Spline IK/FK: spines, necks, tails and tentacles.

The joints ride on a hidden NURBS ribbon (``uvPin``): stable twist, no
flipping. The ribbon's shape comes from IK controls; each control holds its
own tangents, so rotating a control bends the chain around it.

Modes:

* **spine**: COG (moves everything), hips (rotate the pelvis on their own,
  optional Pelvis slot), IK controls (hips / mid / chest by default) with an
  FK layer on top (rotating an FK control carries the IK controls above it).
* **neck**: FK layer, IK base and mid controls, and a **head** control (the
  neck's top) whose orientation follows the neck, the chest, the COG or the
  world (``space``). Optional Head slot: the head joint follows it.
* **chain** (tail, tentacle): FK controls on every joint and IK controls,
  blended by ``ikFk``. **Wave** (FK): ``waveAmplitude``, ``waveLength``,
  ``waveSpeed``, ``waveOffset``, ``waveFalloff``; it animates with time.

All modes: ``stretch`` (0 keeps the length), ``volume`` (film: the joints get
thinner when the chain stretches).
"""

import math

from maya import cmds

from jeffy.core import attributes, mathlib, matrix, naming, nodes
from jeffy.setups.core import controls, scene
from jeffy.setups.core import tag as tag_module
from jeffy.setups.core.base import Setup
from jeffy.setups.core.schema import GAME_SAFE_OPTION, SIZE_OPTION, Option, SetupError, Slot
from jeffy.setups.tools import common

MODES = ("spine", "neck", "chain")
SWITCH = "ikFk"


@scene.register
class SplineIkFk(Setup):
    TYPE = "spline"
    LABEL = "Spline IK/FK"
    CATEGORY = "build"
    ORDER = 30
    DESCRIPTION = ("Spines (COG, independent hips, IK with an FK layer), necks (head with orient spaces) and "
                   "chains (tails, tentacles: IK/FK switch and an automatic wave). The joints ride on a hidden "
                   "ribbon: stable twist, stretch and volume.")
    SLOTS = (
        Slot("start", "Start", tip="First joint of the chain (first spine joint, first neck joint, tail root)"),
        Slot("end", "End", tip="Last joint of the chain (chest, last neck joint, tail end)"),
        Slot("pelvis", "Pelvis", optional=True, tip="Spine mode: the pelvis joint, driven by the hips control"),
        Slot("head", "Head", optional=True, tip="Neck mode: the head joint, driven by the head control"),
    )
    OPTIONS = (
        Option("mode", "Mode", "spine", choices=MODES),
        Option("ik_controls", "IK controls", 3, minimum=2, maximum=20,
               tip="Controls shaping the ribbon (spine: hips, mid, chest)"),
        Option("fk_controls", "FK controls", 3, minimum=1, maximum=20,
               tip="Spine / neck: FK controls on top of the IK ones (chain mode: one per joint)"),
        Option("stretch", "Stretch", True, tip="'stretch' attribute (0 keeps the chain's length)"),
        Option("volume", "Volume", True, tip="'volume' attribute: thinner when stretched (not in game safe mode)"),
        Option("wave", "Wave (chain)", True, tip="Chain mode: wave attributes driving the FK controls with time"),
        Option("wave_axis", "Wave axis", "z", choices=("y", "z"), tip="Local axis the FK controls wave around"),
        SIZE_OPTION,
        GAME_SAFE_OPTION,
    )

    @classmethod
    def validate(cls, slots, options):
        chain = common.chain(slots["start"], slots["end"])
        if len(chain) < 3:
            raise SetupError("A spline needs 3 joints or more between Start and End")
        mode = options["mode"]
        if slots.get("pelvis"):
            if mode != "spine":
                raise SetupError("Pelvis is only used in spine mode")
            if slots["pelvis"] in chain:
                raise SetupError("Pelvis must not be one of the spine joints")
        if slots.get("head"):
            if mode != "neck":
                raise SetupError("Head is only used in neck mode")
            if not common.is_child(slots["end"], slots["head"]):
                raise SetupError("Head (%s) must be a child of End (%s)" % (slots["head"], slots["end"]))

    @classmethod
    def driven_joints(cls, slots):
        extra = [slots[key] for key in ("pelvis", "head") if slots.get(key)]
        return common.chain(slots["start"], slots["end"]) + extra

    @classmethod
    def default_name(cls, slots, options):
        return {"spine": "spine", "neck": "neck", "chain": None}[options["mode"]]

    # ------------------------------------------------------------------
    def build_setup(self):
        options = self.options
        mode = options["mode"]
        joints = common.chain(self.slot_node("start"), self.slot_node("end"))
        points = [common.position(joint) for joint in joints]
        lengths = [0.0]
        for a, b in zip(points, points[1:]):
            lengths.append(lengths[-1] + mathlib.distance(a, b))
        total = lengths[-1]
        self.size = total * options["size"]
        self.points, self.lengths, self.total, self.joints = points, lengths, total, joints

        if mode == "spine":
            ik, settings = self._spine()
        elif mode == "neck":
            ik, settings = self._neck()
        else:
            ik, settings = self._chain()
        ik_poses = self._ribbon(ik, settings)

        if mode == "chain":
            switch = attributes.add_attr(settings, SWITCH, "float", default=1.0, minimum=0.0, maximum=1.0)
            fk = self._fk_chain
            for index, joint in enumerate(joints):
                blend = cmds.createNode("blendMatrix", name=naming.unique_name(self._n(common.label(joint) + "IkFk",
                                                                                      "BM")), skipSelect=True)
                cmds.connectAttr(fk[index].node + ".worldMatrix[0]", blend + ".inputMatrix")
                cmds.connectAttr(ik_poses[index], blend + ".target[0].targetMatrix")
                cmds.connectAttr(switch, blend + ".target[0].weight")
                self._output(index, blend + ".outputMatrix")
            fk_vis = nodes.condition(switch, "<", 1.0, 1.0, 0.0, name=self._n("FkVis", "COND"))
            ik_vis = nodes.condition(switch, ">", 0.0, 1.0, 0.0, name=self._n("IkVis", "COND"))
            cmds.connectAttr(fk_vis, self._fk_root + ".visibility")
            for ctl in ik:
                cmds.connectAttr(ik_vis, self.controls_zero(ctl) + ".visibility")
                attributes.add_proxy(switch, ctl)
            for ctl in fk:
                attributes.add_proxy(switch, ctl.node)
            self.follow(self.controls_zero(settings), self.outputs["j%d" % (len(joints) - 1)])
            if options["wave"]:
                self._wave(settings)
        else:
            for index in range(len(joints)):
                self._output(index, ik_poses[index])

    # ------------------------------------------------------------------
    def _n(self, label, suffix):
        return naming.compose(self.name + label, self.side, suffix)

    def controls_zero(self, ctl):
        return controls.zero_of(ctl)

    def _output(self, index, plug):
        joint = self.joints[index]
        child = "j%d" % (index + 1) if index + 1 < len(self.joints) else None
        self.add_output("j%d" % index, plug, joint=joint, stretch_child=child, label=common.label(joint))

    def _point_at(self, fraction):
        """World position at ``fraction`` (0..1) of the chain's length."""
        target = fraction * self.total
        for index in range(len(self.points) - 1):
            if self.lengths[index + 1] >= target - 1e-9:
                span = self.lengths[index + 1] - self.lengths[index]
                t = (target - self.lengths[index]) / span if span else 0.0
                return mathlib.lerp_vector(self.points[index], self.points[index + 1], t)
        return self.points[-1]

    def _world_at(self, fraction):
        return mathlib.compose(translate=self._point_at(fraction))

    def _fk_layer(self, count, parent, last_key=None):
        """World oriented FK controls along the chain (spine / neck). Returns the controls."""
        result = []
        for index in range(count):
            fraction = float(index) / count
            key = last_key if (last_key and index == count - 1) else "fk%d" % index
            ctl = self.control(key, self.name + "FK%d" % (index + 1), shape="circle", size=self.size * 0.22,
                               axis="y", parent=parent, world_matrix=self._world_at(fraction), lock=("s", "v"))
            if result:
                ctl.set_parent_tag(result[-1].node)
            result.append(ctl)
            parent = ctl.node
        return result

    def _ik_layer(self, fractions, fk, keys=None, shapes=None, roles=None):
        """IK controls at ``fractions`` of the chain, each under the FK control below it."""
        result = []
        for index, fraction in enumerate(fractions):
            owner = fk[min(int(fraction * len(fk) + 1e-6), len(fk) - 1)]
            key = (keys or {}).get(index, "ik%d" % index)
            ctl = self.control(key, self.name + key[0].upper() + key[1:], shape=(shapes or {}).get(index, "square"),
                               size=self.size * 0.18, axis="y", parent=owner.node,
                               world_matrix=self._world_at(fraction), lock=("s", "v"),
                               role=(roles or {}).get(index))
            result.append(ctl.node)
        return result

    # ------------------------------------------------------------------
    # Modes
    # ------------------------------------------------------------------
    def _spine(self):
        options = self.options
        pelvis = self.slot_node("pelvis")
        cog = self.control("cog", self.name + "Cog", shape="cog", size=self.size * 0.4, axis="y",
                           world_matrix=self._world_at(0.0), lock=("s", "v"), role="cog")
        hips_point = common.position(pelvis) if pelvis else self.points[0]
        hips = self.control("hips", self.name + "Hips", shape="hip", size=self.size * 0.3, axis="y", parent=cog.node,
                            world_matrix=mathlib.compose(translate=hips_point), lock=("s", "v"), role="hips")
        hips.set_parent_tag(cog.node)
        fk = self._fk_layer(options["fk_controls"], cog.node)
        count = options["ik_controls"]
        last = count - 1
        ik = self._ik_layer([float(i) / last for i in range(count)], fk, keys={0: "hipsIk", last: "chestIk"},
                            shapes={last: "chest"}, roles={last: "chest"})
        if pelvis:
            self.add_output("pelvis", common.offset_plug(self._n("Pelvis", "MM"), hips.node + ".worldMatrix[0]",
                                                         common.world_matrix(pelvis),
                                                         matrix.get_world_matrix(hips.node)),
                            joint=pelvis, label=common.label(pelvis))
        self.add_anchor(cog.zero, cog.node, kind="parent", spaces=("parent", "root", "world"), default="parent")
        return ik, cog.node

    def _neck(self):
        options = self.options
        head_joint = self.slot_node("head")
        root = self.group("Root", parent=self.controls_group, world_matrix=self._world_at(0.0))
        # the last FK control is the head's "neck" space
        fk = self._fk_layer(options["fk_controls"], root, last_key="neck")
        count = options["ik_controls"]
        ik = self._ik_layer([float(i) / (count - 1) for i in range(count - 1)], fk)
        head = self.control("head", self.name + "Head", shape="cube", size=self.size * 0.35, axis="y",
                            world_matrix=mathlib.compose(translate=self.points[-1]), lock=("s", "v"), role="head")
        if head_joint:
            self.add_output("head", common.offset_plug(self._n("Head", "MM"), head.node + ".worldMatrix[0]",
                                                       common.world_matrix(head_joint),
                                                       matrix.get_world_matrix(head.node)),
                            joint=head_joint, label=common.label(head_joint))
        self.add_anchor(root)
        self.add_anchor(head.zero, head.node, kind="orient", spaces=("self:neck", "chest", "cog", "root", "world"),
                        default="neck")
        return ik + [head.node], head.node

    def _chain(self):
        options = self.options
        joints = self.joints
        root = self.group("FkRoot", parent=self.controls_group, match=joints[0])
        self._fk_root = root
        fk = []
        parent = root
        for index, joint in enumerate(joints):
            child = joints[index + 1] if index + 1 < len(joints) else None
            ctl = self.control("fk%d" % index, common.label(joint) + "FK", shape="circle", size=self.size * 0.12,
                               axis=common.bone_axis(joint, child).lstrip("-"), parent=parent, match=joint,
                               lock=("t", "s", "v"))
            if fk:
                ctl.set_parent_tag(fk[-1].node)
            fk.append(ctl)
            parent = ctl.node
        self._fk_chain = fk
        self.add_anchor(root, fk[0].node, kind="orient", spaces=("parent", "root", "world"), default="parent")
        count = options["ik_controls"]
        ik = []
        for index in range(count):
            fraction = float(index) / (count - 1)
            ctl = self.control("ik%d" % index, self.name + "IK%d" % (index + 1), shape="square", size=self.size * 0.1,
                               axis="y", world_matrix=self._world_at(fraction), lock=("s", "v"))
            self.add_anchor(ctl.zero, ctl.node, kind="parent", spaces=("parent", "root", "world"),
                            default="parent")
            ik.append(ctl.node)
        settings = self.control("settings", self.name + "Settings", shape="gear", size=self.size * 0.06, axis="z",
                                position=mathlib.add(self.points[-1], (0.0, self.size * 0.12, 0.0)),
                                lock=("t", "r", "s", "v"), secondary=True)
        return ik, settings.node

    # ------------------------------------------------------------------
    # Ribbon
    # ------------------------------------------------------------------
    def _ribbon(self, ik, holder):
        """Ribbon through the IK controls (with their tangents). Returns one pose plug per joint."""
        options = self.options
        game_safe = options["game_safe"]
        centers = [mathlib.get_translation(matrix.get_world_matrix(ctl)) for ctl in ik]
        rests = [matrix.get_world_matrix(ctl) for ctl in ik]
        columns = []  # (owner index, world point)
        for index, center in enumerate(centers):
            before = centers[index - 1] if index > 0 else None
            after = centers[index + 1] if index + 1 < len(centers) else None
            direction = mathlib.normalize(mathlib.sub(after or center, before or center))
            if index > 0:
                columns.append((index, mathlib.sub(center, mathlib.scale(direction, mathlib.distance(center,
                                                                                                    before) / 3.0))))
            columns.append((index, center))
            if after is not None:
                columns.append((index, mathlib.add(center, mathlib.scale(direction, mathlib.distance(center,
                                                                                                    after) / 3.0))))
        direction = mathlib.normalize(mathlib.sub(self.points[-1], self.points[0]))
        reference = _perpendicular(direction, self.joints[0])
        half = mathlib.scale(reference, self.total * 0.05)
        points = []
        for _owner, center in columns:
            points.extend([mathlib.add(center, half), mathlib.sub(center, half)])
        spans = len(columns) - 3
        knots = [0.0] * 3 + [float(i) for i in range(1, spans)] + [float(spans)] * 3
        shape = cmds.surface(degreeU=3, degreeV=1, knotU=knots, knotV=[0.0, 1.0], point=points)
        surface = cmds.rename(cmds.listRelatives(shape, parent=True)[0],
                              naming.unique_name(self._n("Ribbon", "surface")))
        surface = cmds.parent(surface, self.systems_group)[0]
        shape = cmds.listRelatives(surface, shapes=True, fullPath=True)[0]
        cmds.setAttr(surface + ".inheritsTransform", 0)
        for column, (owner, _center) in enumerate(columns):
            for row in (0, 1):
                local = mathlib.transform_point(points[column * 2 + row], mathlib.inverse(rests[owner]))
                follow = cmds.createNode("pointMatrixMult", name=naming.unique_name(
                    "%s_cv%d%d_PMM" % (naming.strip_namespace(surface), column, row)), skipSelect=True)
                cmds.setAttr(follow + ".inPoint", *local)
                cmds.connectAttr(ik[owner] + ".worldMatrix[0]", follow + ".inMatrix")
                cmds.connectAttr(follow + ".output", "%s.controlPoints[%d]" % (shape, column * 2 + row))

        params = _closest_params(shape, self.points)
        pin = cmds.createNode("uvPin", name=naming.unique_name(self._n("Ribbon", "uv_pin")), skipSelect=True)
        cmds.connectAttr(shape + ".worldSpace[0]", pin + ".deformedGeometry")

        # stretch: rest length / current length along the ribbon's middle
        iso = cmds.createNode("curveFromSurfaceIso", name=naming.unique_name(self._n("RibbonIso", "UTL")),
                              skipSelect=True)
        cmds.setAttr(iso + ".isoparmDirection", 0)  # 0: the curve runs along U (the chain)
        cmds.setAttr(iso + ".isoparmValue", 0.5)
        cmds.connectAttr(shape + ".worldSpace[0]", iso + ".inputSurface")
        info = cmds.createNode("curveInfo", name=naming.unique_name(self._n("RibbonLength", "UTL")), skipSelect=True)
        cmds.connectAttr(iso + ".outputCurve", info + ".inputCurve")
        scale = nodes.decompose_matrix(ik[0] + ".worldMatrix[0]", name=self._n("RibbonScale", "DM"))
        current = nodes.divide(info + ".arcLength", scale + ".outputScaleX", name=self._n("RibbonLength", "MD"))
        rest_length = max(cmds.getAttr(info + ".arcLength") / (cmds.getAttr(scale + ".outputScaleX") or 1.0), 1e-6)
        shrink = nodes.divide(rest_length, nodes.clamp(current, 1e-6, 1e12, name=self._n("RibbonLength", "CLP")),
                              name=self._n("RibbonShrink", "MD"))
        stretch = None
        if options["stretch"]:
            stretch = attributes.add_attr(holder, "stretch", "float", default=1.0, minimum=0.0, maximum=1.0)
        volume = None
        if options["volume"] and not game_safe:
            volume = attributes.add_attr(holder, "volume", "float", default=0.5, minimum=0.0, maximum=1.0)
            root_shrink = nodes.power(shrink, 0.5, name=self._n("RibbonVolume", "MD"))

        # positions: a hidden chain on a spline IK along the ribbon's middle keeps its bone lengths
        # (stretch 0) or stretches them with the curve (stretch 1); each joint takes the ribbon's frame
        # (twist) at the closest point to its hidden joint
        hidden = self._length_chain(iso, scale + ".outputScaleX", current, rest_length, stretch)
        poses = []
        for index, (joint, param) in enumerate(zip(self.joints, params)):
            label = common.label(joint)
            position = nodes.decompose_matrix(hidden[index] + ".worldMatrix[0]", name=self._n(label + "Pos", "DM"))
            closest = cmds.createNode("closestPointOnSurface", name=naming.unique_name(
                self._n(label + "Closest", "UTL")), skipSelect=True)
            cmds.connectAttr(shape + ".worldSpace[0]", closest + ".inputSurface")
            cmds.connectAttr(position + ".outputTranslate", closest + ".inPosition")
            coordinate = nodes.divide(closest + ".result.parameterU", float(spans), name=self._n(label + "U", "MD"))
            cmds.connectAttr(coordinate, "%s.coordinate[%d].coordinateU" % (pin, index))
            cmds.setAttr("%s.coordinate[%d].coordinateV" % (pin, index), 0.5)
            plug = "%s.outputMatrix[%d]" % (pin, index)
            pose = common.offset_plug(self._n(label + "Pose", "MM"), plug, common.world_matrix(joint),
                                      common.plug_matrix(plug))
            if volume:
                profile = math.sin(math.pi * param)
                if profile > 1e-3:
                    pose = _volume(self._n(label + "Volume", "UTL"), pose, root_shrink, volume, profile,
                                   _bone_index(self.joints, index))
            poses.append(pose)
        return poses

    def before_delete(self):
        # the length measure first: it would complain while its curve is being deleted
        for node in tag_module.get_nodes(self.tag, "owned"):
            if cmds.objExists(node) and cmds.nodeType(node) == "curveInfo":
                cmds.delete(node)

    def _length_chain(self, iso, scale, current, rest_length, stretch):
        """Hidden joints on a spline IK along the ribbon's middle curve. Returns them."""
        from jeffy.joints import tools as joint_tools

        curve = cmds.createNode("transform", name=naming.unique_name(self._n("Length", "curve")), skipSelect=True)
        curve = cmds.parent(curve, self.systems_group, relative=True)[0]
        cmds.setAttr(curve + ".inheritsTransform", 0)
        curve_shape = cmds.createNode("nurbsCurve", name=naming.unique_name(curve + "Shape"), parent=curve,
                                      skipSelect=True)
        cmds.connectAttr(iso + ".outputCurve", curve_shape + ".create")
        names = [naming.compose(common.label(joint) + "Length", self.side, "joint") for joint in self.joints]
        chain = joint_tools.create_chain(self.points, names=names, parent=self.systems_group, orient=True,
                                         aim_axis="x", up_axis="y")
        handle, effector = cmds.ikHandle(startJoint=chain[0], endEffector=chain[-1], solver="ikSplineSolver",
                                         curve=curve, createCurve=False, parentCurve=False, rootOnCurve=True,
                                         simplifyCurve=False,
                                         name=naming.unique_name(self._n("Length", "ik_handle")))
        cmds.rename(effector, naming.unique_name(self._n("Length", "effector")))
        handle = cmds.parent(handle, self.systems_group)[0]
        cmds.setAttr(handle + ".visibility", 0)
        # bone lengths: rest * rig scale * lerp(1, current / rest, stretch)
        ratio = nodes.divide(current, rest_length, name=self._n("LengthRatio", "MD"))
        factor = nodes.blend(1.0, ratio, stretch, name=self._n("LengthStretch", "BLD")) if stretch else ratio
        scaled = nodes.multiply(factor, scale, name=self._n("LengthScale", "MDL"))
        for joint in chain[1:]:
            rest = cmds.getAttr(joint + ".translateX")
            cmds.connectAttr(nodes.multiply(scaled, rest, name=self._n(common.label(joint) + "Length", "MDL")),
                             joint + ".translateX", force=True)
        return chain

    # ------------------------------------------------------------------
    def _wave(self, holder):
        """Sine wave on the FK controls (degrees), animated by time."""
        attributes.add_separator(holder, "wave")
        amplitude = attributes.add_attr(holder, "waveAmplitude", "float", default=0.0)
        length = attributes.add_attr(holder, "waveLength", "float", default=1.0, minimum=0.01)
        speed = attributes.add_attr(holder, "waveSpeed", "float", default=10.0)
        offset = attributes.add_attr(holder, "waveOffset", "float", default=0.0)
        falloff = attributes.add_attr(holder, "waveFalloff", "float", default=1.0, minimum=0.0, maximum=1.0)
        moving = nodes.multiply("time1.outTime", speed, name=self._n("WaveTime", "MDL"))
        axis = "yz".index(self.option("wave_axis")) + 1
        count = len(self._fk_chain)
        for index, ctl in enumerate(self._fk_chain):
            fraction = float(index) / max(count - 1, 1)
            label = "Wave%d" % index
            along = nodes.multiply(nodes.divide(fraction, length, name=self._n(label, "MD")), 360.0,
                                   name=self._n(label + "Deg", "MDL"))
            phase = nodes.add(nodes.subtract(along, moving, name=self._n(label, "PMA")), offset,
                              name=self._n(label + "Phase", "ADL"))
            sine = cmds.createNode("sin", name=naming.unique_name(self._n(label, "SIN")), skipSelect=True)
            cmds.connectAttr(phase, sine + ".input")
            weight = nodes.blend(1.0, fraction, falloff, name=self._n(label + "Weight", "BLD"))
            angle = nodes.multiply(nodes.multiply(sine + ".output", amplitude, name=self._n(label + "Amp", "MDL")),
                                   weight, name=self._n(label + "Angle", "MDL"))
            plugs = [None, None, None]
            plugs[axis] = angle
            common.compose_zero(ctl.zero, pre_rotate_plug=tuple(plugs))


def _perpendicular(direction, joint):
    """A world vector perpendicular to ``direction`` (from the joint's axes)."""
    world = matrix.get_world_matrix(joint)
    axes = [mathlib.normalize(axis) for axis in mathlib.axes(world)[:3]]
    best = min(axes, key=lambda axis: abs(mathlib.dot(axis, direction)))
    return mathlib.normalize(mathlib.sub(best, mathlib.scale(direction, mathlib.dot(best, direction))))


def _closest_params(shape, points):
    """Normalized U of the closest point on the surface to each point."""
    from maya.api import OpenMaya as om

    selection = om.MSelectionList()
    selection.add(shape)
    surface = om.MFnNurbsSurface(selection.getDagPath(0))
    low, high = surface.knotDomainInU
    result = []
    for point in points:
        _closest, u, _v = surface.closestPoint(om.MPoint(*point), space=om.MSpace.kWorld)
        result.append(min(max((u - low) / (high - low), 0.0), 1.0))
    return result


def _arc_fractions(shape, params, samples=400):
    """Fraction of the ribbon's middle length (0..1) at each normalized U."""
    from maya.api import OpenMaya as om

    selection = om.MSelectionList()
    selection.add(shape)
    surface = om.MFnNurbsSurface(selection.getDagPath(0))
    low, high = surface.knotDomainInU
    v_low, v_high = surface.knotDomainInV
    v = (v_low + v_high) * 0.5
    cumulative = [0.0]
    previous = surface.getPointAtParam(low, v, om.MSpace.kWorld)
    for step in range(1, samples + 1):
        point = surface.getPointAtParam(low + (high - low) * step / samples, v, om.MSpace.kWorld)
        cumulative.append(cumulative[-1] + point.distanceTo(previous))
        previous = point
    total = cumulative[-1] or 1.0
    result = []
    for param in params:
        position = param * samples
        index = min(int(position), samples - 1)
        t = position - index
        result.append((cumulative[index] + (cumulative[index + 1] - cumulative[index]) * t) / total)
    return result


def _bone_index(joints, index):
    if index + 1 < len(joints):
        return common.bone_axis_index(joints[index], joints[index + 1])[0]
    return common.bone_axis_index(joints[index - 1], joints[index])[0]


def _volume(name, pose, root_shrink, volume, profile, bone_index):
    """Scale the pose's non-bone axes by ``1 + (sqrt(rest / current) - 1) * volume * profile``."""
    amount = nodes.multiply(nodes.multiply(nodes.subtract(root_shrink, 1.0), volume), profile)
    factor = nodes.add(amount, 1.0)
    compose = cmds.createNode("composeMatrix", name=naming.unique_name(name + "_CM"), skipSelect=True)
    for index, axis in enumerate("XYZ"):
        if index == bone_index:
            cmds.setAttr("%s.inputScale%s" % (compose, axis), 1.0)
        else:
            cmds.connectAttr(factor, "%s.inputScale%s" % (compose, axis))
    scaled = cmds.createNode("multMatrix", name=naming.unique_name(name + "_MM"), skipSelect=True)
    cmds.connectAttr(compose + ".outputMatrix", scaled + ".matrixIn[0]")
    cmds.connectAttr(pose, scaled + ".matrixIn[1]")
    return scaled + ".matrixSum"
