"""Space switching (dynamic parenting) with seamless switching.

::

    from jeffy.rig import space_switch
    space_switch.create("L_armIK_CTL", [("world", "C_global_CTL"),
                                         ("chest", "C_chest_CTL"),
                                         ("head", "C_head_CTL")])
    space_switch.switch("L_armIK_CTL", "chest")   # no pop, pose is kept

Two methods are available:

* ``constraint`` - a parent/orient/point constraint whose weights are driven
  by condition nodes (works everywhere, supports blending modes).
* ``matrix`` - a ``choice`` node selecting pre-multiplied matrices plugged
  into ``offsetParentMatrix`` (Maya 2020+, faster, parent mode only).
"""

import json

from maya import cmds

from jeffy.controls.control import Control
from jeffy.core import attributes, mathlib, matrix, naming, nodes, transform
from jeffy.rig import common

MODES = ("parent", "orient", "point")
METHODS = ("constraint", "matrix")
SPACES_ATTR = "jeffySpaces"


def _driven_for(control):
    """Default driven node: the offset group directly above the control."""
    try:
        ctl = Control(control)
        offsets = ctl.offsets
        if offsets:
            return offsets[-1]
    except ValueError:
        pass
    parent = cmds.listRelatives(control, parent=True)
    if not parent:
        raise ValueError("%s has no parent group to drive - add an offset group first" % control)
    return parent[0]


def create(control, spaces, driven=None, attr="space", mode="parent", method="constraint", default=0,
           attr_node=None):
    """Add a space switch to ``control``.

    :param spaces: list of ``(label, target)`` tuples (or a dict)
    :param driven: node receiving the constraint, defaults to the offset
        group directly above the control
    :param attr_node: node holding the enum attribute (defaults to control)
    :returns: the enum attribute plug
    """
    if mode not in MODES:
        raise ValueError("mode must be one of %s" % (MODES,))
    if method not in METHODS:
        raise ValueError("method must be one of %s" % (METHODS,))
    if isinstance(spaces, dict):
        spaces = list(spaces.items())
    spaces = [(label, target) for label, target in spaces if target and cmds.objExists(target)]
    if not spaces:
        raise ValueError("No valid space targets")
    driven = driven or _driven_for(control)
    attr_node = attr_node or control
    labels = [label for label, _target in spaces]
    targets = [target for _label, target in spaces]

    attributes.add_separator(attr_node, "spaces")
    enum = attributes.add_attr(attr_node, attr, "enum", enum_names=labels, default=min(default, len(labels) - 1))
    attributes.set_string(control, SPACES_ATTR, json.dumps({"attr": "%s.%s" % (attr_node, attr), "labels": labels}))

    base = naming.short_name(control) + "_" + attr
    if method == "matrix":
        if mode != "parent":
            raise ValueError("The matrix method only supports parent mode")
        _matrix_switch(driven, targets, enum, base)
    else:
        _constraint_switch(driven, targets, enum, mode, base)
    return enum


def _constraint_switch(driven, targets, enum, mode, base):
    command = {"parent": cmds.parentConstraint, "orient": cmds.orientConstraint, "point": cmds.pointConstraint}[mode]
    constraint = command(targets + [driven], maintainOffset=True, name=naming.unique_name(base + "_CON"))[0]
    if mode in ("parent", "orient"):
        cmds.setAttr(constraint + ".interpType", 2)
    for i, weight in enumerate(common.constraint_weight_plugs(constraint)):
        condition = nodes.condition(enum, "==", i, 1.0, 0.0, name="%s%d_COND" % (base, i))
        cmds.connectAttr(condition, weight, force=True)
    return constraint


def _matrix_switch(driven, targets, enum, base):
    transform.bake_to_offset_parent_matrix(driven)
    rest_world = matrix.get_world_matrix(driven)
    transform.reset(driven)
    choice = cmds.createNode("choice", name=naming.unique_name(base + "_CHOICE"), skipSelect=True)
    cmds.connectAttr(enum, choice + ".selector")
    for i, target in enumerate(targets):
        offset = mathlib.mult(rest_world, mathlib.inverse(matrix.get_world_matrix(target)))
        mm = cmds.createNode("multMatrix", name=naming.unique_name("%s%d_MM" % (base, i)), skipSelect=True)
        matrix.set_matrix_attr(mm + ".matrixIn[0]", offset)
        cmds.connectAttr(target + ".worldMatrix[0]", mm + ".matrixIn[1]")
        cmds.connectAttr(driven + ".parentInverseMatrix[0]", mm + ".matrixIn[2]")
        cmds.connectAttr(mm + ".matrixSum", "%s.input[%d]" % (choice, i))
    cmds.connectAttr(choice + ".output", driven + ".offsetParentMatrix", force=True)
    return choice


def get_spaces(control):
    """Return ``(attr_plug, labels)`` of a control's space switch (or None)."""
    raw = attributes.get_string(control, SPACES_ATTR)
    if raw:
        data = json.loads(raw)
        return data["attr"], data["labels"]
    if cmds.attributeQuery("space", node=control, exists=True):
        labels = cmds.attributeQuery("space", node=control, listEnum=True)[0].split(":")
        return control + ".space", labels
    return None


def switch(control, space, match=True, key=False):
    """Change space without moving the control (seamless switch).

    ``space`` may be the label or the index. With ``key=True`` the control
    and switch attribute are keyed on the previous and current frame.
    """
    info = get_spaces(control)
    if not info:
        raise ValueError("%s has no space switch" % control)
    plug, labels = info
    index = labels.index(space) if isinstance(space, str) else int(space)
    world = matrix.get_world_matrix(control)
    if key:
        frame = cmds.currentTime(query=True)
        cmds.setKeyframe(control, time=frame - 1)
        cmds.setKeyframe(plug, time=frame - 1)
    cmds.setAttr(plug, index)
    if match:
        matrix.set_world_matrix(control, world, scale=False)
    if key:
        cmds.setKeyframe(control)
        cmds.setKeyframe(plug)
    return labels[index]


def switch_selected(space, key=False):
    done = []
    for control in cmds.ls(selection=True) or []:
        info = get_spaces(control)
        if info and (not isinstance(space, str) or space in info[1]):
            switch(control, space, key=key)
            done.append(control)
    return done
