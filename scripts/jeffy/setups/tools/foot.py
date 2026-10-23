"""Reverse Foot: a foot roll control and ground pivots on an IK/FK Limb (leg).

::

    L_legIK_CTL
      L_legFootRoll_ZRO > OFF > CTL        rotateX roll, rotateZ bank, rotateY ball twist
      L_legHeelPivot   ZRO > OFF > CTL      ground pivots you can grab (pivotsVis)
        L_legToePivot
          L_legOuterPivot
            L_legInnerPivot
              L_legBallPivot
                ankle (the limb's IK end moves here)
              L_legToeTap                  toe tap / FK-like toe in IK

Roll (rotateX of the roll control): negative rolls on the heel; positive
rolls on the ball up to ``rollBreak`` degrees, then on the toe tip; past
``rollStraight`` the ball straightens back. Bank (rotateZ): positive rolls on
the outer edge, negative on the inner edge. Attributes: ``heelTwist``,
``toeTwist``, ``toeTap``, ``rollBreak``, ``rollStraight``, ``pivotsVis``.

The ball joint is driven too: by the toe tap pivot in IK and by an FK toe
control (under the limb's FK end control) in FK. IK/FK snapping and auto-snap
include the foot.
"""

from maya import cmds

from jeffy.core import attributes, mathlib, matrix, naming, nodes
from jeffy.setups.core import controls, scene
from jeffy.setups.core import guides as guides_module
from jeffy.setups.core import tag as tag_module
from jeffy.setups.core.base import Setup
from jeffy.setups.core.schema import NODE, SIZE_OPTION, Option, SetupError, Slot
from jeffy.setups.tools import common

GUIDE_KEYS = ("heel", "toe", "inner", "outer", "roll")
PIVOTS = ("heel", "toe", "outer", "inner", "ball")
ROLL_ATTRS = ("heelTwist", "toeTwist", "toeTap")


@scene.register
class ReverseFoot(Setup):
    TYPE = "reverse_foot"
    LABEL = "Reverse Foot"
    CATEGORY = "layer"
    ORDER = 80
    DESCRIPTION = ("Foot roll on an IK/FK Limb (leg): a roll control (X roll, Z bank, Y ball twist) and ground "
                   "pivots you can grab (heel, toe, inner, outer, ball, toe tap). Drives the ball joint in IK and "
                   "FK. Preview to place the heel, toe, bank and roll guides.")
    SLOTS = (
        Slot("base", "Leg", kind=NODE, tip="Any control of the leg's IK/FK Limb"),
        Slot("ball", "Ball", tip="Ball joint (a child of the limb's end joint)"),
        Slot("toe", "Toe tip", optional=True, tip="Toe end joint (empty: the ball's child joint)"),
    )
    OPTIONS = (
        Option("roll_break", "Roll break", 30.0, minimum=1.0, maximum=170.0,
               tip="Roll angle where the foot leaves the ball for the toe tip (rollBreak)"),
        Option("roll_straight", "Roll straight", 60.0, minimum=2.0, maximum=180.0,
               tip="Roll angle where the ball is straight again (rollStraight)"),
        Option("pivots", "Ground pivot controls", True, tip="Grabbable heel / toe / bank / ball / toe tap controls"),
        SIZE_OPTION,
    )
    GUIDES = GUIDE_KEYS
    BASE_TYPES = ("ikfk_limb",)

    # ------------------------------------------------------------------
    @classmethod
    def resolve_name_side(cls, slots, options, name=None, side=None):
        base = cls.find_base(slots)
        name = naming.legalize(str(name or (base.name + "Foot")).strip()).strip("_")
        return name, (side if side and side != "auto" else base.side)

    @classmethod
    def validate(cls, slots, options):
        base = cls.find_base(slots)
        ankle = base.slot_node("end")
        if not common.is_child(ankle, slots["ball"]):
            raise SetupError("Ball (%s) must be a child of the leg's end joint (%s)" % (slots["ball"], ankle))
        if slots.get("toe") and not common.is_child(slots["ball"], slots["toe"]):
            raise SetupError("Toe tip (%s) must be a child of Ball (%s)" % (slots["toe"], slots["ball"]))
        if options["roll_straight"] <= options["roll_break"]:
            raise SetupError("Roll straight must be bigger than roll break")
        for layer in base.layers():
            if layer.TYPE == cls.TYPE:
                raise SetupError("%s already has %s" % (base.describe(), layer.describe()))

    @classmethod
    def driven_joints(cls, slots):
        return [slots["ball"]]

    @classmethod
    def rig_lookup_node(cls, slots):
        return slots.get("base")

    @classmethod
    def default_guides(cls, slots, options, side):
        base = cls.find_base(slots)
        ankle = common.position(base.slot_node("end"))
        ball = common.position(slots["ball"])
        toe = _toe_point(slots, ankle, ball)
        frame = _foot_frame(ankle, toe)
        forward, sideways = frame["forward"], frame["side"]
        ground = toe[1]
        length = mathlib.distance(ankle, ball)
        heel = mathlib.sub((ankle[0], ground, ankle[2]), mathlib.scale(forward, length * 0.3))
        outer_sign = 1.0 if ankle[0] >= 0 else -1.0
        ball_ground = (ball[0], ground, ball[2])
        width = length * 0.45
        outer = mathlib.add(ball_ground, mathlib.scale(sideways, width * outer_sign))
        inner = mathlib.add(ball_ground, mathlib.scale(sideways, -width * outer_sign))
        roll = mathlib.add(mathlib.sub(heel, mathlib.scale(forward, length * 0.45)), (0.0, length * 0.2, 0.0))
        return {"heel": heel, "toe": (toe[0], ground, toe[2]), "inner": inner, "outer": outer, "roll": roll}

    @classmethod
    def guide_size(cls, slots, options):
        base = cls.find_base(slots)
        return common.length(base.slot_node("end"), slots["ball"]) * 0.12

    @classmethod
    def create(cls, *args, **kwargs):
        setup = super(ReverseFoot, cls).create(*args, **kwargs)
        from jeffy.setups.tools import ikfk_limb

        ikfk_limb.install_auto_snap()  # watch the roll / FK toe ikFk proxies too
        return setup

    # ------------------------------------------------------------------
    def build_setup(self):
        options = self.options
        base = self.base
        ctls = base.controls
        ik_ctl, settings = ctls["ik"], ctls["settings"]
        ankle_joint, ball_joint = base.slot_node("end"), self.slot_node("ball")
        guides = dict((key, guides_module.position(value)) for key, value in self.guides.items())
        ankle = common.position(ankle_joint)
        frame = _foot_frame(ankle, guides["toe"])
        length = mathlib.distance(guides["heel"], guides["toe"])
        size = length * options["size"]

        def frame_at(point):
            return mathlib.from_axes(frame["side"], frame["up"], frame["forward"], point)

        # roll control
        prefix = base.name
        roll = self.control("roll", prefix + "FootRoll", shape="circle_arrows", size=size * 0.18, axis="y",
                            parent=ik_ctl, world_matrix=frame_at(guides["roll"]), lock=("t", "s", "v"))
        roll_ctl = roll.node
        attributes.add_separator(roll_ctl, "foot")
        roll_break = attributes.add_attr(roll_ctl, "rollBreak", "float", default=options["roll_break"], minimum=0.0)
        roll_straight = attributes.add_attr(roll_ctl, "rollStraight", "float", default=options["roll_straight"],
                                            minimum=0.0)
        for attr in ROLL_ATTRS:
            attributes.add_attr(roll_ctl, attr, "float", default=0.0)
        pivots_vis = attributes.add_attr(roll_ctl, "pivotsVis", "bool", default=True, keyable=False,
                                         channel_box=True)
        cmds.setAttr(pivots_vis, True)
        attributes.add_proxy("%s.ikFk" % settings, roll_ctl)

        # roll network (degrees)
        value = roll_ctl + ".rotateX"
        heel_roll = nodes.minimum(value, 0.0, name=self._n("HeelRoll", "COND"))
        forward_roll = nodes.maximum(value, 0.0, name=self._n("ForwardRoll", "COND"))
        linear = nodes.clamp(value, 0.0, roll_break, name=self._n("BallLinear", "CLP"))
        straight = nodes.remap(value, roll_break, roll_straight, 0.0, 1.0, name=self._n("BallStraight", "RMV"))
        ball_roll = nodes.multiply(linear, nodes.reverse(straight, name=self._n("BallStraight", "REV")),
                                   name=self._n("BallRoll", "MDL"))
        toe_roll = nodes.subtract(forward_roll, ball_roll, name=self._n("ToeRoll", "PMA"))
        bank = roll_ctl + ".rotateZ"
        out_bank = nodes.maximum(bank, 0.0, name=self._n("OuterBank", "COND"))
        in_bank = nodes.maximum(nodes.negate(bank, name=self._n("InnerBankNeg", "MDL")), 0.0,
                                name=self._n("InnerBank", "COND"))
        # a positive Z rotation lifts the +X side: pick the sign so each edge rolls the foot onto itself
        outer_sign = -1.0 if mathlib.dot(mathlib.sub(guides["outer"], guides["inner"]), frame["side"]) > 0 else 1.0
        auto = {
            "heel": (heel_roll, roll_ctl + ".heelTwist", None),
            "toe": (toe_roll, roll_ctl + ".toeTwist", None),
            "outer": (None, None, nodes.multiply(out_bank, outer_sign, name=self._n("OuterBankSign", "MDL"))),
            "inner": (None, None, nodes.multiply(in_bank, -outer_sign, name=self._n("InnerBankSign", "MDL"))),
            "ball": (ball_roll, roll_ctl + ".rotateY", None),
        }
        points = {"heel": guides["heel"], "toe": guides["toe"], "outer": guides["outer"], "inner": guides["inner"],
                  "ball": common.position(ball_joint)}

        parent = ik_ctl
        pivots = {}
        for key in PIVOTS:
            node = self._pivot(key, parent, frame_at(points[key]), size, options["pivots"], pivots_vis, prefix)
            pivots[key] = node
            parent = node["node"]
        for key in PIVOTS:
            common.compose_zero(pivots[key]["zero"], pre_rotate_plug=auto[key])

        # ankle: the limb's IK end follows the ball pivot
        end_ref = tag_module.get_node(base.tag, "ik_end_ref") or \
            naming.compose(base.name + "IkEnd", base.side, "group")
        ankle_group = self.group("Ankle", parent=pivots["ball"]["node"], world_matrix=frame_at(ankle),
                                 visible=False)
        tag_module.set_node(self.tag, "end_ref", end_ref)
        tag_module.set_data(self.tag, "end_ref_local", list(cmds.getAttr(end_ref + ".matrix")))
        cmds.parent(end_ref, ankle_group)

        # toe tap + IK ball pose
        tap = self._pivot("tap", pivots["inner"]["node"], frame_at(points["ball"]), size, options["pivots"],
                          pivots_vis, prefix, label="ToeTap")
        tap_value = nodes.negate(roll_ctl + ".toeTap", name=self._n("ToeTap", "MDL"))
        common.compose_zero(tap["zero"], pre_rotate_plug=(tap_value, None, None))
        ik_ball = self.group("IkBall", parent=tap["node"], match=ball_joint, visible=False)

        # FK toe under the limb's FK end control
        fk_end = ctls["fk2"]
        fk_ball = self.control("fkBall", common.label(ball_joint) + "FK", shape="circle", size=size * 0.12,
                               axis=common.bone_axis(ball_joint).lstrip("-"), parent=fk_end, match=ball_joint,
                               lock=("t", "s", "v"))
        fk_ball.set_parent_tag(fk_end)
        attributes.add_proxy("%s.ikFk" % settings, fk_ball.node)

        blend = cmds.createNode("blendMatrix", name=naming.unique_name(self._n("BallIkFk", "BM")), skipSelect=True)
        cmds.connectAttr(fk_ball.node + ".worldMatrix[0]", blend + ".inputMatrix")
        cmds.connectAttr(ik_ball + ".worldMatrix[0]", blend + ".target[0].targetMatrix")
        cmds.connectAttr("%s.ikFk" % settings, blend + ".target[0].weight")
        self.add_output("ball", blend + ".outputMatrix", joint=ball_joint, label=common.label(ball_joint))
        tag_module.set_node(self.tag, "ik_ball", ik_ball)
        tag_module.set_nodes(self.tag, "pivot_controls", [pivots[key]["node"] for key in PIVOTS] + [tap["node"]])

    # ------------------------------------------------------------------
    def _n(self, label, suffix):
        return naming.compose(self.name + label, self.side, suffix)

    def _pivot(self, key, parent, world, size, as_control, visibility, prefix, label=None):
        """A pivot: a ground control (``ZRO > OFF > CTL``) or a plain group."""
        label = prefix + (label or (key[0].upper() + key[1:] + "Pivot"))
        if as_control:
            ctl = self.control(key, label, shape="sphere", size=size * 0.035, axis="y", parent=parent,
                               world_matrix=world, lock=("t", "s", "v"), secondary=True)
            for shape in cmds.listRelatives(ctl.node, shapes=True, fullPath=True) or []:
                cmds.connectAttr(visibility, shape + ".visibility")
            return {"zero": ctl.zero, "node": ctl.node}
        zero = self.group(label + "Zero", parent=parent, world_matrix=world)
        node = self.group(label, parent=zero)
        return {"zero": zero, "node": node}

    def before_delete(self):
        end_ref = tag_module.get_node(self.tag, "end_ref")
        base = self.base
        if not end_ref or base is None or not cmds.objExists(base.tag):
            return
        ik_ctl = base.controls.get("ik")
        if ik_ctl and cmds.objExists(ik_ctl):
            end_ref = cmds.parent(end_ref, ik_ctl, relative=True)[0]
            local = tag_module.get_data(self.tag, "end_ref_local")
            if local:
                matrix.set_world_matrix(end_ref, mathlib.mult(local, cmds.getAttr(ik_ctl + ".worldMatrix[0]")),
                                        scale=False)

    # ------------------------------------------------------------------
    # IK/FK snapping (called by the limb)
    # ------------------------------------------------------------------
    def reset_ik(self, limb):
        """Zero the roll control and the pivots before the IK control snaps onto FK."""
        roll = self.controls.get("roll")
        touched = []
        if roll:
            for attr in ("rotateX", "rotateY", "rotateZ") + ROLL_ATTRS:
                if attributes.is_settable(roll, attr):
                    cmds.setAttr("%s.%s" % (roll, attr), 0.0)
            touched.append(roll)
        for node in tag_module.get_nodes(self.tag, "pivot_controls"):
            if controls.key_of(node):  # a control (pivots can be plain groups)
                for attr in ("rotateX", "rotateY", "rotateZ"):
                    if attributes.is_settable(node, attr):
                        cmds.setAttr("%s.%s" % (node, attr), 0.0)
                touched.append(node)
        return touched

    def snap_fk_to_ik(self, limb):
        """FK toe onto the IK ball."""
        fk_ball = self.controls.get("fkBall")
        ik_ball = tag_module.get_node(self.tag, "ik_ball")
        if fk_ball and ik_ball:
            matrix.set_world_matrix(fk_ball, matrix.get_world_matrix(ik_ball), translate=False, scale=False)
            return [fk_ball]
        return []

    def snap_ik_to_fk(self, limb):
        """Toe tap so the IK ball matches the FK toe."""
        roll = self.controls.get("roll")
        fk_ball = self.controls.get("fkBall")
        ik_ball = tag_module.get_node(self.tag, "ik_ball")
        if not (roll and fk_ball and ik_ball) or not attributes.is_settable(roll, "toeTap"):
            return []
        target = mathlib.normalize(mathlib.axes(matrix.get_world_matrix(fk_ball))[0])
        plug = roll + ".toeTap"

        def error(angle):
            cmds.setAttr(plug, angle)
            return 1.0 - mathlib.dot(mathlib.normalize(mathlib.axes(matrix.get_world_matrix(ik_ball))[0]), target)

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
        return [roll]


def _toe_point(slots, ankle, ball):
    toe = slots.get("toe") or common.child_joint(slots["ball"])
    if toe:
        return common.position(toe)
    forward = mathlib.sub(ball, ankle)
    return mathlib.add(ball, mathlib.scale((forward[0], 0.0, forward[2]), 0.5))


def _foot_frame(ankle, toe):
    """Foot axes: forward (ankle -> toe on the ground), up (world Y), side."""
    forward = mathlib.sub(toe, ankle)
    forward = (forward[0], 0.0, forward[2])
    if mathlib.length(forward) < 1e-6:
        forward = (0.0, 0.0, 1.0)
    forward = mathlib.normalize(forward)
    up = (0.0, 1.0, 0.0)
    side = mathlib.normalize(mathlib.cross(up, forward))
    return {"forward": forward, "up": up, "side": side}
