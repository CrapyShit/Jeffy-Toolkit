"""The :class:`Control` object - an animator control with offset groups.

Example::

    from jeffy.controls.control import Control
    ctl = Control.create("arm", side="L", shape="circle", axis="x", size=2,
                         match="L_arm_JNT", offsets=("zero", "offset"))
    ctl.node       # 'L_arm_CTL'
    ctl.zero       # 'L_arm_ZRO' (top group)
    ctl.offsets    # ['L_arm_ZRO', 'L_arm_OFF']
"""

from maya import cmds

from jeffy.controls import library, shapes
from jeffy.core import attributes, color, dag, naming

CONTROL_ATTR = "jeffyControl"
OFFSETS_ATTR = "jeffyOffsets"
SIDE_ATTR = "jeffySide"


class Control(object):
    """Thin wrapper around a control transform."""

    def __init__(self, node):
        if not cmds.objExists(node):
            raise ValueError("Control %s does not exist" % node)
        self.node = node

    def __repr__(self):
        return "Control(%r)" % self.node

    def __str__(self):
        return self.node

    # ------------------------------------------------------------------
    @classmethod
    def create(
        cls,
        name="control",
        side=None,
        shape="circle",
        size=1.0,
        color_value=None,
        axis="y",
        offsets=("zero",),
        parent=None,
        match=None,
        match_rotation=True,
        position=None,
        lock=("v",),
        line_width=None,
        rotate_order=None,
        shape_offset=(0.0, 0.0, 0.0),
        full_name=None,
        tag=True,
        secondary=False,
    ):
        """Create a control.

        :param name: base name (composed with ``side`` by the naming convention)
        :param shape: library shape name or shape data (list of curve dicts)
        :param axis: axis the shape faces (``x``, ``-x``, ``y`` ...)
        :param offsets: type keys (``zero``, ``offset``, ``sdk``, ``space``) or
            raw suffixes for the groups created above the control, top first
        :param match: node to snap the control to
        :param lock: attributes to lock & hide (``t``, ``r``, ``s`` shortcuts)
        :param color_value: colour spec; defaults to the side colour
        """
        ctl_name = full_name or naming.compose(name, side, "control")
        ctl_name = naming.unique_name(ctl_name)
        if isinstance(shape, str):
            data = library.get_shape(shape)
        else:
            data = shape
        data = library.transform_shape(data, size=size, axis=axis, offset=shape_offset)
        node = shapes.create_curves(data, ctl_name)

        # offset groups, top -> bottom
        groups = []
        base = ctl_name
        ctl_suffix = naming.suffix("control")
        if base.endswith("_" + ctl_suffix):
            base = base[: -len(ctl_suffix) - 1]
        current_parent = parent
        for key in offsets or ():
            group_name = naming.unique_name("%s_%s" % (base, naming.suffix(key)))
            group = cmds.createNode("transform", name=group_name, skipSelect=True)
            if current_parent:
                group = cmds.parent(group, current_parent, relative=True)[0]
            groups.append(group)
            current_parent = group
        if current_parent:
            node = cmds.parent(node, current_parent, relative=True)[0]

        top = groups[0] if groups else node
        if match:
            cmds.matchTransform(top, match, position=True, rotation=match_rotation, scale=False)
        elif position is not None:
            cmds.xform(top, worldSpace=True, translation=position)

        if rotate_order is not None:
            order = rotate_order if isinstance(rotate_order, int) else "xyz yzx zxy xzy yxz zyx".split().index(
                rotate_order)
            cmds.setAttr(node + ".rotateOrder", order)

        if color_value is None:
            color_value = color.side_color(side or naming.side_from_name(ctl_name), secondary=secondary)
        color.set_color(node, color_value)
        if line_width:
            shapes.set_line_width(node, line_width)

        ctl = cls(node)
        ctl._tag(side, groups, tag)
        if lock:
            attributes.lock_hide(node, lock)
        return ctl

    def _tag(self, side, groups, controller_tag):
        attributes.add_attr(self.node, CONTROL_ATTR, "bool", default=True, keyable=False)
        cmds.setAttr("%s.%s" % (self.node, CONTROL_ATTR), True, lock=True)
        attributes.set_string(self.node, SIDE_ATTR, side or "")
        cmds.setAttr("%s.%s" % (self.node, SIDE_ATTR), lock=True)
        attributes.add_attr(self.node, OFFSETS_ATTR, "message", multi=True)
        for i, group in enumerate(groups):
            cmds.connectAttr(group + ".message", "%s.%s[%d]" % (self.node, OFFSETS_ATTR, i), force=True)
        if controller_tag:
            try:
                cmds.controller(self.node)
            except RuntimeError:
                pass

    # ------------------------------------------------------------------
    @property
    def name(self):
        return self.node

    @property
    def offsets(self):
        """Offset groups above the control (top first)."""
        if not cmds.attributeQuery(OFFSETS_ATTR, node=self.node, exists=True):
            return []
        indices = cmds.getAttr("%s.%s" % (self.node, OFFSETS_ATTR), multiIndices=True) or []
        result = []
        for index in indices:
            sources = cmds.listConnections("%s.%s[%d]" % (self.node, OFFSETS_ATTR, index), source=True,
                                           destination=False) or []
            result.extend(sources)
        return result

    @property
    def zero(self):
        """Top most offset group (or the control itself)."""
        offsets = self.offsets
        return offsets[0] if offsets else self.node

    @property
    def last_offset(self):
        """Offset group directly above the control (or the control's parent)."""
        offsets = self.offsets
        return offsets[-1] if offsets else dag.get_parent(self.node)

    @property
    def side(self):
        return attributes.get_string(self.node, SIDE_ATTR) or naming.side_from_name(self.node)

    @property
    def shapes(self):
        return shapes.curve_shapes(self.node)

    # ------------------------------------------------------------------
    def set_color(self, value):
        color.set_color(self.node, value)

    def set_shape(self, shape, size=None, axis="y"):
        shapes.replace_shape(self.node, shape, size=size, axis=axis)

    def scale_shape(self, factor):
        shapes.scale_shapes(self.node, factor)

    def rotate_shape(self, rotation):
        shapes.rotate_shapes(self.node, rotation)

    def lock_hide(self, attrs):
        attributes.lock_hide(self.node, attrs)

    def add_attr(self, name, attr_type="float", **kwargs):
        return attributes.add_attr(self.node, name, attr_type, **kwargs)

    def add_separator(self, label="settings"):
        return attributes.add_separator(self.node, label)

    def add_offset(self, suffix="OFF"):
        """Insert an extra group directly above the control."""
        group = dag.insert_parent(self.node, naming.unique_name("%s_%s" % (self.node, suffix)))
        indices = cmds.getAttr("%s.%s" % (self.node, OFFSETS_ATTR), multiIndices=True) or []
        index = (max(indices) + 1) if indices else 0
        cmds.connectAttr(group + ".message", "%s.%s[%d]" % (self.node, OFFSETS_ATTR, index), force=True)
        return group

    def set_parent_tag(self, parent_control):
        """Set the controller tag parent (used by pick walking / evaluation)."""
        try:
            cmds.controller(self.node, parent_control, parent=True)
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def is_control(node):
    return cmds.attributeQuery(CONTROL_ATTR, node=node, exists=True)


def list_controls(namespace=None):
    """Every toolkit control in the scene (optionally inside a namespace)."""
    patterns = ["*.%s" % CONTROL_ATTR, "*:*.%s" % CONTROL_ATTR]
    if namespace:
        patterns = ["%s:*.%s" % (namespace.rstrip(":"), CONTROL_ATTR)]
    result = []
    for pattern in patterns:
        for node in cmds.ls(pattern, objectsOnly=True) or []:
            if node not in result:
                result.append(node)
    return result


def tag_as_control(nodes, side=None):
    """Turn existing curves into toolkit controls (adds tag attributes)."""
    if isinstance(nodes, str):
        nodes = [nodes]
    result = []
    for node in nodes:
        ctl = Control(node)
        if not is_control(node):
            ctl._tag(side or naming.side_from_name(node), [], True)
        result.append(ctl)
    return result


def create_on_nodes(nodes, shape="circle", size=1.0, axis="x", suffix_replace=("JNT", "CTL"), offsets=("zero",),
                    parent_hierarchy=True, color_value=None):
    """Create one control matching each node.

    Names are derived from the node names (``L_arm_JNT`` -> ``L_arm_CTL``).
    When ``parent_hierarchy`` is on and the nodes form a hierarchy, the
    controls are parented the same way (great for quick FK setups).
    """
    controls = []
    by_node = {}
    for node in nodes:
        short = naming.strip_namespace(node)
        old, new = suffix_replace
        if short.endswith("_" + old):
            ctl_name = short[: -len(old)] + new
        else:
            ctl_name = short + "_" + naming.suffix("control")
        side = naming.side_from_name(short)
        ctl = Control.create(full_name=ctl_name, side=side, shape=shape, size=size, axis=axis, offsets=offsets,
                             match=node, color_value=color_value)
        controls.append(ctl)
        by_node[dag.long_name(node)] = ctl
    if parent_hierarchy:
        for node in nodes:
            ctl = by_node[dag.long_name(node)]
            parent = dag.get_parent(node)
            while parent:
                if parent in by_node:
                    cmds.parent(ctl.zero, by_node[parent].node)
                    ctl.set_parent_tag(by_node[parent].node)
                    break
                parent = dag.get_parent(parent)
    return controls
