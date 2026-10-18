"""A small scene-aware stand-in for ``maya.cmds`` used by the build tests.

The default test setup replaces Maya with ``MagicMock`` objects, so every
command "succeeds" and real wiring bugs (stale DAG paths after a reparent,
plugs that do not exist, double connections, setting connected or locked
attributes...) are never caught. This module keeps an actual scene:

* DAG nodes with parents/children, unique-path naming like Maya
  (``|grp|node`` full paths, shortest unique partial paths as return values,
  "More than one object matches name" for ambiguous short names),
* attributes with values, locks, keyable state, user attributes and proxies,
* connections (``connectAttr``/``listConnections``) with Maya's errors,
* world matrices computed from translate / rotate / jointOrient / scale /
  offsetParentMatrix and parent world matrices,
* constraints and IK handles as nodes wired the way Maya wires them.

It does not evaluate the dependency graph (no IK solving, no utility node
math); the tests check the wiring instead. Unknown commands raise
``NotImplementedError`` so missing coverage is obvious.
"""

import re

from jeffy.core import mathlib

# ---------------------------------------------------------------------------
# Attribute definitions
# ---------------------------------------------------------------------------
SHORT_NAMES = {
    "t": "translate", "tx": "translateX", "ty": "translateY", "tz": "translateZ",
    "r": "rotate", "rx": "rotateX", "ry": "rotateY", "rz": "rotateZ",
    "s": "scale", "sx": "scaleX", "sy": "scaleY", "sz": "scaleZ",
    "v": "visibility", "ro": "rotateOrder", "jo": "jointOrient",
    "jox": "jointOrientX", "joy": "jointOrientY", "joz": "jointOrientZ",
    "ra": "rotateAxis", "it": "inheritsTransform", "sh": "shear",
}
COMPOUNDS = {
    "translate": ("translateX", "translateY", "translateZ"),
    "rotate": ("rotateX", "rotateY", "rotateZ"),
    "scale": ("scaleX", "scaleY", "scaleZ"),
    "jointOrient": ("jointOrientX", "jointOrientY", "jointOrientZ"),
    "rotateAxis": ("rotateAxisX", "rotateAxisY", "rotateAxisZ"),
    "shear": ("shearXY", "shearXZ", "shearYZ"),
    "preferredAngle": ("preferredAngleX", "preferredAngleY", "preferredAngleZ"),
    "rotatePivot": ("rotatePivotX", "rotatePivotY", "rotatePivotZ"),
    "scalePivot": ("scalePivotX", "scalePivotY", "scalePivotZ"),
    "overrideColorRGB": ("overrideColorR", "overrideColorG", "overrideColorB"),
}
PARENT_OF = {child: parent for parent, children in COMPOUNDS.items() for child in children}

TRANSFORM_DEFAULTS = {
    "translateX": 0.0, "translateY": 0.0, "translateZ": 0.0,
    "rotateX": 0.0, "rotateY": 0.0, "rotateZ": 0.0,
    "scaleX": 1.0, "scaleY": 1.0, "scaleZ": 1.0,
    "shearXY": 0.0, "shearXZ": 0.0, "shearYZ": 0.0,
    "rotateAxisX": 0.0, "rotateAxisY": 0.0, "rotateAxisZ": 0.0,
    "rotatePivotX": 0.0, "rotatePivotY": 0.0, "rotatePivotZ": 0.0,
    "scalePivotX": 0.0, "scalePivotY": 0.0, "scalePivotZ": 0.0,
    "visibility": True, "rotateOrder": 0, "inheritsTransform": True,
    "overrideEnabled": False, "overrideDisplayType": 0, "overrideColor": 0, "overrideRGBColors": False,
    "overrideColorR": 0.0, "overrideColorG": 0.0, "overrideColorB": 0.0,
    "displayLocalAxis": False, "displayHandle": False, "template": False,
    "useOutlinerColor": False,
}
JOINT_DEFAULTS = {
    "jointOrientX": 0.0, "jointOrientY": 0.0, "jointOrientZ": 0.0,
    "preferredAngleX": 0.0, "preferredAngleY": 0.0, "preferredAngleZ": 0.0,
    "radius": 1.0, "segmentScaleCompensate": True, "drawStyle": 0, "side": 0, "type": 0,
    "otherType": "", "drawLabel": False, "lockInfluenceWeights": False,
}
#: matrix outputs computed on demand (index suffix optional)
COMPUTED = ("worldMatrix", "worldInverseMatrix", "parentMatrix", "parentInverseMatrix", "matrix",
            "inverseMatrix", "xformMatrix")
#: always-present plugs on DAG nodes that are only connection points
DAG_PLUGS = ("message", "offsetParentMatrix", "inverseScale", "instObjGroups", "boundingBox", "center",
             "drawOverride", "worldSpace", "local", "controlPoints", "create", "intermediateObject",
             "outTranslate", "outRotate", "inputSurface", "inputMesh", "inputWorldMatrix", "parameterU",
             "parameterV", "worldMesh", "outMesh", "startPosition", "startPositionMatrix", "restPose",
             "startDirection", "pointLock", "degree", "outHair", "currentPosition", "outCurve",
             "lineWidth", "localPosition", "localScale", "localScaleX", "localScaleY", "localScaleZ",
             "dispCV", "currentTime", "inputActive", "inputActiveStart", "outputObjects", "nextState",
             "startFrame", "active", "inputHair", "outputHair", "currentState", "startState", "enable",
             "stiffness", "damp", "drag", "mass", "startCurveAttract", "spans", "form", "cv",
             "editPoints", "u", "v", "uv", "f", "vtx", "e")

TRANSFORM_TYPES = ("transform", "joint", "ikHandle", "ikEffector", "parentConstraint", "pointConstraint",
                   "orientConstraint", "scaleConstraint", "aimConstraint", "poleVectorConstraint", "nucleus")
SHAPE_TYPES = ("nurbsCurve", "locator", "mesh", "nurbsSurface", "follicle", "hairSystem")
CONSTRAINT_TYPES = ("parentConstraint", "pointConstraint", "orientConstraint", "scaleConstraint",
                    "aimConstraint", "poleVectorConstraint")
INHERITANCE = {
    "joint": ("joint", "transform", "dagNode", "entity"),
    "transform": ("transform", "dagNode", "entity"),
    "ikHandle": ("ikHandle", "transform", "dagNode"),
    "ikEffector": ("ikEffector", "transform", "dagNode"),
    "nucleus": ("nucleus", "transform", "dagNode"),
}
for _shape in SHAPE_TYPES:
    INHERITANCE[_shape] = (_shape, "shape", "geometryShape", "dagNode")
for _con in CONSTRAINT_TYPES:
    INHERITANCE[_con] = (_con, "constraint", "transform", "dagNode")


class MayaError(RuntimeError):
    pass


def _index_split(attr):
    """``'matrixIn[2]'`` -> ``('matrixIn', 2)``; ``'tx'`` -> ``('tx', None)``."""
    match = re.match(r"^(\w+)\[(\d+)\]$", attr)
    if match:
        return match.group(1), int(match.group(2))
    return attr, None


class Node(object):
    _counter = 0

    def __init__(self, scene, name, node_type, parent=None):
        Node._counter += 1
        self.id = Node._counter
        self.scene = scene
        self.name = name
        self.type = node_type
        self.parent = parent
        self.children = []
        self.values = {}
        self.locked = set()
        self.hidden = set()
        self.channel_box = set()
        self.user_attrs = {}  # long name -> dict(type, multi, proxy, enum, min, max, default)
        self.short_user = {}
        self.data = {}  # free-form (constraint targets, ik handle info...)
        self.dag = node_type in TRANSFORM_TYPES or node_type in SHAPE_TYPES
        if node_type in TRANSFORM_TYPES:
            self.values.update(TRANSFORM_DEFAULTS)
        if node_type == "joint":
            self.values.update(JOINT_DEFAULTS)
        if node_type in SHAPE_TYPES:
            self.values.update({"overrideEnabled": False, "overrideDisplayType": 0, "overrideColor": 0,
                                "overrideRGBColors": False, "intermediateObject": False, "visibility": True,
                                "overrideColorR": 0.0, "overrideColorG": 0.0, "overrideColorB": 0.0,
                                "lineWidth": -1.0, "parameterU": 0.0, "parameterV": 0.0})

    # ------------------------------------------------------------------
    def path(self):
        parts = []
        node = self
        while node is not None:
            parts.append(node.name)
            node = node.parent
        return "|" + "|".join(reversed(parts)) if self.dag else self.name

    def is_a(self, type_name):
        return type_name in INHERITANCE.get(self.type, (self.type,))

    @property
    def is_transform(self):
        return self.type in TRANSFORM_TYPES

    @property
    def is_shape(self):
        return self.type in SHAPE_TYPES

    # ------------------------------------------------------------------
    def long_attr(self, attr):
        base, index = _index_split(attr)
        if base in SHORT_NAMES:
            base = SHORT_NAMES[base]
        elif base in self.short_user:
            base = self.short_user[base]
        return base if index is None else "%s[%d]" % (base, index)

    def has_attr(self, attr):
        attr = self.long_attr(attr)
        if "." in attr:  # compound children of multi (target[0].weight) -> utility nodes
            return not self.dag or self.type in CONSTRAINT_TYPES
        base, _index = _index_split(attr)
        if base in self.user_attrs or base in self.values or base in COMPOUNDS:
            if base in COMPOUNDS and self.dag:
                return all(child in self.values for child in COMPOUNDS[base])
            return True
        if base in COMPUTED and self.is_transform:
            return True
        if self.dag and base in DAG_PLUGS:
            return True
        if self.is_shape and base in ("worldMatrix", "worldInverseMatrix", "parentMatrix",
                                      "parentInverseMatrix"):
            return True
        # constraints / ik handles / utility nodes: accept any attribute name
        return not self.dag or self.type in CONSTRAINT_TYPES or self.type in ("ikHandle", "ikEffector",
                                                                             "nucleus", "follicle",
                                                                             "hairSystem")

    # ------------------------------------------------------------------
    def local_matrix(self):
        v = self.values
        order = mathlib_rotate_order(int(v.get("rotateOrder", 0)))
        scale = mathlib.compose(scale_values=(v["scaleX"], v["scaleY"], v["scaleZ"]))
        rotate_axis = mathlib.euler_to_matrix((v["rotateAxisX"], v["rotateAxisY"], v["rotateAxisZ"]), "xyz")
        rotate = mathlib.euler_to_matrix((v["rotateX"], v["rotateY"], v["rotateZ"]), order)
        result = mathlib.mult(mathlib.mult(scale, rotate_axis), rotate)
        if self.type == "joint":
            orient = mathlib.euler_to_matrix((v["jointOrientX"], v["jointOrientY"], v["jointOrientZ"]), "xyz")
            result = mathlib.mult(result, orient)
        return mathlib.set_translation(result, (v["translateX"], v["translateY"], v["translateZ"]))

    def offset_parent(self):
        value = self.values.get("offsetParentMatrix")
        return list(value) if value else mathlib.identity()

    def parent_world(self):
        """World matrix of the parent space (identity when not inheriting)."""
        if self.is_transform and not self.values.get("inheritsTransform", True):
            return mathlib.identity()
        if self.parent is None:
            return mathlib.identity()
        return self.parent.world_matrix()

    def world_matrix(self):
        if not self.is_transform:
            return self.parent.world_matrix() if self.parent else mathlib.identity()
        return mathlib.mult(mathlib.mult(self.local_matrix(), self.offset_parent()), self.parent_world())


def mathlib_rotate_order(index):
    return ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")[index]


# ---------------------------------------------------------------------------
# The fake cmds module
# ---------------------------------------------------------------------------
class FakeCmds(object):
    """Implements the subset of ``maya.cmds`` the toolkit uses while building."""

    def __init__(self):
        self.nodes = []
        self.connections = {}  # (node_id, attr) -> (node_id, attr)
        self.selection = []
        self.log = []
        self.undo_stack = []
        self.mutations = 0
        self.loaded_plugins = set()
        self.default_nodes()

    def default_nodes(self):
        self._create("time", "time1")

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        raise NotImplementedError("fake maya.cmds.%s is not implemented" % name)

    # ------------------------------------------------------------------
    # Name resolution
    # ------------------------------------------------------------------
    def _matches(self, name):
        if not isinstance(name, str):
            raise TypeError("Expected a node name, got %r" % (name,))
        name = name.split(".", 1)[0] if "." in name else name
        if "|" in name:
            if name.startswith("|"):
                return [n for n in self.nodes if n.dag and n.path() == name]
            return [n for n in self.nodes if n.dag and (n.path().endswith("|" + name))]
        return [n for n in self.nodes if n.name == name]

    def _node(self, name, command="cmd"):
        matches = self._matches(name)
        if not matches:
            raise MayaError("%s: No object matches name: %s" % (command, name))
        if len(matches) > 1:
            raise MayaError("%s: More than one object matches name: %s" % (command, name))
        return matches[0]

    def _display(self, node, full=False):
        """Maya's return value: shortest unique partial path (or full path)."""
        if not node.dag:
            return node.name
        if full:
            return node.path()
        parts = node.path().strip("|").split("|")
        for count in range(1, len(parts) + 1):
            candidate = "|".join(parts[-count:])
            if len(self._matches(candidate)) == 1:
                return candidate
        return node.path()

    def _plug(self, plug, command="cmd"):
        if "." not in plug:
            raise MayaError("%s: Invalid plug %s" % (command, plug))
        node_name, attr = plug.split(".", 1)
        node = self._node(node_name, command)
        long_attr = node.long_attr(attr) if "." not in attr else self._long_compound(node, attr)
        if not node.has_attr(long_attr):
            raise MayaError("%s: No object matches name: %s" % (command, plug))
        return node, long_attr

    def _long_compound(self, node, attr):
        head, rest = attr.split(".", 1)
        return node.long_attr(head) + "." + rest

    def _unique(self, base):
        if not self._matches(base):
            return base
        stem = re.sub(r"\d+$", "", base)
        index = 1
        while self._matches("%s%d" % (stem, index)):
            index += 1
        return "%s%d" % (stem, index)

    def _create(self, node_type, name=None, parent=None):
        self.mutations += 1
        name = self._unique(name or (node_type + "1"))
        node = Node(self, name, node_type, parent)
        if parent is not None:
            parent.children.append(node)
        self.nodes.append(node)
        return node

    # ------------------------------------------------------------------
    # Node creation
    # ------------------------------------------------------------------
    def createNode(self, node_type, name=None, parent=None, skipSelect=False, shared=False):
        parent_node = self._node(parent, "createNode") if parent else None
        if node_type in SHAPE_TYPES and parent_node is None:
            transform_name = name[:-5] if name and name.endswith("Shape") else (node_type + "1")
            transform = self._create("transform", transform_name)
            shape = self._create(node_type, name or (transform.name + "Shape"), transform)
            return self._display(shape)
        node = self._create(node_type, name, parent_node)
        return self._display(node)

    def spaceLocator(self, name=None, position=None):
        transform = self._create("transform", name or "locator1")
        self._create("locator", transform.name + "Shape", transform)
        return [self._display(transform)]

    def curve(self, name=None, degree=3, point=None, editPoint=None, periodic=False, knot=None, **_kwargs):
        transform = self._create("transform", name or "curve1")
        shape = self._create("nurbsCurve", "curveShape1", transform)
        shape.data["points"] = [tuple(p) for p in (point or editPoint or [])]
        shape.data["degree"] = degree
        return self._display(transform)

    def duplicate(self, node, parentOnly=False, name=None, returnRootsOnly=False, **_kwargs):
        source = self._node(node, "duplicate")
        copy = self._create(source.type, name or source.name, source.parent)
        copy.values = dict(source.values)
        copy.locked = set(source.locked)
        for attr, info in source.user_attrs.items():
            copy.user_attrs[attr] = dict(info)
        if not parentOnly:
            raise NotImplementedError("duplicate without parentOnly")
        return [self._display(copy)]

    def delete(self, *nodes):
        targets = []
        for item in nodes:
            for name in ([item] if isinstance(item, str) else item):
                targets.append(self._node(name, "delete"))
        for node in targets:
            self._delete(node)

    def _delete(self, node):
        if node not in self.nodes:
            return
        for child in list(node.children):
            self._delete(child)
        if node.parent is not None:
            node.parent.children.remove(node)
        self.nodes.remove(node)
        for key, source in list(self.connections.items()):
            if key[0] == node.id or source[0] == node.id:
                del self.connections[key]

    def rename(self, node, new_name, ignoreShape=False):
        target = self._node(node, "rename")
        siblings = target.parent.children if target.parent else [n for n in self.nodes if n.parent is None]
        name = new_name
        if any(s is not target and s.name == name for s in siblings) or (
                not target.dag and any(n is not target and n.name == name for n in self.nodes)):
            stem = re.sub(r"\d+$", "", name)
            index = 1
            while any(s.name == "%s%d" % (stem, index) for s in siblings):
                index += 1
            name = "%s%d" % (stem, index)
        target.name = name
        return self._display(target)

    # ------------------------------------------------------------------
    # Hierarchy
    # ------------------------------------------------------------------
    def parent(self, *args, **kwargs):
        world = kwargs.get("world", kwargs.get("w", False))
        relative = kwargs.get("relative", kwargs.get("r", False))
        shape_flag = kwargs.get("shape", kwargs.get("s", False))
        names = []
        for item in args:
            names.extend([item] if isinstance(item, str) else list(item))
        if world:
            children, new_parent = names, None
        else:
            children, new_parent = names[:-1], self._node(names[-1], "parent")
        result = []
        for name in children:
            child = self._node(name, "parent")
            if child.is_shape and not shape_flag and new_parent is not None:
                raise MayaError("parent: use -shape to parent shapes")
            ancestor = new_parent
            while ancestor is not None:
                if ancestor is child:
                    raise MayaError("parent: Cannot parent a node under itself")
                ancestor = ancestor.parent
            if child.parent is new_parent:
                result.append(self._display(child))
                continue
            world_before = child.world_matrix() if child.is_transform else None
            if child.parent is not None:
                child.parent.children.remove(child)
            child.parent = new_parent
            if new_parent is not None:
                new_parent.children.append(child)
                if any(c is not child and c.name == child.name for c in new_parent.children):
                    child.name = self._unique(child.name)
            if child.is_transform and not relative:
                self._set_world(child, world_before)
            result.append(self._display(child))
        return result

    def listRelatives(self, node=None, parent=False, children=False, shapes=False, allDescendents=False,
                      type=None, fullPath=False, path=False, noIntermediate=False, allParents=False):
        if node is None:
            return None
        nodes = node if isinstance(node, (list, tuple)) else [node]
        result = []
        for name in nodes:
            target = self._node(name, "listRelatives")
            if parent or allParents:
                found = [target.parent] if target.parent else []
            elif allDescendents:
                found = []
                stack = [(target, False)]
                while stack:  # children before parents, like Maya
                    current, expanded = stack.pop()
                    if expanded:
                        if current is not target:
                            found.append(current)
                        continue
                    stack.append((current, True))
                    stack.extend((c, False) for c in current.children)
            else:
                found = list(target.children)
                if shapes:
                    found = [c for c in found if c.is_shape]
            if noIntermediate:
                found = [c for c in found if not c.values.get("intermediateObject")]
            if type:
                types = [type] if isinstance(type, str) else list(type)
                found = [c for c in found if any(c.is_a(t) for t in types)]
            result.extend(self._display(c, fullPath) for c in found)
        return result or None

    def ls(self, *args, **kwargs):
        long_names = kwargs.get("long", kwargs.get("l", False))
        if kwargs.get("selection", kwargs.get("sl", False)) or kwargs.get("orderedSelection",
                                                                         kwargs.get("os", False)):
            nodes = [n for n in self.selection if n in self.nodes]
        else:
            names = []
            for item in args:
                names.extend([item] if isinstance(item, str) else list(item or []))
            if args:
                nodes = []
                for name in names:
                    if "." in name:
                        node_pattern, attr = name.split(".", 1)
                        if ":" in node_pattern:
                            continue  # no namespaces in the fake scene
                        pattern = re.compile("^" + re.escape(node_pattern).replace("\\*", ".*") + "$")
                        nodes.extend(n for n in self.nodes if pattern.match(n.name) and (
                            attr in n.user_attrs or attr in n.values))
                    elif "*" in name:
                        pattern = re.compile("^" + re.escape(name).replace("\\*", ".*") + "$")
                        nodes.extend(n for n in self.nodes if pattern.match(n.name))
                    else:
                        nodes.extend(self._matches(name))
            else:
                nodes = list(self.nodes)
        node_type = kwargs.get("type")
        if node_type:
            types = [node_type] if isinstance(node_type, str) else list(node_type)
            nodes = [n for n in nodes if any(n.is_a(t) for t in types)]
        if kwargs.get("transforms"):
            nodes = [n for n in nodes if n.is_transform]
        return [self._display(n, long_names) for n in nodes]

    def objExists(self, name):
        if "." in name:
            node_name, attr = name.split(".", 1)
            matches = self._matches(node_name)
            if len(matches) != 1:
                return bool(matches)
            node = matches[0]
            attr = node.long_attr(attr) if "." not in attr else self._long_compound(node, attr)
            return node.has_attr(attr)
        return bool(self._matches(name))

    def nodeType(self, name):
        return self._node(name, "nodeType").type

    def objectType(self, name, isAType=None, isType=None):
        node = self._node(name, "objectType")
        if isAType:
            return node.is_a(isAType)
        if isType:
            return node.type == isType
        return node.type

    def select(self, *args, **kwargs):
        if kwargs.get("clear") or kwargs.get("cl"):
            self.selection = []
            return
        names = []
        for item in args:
            names.extend([item] if isinstance(item, str) else list(item or []))
        nodes = [self._node(n, "select") for n in names]
        if kwargs.get("add"):
            self.selection.extend(nodes)
        else:
            self.selection = nodes

    # ------------------------------------------------------------------
    # Attributes
    # ------------------------------------------------------------------
    def _source(self, node, attr):
        return self.connections.get((node.id, attr))

    def _is_connected(self, node, attr):
        if self._source(node, attr):
            return True
        parent = PARENT_OF.get(attr)
        if parent and self._source(node, parent):
            return True
        for child in COMPOUNDS.get(attr, ()):
            if self._source(node, child):
                return True
        return False

    def _is_locked(self, node, attr):
        return attr in node.locked or PARENT_OF.get(attr) in node.locked

    def getAttr(self, plug, settable=False, lock=False, keyable=False, channelBox=False, multiIndices=False,
                type=False, size=False, **_kwargs):
        node, attr = self._plug(plug, "getAttr")
        if settable:
            return not self._is_connected(node, attr) and not self._is_locked(node, attr)
        if lock:
            return self._is_locked(node, attr)
        if keyable:
            return attr not in node.hidden
        if channelBox:
            return attr in node.channel_box
        if multiIndices:
            prefix = attr + "["
            indices = set()
            for key in list(node.values) + [k[1] for k in self.connections if k[0] == node.id]:
                if key.startswith(prefix):
                    indices.add(int(key[len(prefix):].split("]")[0]))
            for source in self.connections.values():
                if source[0] == node.id and source[1].startswith(prefix):
                    indices.add(int(source[1][len(prefix):].split("]")[0]))
            return sorted(indices) or None
        base, _index = _index_split(attr)
        if base in COMPUTED:
            return self._computed(node, base)
        if base in COMPOUNDS:
            return [tuple(node.values.get(c, 0.0) for c in COMPOUNDS[base])]
        if attr in node.user_attrs and node.user_attrs[attr].get("proxy"):
            return self.getAttr(node.user_attrs[attr]["proxy"])
        value = node.values.get(attr)
        if value is None:
            info = node.user_attrs.get(attr)
            if info:
                return info.get("default", 0)
            if attr == "offsetParentMatrix":
                return mathlib.identity()
            return 0.0
        return value

    def _computed(self, node, base):
        world = node.world_matrix()
        if base == "worldMatrix":
            return world
        if base == "worldInverseMatrix":
            return mathlib.inverse(world)
        if base == "parentMatrix":
            return node.parent_world()
        if base == "parentInverseMatrix":
            return mathlib.inverse(node.parent_world())
        if base in ("matrix", "xformMatrix"):
            return node.local_matrix()
        return mathlib.inverse(node.local_matrix())

    def setAttr(self, plug, *values, **kwargs):
        node, attr = self._plug(plug, "setAttr")
        flags_only = not values
        if values:
            self._set_value(node, attr, plug, values, kwargs)
        if "lock" in kwargs or "l" in kwargs:
            locked = kwargs.get("lock", kwargs.get("l"))
            targets = [attr] + list(COMPOUNDS.get(attr, ()))
            for item in targets:
                (node.locked.add if locked else node.locked.discard)(item)
        if "keyable" in kwargs or "k" in kwargs:
            keyable = kwargs.get("keyable", kwargs.get("k"))
            (node.hidden.discard if keyable else node.hidden.add)(attr)
        if "channelBox" in kwargs or "cb" in kwargs:
            channel = kwargs.get("channelBox", kwargs.get("cb"))
            (node.channel_box.add if channel else node.channel_box.discard)(attr)
            if channel:
                node.hidden.add(attr)
        if flags_only:
            return

    def _set_value(self, node, attr, plug, values, kwargs):
        if self._is_locked(node, attr):
            raise MayaError("setAttr: The attribute '%s.%s' is locked or connected and cannot be modified."
                            % (node.name, attr))
        if self._is_connected(node, attr):
            raise MayaError("setAttr: The attribute '%s.%s' is locked or connected and cannot be modified."
                            % (node.name, attr))
        value_type = kwargs.get("type")
        base, _index = _index_split(attr)
        if base in COMPUTED:
            raise MayaError("setAttr: '%s' is a computed output" % plug)
        if value_type == "matrix":
            node.values[attr] = list(values)
        elif value_type == "string":
            node.values[attr] = values[0]
        elif attr in COMPOUNDS:
            for child, value in zip(COMPOUNDS[attr], values):
                node.values[child] = value
        else:
            node.values[attr] = values[0] if len(values) == 1 else list(values)

    def addAttr(self, node=None, longName=None, attributeType=None, dataType=None, proxy=None, multi=False,
                parent=None, shortName=None, **kwargs):
        target = self._node(node, "addAttr")
        if target.has_attr(longName) and (longName in target.user_attrs or longName in target.values):
            raise MayaError("addAttr: Found attribute named '%s' already on %s" % (longName, target.name))
        if proxy:
            self._plug(proxy, "addAttr")  # must exist
        info = {"type": attributeType or dataType, "multi": multi, "proxy": proxy,
                "default": kwargs.get("defaultValue"), "enum": kwargs.get("enumName"),
                "min": kwargs.get("minValue"), "max": kwargs.get("maxValue")}
        target.user_attrs[longName] = info
        if shortName:
            target.short_user[shortName] = longName
        if not multi and not proxy and (attributeType or dataType) not in ("message", "matrix", None):
            default = kwargs.get("defaultValue")
            target.values[longName] = default if default is not None else (
                "" if dataType == "string" else 0.0)
        if not kwargs.get("keyable", False) and attributeType != "message":
            target.hidden.add(longName)

    def deleteAttr(self, plug=None, attribute=None):
        node, attr = self._plug(plug, "deleteAttr")
        node.user_attrs.pop(attr, None)
        node.values.pop(attr, None)

    def attributeQuery(self, attr, node=None, exists=False, longName=False, listEnum=False, multi=False,
                       **_kwargs):
        target = self._node(node, "attributeQuery")
        long_attr = target.long_attr(attr)
        if exists:
            return target.has_attr(long_attr) and (
                long_attr in target.user_attrs or long_attr in target.values or long_attr in COMPOUNDS
                or _index_split(long_attr)[0] in COMPUTED or long_attr in DAG_PLUGS or not target.dag)
        if not target.has_attr(long_attr):
            raise MayaError("attributeQuery: No attribute named %s on %s" % (attr, node))
        if longName:
            return long_attr
        if listEnum:
            return [target.user_attrs.get(long_attr, {}).get("enum") or ""]
        if multi:
            return bool(target.user_attrs.get(long_attr, {}).get("multi"))
        return None

    def listAttr(self, node, userDefined=False, keyable=False, **_kwargs):
        target = self._node(node, "listAttr")
        if userDefined:
            return list(target.user_attrs) or None
        return list(target.values) or None

    def connectAttr(self, source, destination, force=False, f=False, nextAvailable=False):
        force = force or f
        src_node, src_attr = self._plug(source, "connectAttr")
        dst_node, dst_attr = self._plug(destination, "connectAttr")
        if src_node is dst_node and src_attr == dst_attr:
            raise MayaError("connectAttr: cannot connect a plug to itself")
        if self._is_locked(dst_node, dst_attr):
            raise MayaError("connectAttr: The destination attribute '%s' is locked" % destination)
        existing = self._source(dst_node, dst_attr)
        if existing and not force:
            raise MayaError("connectAttr: '%s' already has an incoming connection from '%s'."
                            % (destination, self._plug_name(existing)))
        if existing == (src_node.id, src_attr):
            if not force:
                raise MayaError("connectAttr: '%s' is already connected to '%s'." % (source, destination))
        # a compound and its children cannot both be driven
        for child in COMPOUNDS.get(dst_attr, ()):
            if self._source(dst_node, child):
                if not force:
                    raise MayaError("connectAttr: '%s.%s' already has an incoming connection" % (
                        destination, child))
                del self.connections[(dst_node.id, child)]
        parent = PARENT_OF.get(dst_attr)
        if parent and self._source(dst_node, parent):
            if not force:
                raise MayaError("connectAttr: parent '%s' of '%s' is connected" % (parent, destination))
            del self.connections[(dst_node.id, parent)]
        self.connections[(dst_node.id, dst_attr)] = (src_node.id, src_attr)
        self.mutations += 1

    def disconnectAttr(self, source, destination):
        dst_node, dst_attr = self._plug(destination, "disconnectAttr")
        self.connections.pop((dst_node.id, dst_attr), None)

    def _by_id(self, node_id):
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def _plug_name(self, key):
        node = self._by_id(key[0])
        return "%s.%s" % (self._display(node), key[1])

    def listConnections(self, target, source=True, destination=True, plugs=False, type=None,
                        connections=False, skipConversionNodes=False, shapes=False, exactType=False, **_k):
        if "." in target:
            node, attr = self._plug(target, "listConnections")
            attrs = {attr} | set(COMPOUNDS.get(attr, ()))
        else:
            node = self._node(target, "listConnections")
            attrs = None
        result = []
        for (dst_id, dst_attr), (src_id, src_attr) in self.connections.items():
            if source and dst_id == node.id and (attrs is None or dst_attr in attrs
                                                 or dst_attr.split(".")[0] in attrs):
                other = self._by_id(src_id)
                result.append((other, src_attr))
            if destination and src_id == node.id and (attrs is None or src_attr in attrs):
                other = self._by_id(dst_id)
                result.append((other, dst_attr))
        if type:
            result = [(n, a) for n, a in result if n.is_a(type)]
        if plugs:
            return ["%s.%s" % (self._display(n), a) for n, a in result] or None
        names = []
        for n, _a in result:
            display = self._display(n)
            if display not in names:
                names.append(display)
        return names or None

    def isConnected(self, source, destination):
        dst_node, dst_attr = self._plug(destination, "isConnected")
        src_node, src_attr = self._plug(source, "isConnected")
        return self._source(dst_node, dst_attr) == (src_node.id, src_attr)

    # ------------------------------------------------------------------
    # Transforms
    # ------------------------------------------------------------------
    def _set_world(self, node, world):
        """Write local channels so the world matrix becomes ``world`` (settable only)."""
        local = mathlib.mult(world, mathlib.inverse(mathlib.mult(node.offset_parent(), node.parent_world())))
        translate, rotate, scale = self._decompose(node, local)
        for axis, value in zip("XYZ", translate):
            self._write(node, "translate" + axis, value)
        for axis, value in zip("XYZ", rotate):
            self._write(node, "rotate" + axis, value)
        for axis, value in zip("XYZ", scale):
            self._write(node, "scale" + axis, value)

    def _write(self, node, attr, value):
        if not self._is_connected(node, attr) and not self._is_locked(node, attr):
            node.values[attr] = value

    def _decompose(self, node, local):
        x_axis, y_axis, z_axis, position = mathlib.axes(local)
        scale = [mathlib.length(x_axis), mathlib.length(y_axis), mathlib.length(z_axis)]
        if mathlib.dot(mathlib.cross(x_axis, y_axis), z_axis) < 0:
            scale[0] = -scale[0]
        rotation = mathlib.from_axes(mathlib.scale(x_axis, 1.0 / scale[0]), mathlib.scale(y_axis, 1.0 / scale[1]),
                                     mathlib.scale(z_axis, 1.0 / scale[2]))
        v = node.values
        rotate_axis = (v["rotateAxisX"], v["rotateAxisY"], v["rotateAxisZ"])
        if any(abs(a) > 1e-9 for a in rotate_axis):
            rotation = mathlib.mult(mathlib.inverse(mathlib.euler_to_matrix(rotate_axis, "xyz")), rotation)
        if node.type == "joint":
            orient = (v["jointOrientX"], v["jointOrientY"], v["jointOrientZ"])
            rotation = mathlib.mult(rotation, mathlib.inverse(mathlib.euler_to_matrix(orient, "xyz")))
        euler = mathlib.matrix_to_euler(rotation, mathlib_rotate_order(int(v.get("rotateOrder", 0))))
        return position, euler, scale

    def xform(self, node, query=False, worldSpace=False, objectSpace=False, matrix=None, translation=None,
              rotation=None, rotatePivot=False, scale=None, relative=False, **_kwargs):
        if "." in node:
            raise NotImplementedError("xform on components")
        target = self._node(node, "xform")
        if query:
            world = target.world_matrix() if worldSpace else target.local_matrix()
            if matrix:
                return list(world)
            if translation or rotatePivot:
                return list(mathlib.get_translation(world))
            if rotation:
                return list(self._decompose(target, world)[1])
            raise NotImplementedError("xform query flags")
        if matrix is not None:
            if worldSpace:
                self._set_world(target, list(matrix))
            else:
                self._set_world(target, mathlib.mult(list(matrix), mathlib.mult(target.offset_parent(),
                                                                                target.parent_world())))
        if translation is not None:
            if worldSpace:
                space = mathlib.mult(target.offset_parent(), target.parent_world())
                local = mathlib.transform_point(translation, mathlib.inverse(space))
            else:
                local = translation
            for axis, value in zip("XYZ", local):
                if self._is_connected(target, "translate" + axis) or self._is_locked(target, "translate" + axis):
                    raise MayaError("xform: translate of %s is locked or connected" % node)
                target.values["translate" + axis] = value
        if rotation is not None:
            if worldSpace:
                world = target.world_matrix()
                desired = mathlib.set_translation(mathlib.euler_to_matrix(rotation, "xyz"),
                                                  mathlib.get_translation(world))
                self._set_world(target, desired)
            else:
                for axis, value in zip("XYZ", rotation):
                    target.values["rotate" + axis] = value

    def matchTransform(self, node, target, position=False, rotation=False, scale=False, pivots=False):
        source = self._node(node, "matchTransform")
        goal = self._node(target, "matchTransform").world_matrix()
        current = source.world_matrix()
        cur_x, cur_y, cur_z, cur_t = mathlib.axes(current)
        goal_x, goal_y, goal_z, goal_t = mathlib.axes(goal)
        lengths = [mathlib.length(a) or 1.0 for a in (cur_x, cur_y, cur_z)]
        if rotation:
            axes = [mathlib.scale(mathlib.normalize(a), s) for a, s in zip((goal_x, goal_y, goal_z), lengths)]
        else:
            axes = [cur_x, cur_y, cur_z]
        translate = goal_t if position else cur_t
        self._set_world(source, mathlib.from_axes(axes[0], axes[1], axes[2], translate))

    def makeIdentity(self, nodes, apply=False, translate=False, rotate=False, scale=False, **_kwargs):
        for name in [nodes] if isinstance(nodes, str) else nodes:
            node = self._node(name, "makeIdentity")
            if rotate and node.type == "joint":
                world = node.world_matrix()
                local = mathlib.mult(world, mathlib.inverse(mathlib.mult(node.offset_parent(),
                                                                         node.parent_world())))
                rotation = mathlib.orthonormalize(local)
                euler = mathlib.matrix_to_euler(rotation, "xyz")
                for axis, value in zip("XYZ", euler):
                    node.values["jointOrient" + axis] = value
                    node.values["rotate" + axis] = 0.0
            elif rotate:
                for axis in "XYZ":
                    node.values["rotate" + axis] = 0.0

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    def _constraint(self, kind, args, kwargs, outputs):
        names = []
        for item in args:
            names.extend([item] if isinstance(item, str) else list(item))
        if kwargs.get("query") or kwargs.get("q"):
            node = self._node(names[0], kind)
            targets = node.data.get("targets", [])
            if kwargs.get("weightAliasList") or kwargs.get("wal"):
                return ["%sW%d" % (self._by_id(t).name, i) for i, t in enumerate(targets)]
            if kwargs.get("targetList") or kwargs.get("tl"):
                return [self._display(self._by_id(t)) for t in targets]
            raise NotImplementedError("constraint query")
        targets = [self._node(n, kind) for n in names[:-1]]
        driven = self._node(names[-1], kind)
        if not targets:
            raise MayaError("%s: no target" % kind)
        skip = kwargs.get("skipTranslate", kwargs.get("st", ())) or ()
        skip_rotate = kwargs.get("skipRotate", kwargs.get("sr", ())) or ()
        existing = [c for c in driven.children if c.type == kind]
        if existing:
            constraint = existing[0]
        else:
            name = kwargs.get("name") or kwargs.get("n") or "%s_%s1" % (driven.name, kind)
            constraint = self._create(kind, name, driven)
            constraint.values["interpType"] = 1
            constraint.data["targets"] = []
            for attr in outputs:
                axes = "XYZ"
                skipped = skip if attr == "translate" else skip_rotate if attr == "rotate" else ()
                for axis in axes:
                    if axis.lower() in skipped:
                        continue
                    child = attr + axis
                    if attr in ("translate", "rotate", "scale"):
                        if self._is_locked(driven, child):
                            raise MayaError("%s: '%s.%s' is locked - cannot constrain" % (kind, driven.name, child))
                        if self._source(driven, child) or self._source(driven, attr):
                            raise MayaError("%s: '%s.%s' is already connected - cannot constrain" % (
                                kind, driven.name, child))
                        self.connections[(driven.id, child)] = (constraint.id, "constraint" + child[0].upper()
                                                                + child[1:])
        for target in targets:
            index = len(constraint.data["targets"])
            constraint.data["targets"].append(target.id)
            alias = "%sW%d" % (target.name, index)
            constraint.user_attrs[alias] = {"type": "double", "default": 1.0}
            constraint.values[alias] = 1.0
            self.connections[(constraint.id, "target[%d].targetParentMatrix" % index)] = (
                target.id, "parentMatrix[0]")
        constraint.data["maintainOffset"] = kwargs.get("maintainOffset", kwargs.get("mo", False))
        return [self._display(constraint)]

    def parentConstraint(self, *args, **kwargs):
        return self._constraint("parentConstraint", args, kwargs, ("translate", "rotate"))

    def pointConstraint(self, *args, **kwargs):
        return self._constraint("pointConstraint", args, kwargs, ("translate",))

    def orientConstraint(self, *args, **kwargs):
        return self._constraint("orientConstraint", args, kwargs, ("rotate",))

    def scaleConstraint(self, *args, **kwargs):
        return self._constraint("scaleConstraint", args, kwargs, ("scale",))

    def aimConstraint(self, *args, **kwargs):
        return self._constraint("aimConstraint", args, kwargs, ("rotate",))

    def poleVectorConstraint(self, *args, **kwargs):
        names = [a for a in args]
        handle = self._node(names[-1], "poleVectorConstraint")
        if handle.type != "ikHandle":
            raise MayaError("poleVectorConstraint: %s is not an ikHandle" % names[-1])
        return self._constraint("poleVectorConstraint", args, kwargs, ("poleVector",))

    # ------------------------------------------------------------------
    # IK
    # ------------------------------------------------------------------
    def ikHandle(self, startJoint=None, endEffector=None, solver="ikRPsolver", name=None, curve=None, **kwargs):
        start = self._node(startJoint, "ikHandle")
        end = self._node(endEffector, "ikHandle")
        if start.type != "joint" or end.type != "joint":
            raise MayaError("ikHandle: start and end must be joints")
        ancestor = end
        while ancestor is not None and ancestor is not start:
            ancestor = ancestor.parent
        if ancestor is None:
            raise MayaError("ikHandle: %s is not below %s" % (endEffector, startJoint))
        effector = self._create("ikEffector", "effector1", end.parent)
        handle = self._create("ikHandle", name or "ikHandle1")
        handle.data.update(start=start.id, end=end.id, solver=solver, effector=effector.id)
        handle.values.update({"twist": 0.0, "poleVectorX": 0.0, "poleVectorY": 0.0, "poleVectorZ": 0.0,
                              "dTwistControlEnable": False, "dWorldUpType": 0, "dForwardAxis": 0,
                              "dWorldUpAxis": 0})
        self._set_world(handle, end.world_matrix())
        # the solver drives the rotations of every joint from start to end's parent
        joint = end.parent
        while True:
            for axis in "XYZ":
                if self._is_locked(joint, "rotate" + axis):
                    raise MayaError("ikHandle: rotate%s of %s is locked" % (axis, joint.name))
            joint.data["ik_solved_by"] = handle.id
            if joint is start:
                break
            joint = joint.parent
        return [self._display(handle), self._display(effector)]

    # ------------------------------------------------------------------
    # Misc commands
    # ------------------------------------------------------------------
    def pluginInfo(self, name, query=False, loaded=False, **_kwargs):
        return name in self.loaded_plugins

    def loadPlugin(self, name, quiet=False):
        self.loaded_plugins.add(name)
        return [name]

    def controller(self, *args, **kwargs):
        return None

    def undoInfo(self, **kwargs):
        if kwargs.get("query") or kwargs.get("q"):
            if kwargs.get("state"):
                return True
            if kwargs.get("undoName"):
                return self.undo_stack[-1] if self.undo_stack else ""
            return None
        if kwargs.get("openChunk"):
            self.undo_stack.append(kwargs.get("chunkName", ""))
            self._chunk_start = self.mutations
        if kwargs.get("closeChunk") and self.mutations == getattr(self, "_chunk_start", None):
            self.undo_stack.pop()  # Maya does not record empty chunks
        return None

    def undo(self):
        self.log.append("undo: %s" % (self.undo_stack.pop() if self.undo_stack else ""))

    def warning(self, text):
        self.log.append("warning: " + text)

    def inViewMessage(self, **kwargs):
        return None

    def refresh(self, **kwargs):
        return None

    def about(self, apiVersion=False, **kwargs):
        return 20240000 if apiVersion else "2024"

    def currentTime(self, *args, **kwargs):
        return 1.0

    def playbackOptions(self, **kwargs):
        return 1.0 if kwargs.get("minTime") else 120.0

    def rebuildCurve(self, curve, **kwargs):
        self._node(curve, "rebuildCurve")
        return [curve]

    def move(self, *args, **kwargs):
        """Component moves (control shape CVs): validate the shapes exist."""
        for item in args:
            if isinstance(item, str) and "." in item:
                self._node(item.split(".")[0], "move")
            elif isinstance(item, (list, tuple)):
                for name in item:
                    if isinstance(name, str) and "." in name:
                        self._node(name.split(".")[0], "move")

    def scale(self, *args, **kwargs):
        self.move(*args, **kwargs)

    def rotate(self, *args, **kwargs):
        self.move(*args, **kwargs)

    def sets(self, *args, **kwargs):
        names = []
        for item in args:
            names.extend([item] if isinstance(item, str) else list(item or []))
        for name in names:
            self._node(name, "sets")
        node = self._create("objectSet", kwargs.get("name") or kwargs.get("n") or "set1")
        node.data["members"] = names
        return node.name

    def listHistory(self, node, pruneDagObjects=False, **kwargs):
        start = self._node(node, "listHistory")
        seen, queue = [start], [start]
        while queue:
            current = queue.pop()
            for (dst_id, _dst_attr), (src_id, _src_attr) in self.connections.items():
                if dst_id == current.id:
                    source = self._by_id(src_id)
                    if source not in seen:
                        seen.append(source)
                        queue.append(source)
        if pruneDagObjects:
            seen = [n for n in seen if not n.dag]
        return [self._display(n) for n in seen] or None

    def dagPose(self, *args, **kwargs):
        return "bindPose1"

    def skinCluster(self, *args, **kwargs):
        names = []
        for item in args:
            names.extend([item] if isinstance(item, str) else list(item))
        if kwargs.get("query") or kwargs.get("q") or kwargs.get("edit") or kwargs.get("e"):
            raise NotImplementedError("skinCluster query/edit")
        geometry = self._node(names[-1], "skinCluster")
        influences = [self._node(n, "skinCluster") for n in names[:-1]]
        node = self._create("skinCluster", kwargs.get("name") or kwargs.get("n") or "skinCluster1")
        node.data["influences"] = [i.id for i in influences]
        node.data["geometry"] = geometry.id
        for i, influence in enumerate(influences):
            self.connections[(node.id, "matrix[%d]" % i)] = (influence.id, "worldMatrix[0]")
        return [node.name]


# ---------------------------------------------------------------------------
# Scene helpers for tests
# ---------------------------------------------------------------------------
def install(monkeypatch):
    """Replace ``cmds`` in every imported jeffy module with a fresh FakeCmds."""
    import sys

    fake = FakeCmds()
    import maya

    monkeypatch.setattr(maya, "cmds", fake, raising=False)
    monkeypatch.setitem(sys.modules, "maya.cmds", fake)
    for name, module in list(sys.modules.items()):
        if name.startswith("jeffy") and module is not None and hasattr(module, "cmds"):
            monkeypatch.setattr(module, "cmds", fake)
    return fake


def driver_of(cmds, plug):
    """``'node.attr'`` -> ``'src.attr'`` (or ``None``)."""
    node, attr = cmds._plug(plug)
    key = cmds._source(node, attr)
    return cmds._plug_name(key) if key else None


# ---------------------------------------------------------------------------
# Tiny dependency graph evaluator (scalar utility networks at the current pose)
# ---------------------------------------------------------------------------
def evaluate(cmds, plug, _depth=0):
    """Value of ``plug`` following connections through utility nodes.

    Transforms are read at their stored pose (constraints are not solved), so
    this is meant for checking networks at the rest pose right after a build.
    """
    if _depth > 200:
        raise RuntimeError("evaluation too deep (cycle?) at %s" % plug)
    node, attr = cmds._plug(plug, "evaluate")
    source = cmds._source(node, attr)
    if source is not None:
        src = cmds._by_id(source[0])
        return _output(cmds, src, source[1], _depth + 1)
    if attr in node.user_attrs and node.user_attrs[attr].get("proxy"):
        return evaluate(cmds, node.user_attrs[attr]["proxy"], _depth + 1)
    return cmds.getAttr(plug)


def _input(cmds, node, attr, depth, default=0.0):
    plug = "%s.%s" % (cmds._display(node), attr)
    key = (node.id, attr)
    if key in cmds.connections or attr in node.values:
        return evaluate(cmds, plug, depth)
    return default


def _output(cmds, node, attr, depth):
    t = node.type
    get = lambda a, d=0.0: _input(cmds, node, a, depth, d)  # noqa: E731
    if node.is_transform or node.is_shape or t not in _EVALUATORS:
        if t in _EVALUATORS:
            pass
        else:
            return cmds.getAttr("%s.%s" % (cmds._display(node), attr))
    return _EVALUATORS[t](cmds, node, attr, get)


def _pma(cmds, node, attr, get):
    indices = sorted({int(k.split("[")[1].split("]")[0]) for k in list(node.values) +
                      [c[1] for c in cmds.connections if c[0] == node.id] if k.startswith("input1D[")})
    values = [get("input1D[%d]" % i) for i in indices]
    op = int(node.values.get("operation", 1))
    if op == 1:
        return sum(values)
    if op == 2:
        return values[0] - sum(values[1:])
    return sum(values) / float(len(values))


def _md(cmds, node, attr, get):
    a, b = get("input1X"), get("input2X", 1.0)
    op = int(node.values.get("operation", 1))
    return {1: lambda: a * b, 2: lambda: a / b, 3: lambda: a ** b}.get(op, lambda: a)()


def _condition(cmds, node, attr, get):
    import operator

    ops = [operator.eq, operator.ne, operator.gt, operator.ge, operator.lt, operator.le]
    first, second = get("firstTerm"), get("secondTerm")
    result = ops[int(node.values.get("operation", 0))](first, second)
    return get("colorIfTrueR") if result else get("colorIfFalseR")


def _matrix_input(cmds, node, attr):
    plug = "%s.%s" % (cmds._display(node), attr)
    key = (node.id, attr)
    if key in cmds.connections:
        src_node = cmds._by_id(cmds.connections[key][0])
        return cmds.getAttr("%s.%s" % (cmds._display(src_node), cmds.connections[key][1]))
    return cmds.getAttr(plug) if attr in node.values else mathlib.identity()


def _decompose_matrix(cmds, node, attr, get):
    matrix = _matrix_input(cmds, node, "inputMatrix")
    x_axis, y_axis, z_axis, position = mathlib.axes(matrix)
    if attr.startswith("outputScale"):
        axis = {"X": x_axis, "Y": y_axis, "Z": z_axis}[attr[-1]]
        return mathlib.length(axis)
    if attr.startswith("outputTranslate"):
        return position["XYZ".index(attr[-1])] if attr != "outputTranslate" else position
    raise NotImplementedError("decomposeMatrix.%s" % attr)


def _distance(cmds, node, attr, get):
    a = mathlib.get_translation(_matrix_input(cmds, node, "inMatrix1"))
    b = mathlib.get_translation(_matrix_input(cmds, node, "inMatrix2"))
    return mathlib.distance(a, b)


_EVALUATORS = {
    "multDoubleLinear": lambda c, n, a, g: g("input1") * g("input2", 1.0),
    "addDoubleLinear": lambda c, n, a, g: g("input1") + g("input2"),
    "plusMinusAverage": _pma,
    "multiplyDivide": _md,
    "reverse": lambda c, n, a, g: 1.0 - g("inputX"),
    "clamp": lambda c, n, a, g: min(max(g("inputR"), g("minR")), g("maxR")),
    "condition": _condition,
    "blendColors": lambda c, n, a, g: g("color1R") * g("blender", 0.5) + g("color2R") * (1 - g("blender", 0.5)),
    "decomposeMatrix": _decompose_matrix,
    "distanceBetween": _distance,
}
