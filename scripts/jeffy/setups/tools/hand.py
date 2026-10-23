"""Hand: fingers (or toes) with poses, master controls, metacarpals and IK fingers.

Give the wrist (the hand's parent joint) and the first joint of each finger
(the metacarpal when there is one). Per finger:

* FK controls on its joints (and its metacarpal),
* a **master** control that bends the whole finger,
* optional **IK** (``<finger>Ik`` on the hand control) with an IK tip control
  whose space can be the hand or the world, to keep a fingertip on a surface.

A **hand** control on the back of the hand holds the poses: ``curl``,
``spread``, ``fist``, ``relax``, ``cup`` and ``<finger>Curl``. Poses and
masters rotate the controls' ``ZRO`` (through its ``offsetParentMatrix``), so
the controls stay at zero and ``OFF`` stays free.
"""

from maya import cmds

from jeffy.core import attributes, mathlib, matrix, naming, nodes, transform
from jeffy.joints import tools as joint_tools
from jeffy.setups.core import scene
from jeffy.setups.core.base import Setup
from jeffy.setups.core.schema import JOINTS, SIZE_OPTION, Option, SetupError, Slot
from jeffy.setups.tools import common

METACARPALS = ("auto", "all", "all but thumb", "none")
POSES = ("curl", "spread", "fist", "relax", "cup")
DEGREES = 9.0  # a pose value of 10 bends a joint ~90 degrees


@scene.register
class Hand(Setup):
    TYPE = "hand"
    LABEL = "Hand / Fingers"
    CATEGORY = "build"
    ORDER = 45
    DESCRIPTION = ("Fingers (or toes): FK controls, a master control per finger, metacarpals, IK fingers for "
                   "contact, and a hand control with curl / spread / fist / relax / cup poses.")
    SLOTS = (
        Slot("wrist", "Wrist", tip="The hand's root joint (the wrist): the hand follows whatever drives it"),
        Slot("fingers", "Fingers", kind=JOINTS,
             tip="First joint of each finger, in order (thumb first when there is one). The metacarpal when the "
                 "finger has one."),
    )
    OPTIONS = (
        Option("metacarpals", "Metacarpals", "auto", choices=METACARPALS,
               tip="Which fingers start with a metacarpal. auto: chains of 5 joints or more (metacarpal, 3 "
                   "phalanges, tip)"),
        Option("thumb", "First finger is the thumb", True),
        Option("ik", "IK fingers", False, tip="IK on the first three phalanges of each finger (contact)"),
        Option("tip_controls", "Control on the tips", False, tip="Also a control on each finger's last joint"),
        Option("flip_curl", "Flip curl direction", False, tip="Use when the fingers curl the wrong way"),
        SIZE_OPTION,
    )

    @classmethod
    def default_name(cls, slots, options):
        return "hand"

    @classmethod
    def validate(cls, slots, options):
        wrist = slots["wrist"]
        for root in slots["fingers"]:
            if not scene.is_ancestor(wrist, root) or root == wrist:
                raise SetupError("%s is not below the wrist (%s)" % (root, wrist))
            if len(_chain(root)) < 2:
                raise SetupError("%s has no child joints" % root)

    @classmethod
    def driven_joints(cls, slots):
        joints = []
        for root in slots["fingers"]:
            joints.extend(_chain(root))
        return joints

    def attach_joint(self):
        return self.slot_node("wrist")

    # ------------------------------------------------------------------
    def build_setup(self):
        options = self.options
        wrist = self.slot_node("wrist")
        roots = self.slot_nodes("fingers")
        fingers = [self._finger_info(index, root) for index, root in enumerate(roots)]
        hand_length = max(mathlib.distance(common.position(wrist), common.position(info["joints"][-1]))
                          for info in fingers)
        size = hand_length * options["size"]
        palm = self._palm_normal(wrist, fingers)
        lateral = self._lateral(fingers)
        self._ik_blends = {}

        root_group = self.group("Root", parent=self.controls_group, match=wrist)
        self.add_anchor(root_group)
        back = mathlib.add(mathlib.centroid([common.position(f["phalanges"][0]) for f in fingers]),
                           mathlib.scale(palm, -hand_length * 0.25))
        hand = self.control("hand", self.name, shape="hand", size=size * 0.25, axis="y", parent=root_group,
                            world_matrix=_frame(back, common.world_matrix(wrist)), lock=("t", "r", "s", "v"),
                            secondary=True)
        attributes.add_separator(hand.node, "poses")
        poses = dict((pose, attributes.add_attr(hand.node, pose, "float", default=0.0)) for pose in POSES)
        attributes.add_separator(hand.node, "fingers")

        non_thumb = [f for f in fingers if not f["thumb"]]
        middle = mathlib.centroid([common.position(f["phalanges"][0]) for f in non_thumb]) if non_thumb else None
        spreads = [mathlib.dot(mathlib.sub(common.position(f["phalanges"][0]), middle), lateral)
                   if middle else 0.0 for f in fingers]
        reach = max([abs(value) for value in spreads] + [1e-6])

        for info in fingers:
            info["curl_toward"] = palm
            if info["thumb"]:
                centre = mathlib.midpoint(common.position(wrist), middle) if middle else None
                info["curl_toward"] = self._thumb_curl(info, palm, centre)
        for order, info in enumerate(fingers):
            rank = non_thumb.index(info) / float(max(len(non_thumb) - 1, 1)) if not info["thumb"] else 0.0
            finger_curl = attributes.add_attr(hand.node, info["label"] + "Curl", "float", default=0.0)
            ik_attr = attributes.add_attr(hand.node, info["label"] + "Ik", "float", default=0.0, minimum=0.0,
                                          maximum=1.0) if options["ik"] and len(info["phalanges"]) >= 4 else None
            self._build_finger(info, root_group, hand.node, size, palm, lateral, poses, finger_curl, ik_attr,
                               spread_weight=spreads[order] / reach, rank=rank)

    # ------------------------------------------------------------------
    def _finger_info(self, index, root):
        options = self.options
        joints = _chain(root)
        thumb = options["thumb"] and index == 0
        mode = options["metacarpals"]
        if mode == "auto":
            meta = len(joints) >= 5
        else:
            meta = mode == "all" or (mode == "all but thumb" and not thumb)
        meta = meta and len(joints) >= 3
        label = common.label(joints[1] if meta else joints[0]).rstrip("0123456789").rstrip("_") or "finger"
        return {"joints": joints, "meta": joints[0] if meta else None, "phalanges": joints[1:] if meta else joints,
                "thumb": thumb, "label": naming.legalize(label)}

    def _palm_normal(self, wrist, fingers):
        """Unit vector toward the palm (fingers curl toward it)."""
        bulge = (0.0, 0.0, 0.0)
        for info in [f for f in fingers if not f["thumb"]] or fingers:  # the thumb bends in its own plane
            chain = info["phalanges"]
            if len(chain) >= 3:
                points = [common.position(j) for j in chain[:3]]
                closest = mathlib.closest_point_on_line(points[1], points[0], points[2])
                bulge = mathlib.add(bulge, mathlib.sub(points[1], closest))  # knuckles stick out to the back
        size = sum(common.length(info["phalanges"][0], info["phalanges"][-1]) for info in fingers) / len(fingers)
        if mathlib.length(bulge) > size * 0.02:
            normal = mathlib.normalize(mathlib.scale(bulge, -1.0))
        else:
            first, last = fingers[1 if len(fingers) > 2 else 0], fingers[-1]
            wrist_point = common.position(wrist)
            normal = mathlib.normalize(mathlib.cross(mathlib.sub(common.position(first["phalanges"][0]), wrist_point),
                                                     mathlib.sub(common.position(last["phalanges"][0]), wrist_point)))
            if mathlib.dot(normal, (0.0, -1.0, 0.0)) < 0:  # T pose: palms face down
                normal = mathlib.scale(normal, -1.0)
        if self.option("flip_curl"):
            normal = mathlib.scale(normal, -1.0)
        return normal

    def _thumb_curl(self, info, palm, centre):
        """Where the thumb curls to: its own bend plane, else across the palm.

        The thumb sits turned about its bone compared with the other fingers,
        so the palm's normal would bend it sideways. Its own knuckle bulge
        (when the skeleton has it slightly bent) gives its real plane;
        a straight thumb curls toward the centre of the palm (between the
        wrist and the finger bases).
        """
        chain = info["phalanges"]
        points = [common.position(joint) for joint in chain[:3]]
        across = None
        if centre is not None:
            across = mathlib.sub(centre, points[0])
            bone = mathlib.normalize(mathlib.sub(points[-1], points[0]))
            across = mathlib.sub(across, mathlib.scale(bone, mathlib.dot(across, bone)))
            if mathlib.length(across) > 1e-6:
                across = mathlib.normalize(mathlib.add(mathlib.normalize(across), mathlib.scale(palm, 0.5)))
            else:
                across = None
        if len(points) >= 3:
            closest = mathlib.closest_point_on_line(points[1], points[0], points[2])
            bulge = mathlib.sub(points[1], closest)
            if mathlib.length(bulge) > mathlib.distance(points[0], points[2]) * 0.02:
                own = mathlib.normalize(mathlib.scale(bulge, -1.0))  # the knuckle sticks out to the back
                if self.option("flip_curl"):
                    own = mathlib.scale(own, -1.0)
                if across is None or mathlib.dot(own, across) > -0.2:  # trust it unless it bends away
                    return own
        return across or palm

    @staticmethod
    def _lateral(fingers):
        others = [f for f in fingers if not f["thumb"]] or fingers
        a, b = common.position(others[0]["phalanges"][0]), common.position(others[-1]["phalanges"][0])
        direction = mathlib.sub(b, a)
        return mathlib.normalize(direction) if mathlib.length(direction) > 1e-6 else (0.0, 0.0, 1.0)

    def _build_finger(self, info, root_group, hand, size, palm, lateral, poses, finger_curl, ik_attr, spread_weight,
                      rank):
        options = self.options
        label = info["label"]
        phalanges = info["phalanges"]
        count = len(phalanges) if options["tip_controls"] else max(len(phalanges) - 1, 1)
        parent = root_group
        meta_ctl = None
        if info["meta"]:
            meta = info["meta"]
            meta_ctl = self.control(label + "Meta", common.label(meta) + "FK", shape="square", size=size * 0.05,
                                    axis=common.bone_axis(meta).lstrip("-"), parent=parent, match=meta,
                                    lock=("t", "s", "v"), secondary=True)
            meta_ctl.set_parent_tag(hand)
            cup = _scaled_sum(self._n(label + "Cup", "UTL"), [(poses["cup"], DEGREES * 0.4 * rank)])
            axis, sign = _bend_axis(meta, phalanges[0], palm)
            plugs = [None, None, None]
            plugs[axis] = nodes.multiply(cup, sign, name=self._n(label + "CupSign", "MDL"))
            common.compose_zero(meta_ctl.zero, pre_rotate_plug=tuple(plugs))
            parent = meta_ctl.node

        master = self.control(label + "Master", label + "Master", shape="arrow", size=size * 0.06,
                              axis=common.bone_axis(phalanges[0]).lstrip("-"), parent=parent, match=phalanges[0],
                              lock=("t", "s", "v"), secondary=True)
        fk = []
        for index, joint in enumerate(phalanges[:count]):
            child = phalanges[index + 1] if index + 1 < len(phalanges) else None
            ctl = self.control("%sFk%d" % (label, index), common.label(joint) + "FK", shape="circle",
                               size=size * 0.04, axis=common.bone_axis(joint, child).lstrip("-"), parent=parent,
                               match=joint, lock=("t", "s", "v"))
            ctl.set_parent_tag(fk[-1].node if fk else (meta_ctl.node if meta_ctl else hand))
            fk.append(ctl)
            parent = ctl.node

        thumb = info["thumb"]
        fist_weight = 0.5 if thumb else 1.0
        relax_weight = 0.0 if thumb else 0.3 + 0.5 * rank
        for index, ctl in enumerate(fk):
            joint = phalanges[index]
            next_joint = phalanges[index + 1] if index + 1 < len(phalanges) else None
            axis, sign = _bend_axis(joint, next_joint, info["curl_toward"])
            bend = _scaled_sum(self._n("%sBend%d" % (label, index), "UTL"), [
                (poses["curl"], DEGREES), (finger_curl, DEGREES), (poses["fist"], DEGREES * fist_weight),
                (poses["relax"], DEGREES * relax_weight * (1.0 - 0.15 * index))])
            vector = [None, None, None]
            vector[axis] = nodes.multiply(bend, sign, name=self._n("%sBendSign%d" % (label, index), "MDL"))
            if index == 0 and abs(spread_weight) > 1e-3 and not thumb:
                spread_axis, spread_sign = _spread_axis(joint, next_joint, palm, lateral, spread_weight)
                if spread_axis != axis:
                    vector[spread_axis] = nodes.multiply(poses["spread"], DEGREES * 0.3 * spread_sign,
                                                         name=self._n("%sSpread" % label, "MDL"))
            total = cmds.createNode("plusMinusAverage", name=naming.unique_name(
                self._n("%sRot%d" % (label, index), "PMA")), skipSelect=True)
            cmds.connectAttr(master.node + ".rotate", total + ".input3D[0]")
            for axis_index, axis_name in enumerate("xyz"):
                if vector[axis_index]:
                    cmds.connectAttr(vector[axis_index], "%s.input3D[1].input3D%s" % (total, axis_name))
            common.compose_zero(ctl.zero, pre_rotate_plug=total + ".output3D",
                                rotate_order_plug=master.node + ".rotateOrder")

        for index, joint in enumerate(phalanges):
            if index < len(fk):
                plug = fk[index].node + ".worldMatrix[0]"
            else:
                tip = self.group(common.label(joint) + "Tip", parent=fk[-1].node, match=joint, visible=False)
                plug = tip + ".worldMatrix[0]"
            if ik_attr and index < 3:
                plug = self._ik_blend(label, index, plug, ik_attr)
            self.add_output("%s%d" % (label, index), plug, joint=joint, label=common.label(joint))
        if info["meta"]:
            self.add_output(label + "Meta", meta_ctl.node + ".worldMatrix[0]", joint=info["meta"],
                            label=common.label(info["meta"]))
        if ik_attr:
            self._ik_finger(label, phalanges, root_group, size, info["curl_toward"], ik_attr)

    # ------------------------------------------------------------------
    # IK fingers
    # ------------------------------------------------------------------
    def _ik_finger(self, label, phalanges, root_group, size, palm, ik_attr):
        """Hidden planar IK on the first three phalanges, tip control with hand / world space."""
        joints = phalanges[:3]
        points = [common.position(j) for j in joints]
        bend = _bend_direction_or(points, palm)
        normal = mathlib.normalize(mathlib.cross(mathlib.sub(points[1], points[0]), bend))
        system = self.group(label + "Ik", parent=self.systems_group, match=joints[0])
        follow_ref = self.group(label + "IkRoot", parent=root_group, match=joints[0], visible=False)
        local = cmds.createNode("multMatrix", name=naming.unique_name(system + "_follow_MM"), skipSelect=True)
        cmds.connectAttr(follow_ref + ".worldMatrix[0]", local + ".matrixIn[0]")
        cmds.connectAttr(matrix.parent_inverse_plug(system), local + ".matrixIn[1]")
        transform.reset(system)
        cmds.connectAttr(local + ".matrixSum", system + ".offsetParentMatrix", force=True)
        chain = []
        parent = system
        for joint, world in zip(joints, _planar(points, normal)):
            ik_joint = joint_tools.create_joint(naming.compose(common.label(joint) + "IK", self.side, "joint"),
                                                parent=parent, position=mathlib.get_translation(world))
            matrix.set_joint_orient_from_matrix(ik_joint, world)
            chain.append(ik_joint)
            parent = ik_joint
        cmds.setAttr(chain[1] + ".preferredAngleZ", 10.0)
        handle, effector = cmds.ikHandle(startJoint=chain[0], endEffector=chain[2], solver="ikRPsolver",
                                         name=naming.unique_name(self._n(label, "ik_handle")))
        cmds.rename(effector, naming.unique_name(self._n(label, "effector")))
        handle = cmds.parent(handle, system)[0]
        cmds.setAttr(handle + ".visibility", 0)
        ctl = self.control(label + "IkTip", label + "IK", shape="sphere", size=size * 0.035,
                           world_matrix=common.world_matrix(joints[2]), lock=("s", "v"))
        self.add_anchor(ctl.zero, ctl.node, kind="parent", spaces=("parent", "world", "root"), default="parent")
        cmds.connectAttr(ik_attr, ctl.zero + ".visibility")
        goal = nodes.decompose_matrix(ctl.node + ".worldMatrix[0]", name=self._n(label + "IkGoal", "DM"))
        handle_local = cmds.createNode("pointMatrixMult", name=naming.unique_name(self._n(label + "IkGoal", "UTL")),
                                       skipSelect=True)
        cmds.connectAttr(goal + ".outputTranslate", handle_local + ".inPoint")
        cmds.connectAttr(system + ".worldInverseMatrix[0]", handle_local + ".inMatrix")
        cmds.connectAttr(handle_local + ".output", handle + ".translate")
        pole = self.group(label + "IkPole", parent=follow_ref, visible=False)
        cmds.xform(pole, worldSpace=True, translation=mathlib.add(points[1], mathlib.scale(
            mathlib.scale(palm, -1.0), common.length(joints[0], joints[2]))))
        common.pole_vector(self.name + label[0].upper() + label[1:], self.side, handle, system, pole)
        for index, (joint, ik_joint) in enumerate(zip(joints, chain)):
            if index == 2:
                pose = common.blend_matrices(self._n(label + "IkEnd", "BM"), ctl.node + ".worldMatrix[0]",
                                             ik_joint + ".worldMatrix[0]", 1.0, rotate=0.0)
                pose = common.offset_plug(self._n(label + "IkEndRest", "MM"), pose, common.world_matrix(joint),
                                          common.plug_matrix(pose))
            else:
                pose = common.offset_plug(self._n("%sIkPose%d" % (label, index), "MM"),
                                          ik_joint + ".worldMatrix[0]", common.world_matrix(joint),
                                          common.world_matrix(ik_joint))
            cmds.connectAttr(pose, "%s.target[0].targetMatrix" % self._ik_blends[(label, index)], force=True)

    def _ik_blend(self, label, index, fk_plug, ik_attr):
        blend = cmds.createNode("blendMatrix", name=naming.unique_name(self._n("%sIkFk%d" % (label, index), "BM")),
                                skipSelect=True)
        cmds.connectAttr(fk_plug, blend + ".inputMatrix")
        cmds.connectAttr(ik_attr, blend + ".target[0].weight")
        self._ik_blends[(label, index)] = blend
        return blend + ".outputMatrix"

    def _n(self, label, suffix):
        return naming.compose(self.name + label[0].upper() + label[1:], self.side, suffix)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _chain(root):
    """``root`` and its first child joints down to the end."""
    result = [root]
    current = root
    while True:
        child = common.child_joint(current)
        if not child:
            return result
        result.append(child)
        current = child


def _frame(point, orientation):
    world = list(mathlib.orthonormalize(orientation))
    world[12:15] = point
    return world


def _scaled_sum(name, terms):
    """``sum(plug * weight)`` of ``(plug, weight)`` pairs (weight 0 skipped)."""
    total = cmds.createNode("plusMinusAverage", name=naming.unique_name(name + "_PMA"), skipSelect=True)
    index = 0
    for plug, weight in terms:
        if abs(weight) < 1e-9:
            continue
        cmds.connectAttr(nodes.multiply(plug, weight), "%s.input1D[%d]" % (total, index))
        index += 1
    return total + ".output1D"


def _bend_axis(joint, child, palm):
    """Local axis index and sign of ``joint`` that curls its bone toward the palm."""
    world = matrix.get_world_matrix(joint)
    if child:
        bone = mathlib.normalize(mathlib.sub(common.position(child), common.position(joint)))
    else:
        bone = mathlib.normalize(mathlib.axes(world)[0])
    wanted = mathlib.normalize(mathlib.cross(bone, palm))  # rotating about bone x palm moves the bone to the palm
    axes = [mathlib.normalize(axis) for axis in mathlib.axes(world)[:3]]
    index = max(range(3), key=lambda i: abs(mathlib.dot(axes[i], wanted)))
    return index, (1.0 if mathlib.dot(axes[index], wanted) >= 0 else -1.0)


def _spread_axis(joint, child, palm, lateral, weight):
    """Local axis index (around the palm normal) and signed weight spreading the finger away from the middle.

    ``weight`` is the finger's lateral offset from the middle (-1..1).
    """
    world = matrix.get_world_matrix(joint)
    axes = [mathlib.normalize(axis) for axis in mathlib.axes(world)[:3]]
    index = max(range(3), key=lambda i: abs(mathlib.dot(axes[i], palm)))
    bone = mathlib.normalize(mathlib.sub(common.position(child), common.position(joint))) if child else axes[0]
    moves = mathlib.cross(axes[index], bone)  # where a positive rotation around that axis moves the bone
    sign = 1.0 if mathlib.dot(moves, lateral) >= 0 else -1.0
    return index, sign * weight


def _bend_direction_or(points, palm):
    projected = mathlib.closest_point_on_line(points[1], points[0], points[2])
    direction = mathlib.sub(points[1], projected)
    if mathlib.length(direction) > 1e-4 * mathlib.distance(points[0], points[2]):
        return mathlib.normalize(direction)
    return mathlib.normalize(mathlib.scale(palm, -1.0))


def _planar(points, normal):
    aims = [mathlib.normalize(mathlib.sub(points[1], points[0])), mathlib.normalize(mathlib.sub(points[2],
                                                                                              points[1]))]
    aims.append(aims[1])
    result = []
    for point, aim in zip(points, aims):
        up = mathlib.normalize(mathlib.cross(normal, aim))
        result.append(mathlib.from_axes(aim, up, normal, point))
    return result
