"""IK/FK Limb: arms and legs on three joints (Start, Mid, End).

Built with matrix and utility nodes only (no constraint nodes):

* a hidden IK chain (``ikRPsolver``) whose pole vector, twist and goal are
  computed by nodes: soft IK, stretch, pin to the pole, upper/lower length,
* FK controls on the joints (``length`` stretch),
* ``blendMatrix`` per joint between FK and IK, driven by ``ikFk`` on the
  settings control (also a proxy attribute on every limb control),
* the outputs drive your bind joints (translate stretch, or scale stretch
  when *Game safe* is off).

Knee / elbow: a **pole** control, or **no-flip** (no pole, the knee follows
the IK control and a ``kneeTwist`` attribute aims it).

Animation helpers: :func:`snap_fk_to_ik`, :func:`snap_ik_to_fk`, :func:`toggle`.

**Auto-snap**: with ``autoSnap`` on (settings control), changing ``ikFk``
snaps the side you switch to onto the other one, so the bend is kept. It runs
from a callback installed by the toolkit (and by a script node when the scene
is opened). Keyed switches during playback are not snapped.
"""

import math

from maya import cmds

from jeffy.core import attributes, mathlib, matrix, naming, nodes
from jeffy.geometry import curves
from jeffy.joints import tools as joint_tools
from jeffy.setups.core import guides as guides_module
from jeffy.setups.core import scene
from jeffy.setups.core import tag as tag_module
from jeffy.setups.core.base import Setup
from jeffy.setups.core.schema import GAME_SAFE_OPTION, SIZE_OPTION, Option, SetupError, Slot
from jeffy.setups.tools import common

SWITCH = "ikFk"
AUTO_SNAP = "autoSnap"
SCRIPT_NODE = "jeffySetupBelt_autoSnap_SN"
SCRIPT = ("try:\n"
          "    from jeffy.setups.tools import ikfk_limb\n"
          "    ikfk_limb.install_auto_snap()\n"
          "except Exception:\n"
          "    pass\n")
KEYS = ("start", "mid", "end")
EPSILON = 1e-4
FK_SPACES = ("parent", "chest", "hips", "cog", "root", "world")
IK_SPACES = ("root", "world", "cog", "hips", "chest", "head", "parent")
POLE_SPACES = ("root", "world", "self:ik", "parent")
#: IK control attributes reset when snapping IK onto FK
RESET_ON_SNAP = ("twist", "pin")


@scene.register
class IkFkLimb(Setup):
    TYPE = "ikfk_limb"
    LABEL = "IK/FK Limb"
    CATEGORY = "build"
    ORDER = 20
    DESCRIPTION = ("Arms and legs on three joints. Hidden IK and FK systems blend into your joints: stretch, soft IK, "
                   "pin to the pole, pole or no-flip knee, seamless IK/FK snapping. Bend the elbow / knee slightly "
                   "in the skeleton so the IK knows which way it bends.")
    SLOTS = (
        Slot("start", "Start", tip="Shoulder or hip joint"),
        Slot("mid", "Mid", tip="Elbow or knee joint (a child of Start)"),
        Slot("end", "End", tip="Wrist or ankle joint (a child of Mid)"),
    )
    OPTIONS = (
        Option("knee", "Elbow / knee", "pole", choices=("pole", "no-flip"),
               tip="pole: a pole vector control aims the elbow / knee.\n"
                   "no-flip: no pole control, the knee follows the IK control's orientation and 'kneeTwist' "
                   "aims it (classic leg setup)."),
        Option("stretch", "Stretch", True, tip="'stretch' attribute: the limb gets longer to reach the IK control"),
        Option("soft", "Soft IK", True, tip="'softness' attribute: no pop when the limb straightens"),
        Option("pin", "Pin to pole", True, tip="'pin' attribute: the elbow / knee locks onto the pole control"),
        Option("ik_orient", "IK control orientation", "world", choices=("world", "joint"),
               tip="world: the IK control is aligned to the world axes. joint: to the end joint."),
        Option("default_mode", "Start in", "ik", choices=("ik", "fk"), tip="Default value of the IK/FK switch"),
        Option("pole_distance", "Pole distance", 0.6, minimum=0.05, maximum=20.0, step=0.1,
               tip="Default pole distance from the elbow / knee, in limb lengths (or move the pole guide)"),
        SIZE_OPTION,
        GAME_SAFE_OPTION,
    )
    GUIDES = ("pole", "settings")
    SCALE_STRETCH = True

    # ------------------------------------------------------------------
    @classmethod
    def validate(cls, slots, options):
        start, mid, end = slots["start"], slots["mid"], slots["end"]
        if not common.is_child(start, mid):
            raise SetupError("Mid (%s) must be a child of Start (%s)" % (mid, start))
        if not common.is_child(mid, end):
            raise SetupError("End (%s) must be a child of Mid (%s)" % (end, mid))
        points = [common.position(j) for j in (start, mid, end)]
        if _bend_direction(points) is None:
            raise SetupError("%s, %s and %s are in a straight line. Bend the elbow / knee slightly in the skeleton "
                             "so the IK knows which way it bends." % (start, mid, end))

    @classmethod
    def driven_joints(cls, slots):
        return [slots["start"], slots["mid"], slots["end"]]

    @classmethod
    def default_name(cls, slots, options):
        return None

    @classmethod
    def default_guides(cls, slots, options, side):
        points = [common.position(slots[key]) for key in KEYS]
        total = mathlib.distance(points[0], points[1]) + mathlib.distance(points[1], points[2])
        pole = mathlib.pole_vector_position(points[0], points[1], points[2], options["pole_distance"])
        sign = -1.0 if side == naming.SIDE_RIGHT or points[2][0] < -EPSILON else 1.0
        settings = mathlib.add(points[2], (sign * total * 0.12, total * 0.15, 0.0))
        return {"pole": pole, "settings": settings}

    @classmethod
    def guide_size(cls, slots, options):
        points = [common.position(slots[key]) for key in KEYS]
        return (mathlib.distance(points[0], points[1]) + mathlib.distance(points[1], points[2])) * 0.04

    # ------------------------------------------------------------------
    def build_setup(self):
        options = self.options
        joints = [self.slot_node(key) for key in KEYS]
        worlds = [common.world_matrix(joint) for joint in joints]
        points = [tuple(mathlib.get_translation(world)) for world in worlds]
        upper = mathlib.distance(points[0], points[1])
        lower = mathlib.distance(points[1], points[2])
        total = upper + lower
        size = total * options["size"]
        no_flip = options["knee"] == "no-flip"

        # systems ----------------------------------------------------------
        # The hidden IK chain has its own planar orientation (X down the bone, Z on the bend axis) so the
        # RP solver bends it cleanly whatever the orientation of your joints; fixed offsets map it back.
        sys_in = self.group("In", match=joints[0])
        ik_joints = []
        parent = sys_in
        for joint, ik_matrix in zip(joints, _planar_matrices(points)):
            ik_joint = joint_tools.create_joint(naming.compose(common.label(joint) + "IK", self.side, "joint"),
                                                parent=parent, position=mathlib.get_translation(ik_matrix))
            matrix.set_joint_orient_from_matrix(ik_joint, ik_matrix)
            ik_joints.append(ik_joint)
            parent = ik_joint
        tag_module.set_nodes(self.tag, "ik_joints", ik_joints)
        handle, effector = cmds.ikHandle(startJoint=ik_joints[0], endEffector=ik_joints[2], solver="ikRPsolver",
                                         name=naming.unique_name(naming.compose(self.name, self.side, "ik_handle")))
        cmds.rename(effector, naming.unique_name(naming.compose(self.name, self.side, "effector")))
        handle = cmds.parent(handle, self.systems_group)[0]

        # controls ---------------------------------------------------------
        fk = []
        parent = self.controls_group
        for index, joint in enumerate(joints):
            child = joints[index + 1] if index < 2 else None  # the end joint faces its own child (hand / foot)
            axis = common.bone_axis(joint, child).lstrip("-")
            ctl = self.control("fk%d" % index, common.label(joint) + "FK", shape="circle", size=size * 0.09,
                               axis=axis, parent=parent, match=joint, lock=("t", "s", "v"))
            if fk:
                ctl.set_parent_tag(fk[-1].node)
            fk.append(ctl)
            parent = ctl.node

        ik_world = worlds[2] if options["ik_orient"] == "joint" else mathlib.compose(translate=points[2])
        ik_ctl = self.control("ik", self.name + "IK", shape="cube", size=size * 0.07, axis="y",
                              world_matrix=ik_world, lock=("s", "v"))
        end_ref = self.group("IkEnd", parent=ik_ctl.node, world_matrix=worlds[2], visible=False)
        tag_module.set_node(self.tag, "ik_end_ref", end_ref)

        pole_point = _pole_in_plane(points, guides_module.position(self.guides.get("pole")),
                                    options["pole_distance"])
        pole = None
        if not no_flip:
            pole = self.control("pole", self.name + "Pole", shape="octahedron", size=size * 0.035, axis="y",
                                position=pole_point, lock=("r", "s", "v"))
        settings_point = guides_module.position(self.guides.get("settings")) or \
            self.default_guides(self._slots, options, self.side)["settings"]
        settings = self.control("settings", self.name + "Settings", shape="gear", size=size * 0.04, axis="z",
                                position=settings_point, lock=("t", "r", "s", "v"), secondary=True)
        switch = attributes.add_attr(settings.node, SWITCH, "float", default=1.0 if options["default_mode"] == "ik"
                                     else 0.0, minimum=0.0, maximum=1.0)
        cmds.setAttr(switch, 1.0 if options["default_mode"] == "ik" else 0.0)
        auto = attributes.add_attr(settings.node, AUTO_SNAP, "bool", default=True, keyable=False, channel_box=True)
        cmds.setAttr(auto, True)

        # FK stretch -------------------------------------------------------
        if options["stretch"]:
            for index in (1, 2):
                length = attributes.add_attr(fk[index - 1].node, "length", "float", default=1.0, minimum=0.001)
                common.compose_zero(fk[index].zero, length_plug=length)

        # IK network -------------------------------------------------------
        ctl = ik_ctl.node
        attributes.add_separator(ctl, "ik")
        twist_name = "kneeTwist" if no_flip else "twist"
        twist = attributes.add_attr(ctl, twist_name, "float", default=0.0)
        pole_target = pole.node if pole else self._no_flip_target(ik_ctl.node, points, total)
        self._pole_vector(handle, sys_in, pole_target)
        self._ik_goal(handle, sys_in, end_ref, ctl, pole, ik_joints, upper, lower)
        if no_flip:
            offset = _solve_twist(handle, ik_joints[1], points[1])
            twist_sum = nodes.add(offset, twist, name=naming.compose(self.name + "KneeTwist", self.side, "UTL"))
            cmds.connectAttr(twist_sum, handle + ".twist", force=True)
            tag_module.set_data(self.tag, "twist_offset", offset)
        else:
            cmds.connectAttr(twist, handle + ".twist", force=True)

        ik_end = cmds.createNode("blendMatrix", name=naming.unique_name(naming.compose(self.name + "IkEnd", self.side,
                                                                                       "blend_matrix")),
                                 skipSelect=True)
        cmds.connectAttr(end_ref + ".worldMatrix[0]", ik_end + ".inputMatrix")
        cmds.connectAttr(ik_joints[2] + ".worldMatrix[0]", ik_end + ".target[0].targetMatrix")
        for attr, value in (("weight", 1.0), ("translateWeight", 1.0), ("rotateWeight", 0.0), ("scaleWeight", 0.0),
                            ("shearWeight", 0.0)):
            cmds.setAttr("%s.target[0].%s" % (ik_end, attr), value)
        # IK poses in the orientation of your joints
        ik_nodes = []
        for index in (0, 1):
            offset = cmds.createNode("multMatrix", name=naming.unique_name(naming.compose(
                common.label(joints[index]) + "IkPose", self.side, "mult_matrix")), skipSelect=True)
            matrix.set_matrix_attr(offset + ".matrixIn[0]", mathlib.mult(
                worlds[index], mathlib.inverse(common.world_matrix(ik_joints[index]))))
            cmds.connectAttr(ik_joints[index] + ".worldMatrix[0]", offset + ".matrixIn[1]")
            ik_nodes.append(offset)
        ik_nodes.append(ik_end)
        tag_module.set_nodes(self.tag, "ik_poses", ik_nodes)

        # blend + outputs ----------------------------------------------------
        ik_mats = [ik_nodes[0] + ".matrixSum", ik_nodes[1] + ".matrixSum", ik_end + ".outputMatrix"]
        for index, key in enumerate(KEYS):
            blend = cmds.createNode("blendMatrix", name=naming.unique_name(naming.compose(
                common.label(joints[index]) + "IkFk", self.side, "blend_matrix")), skipSelect=True)
            cmds.connectAttr(fk[index].node + ".worldMatrix[0]", blend + ".inputMatrix")
            cmds.connectAttr(ik_mats[index], blend + ".target[0].targetMatrix")
            cmds.connectAttr(switch, blend + ".target[0].weight")
            child = KEYS[index + 1] if index < 2 else None
            self.add_output(key, blend + ".outputMatrix", joint=joints[index], stretch_child=child,
                            label=common.label(joints[index]))
        outputs = self.outputs
        self.follow(settings.zero, outputs["end"])

        # visibility, proxies, line ------------------------------------------
        fk_vis = nodes.condition(switch, "<", 1.0, 1.0, 0.0, name=naming.compose(self.name + "FkVis", self.side,
                                                                                "condition"))
        ik_vis = nodes.condition(switch, ">", 0.0, 1.0, 0.0, name=naming.compose(self.name + "IkVis", self.side,
                                                                                "condition"))
        cmds.connectAttr(fk_vis, fk[0].zero + ".visibility")
        cmds.connectAttr(ik_vis, ik_ctl.zero + ".visibility")
        limb_controls = [c.node for c in fk] + [ik_ctl.node]
        if pole:
            cmds.connectAttr(ik_vis, pole.zero + ".visibility")
            limb_controls.append(pole.node)
            line = curves.create_connector_line(outputs["mid"], pole.node,
                                                name=naming.compose(self.name + "PoleLine", self.side, "curve"),
                                                parent=self.controls_group)
            cmds.connectAttr(ik_vis, line + ".visibility")
        for node in limb_controls:
            attributes.add_proxy(switch, node)

        # anchors (auto-attach + spaces) -------------------------------------
        self.add_anchor(sys_in)
        self.add_anchor(fk[0].zero, fk[0].node, kind="orient", spaces=FK_SPACES, default="parent")
        self.add_anchor(ik_ctl.zero, ik_ctl.node, kind="parent", spaces=IK_SPACES, default="root")
        if pole:
            self.add_anchor(pole.zero, pole.node, kind="parent", spaces=POLE_SPACES, default="root")

        # data for IK/FK snapping
        ik_offset = mathlib.mult(matrix.get_world_matrix(ik_ctl.node), mathlib.inverse(worlds[2]))
        tag_module.set_data(self.tag, "snap", {
            "ik_offset": list(ik_offset), "upper": upper, "lower": lower,
            "pole_factor": mathlib.distance(points[1], pole_point) / total if total else 1.0,
        })

    # ------------------------------------------------------------------
    @classmethod
    def create(cls, *args, **kwargs):
        _ensure_script_node()  # before the build: its Node Editor tab must not pick it up
        setup = super(IkFkLimb, cls).create(*args, **kwargs)
        install_auto_snap()
        return setup

    def delete(self, layers=True, mirror=False):
        super(IkFkLimb, self).delete(layers=layers, mirror=mirror)
        if not scene.all_setups(setup_type=IkFkLimb.TYPE):
            remove_auto_snap()
            if cmds.objExists(SCRIPT_NODE):
                cmds.delete(SCRIPT_NODE)

    def _name(self, label, suffix="UTL"):
        return naming.compose(self.name + label, self.side, suffix)

    def _no_flip_target(self, ik_control, points, total):
        """Hidden pole target beside the end joint, following the IK control."""
        limb = mathlib.normalize(mathlib.sub(points[2], points[0]))
        side = mathlib.normalize(mathlib.cross(limb, _bend_direction(points)))
        target = self.group("NoFlipPole", parent=ik_control, visible=False)
        cmds.xform(target, worldSpace=True, translation=mathlib.add(points[2], mathlib.scale(side, total)))
        return target

    def _pole_vector(self, handle, sys_in, target):
        """``handle.poleVector`` = (target - start) in the handle's parent space (no constraint)."""
        common.pole_vector(self.name, self.side, handle, sys_in, target)

    def _ik_goal(self, handle, sys_in, end_ref, ctl, pole, ik_joints, upper, lower):
        """Soft IK, stretch and pin: the handle position and the IK joint lengths.

        ::

            D   = distance(start, IK end) / rig scale
            L   = upper * upperLength + lower * lowerLength
            sd  = softness * L * 0.25                      (soft zone)
            Ds  = D > L - sd ? L - sd + sd * (1 - e^-((D - L + sd) / sd)) : D
            f   = lerp(1, D / Ds, stretch)                 (length factor)
            goal = lerp(start + dir * Ds, IK end, 1 - (1 - stretch) * (1 - pin))
        """
        options = self.options
        name = self._name
        start = nodes.decompose_matrix(sys_in + ".worldMatrix[0]", name=name("GoalStart", "DM"))
        end = nodes.decompose_matrix(end_ref + ".worldMatrix[0]", name=name("GoalEnd", "DM"))
        scale = start + ".outputScaleX"
        distance = nodes.distance_between(sys_in, end_ref, name=name("Goal", "DIST"))
        current = nodes.divide(distance, scale, name=name("GoalNorm", "MD"))

        upper_length = attributes.add_attr(ctl, "upperLength", "float", default=1.0, minimum=0.001)
        lower_length = attributes.add_attr(ctl, "lowerLength", "float", default=1.0, minimum=0.001)
        upper_plug = nodes.multiply(upper, upper_length, name=name("UpperLength", "MDL"))
        lower_plug = nodes.multiply(lower, lower_length, name=name("LowerLength", "MDL"))
        chain = nodes.add(upper_plug, lower_plug, name=name("ChainLength", "ADL"))

        if options["soft"]:
            softness = attributes.add_attr(ctl, "softness", "float", default=0.0, minimum=0.0, maximum=1.0)
            soft_zone = nodes.clamp(nodes.multiply(nodes.multiply(softness, chain, name=name("SoftZone", "MDL")), 0.25,
                                                   name=name("SoftZoneQuarter", "MDL")), EPSILON, 1.0e9,
                                    name=name("SoftZone", "CLP"))
            hard = nodes.subtract(chain, soft_zone, name=name("SoftStart", "PMA"))
            over = nodes.subtract(current, hard, name=name("SoftOver", "PMA"))
            exponent = nodes.clamp(nodes.divide(nodes.negate(over, name=name("SoftNeg", "MDL")), soft_zone,
                                                name=name("SoftExp", "MD")), -50.0, 50.0, name=name("SoftExp", "CLP"))
            falloff = nodes.power(math.e, exponent, name=name("SoftFalloff", "MD"))
            soft_value = nodes.add(hard, nodes.multiply(soft_zone, nodes.reverse(falloff, name=name("SoftRev", "REV")),
                                                        name=name("SoftValue", "MDL")), name=name("SoftValue", "ADL"))
            reach = nodes.condition(current, ">", hard, soft_value, current, name=name("Soft", "COND"))
        else:
            reach = nodes.condition(current, ">", chain, chain, current, name=name("Reach", "COND"))
        reach = nodes.clamp(reach, EPSILON, 1.0e12, name=name("Reach", "CLP"))

        factor = None
        weight = None
        if options["stretch"]:
            stretch = attributes.add_attr(ctl, "stretch", "float", default=0.0, minimum=0.0, maximum=1.0)
            ratio = nodes.divide(current, reach, name=name("StretchRatio", "MD"))
            factor = nodes.blend(1.0, ratio, stretch, name=name("Stretch", "BLD"))
            weight = stretch
        pin = None
        if options["pin"] and pole is not None:
            pin = attributes.add_attr(ctl, "pin", "float", default=0.0, minimum=0.0, maximum=1.0)
            if weight is None:
                weight = pin
            else:
                both = nodes.multiply(nodes.reverse(weight, name=name("GoalStretchRev", "REV")),
                                      nodes.reverse(pin, name=name("GoalPinRev", "REV")), name=name("GoalFree", "MDL"))
                weight = nodes.reverse(both, name=name("GoalWeight", "REV"))

        # goal position (world) -> handle parent space
        direction = cmds.createNode("plusMinusAverage", name=naming.unique_name(name("GoalDir", "PMA")),
                                    skipSelect=True)
        cmds.setAttr(direction + ".operation", 2)
        cmds.connectAttr(end + ".outputTranslate", direction + ".input3D[0]")
        cmds.connectAttr(start + ".outputTranslate", direction + ".input3D[1]")
        # direction * reach / distance (no normalize node: it errors on zero vectors)
        ratio = nodes.divide(nodes.multiply(reach, scale, name=name("ReachWorld", "MDL")),
                             nodes.clamp(distance, EPSILON, 1.0e12, name=name("GoalDist", "CLP")),
                             name=name("GoalRatio", "MD"))
        offset = cmds.createNode("multiplyDivide", name=naming.unique_name(name("GoalOffset", "MD")), skipSelect=True)
        cmds.connectAttr(direction + ".output3D", offset + ".input1")
        for axis in "XYZ":
            cmds.connectAttr(ratio, offset + ".input2" + axis)
        soft_point = cmds.createNode("plusMinusAverage", name=naming.unique_name(name("GoalSoft", "PMA")),
                                     skipSelect=True)
        cmds.connectAttr(start + ".outputTranslate", soft_point + ".input3D[0]")
        cmds.connectAttr(offset + ".output", soft_point + ".input3D[1]")
        goal = soft_point + ".output3D"
        if weight is not None:
            mix = cmds.createNode("blendColors", name=naming.unique_name(name("Goal", "BLD")), skipSelect=True)
            cmds.connectAttr(end + ".outputTranslate", mix + ".color1")
            cmds.connectAttr(goal, mix + ".color2")
            cmds.connectAttr(weight, mix + ".blender")
            goal = mix + ".output"
        local = cmds.createNode("pointMatrixMult", name=naming.unique_name(name("GoalLocal", "UTL")), skipSelect=True)
        cmds.connectAttr(goal, local + ".inPoint")
        parent_inverse = matrix.parent_inverse_plug(handle)
        if parent_inverse:
            cmds.connectAttr(parent_inverse, local + ".inMatrix")
        cmds.connectAttr(local + ".output", handle + ".translate", force=True)

        # joint lengths
        finals = [upper_plug, lower_plug]
        if factor is not None:
            finals = [nodes.multiply(plug, factor, name=name(label + "Stretch", "MDL"))
                      for plug, label in zip(finals, ("Upper", "Lower"))]
        if pin is not None:
            to_pole = nodes.divide(nodes.distance_between(sys_in, pole.node, name=name("PinUpper", "DIST")), scale,
                                   name=name("PinUpper", "MD"))
            from_pole = nodes.divide(nodes.distance_between(pole.node, end_ref, name=name("PinLower", "DIST")), scale,
                                     name=name("PinLower", "MD"))
            finals = [nodes.blend(finals[0], to_pole, pin, name=name("PinUpper", "BLD")),
                      nodes.blend(finals[1], from_pole, pin, name=name("PinLower", "BLD"))]
        for joint, final, rest_length in zip(ik_joints[1:], finals, (upper, lower)):
            ratio = nodes.divide(final, rest_length, name=name(common.label(joint) + "Length", "MD"))
            rest = list(cmds.getAttr(joint + ".translate")[0])
            scaled = cmds.createNode("multiplyDivide", name=naming.unique_name(name(common.label(joint) + "Translate",
                                                                                    "MD")), skipSelect=True)
            cmds.setAttr(scaled + ".input1", *rest)
            for axis in "XYZ":
                cmds.connectAttr(ratio, scaled + ".input2" + axis)
            cmds.connectAttr(scaled + ".output", joint + ".translate", force=True)
        cmds.setAttr(handle + ".visibility", 0)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def _bend_direction(points):
    """Unit vector from the start-end line to the mid joint (``None`` when straight)."""
    projected = mathlib.closest_point_on_line(points[1], points[0], points[2])
    direction = mathlib.sub(points[1], projected)
    total = mathlib.distance(points[0], points[1]) + mathlib.distance(points[1], points[2])
    if mathlib.length(direction) < max(total * 1e-4, 1e-6):
        return None
    return mathlib.normalize(direction)


def _planar_matrices(points):
    """World matrices of the hidden IK joints: X down each bone, Z on the bend axis."""
    normal = mathlib.normalize(mathlib.cross(mathlib.sub(points[1], points[0]), mathlib.sub(points[2], points[1])))
    aims = [mathlib.normalize(mathlib.sub(points[1], points[0])), mathlib.normalize(mathlib.sub(points[2], points[1]))]
    aims.append(aims[1])
    result = []
    for point, aim in zip(points, aims):
        up = mathlib.normalize(mathlib.cross(normal, aim))
        result.append(mathlib.from_axes(aim, up, normal, point))
    return result


def _pole_in_plane(points, guide, distance_factor):
    """Pole position in the limb plane (a guide is projected onto it, keeping its side)."""
    default = mathlib.pole_vector_position(points[0], points[1], points[2], distance_factor)
    if guide is None:
        return tuple(default)
    normal = mathlib.normalize(mathlib.cross(mathlib.sub(points[1], points[0]), mathlib.sub(points[2], points[1])))
    projected = mathlib.project_on_plane(guide, points[1], normal)
    bend = _bend_direction(points)
    offset = mathlib.sub(projected, mathlib.closest_point_on_line(projected, points[0], points[2]))
    if mathlib.length(offset) < 1e-4 or mathlib.dot(offset, bend) <= 0:
        return tuple(default)
    return tuple(projected)


def _solve_twist(handle, mid_joint, rest_point):
    """Handle twist putting the IK mid joint back on its rest position (no-flip knee)."""
    def error(angle):
        cmds.setAttr(handle + ".twist", angle)
        return mathlib.distance(cmds.xform(mid_joint, query=True, worldSpace=True, translation=True), rest_point)

    best = min(range(-180, 181, 5), key=error)
    low, high = best - 5.0, best + 5.0
    for _step in range(40):  # golden section refinement
        a = high - (high - low) * 0.618
        b = low + (high - low) * 0.618
        if error(a) < error(b):
            high = b
        else:
            low = a
    angle = round((low + high) * 0.5, 4)
    cmds.setAttr(handle + ".twist", 0.0)
    return angle


# ---------------------------------------------------------------------------
# Animation: IK/FK snapping
# ---------------------------------------------------------------------------
def find_limb(node):
    """The IK/FK limb setup a node belongs to (or ``None``)."""
    setup = scene.find_setup(node)
    return setup if isinstance(setup, IkFkLimb) else None


def _limb(node_or_setup):
    setup = node_or_setup if isinstance(node_or_setup, IkFkLimb) else find_limb(node_or_setup)
    if setup is None:
        raise SetupError("%s is not part of an IK/FK Limb" % node_or_setup)
    return setup


def _key(nodes_to_key, switch_plug):
    cmds.setKeyframe([n for n in nodes_to_key if n], attribute=["translate", "rotate"])
    cmds.setKeyframe(switch_plug)
    for node in nodes_to_key:
        for attr in ("length", "upperLength", "lowerLength", "twist", "kneeTwist", "pin"):
            if node and cmds.attributeQuery(attr, node=node, exists=True) and \
                    attributes.is_settable(node, attr):
                cmds.setKeyframe(node, attribute=attr)


def snap_fk_to_ik(limb, switch=True, key=False):
    """Put the FK controls on the current IK pose (and switch to FK)."""
    setup = _limb(limb)
    ctls = setup.controls
    fk = [ctls["fk0"], ctls["fk1"], ctls["fk2"]]
    poses = tag_module.get_nodes(setup.tag, "ik_poses")
    targets = [cmds.getAttr(poses[0] + ".matrixSum"), cmds.getAttr(poses[1] + ".matrixSum"),
               cmds.getAttr(poses[2] + ".outputMatrix")]
    data = tag_module.get_data(setup.tag, "snap", {})
    scale = mathlib.length(mathlib.axes(targets[0])[0]) or 1.0
    points = [mathlib.get_translation(t) for t in targets]
    for index, rest in ((0, data.get("upper")), (1, data.get("lower"))):
        plug = fk[index] + ".length"
        if rest and cmds.objExists(plug) and attributes.is_settable(fk[index], "length"):
            cmds.setAttr(plug, mathlib.distance(points[index], points[index + 1]) / scale / rest)
    for ctl, target in zip(fk, targets):
        matrix.set_world_matrix(ctl, target, translate=False, scale=False)
    keyed = list(fk) + _layer_hooks(setup, "snap_fk_to_ik")
    switch_plug = "%s.%s" % (ctls["settings"], SWITCH)
    if switch:
        _set_switch(setup, 0.0)
    if key:
        _key(keyed, switch_plug)
    return setup


def snap_ik_to_fk(limb, switch=True, key=False):
    """Put the IK control (and pole / knee twist) on the current FK pose (and switch to IK)."""
    setup = _limb(limb)
    ctls = setup.controls
    fk = [ctls["fk0"], ctls["fk1"], ctls["fk2"]]
    ik_ctl = ctls["ik"]
    pole = ctls.get("pole")
    data = tag_module.get_data(setup.tag, "snap", {})
    worlds = [cmds.getAttr(ctl + ".worldMatrix[0]") for ctl in fk]
    points = [mathlib.get_translation(w) for w in worlds]

    keyed = [ik_ctl, pole] + _layer_hooks(setup, "reset_ik")
    for attr in RESET_ON_SNAP:
        if cmds.attributeQuery(attr, node=ik_ctl, exists=True) and attributes.is_settable(ik_ctl, attr):
            cmds.setAttr("%s.%s" % (ik_ctl, attr), 0.0)
    for attr, fk_ctl in (("upperLength", fk[0]), ("lowerLength", fk[1])):
        if cmds.attributeQuery(attr, node=ik_ctl, exists=True) and attributes.is_settable(ik_ctl, attr):
            value = cmds.getAttr(fk_ctl + ".length") if cmds.attributeQuery("length", node=fk_ctl, exists=True) \
                else 1.0
            cmds.setAttr("%s.%s" % (ik_ctl, attr), value)
    matrix.set_world_matrix(ik_ctl, mathlib.mult(data["ik_offset"], worlds[2]), scale=False)
    if pole:
        total = mathlib.distance(points[0], points[1]) + mathlib.distance(points[1], points[2])
        factor = data.get("pole_factor", 1.0)
        target = mathlib.pole_vector_position(points[0], points[1], points[2], factor) if total else points[1]
        cmds.xform(pole, worldSpace=True, translation=target)
    elif cmds.attributeQuery("kneeTwist", node=ik_ctl, exists=True):
        _match_knee_twist(setup, ik_ctl, points[1])
    keyed += _layer_hooks(setup, "snap_ik_to_fk")
    switch_plug = "%s.%s" % (ctls["settings"], SWITCH)
    if switch:
        _set_switch(setup, 1.0)
    if key:
        _key(keyed, switch_plug)
    return setup


def _match_knee_twist(setup, ik_ctl, target):
    ik_mid = tag_module.get_nodes(setup.tag, "ik_joints")[1]
    plug = ik_ctl + ".kneeTwist"

    def error(angle):
        cmds.setAttr(plug, angle)
        return mathlib.distance(cmds.xform(ik_mid, query=True, worldSpace=True, translation=True), target)

    best = min(range(-180, 181, 5), key=error)
    low, high = best - 5.0, best + 5.0
    for _step in range(40):
        a = high - (high - low) * 0.618
        b = low + (high - low) * 0.618
        if error(a) < error(b):
            high = b
        else:
            low = a
    cmds.setAttr(plug, (low + high) * 0.5)


def _layer_hooks(setup, hook):
    """Let layers (reverse foot...) take part in snapping. Returns nodes to key."""
    nodes_to_key = []
    for layer in setup.all_layers():
        method = getattr(layer, hook, None)
        if method is not None:
            nodes_to_key.extend(method(setup) or [])
    return nodes_to_key


def _set_switch(setup, value):
    """Set ``ikFk`` without triggering the auto-snap callback."""
    _AUTO["busy"] = True
    try:
        cmds.setAttr("%s.%s" % (setup.controls["settings"], SWITCH), value)
    finally:
        _AUTO["busy"] = False
    _AUTO["values"][setup.tag] = value


# ---------------------------------------------------------------------------
# Auto-snap (callbacks on ikFk)
# ---------------------------------------------------------------------------
_AUTO = {"callbacks": [], "values": {}, "busy": False}


def install_auto_snap():
    """Watch ``ikFk`` on every IK/FK limb of the scene (safe to call again)."""
    from maya.api import OpenMaya as om

    remove_auto_snap()
    for limb in scene.all_setups(setup_type=IkFkLimb.TYPE):
        ctls = limb.controls
        settings = ctls.get("settings")
        if not settings:
            continue
        _AUTO["values"][limb.tag] = cmds.getAttr("%s.%s" % (settings, SWITCH))
        watched = [settings]
        for owner in [limb] + limb.all_layers():
            for node in owner.controls.values():
                if node not in watched and cmds.attributeQuery(SWITCH, node=node, exists=True):
                    watched.append(node)
        for node in watched:
            selection = om.MSelectionList()
            selection.add(node)
            _AUTO["callbacks"].append(om.MNodeMessage.addAttributeChangedCallback(
                selection.getDependNode(0), _on_attribute, limb.tag))
    return len(_AUTO["callbacks"])


def remove_auto_snap():
    from maya.api import OpenMaya as om

    for callback in _AUTO["callbacks"]:
        try:
            om.MMessage.removeCallback(callback)
        except RuntimeError:
            pass
    _AUTO["callbacks"] = []
    _AUTO["values"].clear()


def _on_attribute(message, plug, _other, limb_tag):
    from maya.api import OpenMaya as om

    if _AUTO["busy"] or not (message & om.MNodeMessage.kAttributeSet):
        return
    if plug.partialName(useLongNames=True) != SWITCH or not cmds.objExists(limb_tag):
        return
    setup = scene.wrap(limb_tag)
    settings = setup.controls.get("settings") if setup is not None else None
    if not settings:
        return
    new = cmds.getAttr("%s.%s" % (settings, SWITCH))
    old = _AUTO["values"].get(limb_tag, new)
    _AUTO["values"][limb_tag] = new
    if abs(new - old) < 1e-6 or not cmds.getAttr("%s.%s" % (settings, AUTO_SNAP)):
        return
    if cmds.play(query=True, state=True):
        return
    _AUTO["busy"] = True
    try:
        if new > old:
            snap_ik_to_fk(setup, switch=False)
        else:
            snap_fk_to_ik(setup, switch=False)
    except Exception as error:  # never break the user's channel box edit
        cmds.warning("[Jeffy] auto-snap failed on %s: %s" % (setup.describe(), error))
    finally:
        _AUTO["busy"] = False


def _ensure_script_node():
    """Reinstall the callbacks when the scene is opened (script node, python)."""
    if not cmds.objExists(SCRIPT_NODE):
        cmds.scriptNode(name=SCRIPT_NODE, scriptType=1, beforeScript=SCRIPT, sourceType="python")


def toggle(node, key=False):
    """Snap and switch to the other mode (IK -> FK or FK -> IK)."""
    setup = _limb(node)
    if cmds.getAttr("%s.%s" % (setup.controls["settings"], SWITCH)) >= 0.5:
        return snap_fk_to_ik(setup, key=key)
    return snap_ik_to_fk(setup, key=key)
