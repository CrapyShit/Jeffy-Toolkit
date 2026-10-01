"""Pose tools for rigs: reset, bind pose, save/load, mirror and flip.

Mirroring works out, per control pair, how each local axis maps across the
mirror plane (by comparing the *rest* frames of the two controls), so it
handles behaviour-mirrored joints, world aligned IK controls and centre
controls without any per-rig configuration.
"""

import json

from maya import cmds

from jeffy.controls.control import list_controls
from jeffy.core import attributes, fileio, mathlib, matrix, naming

BIND_POSE_ATTR = "jeffyBindPose"
TRANSLATE = ("translateX", "translateY", "translateZ")
ROTATE = ("rotateX", "rotateY", "rotateZ")
SHORT = {"tx": "translateX", "ty": "translateY", "tz": "translateZ", "rx": "rotateX", "ry": "rotateY",
         "rz": "rotateZ"}


def get_controls(nodes=None, namespace=None):
    """Controls to work on: given nodes, the selection, or every control."""
    if nodes:
        return list(nodes)
    selection = cmds.ls(selection=True) or []
    if selection:
        return selection
    return list_controls(namespace)


def _keyable(node):
    return cmds.listAttr(node, keyable=True, unlocked=True, scalar=True) or []


def get_pose(controls=None):
    """``{control_short_name: {attr: value}}`` of keyable attributes."""
    pose = {}
    for control in get_controls(controls):
        values = {}
        for attr in _keyable(control):
            value = cmds.getAttr("%s.%s" % (control, attr))
            if isinstance(value, (int, float, bool)):
                values[attr] = value
        pose[naming.strip_namespace(control)] = values
    return pose


def apply_pose(pose, namespace="", blend=1.0, controls=None):
    """Apply a pose dictionary (optionally blended with the current pose)."""
    wanted = set(naming.strip_namespace(c) for c in controls) if controls else None
    for name, values in pose.items():
        if wanted is not None and name not in wanted:
            continue
        node = "%s:%s" % (namespace, name) if namespace else name
        if not cmds.objExists(node):
            continue
        for attr, value in values.items():
            plug = "%s.%s" % (node, attr)
            if not cmds.objExists(plug) or not cmds.getAttr(plug, settable=True):
                continue
            if blend < 1.0:
                value = mathlib.lerp(cmds.getAttr(plug), value, blend)
            cmds.setAttr(plug, value)


def reset(controls=None):
    """Set every keyable attribute of the controls to its default value."""
    attributes.reset(get_controls(controls))


def save_pose(path, controls=None):
    return fileio.write_json(path, {"type": "jeffy_pose", "version": fileio.FORMAT_VERSION,
                                    "pose": get_pose(controls)})


def load_pose(path, namespace="", blend=1.0, controls=None):
    data = fileio.read_json(path)
    apply_pose(data["pose"], namespace, blend, controls)


# ---------------------------------------------------------------------------
# Bind pose
# ---------------------------------------------------------------------------
def store_bind_pose(controls=None):
    """Store the current values as each control's bind pose."""
    for control in get_controls(controls):
        values = get_pose([control])[naming.strip_namespace(control)]
        plug = "%s.%s" % (control, BIND_POSE_ATTR)
        if cmds.objExists(plug):
            cmds.setAttr(plug, lock=False)
        attributes.set_string(control, BIND_POSE_ATTR, json.dumps(values))
        cmds.setAttr(plug, lock=True)


def go_to_bind_pose(controls=None):
    """Restore stored bind poses (controls without one are reset)."""
    for control in get_controls(controls):
        raw = attributes.get_string(control, BIND_POSE_ATTR)
        if raw:
            apply_pose({naming.strip_namespace(control): json.loads(raw)},
                       namespace=naming.get_namespace(control))
        else:
            attributes.reset(control)


# ---------------------------------------------------------------------------
# Mirroring
# ---------------------------------------------------------------------------
def mirror_signs(source, target, axis="x"):
    """Per-axis signs mapping ``source`` local values onto ``target``."""
    return mathlib.mirror_axis_signs(matrix.get_rest_matrix(source), matrix.get_rest_matrix(target), axis)


def mirrored_values(source, target, axis="x"):
    """Values to give ``target`` so it mirrors ``source``'s current pose."""
    signs = mirror_signs(source, target, axis)
    result = {}
    target_attrs = set(_keyable(target))
    for attr in _keyable(source):
        if attr not in target_attrs:
            continue
        value = cmds.getAttr("%s.%s" % (source, attr))
        if isinstance(value, bool):
            result[attr] = value
            continue
        if not isinstance(value, (int, float)):
            continue
        long_name = SHORT.get(attr, attr)
        if long_name in TRANSLATE:
            value = value * signs[TRANSLATE.index(long_name)]
        elif long_name in ROTATE:
            value = -value * signs[ROTATE.index(long_name)]
        result[attr] = value
    return result


def _pairs(controls):
    pairs = []
    seen = set()
    for control in controls:
        if control in seen:
            continue
        other = naming.find_mirror_node(control)
        if other:
            seen.update((control, other))
        else:
            seen.add(control)
        pairs.append((control, other))
    return pairs


def mirror_pose(controls=None, axis="x", source_side=None):
    """Copy the pose of one side onto the other.

    Selected controls are the sources (their counterparts receive the pose).
    With ``source_side="L"`` every left control is mirrored to the right.
    Centre controls are mirrored onto themselves.
    """
    controls = get_controls(controls)
    if source_side:
        controls = [c for c in controls if naming.side_from_name(c) == source_side]
    updates = []
    for control in controls:
        other = naming.find_mirror_node(control)
        target = other or control
        updates.append((target, mirrored_values(control, target, axis)))
    for target, values in updates:
        apply_pose({naming.strip_namespace(target): values}, namespace=naming.get_namespace(target))


def flip_pose(controls=None, axis="x"):
    """Swap left and right poses (and mirror centre controls)."""
    controls = get_controls(controls)
    updates = []
    for control, other in _pairs(controls):
        if other:
            updates.append((other, mirrored_values(control, other, axis)))
            updates.append((control, mirrored_values(other, control, axis)))
        else:
            updates.append((control, mirrored_values(control, control, axis)))
    for target, values in updates:
        apply_pose({naming.strip_namespace(target): values}, namespace=naming.get_namespace(target))


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------
def select_controls(namespace=None):
    controls = list_controls(namespace)
    cmds.select(controls, replace=True)
    return controls


def key_controls(controls=None):
    controls = get_controls(controls)
    cmds.setKeyframe(controls)
    return controls


def create_control_set(name="controls_SET", controls=None):
    controls = controls if controls is not None else list_controls()
    if cmds.objExists(name):
        cmds.sets(controls, addElement=name)
        return name
    return cmds.sets(controls, name=name)
