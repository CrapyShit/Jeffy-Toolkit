"""Edge Ribbon: a ribbon on a mesh edge loop that rides the mesh's blendShape (lips, brows, cheeks).

Select an edge loop (all around the lips) or an edge chain (a brow) and the
setup it follows (the Jaw / Hinge for lips, the head's setup otherwise):

* controls along the loop **follow the blendShape result**, and the animator
  can still move them on top,
* their own **bind joints** ride a ribbon driven by the controls,
* with a Jaw setup, each control has ``jawFollow`` (upper lip 0, corners 0.5,
  lower lip 1 by default),
* a **master** control moves (rotates, scales) every control at once; its
  curve outline follows the lips' shape live.

No double transformation
------------------------
The skin must not move the vertices the blendShape already moved. A second,
hidden *base* ribbon only follows the blendShape (no controls, no jaw, no
head). Each bind joint's ``skinCluster.bindPreMatrix`` is the inverse of its
point on the base ribbon, so the skin only adds what the controls, the jaw
and the head did. Skin the mesh yourself, then run
:meth:`EdgeRibbon.connect_skin` (the *Connect skin* button of the Setups list).

Game safe: engines don't read live bindPreMatrix connections, so each bind
joint carries the offset instead: ``rest * inverse(base) * driven``, under
the head (or jaw parent) bind joint. The skin gets the same result with a
normal bind; the joints sit at their rest spot plus the controls' offset.

Deformer order: the blendShape must come before the skinCluster (the controls
read the blendShape's output, before the skin, so there is no cycle). When
the mesh has no blendShape, an empty one is created at the front of its
deformers; add targets to it whenever.
"""

from maya import cmds
from maya.api import OpenMaya as om
from maya.api import OpenMayaAnim as oma

from jeffy.core import attributes, mathlib, matrix, naming, nodes, transform
from jeffy.joints import tools as joint_tools
from jeffy.setups.core import attach, controls, scene
from jeffy.setups.core import edges as edge_tools
from jeffy.setups.core import tag as tag_module
from jeffy.setups.core.base import Setup
from jeffy.setups.core.schema import EDGES, NODE, SIZE_OPTION, Option, SetupError, Slot
from jeffy.setups.tools import common

#: skin weights of deleted Edge Ribbons, put back by the next build of the same name / side (rebuild)
_STASH = {}
#: R side controls: X points outward (-X), Y up, so both sides move the same way
_RIGHT_FRAME = mathlib.from_axes((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, -1.0))
OUTLINE_SCALE = 1.3
#: shapes offered for the ribbon controls (names from the control shape library)
CONTROL_SHAPES = ("sphere", "circle", "cube", "diamond", "octahedron", "square", "locator")


@scene.register
class EdgeRibbon(Setup):
    TYPE = "edge_ribbon"
    LABEL = "Edge Ribbon"
    CATEGORY = "layer"
    ORDER = 95
    DESCRIPTION = ("A ribbon on a mesh edge loop (lips, brows, cheeks): its controls follow the mesh's blendShape "
                   "and you can still move them, with no double transformation. Own bind joints, jaw follow on a "
                   "Jaw setup, and a master control whose outline follows the lips.")
    SLOTS = (
        Slot("base", "Setup", kind=NODE, tip="Any control of the setup it follows: the Jaw / Hinge for lips, the "
                                             "head's setup for brows or cheeks"),
        Slot("edges", "Edges", kind=EDGES, tip="A closed edge loop (all around the lips) or an open edge chain, on "
                                               "one mesh"),
        Slot("blendshape", "BlendShape", kind=NODE, optional=True,
             tip="The blendShape to follow (default: the first one on the mesh; an empty one is created when the "
                 "mesh has none)"),
    )
    OPTIONS = (
        Option("control_count", "Controls", 8, minimum=2, maximum=40,
               tip="Controls along the loop. On a closed loop with an even count, both corners get one."),
        Option("joint_count", "Bind joints", 20, minimum=2, maximum=200),
        Option("control_shape", "Control shape", "sphere", choices=CONTROL_SHAPES,
               tip="Shape of the ribbon controls (the master keeps its outline)"),
        Option("width", "Ribbon width", 0.0, minimum=0.0, maximum=1000.0, step=0.1,
               tip="0 = automatic (4% of the loop length)"),
        Option("master", "Master control", True,
               tip="A control that moves every control at once; its outline follows the lips' shape"),
        Option("upper_follow", "Upper jaw follow", 0.0, minimum=0.0, maximum=1.0,
               tip="Default jawFollow of the upper lip controls (Jaw setup only)"),
        Option("corner_follow", "Corner jaw follow", 0.5, minimum=0.0, maximum=1.0,
               tip="Default jawFollow of the corner controls (Jaw setup only)"),
        Option("lower_follow", "Lower jaw follow", 1.0, minimum=0.0, maximum=1.0,
               tip="Default jawFollow of the lower lip controls (Jaw setup only)"),
        SIZE_OPTION,
        Option("game_safe", "Game safe", False,
               tip="On: the bind joints carry only the controls' offset (no live bindPreMatrix), under the head "
                   "bind joint - safe for Unreal / Unity.\n"
                   "Off: the bind joints ride the lips; Connect skin wires bindPreMatrix."),
    )

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------
    @classmethod
    def resolve_name_side(cls, slots, options, name=None, side=None):
        base = cls.find_base(slots)
        if not name:
            name = "lips" if base.TYPE == "jaw" else "edgeRibbon"
        name = naming.legalize(str(name).strip()).strip("_")
        if not name:
            raise SetupError("Give the setup a name")
        if not side or side == "auto":
            side = edge_tools.side_of(slots["edges"])
        return name, side

    @classmethod
    def validate(cls, slots, options):
        cls.find_base(slots)
        _ids, points, closed = edge_tools.ordered_loop(slots["edges"])
        if closed and options["control_count"] < 4:
            raise SetupError("A closed loop needs 4 controls or more")
        if len(points) < 3:
            raise SetupError("Select at least 2 connected edges")
        _mesh, shape = edge_tools.mesh_of(slots["edges"])
        blend = slots.get("blendshape")
        if blend:
            if cmds.nodeType(blend) != "blendShape":
                raise SetupError("%s is not a blendShape" % blend)
            _geometry_index(blend, shape)
            _check_order(shape, blend)
        else:
            existing = _blendshapes(shape)
            if existing:
                _check_order(shape, existing[-1])

    @classmethod
    def rig_lookup_node(cls, slots):
        return slots.get("base")

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def build_setup(self):
        options = self.options
        base = self.base
        edges = self.slot_nodes("edges")
        mesh, shape = edge_tools.mesh_of(edges)
        _ids, points, closed = edge_tools.ordered_loop(edges)
        blend = self._blendshape(shape)
        index = _geometry_index(blend, shape)
        game_safe = options["game_safe"]

        world = self.group("World")
        cmds.setAttr(world + ".inheritsTransform", 0)
        hidden = self.group("NoTouch", parent=world, visible=False)

        info_curve = _curve_through(points, closed, naming.compose(self.name + "Loop", self.side, "crv"),
                                    max(len(points) - (0 if closed else 1), 4))
        info = _CurveInfo(info_curve, closed)
        mesh_fn = om.MFnMesh(_dag_path(shape))
        length = info.length
        size = length * 0.025 * options["size"]
        eps = length * 0.01
        anchor = info.length_at_point(min(points, key=lambda p: p[0])) if closed else None
        control_stops = info.distribute(options["control_count"], anchor)
        joint_stops = info.distribute(options["joint_count"], anchor)
        control_points = [info.point_at_length(s) for s in control_stops]
        corners = _corner_indices(control_stops, anchor, closed)

        # what the setup follows
        head, jaw = self._follow_outputs(base, mathlib.centroid(points))
        head_world = head + ".worldMatrix[0]"
        head_rest = controls.rest_matrix(head)
        mesh_world = matrix.get_world_matrix(mesh)
        jaw_space = self._jaw_space(head_rest, jaw) if jaw else None

        # blendShape follow pins (the blendShape output, before the skin)
        pin = cmds.createNode("proximityPin", name=naming.unique_name(self._n("Follow", "proximityPin")),
                              skipSelect=True)
        cmds.connectAttr("%s.outputGeometry[%d]" % (blend, index), pin + ".deformedGeometry")
        cmds.connectAttr(_original_geometry(blend, index, shape), pin + ".originalGeometry")
        tag_module.set_node(self.tag, "pin", pin)

        # master control
        master = None
        local_plug = None
        master_rest = None
        if options["master"]:
            master_rest = self._frame(mathlib.centroid(points), self.side)
            master = self.control("master", self.name + "Master", shape="circle", size=size * 4.0, axis="z",
                                  world_matrix=master_rest, lock=("v",))
            self.follow(master.zero, head)
            offset = cmds.listRelatives(master.node, parent=True)[0]
            local_plug = nodes.mult_matrix([master.node + ".matrix", offset + ".matrix"],
                                           name=self._n("MasterLocal", "MM"))

        labels = _labels(control_points, corners, closed, eps, self.side)
        ctls, drivers, bases, follows = [], [], [], []
        for i, (point, (label, ctl_side, role)) in enumerate(zip(control_points, labels)):
            label = self.name + label
            rest = self._frame(point, ctl_side)
            cmds.setAttr("%s.inputMatrix[%d]" % (pin, i), mathlib.mult(rest, mathlib.inverse(mesh_world)),
                         type="matrix")
            pin_plug = "%s.outputMatrix[%d]" % (pin, i)
            ctl = self.control("c%02d" % i, label, shape=options["control_shape"], size=size, axis="z",
                               world_matrix=rest,
                               lock=("s", "v"), secondary=True, side=ctl_side)
            if master is not None:
                ctl.set_parent_tag(master.node)
            follow = head_world
            if jaw_space:
                default = {"corner": options["corner_follow"], "upper": options["upper_follow"],
                           "lower": options["lower_follow"]}[role]
                weight = attributes.add_attr(ctl.node, "jawFollow", "float", default=default, minimum=0.0,
                                             maximum=1.0)
                cmds.setAttr(weight, default)
                follow = common.blend_matrices(naming.compose(label + "JawFollow", ctl_side, "BM"), head_world,
                                               jaw_space, weight)
            follows.append(follow)
            # ZRO = blendShape pose (rest world) [* master, around its pivot] * head / jaw motion
            inputs = [pin_plug]
            if local_plug:
                inputs += [mathlib.mult(mesh_world, mathlib.inverse(master_rest)), local_plug,
                           mathlib.mult(master_rest, mathlib.inverse(head_rest))]
            else:
                inputs += [mathlib.mult(mesh_world, mathlib.inverse(head_rest))]
            inputs += [follow, matrix.parent_inverse_plug(ctl.zero)]
            zero_mm = _mult(naming.compose(label + "Follow", ctl_side, "MM"), inputs)
            transform.reset(ctl.zero)
            cmds.connectAttr(zero_mm, ctl.zero + ".offsetParentMatrix", force=True)

            driver = joint_tools.create_joint(naming.compose(label + "Drv", ctl_side, "joint"), parent=ctl.node)
            base_joint = joint_tools.create_joint(naming.compose(label + "Base", ctl_side, "joint"), parent=hidden)
            cmds.connectAttr(_mult(naming.compose(label + "Base", ctl_side, "MM"), [pin_plug, mesh_world]),
                             base_joint + ".offsetParentMatrix")
            for joint in (driver, base_joint):
                cmds.setAttr(joint + ".visibility", 0)
            ctls.append(ctl)
            drivers.append(driver)
            bases.append(base_joint)

        if master is not None:
            self._outline(master, pin, follows, mesh_world, head, head_rest, master_rest, closed)

        # the ribbons: driven (controls) and base (blendShape only)
        width = options["width"] or length * 0.04
        spans = max(options["control_count"] * 3, options["joint_count"])
        ribbon = _build_ribbon(info, mesh_fn, width, spans, naming.compose(self.name + "Ribbon", self.side, "surface"))
        ribbon_base = cmds.duplicate(ribbon, name=naming.unique_name(naming.compose(self.name + "RibbonBase",
                                                                                    self.side, "surface")))[0]
        for surface in (ribbon, ribbon_base):
            cmds.parent(surface, hidden)
        ribbon = cmds.ls(ribbon)[0]
        ribbon_base = cmds.ls(ribbon_base)[0]
        _skin_ribbon(ribbon, drivers, control_stops, info, self._n("Ribbon", "skinCluster"))
        _skin_ribbon(ribbon_base, bases, control_stops, info, self._n("RibbonBase", "skinCluster"))
        pins = {}
        for key, surface in (("drv", ribbon), ("base", ribbon_base)):
            uv_pin = cmds.createNode("uvPin", name=naming.unique_name(self._n(key.title() + "Ribbon", "uvPin")),
                                     skipSelect=True)
            surface_shape = cmds.listRelatives(surface, shapes=True, noIntermediate=True, fullPath=True)[0]
            cmds.connectAttr(surface_shape + ".worldSpace[0]", uv_pin + ".deformedGeometry")
            cmds.setAttr(uv_pin + ".normalizedIsoParms", 1)
            pins[key] = uv_pin

        # bind joints
        joint_points = [info.point_at_length(s) for s in joint_stops]
        joint_labels = _labels(joint_points, _corner_indices(joint_stops, anchor, closed), closed, eps, self.side)
        parent_joint = self._parent_joint(base, head) if game_safe else None
        group = None
        if not game_safe:
            rig = self.rig
            group = self.group("Joints", parent=rig.rig_group("skeleton") if rig is not None else None)
        radius = size * 0.3
        binds, pre = [], []
        for k, (point, (label, joint_side, _role)) in enumerate(zip(joint_points, joint_labels)):
            label = self.name + label
            u, _v = _surface_uv(ribbon, point)
            for uv_pin in pins.values():
                cmds.setAttr("%s.coordinate[%d].coordinateU" % (uv_pin, k), u)
                cmds.setAttr("%s.coordinate[%d].coordinateV" % (uv_pin, k), 0.5)
            driven_plug = "%s.outputMatrix[%d]" % (pins["drv"], k)
            base_plug = "%s.outputMatrix[%d]" % (pins["base"], k)
            pin_rest = mathlib.orthonormalize(common.plug_matrix(driven_plug))
            joint_rest = self._frame(mathlib.get_translation(pin_rest), joint_side)
            joint = joint_tools.create_joint(naming.compose(label, joint_side, "joint"),
                                             parent=parent_joint or group,
                                             position=mathlib.get_translation(joint_rest), radius=radius)
            matrix.set_joint_orient_from_matrix(joint, joint_rest)
            driven = common.offset_plug(naming.compose(label + "Driven", joint_side, "MM"), driven_plug, joint_rest,
                                        common.plug_matrix(driven_plug))
            based = common.offset_plug(naming.compose(label + "BindBase", joint_side, "MM"), base_plug, joint_rest,
                                       common.plug_matrix(base_plug))
            inverse = nodes.inverse_matrix(based, name=naming.compose(label + "BindPre", joint_side, "UTL"))
            if game_safe:  # rest * inverse(base) * driven: only the offset, no live bindPreMatrix
                driven = _mult(naming.compose(label + "Offset", joint_side, "MM"), [joint_rest, inverse, driven])
            self.add_output("b%02d" % k, driven, joint=joint, label=label)
            binds.append(joint)
            pre.append(inverse.split(".")[0])
        tag_module.set_nodes(self.tag, "bind_joints", binds)
        tag_module.set_nodes(self.tag, "bind_pre", pre)
        cmds.delete(info_curve)
        cmds.select(clear=True)
        self._restore_skin()

    def _n(self, label, suffix):
        return naming.compose(self.name + label, self.side, suffix)

    @staticmethod
    def _frame(point, side):
        frame = _RIGHT_FRAME if side == naming.SIDE_RIGHT else mathlib.identity()
        return mathlib.set_translation(list(frame), point)

    def _blendshape(self, shape):
        """The blendShape to follow: the slot's, the mesh's first one, or a new empty one (kept on delete)."""
        blend = self.slot_node("blendshape")
        if blend:
            return blend
        existing = _blendshapes(shape)
        if existing:
            return existing[-1]  # the first one applied
        before = set(cmds.ls(uuid=True) or [])
        blend = cmds.blendShape(shape, frontOfChain=True, name=naming.unique_name(self._n("Follow", "BS")))[0]
        created = [uuid for uuid in (cmds.ls(uuid=True) or []) if uuid not in before]
        self.keep(cmds.ls(created) or [])
        tag_module.set_node(self.tag, "created_blendshape", blend)
        return blend

    @staticmethod
    def _follow_outputs(base, centre):
        """``(head output, jaw output or None)``."""
        if base.TYPE == "jaw":
            head = attach.parent_target(base)
            return head, base.outputs.get("jaw")
        outputs = list(base.outputs.values())
        if outputs:
            return min(outputs, key=lambda node: mathlib.distance(
                mathlib.get_translation(controls.rest_matrix(node)), centre)), None
        head = attach.parent_target(base)
        if not head:
            raise SetupError("%s has nothing to follow" % base.describe())
        return head, None

    def _jaw_space(self, head_rest, jaw):
        """The head's rest pose carried by the jaw (equals the head's rest when the jaw is closed)."""
        return _mult(self._n("JawSpace", "MM"), [mathlib.mult(head_rest, mathlib.inverse(
            controls.rest_matrix(jaw))), jaw + ".worldMatrix[0]"])

    @staticmethod
    def _parent_joint(base, head):
        """Game safe: the bind joint the ribbon joints go under (the head)."""
        if base.TYPE == "jaw":
            jaw = base.slot_node("jaw")
            parent = cmds.listRelatives(jaw, parent=True, type="joint") if jaw else None
            if parent:
                return parent[0]
        found = cmds.listConnections("%s.%s" % (head, scene.OUTPUT_JOINT_ATTR), source=True,
                                     destination=False) if cmds.attributeQuery(scene.OUTPUT_JOINT_ATTR, node=head,
                                                                               exists=True) else None
        if found:
            return found[0]
        joints = [node for node in base.driven if cmds.objExists(node)]
        if joints:
            return joints[0]
        raise SetupError("Game safe: found no bind joint to put the ribbon joints under")

    def _outline(self, master, pin, follows, mesh_world, head, head_rest, master_rest, closed):
        """The master's curve follows the controls' blendShape + jaw pose (not the controls: no cycle)."""
        count = len(follows)
        if closed:
            curve = cmds.circle(sections=count, degree=3, normal=(0, 0, 1), constructionHistory=False)[0]
            cvs = count + 3
        else:
            degree = min(3, count - 1)
            curve = cmds.curve(degree=degree, point=[(float(i), 0.0, 0.0) for i in range(count)])
            cvs = count
        shape = cmds.listRelatives(curve, shapes=True, fullPath=True)[0]
        old = cmds.listRelatives(master.node, shapes=True, fullPath=True) or []
        for attr in ("overrideEnabled", "overrideRGBColors", "overrideColor"):
            if old and cmds.attributeQuery(attr, node=old[0], exists=True):
                cmds.setAttr("%s.%s" % (shape, attr), cmds.getAttr("%s.%s" % (old[0], attr)))
        if old:
            cmds.setAttr(shape + ".overrideColorRGB", *cmds.getAttr(old[0] + ".overrideColorRGB")[0])
        shape = cmds.parent(shape, master.node, relative=True, shape=True)[0]
        cmds.delete(curve)
        if old:
            cmds.delete(old)
        shape = cmds.rename(shape, naming.strip_namespace(master.node) + "Shape")
        to_local = mathlib.mult_all(head_rest, mathlib.inverse(master_rest),
                                    mathlib.compose(scale_values=(OUTLINE_SCALE,) * 3))
        points = []
        for i, follow in enumerate(follows):
            mm = _mult(naming.unique_name(self._n("Outline%02d" % i, "MM")), [
                "%s.outputMatrix[%d]" % (pin, i), mathlib.mult(mesh_world, mathlib.inverse(head_rest)), follow,
                head + ".worldInverseMatrix[0]", to_local])
            decompose = nodes.decompose_matrix(mm, name=self._n("Outline%02d" % i, "DM"))
            points.append(decompose + ".outputTranslate")
        for cv in range(cvs):
            cmds.connectAttr(points[cv % count], "%s.controlPoints[%d]" % (shape, cv), force=True)

    # ------------------------------------------------------------------
    # Skin
    # ------------------------------------------------------------------
    def bind_joints(self):
        return tag_module.get_nodes(self.tag, "bind_joints")

    def connect_skin(self):
        """Wire ``bindPreMatrix`` of every skinCluster the bind joints are in. Returns how many were wired.

        Run it after skinning the mesh (or adding the joints to a skinCluster).
        """
        if self.options.get("game_safe"):
            cmds.warning("[Jeffy] %s is game safe: its joints need no bindPreMatrix, nothing to connect"
                         % self.describe())
            return 0
        count = 0
        for joint, inverse in zip(self.bind_joints(), tag_module.get_nodes(self.tag, "bind_pre")):
            for skin, index in _skin_slots(joint):
                target = "%s.bindPreMatrix[%d]" % (skin, index)
                if not cmds.isConnected(inverse + ".outputMatrix", target):
                    cmds.connectAttr(inverse + ".outputMatrix", target, force=True)
                count += 1
        return count

    def _restore_skin(self):
        """Put back the skin weights a rebuild took away, then wire the skin."""
        stash = _STASH.pop((self.name, self.side), None)
        if stash:
            _restore_weights(stash, self.bind_joints())
        if not self.options.get("game_safe"):
            self.connect_skin()

    def before_delete(self):
        joints = [joint for joint in self.bind_joints() if cmds.objExists(joint)]
        stash = _stash_weights(joints)
        if stash:
            _STASH[(self.name, self.side)] = stash
        for joint in joints:  # the skin keeps working without them (weights go to the other influences)
            for skin, _index in _skin_slots(joint):
                cmds.skinCluster(skin, edit=True, removeInfluence=joint)
        self._remove_created_blendshape()

    def on_abort(self):
        self._remove_created_blendshape()

    def _remove_created_blendshape(self):
        blend = tag_module.get_node(self.tag, "created_blendshape") if cmds.objExists(self.tag) else None
        if not blend or not cmds.objExists(blend):
            return
        if cmds.blendShape(blend, query=True, weightCount=True):
            cmds.warning("[Jeffy] kept %s: it has targets now" % blend)
            return
        cmds.delete(blend)


# ---------------------------------------------------------------------------
# Deformers
# ---------------------------------------------------------------------------
def _history_deformers(shape):
    """Deformers of a shape, from the last applied (closest to the shape) to the first."""
    return [node for node in (cmds.listHistory(shape, pruneDagObjects=True) or [])
            if "geometryFilter" in (cmds.nodeType(node, inherited=True) or [])]


def _blendshapes(shape):
    return [node for node in _history_deformers(shape) if cmds.nodeType(node) == "blendShape"]


def _check_order(shape, blend):
    order = _history_deformers(shape)
    skins = [node for node in order if cmds.nodeType(node) == "skinCluster"]
    if skins and blend in order and order.index(blend) < order.index(skins[0]):
        raise SetupError("%s comes after %s in the deformers of %s: the blendShape must come first (reorder the "
                         "deformers)" % (blend, skins[0], naming.short_name(shape)))


def _geometry_index(blend, shape):
    long_shape = cmds.ls(shape, long=True)[0]
    geometries = cmds.deformer(blend, query=True, geometry=True) or []
    indices = cmds.deformer(blend, query=True, geometryIndices=True) or []
    for geometry, index in zip(geometries, indices):
        if (cmds.ls(geometry, long=True) or [None])[0] == long_shape:
            return int(index)
    raise SetupError("%s does not deform %s" % (blend, naming.short_name(shape)))


def _original_geometry(blend, index, shape):
    found = cmds.listConnections("%s.originalGeometry[%d]" % (blend, index), source=True, destination=False,
                                 plugs=True)
    if found:
        return found[0]
    original = [plug for plug in (cmds.deformableShape(shape, originalGeometry=True) or []) if plug]
    if original:
        return original[0].split(".")[0] + ".outMesh"
    raise SetupError("Found no original (Orig) shape for %s" % naming.short_name(shape))


def _skin_slots(joint):
    """``[(skinCluster, influence index)]`` the joint is in."""
    result = []
    for plug in cmds.listConnections(joint + ".worldMatrix[0]", type="skinCluster", source=False, destination=True,
                                     plugs=True) or []:
        node, attr = plug.split(".", 1)
        if attr.startswith("matrix["):
            result.append((node, int(attr[attr.index("[") + 1:attr.index("]")])))
    return result


def _stash_weights(joints):
    """Weights of every vertex the joints influence (all influences), per skinCluster."""
    skins = {}
    for joint in joints:
        for skin, _index in _skin_slots(joint):
            skins.setdefault(skin, []).append(joint)
    result = []
    for skin, members in skins.items():
        geometry = (cmds.skinCluster(skin, query=True, geometry=True) or [None])[0]
        if not geometry:
            continue
        fn = oma.MFnSkinCluster(_mobject(skin))
        vertices = set()
        for joint in members:
            selection, _weights = fn.getPointsAffectedByInfluence(_dag_path(joint))
            for i in range(selection.length()):
                _dag, component = selection.getComponent(i)
                if not component.isNull():
                    vertices.update(om.MFnSingleIndexedComponent(component).getElements())
        rows = {}
        for vertex in vertices:
            name = "%s.vtx[%d]" % (geometry, vertex)
            influences = cmds.skinPercent(skin, name, query=True, transform=None, ignoreBelow=1e-6) or []
            values = cmds.skinPercent(skin, name, query=True, value=True, ignoreBelow=1e-6) or []
            rows[vertex] = [(naming.short_name(i), w) for i, w in zip(influences, values)]
        result.append({"skin": skin, "geometry": geometry, "rows": rows,
                       "joints": [naming.short_name(joint) for joint in members]})
    return result


def _restore_weights(stash, joints):
    names = dict((naming.short_name(joint), joint) for joint in joints)
    for entry in stash:
        skin = entry["skin"]
        if not cmds.objExists(skin) or not cmds.objExists(entry["geometry"]):
            continue
        current = set(naming.short_name(i) for i in cmds.skinCluster(skin, query=True, influence=True) or [])
        wanted = set(entry["joints"]) | set(name for row in entry["rows"].values() for name, _w in row)
        for name in sorted(wanted - current):
            if name in names:
                cmds.skinCluster(skin, edit=True, addInfluence=names[name], weight=0.0, lockWeights=False)
        influences = cmds.skinCluster(skin, query=True, influence=True) or []
        locks = {}
        for influence in influences:
            if cmds.attributeQuery("liw", node=influence, exists=True):
                locks[influence] = cmds.getAttr(influence + ".liw")
                cmds.setAttr(influence + ".liw", 0)
        valid = set(naming.short_name(i) for i in influences)
        for vertex, row in entry["rows"].items():
            pairs = [(name, weight) for name, weight in row if name in valid]
            if pairs:
                cmds.skinPercent(skin, "%s.vtx[%d]" % (entry["geometry"], vertex), transformValue=pairs,
                                 zeroRemainingInfluences=True, normalize=True)
        for influence, value in locks.items():
            cmds.setAttr(influence + ".liw", value)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def _dag_path(node):
    selection = om.MSelectionList()
    selection.add(node)
    return selection.getDagPath(0)


def _mobject(node):
    selection = om.MSelectionList()
    selection.add(node)
    return selection.getDependNode(0)


def _mult(name, inputs):
    """``multMatrix`` of plugs and constant matrices (in order). Returns its output plug."""
    node = cmds.createNode("multMatrix", name=naming.unique_name(name), skipSelect=True)
    index = 0
    for value in inputs:
        if value is None:
            continue
        plug = "%s.matrixIn[%d]" % (node, index)
        if isinstance(value, str):
            cmds.connectAttr(value, plug)
        else:
            matrix.set_matrix_attr(plug, value)
        index += 1
    return node + ".matrixSum"


def _curve_through(points, closed, name, spans):
    form = om.MFnNurbsCurve.kPeriodic if closed else om.MFnNurbsCurve.kOpen
    array = om.MPointArray([om.MPoint(*point) for point in points])
    if closed:
        array.append(om.MPoint(*points[0]))
    created = om.MFnNurbsCurve().createWithEditPoints(array, 3, form, False, False, True)
    node = cmds.rename(om.MFnDagNode(created).fullPathName(), naming.unique_name(name))
    return cmds.rebuildCurve(node, constructionHistory=False, replaceOriginal=True, rebuildType=0, endKnots=1,
                             keepRange=0, keepControlPoints=False, keepEndPoints=True, keepTangents=False,
                             spans=spans, degree=3)[0]


class _CurveInfo(object):
    """Arc length helpers on a curve."""

    def __init__(self, curve, closed):
        self.fn = om.MFnNurbsCurve(_dag_path(curve))
        self.closed = closed
        self.length = self.fn.length()

    def param_at(self, length):
        length = max(0.0, min(length, self.length))
        if self.closed and length >= self.length - 1e-6:
            return self.fn.knotDomain[0]
        return self.fn.findParamFromLength(length)

    def point_at_length(self, length):
        point = self.fn.getPointAtParam(self.param_at(length), om.MSpace.kWorld)
        return (point.x, point.y, point.z)

    def tangent_at_length(self, length):
        return self.fn.tangent(self.param_at(length), om.MSpace.kWorld).normal()

    def length_at_point(self, point):
        _closest, u = self.fn.closestPoint(om.MPoint(*point), space=om.MSpace.kWorld)
        low, high = self.fn.knotDomain
        if self.closed and u >= high - 1e-6:
            return 0.0
        return self.fn.findLengthFromParam(max(low, min(u, high)))

    def distribute(self, count, anchor=None):
        """``count`` lengths along the curve. A closed loop with an even count and an ``anchor`` (the other
        corner) gives each half count / 2, so both corners get one."""
        total = self.length
        if not self.closed:
            if count == 1:
                return [total * 0.5]
            return [total * k / (count - 1) for k in range(count)]
        if anchor is not None and count >= 4 and count % 2 == 0:
            half = count // 2
            return [anchor * k / half for k in range(half)] + [anchor + (total - anchor) * k / half
                                                               for k in range(half)]
        return [total * k / count for k in range(count)]


def _corner_indices(stops, anchor, closed):
    if not closed:
        return {0, len(stops) - 1}
    other = min(range(len(stops)), key=lambda i: abs(stops[i] - anchor)) if anchor is not None else len(stops) // 2
    return {0, other}


def _labels(points, corners, closed, eps, setup_side):
    """``[(label, side, role)]``: role ``corner`` / ``upper`` / ``lower``, numbered from the centre out."""
    corner_y = sum(points[i][1] for i in corners) / float(len(corners))
    entries = []
    for i, point in enumerate(points):
        if point[0] > eps:
            side = naming.SIDE_LEFT
        elif point[0] < -eps:
            side = naming.SIDE_RIGHT
        else:
            side = naming.SIDE_CENTER
        if setup_side in (naming.SIDE_LEFT, naming.SIDE_RIGHT):
            side = setup_side  # a brow on one side: every control on that side
        if i in corners and closed:
            role = "corner"
        else:
            role = "upper" if point[1] >= corner_y - eps else "lower"
            if not closed and i in corners:
                role = "corner"
        entries.append((side, role))
    groups = {}
    for i, (side, role) in enumerate(entries):
        groups.setdefault((side, role if closed else ""), []).append(i)
    numbers = {}
    for indices in groups.values():
        ordered = sorted(indices, key=lambda i: (abs(points[i][0]), i))
        for rank, i in enumerate(ordered):
            numbers[i] = (rank + 1) if len(ordered) > 1 else None
    result = []
    for i, (side, role) in enumerate(entries):
        name = role.title() if closed else ""
        number = numbers[i]
        result.append(((name + ("%02d" % number if number else "")) or "%02d" % (i + 1), side, role))
    return result


def _build_ribbon(info, mesh_fn, width, spans, name):
    samples = max(spans * 2, 16)
    lengths = info.distribute(samples) if info.closed else [info.length * k / samples for k in range(samples + 1)]
    side_a, side_b = [], []
    for s in lengths:
        point = om.MPoint(*info.point_at_length(s))
        tangent = info.tangent_at_length(s)
        _closest, normal, _face = mesh_fn.getClosestPointAndNormal(point, om.MSpace.kWorld)
        across = (tangent ^ om.MVector(normal)).normal() * (width * 0.5)
        side_a.append(point + across)
        side_b.append(point - across)
    curve_a = _curve_through([(p.x, p.y, p.z) for p in side_a], info.closed, name + "A_tmp", spans)
    curve_b = _curve_through([(p.x, p.y, p.z) for p in side_b], info.closed, name + "B_tmp", spans)
    surface = cmds.loft(curve_a, curve_b, constructionHistory=False, uniform=True, close=False, autoReverse=True,
                        degree=1, sectionSpans=1, range=False, polygon=0, reverseSurfaceNormals=True,
                        name=naming.unique_name(name))[0]
    cmds.delete(curve_a, curve_b)
    return surface


def _surface_uv(surface, point):
    fn = om.MFnNurbsSurface(_dag_path(surface))
    _closest, u, v = fn.closestPoint(om.MPoint(*point), space=om.MSpace.kWorld)
    u0, u1 = fn.knotDomainInU
    v0, v1 = fn.knotDomainInV
    return (u - u0) / (u1 - u0), (v - v0) / (v1 - v0)


def _interp_weights(s, stops, total, closed):
    """Linear weights of a length ``s`` between sorted stops."""
    count = len(stops)
    if count == 1:
        return {0: 1.0}
    if not closed:
        if s <= stops[0]:
            return {0: 1.0}
        if s >= stops[-1]:
            return {count - 1: 1.0}
        for i in range(count - 1):
            if stops[i] <= s <= stops[i + 1]:
                t = (s - stops[i]) / max(stops[i + 1] - stops[i], 1e-9)
                return {i: 1.0 - t, i + 1: t}
    for i in range(count):
        a = stops[i]
        b = stops[(i + 1) % count] + (total if i == count - 1 else 0.0)
        position = s + total if (i == count - 1 and s < a) else s
        if a <= position <= b:
            t = (position - a) / max(b - a, 1e-9)
            return {i: 1.0 - t, (i + 1) % count: t}
    return {0: 1.0}


def _skin_ribbon(surface, joints, stops, info, name):
    skin = cmds.skinCluster(joints, surface, toSelectedBones=True, maximumInfluences=2,
                            name=naming.unique_name(name))[0]
    for cv in cmds.ls(surface + ".cv[*][*]", flatten=True):
        point = cmds.pointPosition(cv, world=True)
        weights = _interp_weights(info.length_at_point(point), stops, info.length, info.closed)
        cmds.skinPercent(skin, cv, transformValue=[(joints[i], w) for i, w in weights.items()],
                         zeroRemainingInfluences=True)
    return skin
