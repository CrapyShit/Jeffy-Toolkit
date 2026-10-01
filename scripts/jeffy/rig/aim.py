"""Aim rigs (eyes, look-at controls, aim chains)."""

from maya import cmds

from jeffy.controls.control import Control
from jeffy.core import mathlib, matrix, naming, transform


def _best_axis(node, direction):
    """Local axis of ``node`` most aligned with a world ``direction``."""
    axes = mathlib.axes(matrix.get_world_matrix(node))[:3]
    best = max(range(3), key=lambda i: abs(mathlib.dot(mathlib.normalize(axes[i]), direction)))
    sign = 1.0 if mathlib.dot(axes[best], direction) >= 0 else -1.0
    vector = [0.0, 0.0, 0.0]
    vector[best] = sign
    return tuple(vector)


def build_eye_rig(eyes, name="eyes", side="C", distance=10.0, forward=(0.0, 0.0, 1.0), control_parent=None,
                  up_object=None, size=1.0):
    """Look-at rig for one or more eye joints/transforms.

    A master aim control is placed ``distance`` units in front of the eyes,
    with one child control per eye. Eyes are aim constrained (offset kept)
    with ``up_object`` (usually the head control) as rotation up.
    """
    forward = mathlib.normalize(forward)
    eye_positions = [transform.get_position(e) for e in eyes]
    center = mathlib.centroid(eye_positions)
    master_pos = mathlib.add(center, mathlib.scale(forward, distance))
    spread = max([mathlib.distance(p, center) for p in eye_positions] + [size])
    master = Control.create(name + "Aim", side=side, shape="capsule" if len(eyes) > 1 else "circle",
                            size=spread * 1.6 if len(eyes) > 1 else size, axis="z", parent=control_parent,
                            position=master_pos, offsets=("zero", "space"), lock=("s", "v"))
    controls = []
    for eye, position in zip(eyes, eye_positions):
        parsed = naming.parse(eye)
        eye_side = parsed["side"] or naming.side_from_name(eye) or side
        label = (parsed["name"] or naming.strip_namespace(eye)) + "Aim"
        target = mathlib.add(position, mathlib.scale(forward, distance))
        ctl = Control.create(label, side=eye_side, shape="circle", size=size * 0.5, axis="z", parent=master.node,
                             position=target, lock=("r", "s", "v"))
        ctl.set_parent_tag(master.node)
        aim_vector = _best_axis(eye, forward)
        kwargs = {"maintainOffset": True, "aimVector": aim_vector, "upVector": (0, 1, 0)}
        if up_object:
            kwargs.update(worldUpType="objectrotation", worldUpObject=up_object, worldUpVector=(0, 1, 0))
        else:
            kwargs.update(worldUpType="vector", worldUpVector=(0, 1, 0))
        cmds.aimConstraint(ctl.node, eye, **kwargs)
        controls.append(ctl)
    return {"master": master, "controls": controls}


def aim_chain(nodes_list, target, up_object=None, aim_axis=(1, 0, 0), up_axis=(0, 1, 0)):
    """Aim each node at the next one; the last node aims at ``target``."""
    constraints = []
    for i, node in enumerate(nodes_list):
        aim_target = nodes_list[i + 1] if i + 1 < len(nodes_list) else target
        kwargs = {"aimVector": aim_axis, "upVector": up_axis, "maintainOffset": False}
        if up_object:
            kwargs.update(worldUpType="objectrotation", worldUpObject=up_object, worldUpVector=up_axis)
        constraints.append(cmds.aimConstraint(aim_target, node, **kwargs)[0])
    return constraints
