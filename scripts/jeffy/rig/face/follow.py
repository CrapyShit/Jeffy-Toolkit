"""Partial follow: a control follows another node by a percentage.

The base of face rigging: lip corners follow the jaw by half, cheeks follow
the lip corners a little, the nose follows the upper lip, eyelids follow the
eye ("fleshy eyes")... Each follow is an animatable 0..1 attribute.

::

    from jeffy.rig.face import follow
    follow.add_follow("L_cheek_CTL", "L_lipCorner_CTL", default=0.3)
    follow.add_follow("L_upperLidMain_CTL", "L_eye_JNT", mode="orient", pivot="L_eye_JNT",
                      attr="eyeFollow", default=0.3)
"""

from maya import cmds

from jeffy.controls.control import Control
from jeffy.core import attributes, dag, naming, nodes, transform
from jeffy.rig import common

MODES = ("parent", "orient", "point")


def top_group(node):
    """The highest offset group of a toolkit control (its ``ZRO``), else the node."""
    try:
        return Control(node).zero
    except (ValueError, RuntimeError):
        return node


def add_follow(driven, driver, rest=None, holder=None, attr="follow", default=0.5, mode="parent", pivot=None,
               name=None):
    """Make ``driven`` follow ``driver`` by the ``attr`` percentage.

    A ``...Follow`` group is inserted above the driven control's top group
    and constrained between ``rest`` (0: where it is now, following its own
    parent) and ``driver`` (1: fully following the driver).

    :param rest: node the control follows at 0 (default: its current parent)
    :param holder: node receiving the attribute (default: the driven control)
    :param mode: ``parent``, ``orient`` or ``point`` constraint
    :param pivot: node or position the follow rotates around (``orient``
        mode: use the eye joint to slide lids around the eyeball)
    :returns: the attribute plug
    """
    if mode not in MODES:
        raise ValueError("mode must be one of %s" % (MODES,))
    top = top_group(driven)
    base = name or naming.parse(driven)["name"] or naming.short_name(driven)
    side = naming.parse(driven)["side"]
    group = dag.insert_parent(top, naming.unique_name(naming.compose(base + "Follow", side, "group")))
    if pivot is not None:
        position = transform.get_position(pivot) if isinstance(pivot, str) else tuple(pivot)
        cmds.xform(group, worldSpace=True, pivots=position)
    if rest is None:
        parent = dag.get_parent(group)
        rest = common.create_locator(naming.compose(base + "FollowRest", side, "locator"), parent=parent)
        cmds.matchTransform(rest, group, position=True, rotation=True)
    command = {"parent": cmds.parentConstraint, "orient": cmds.orientConstraint, "point": cmds.pointConstraint}[mode]
    constraint = command(rest, driver, group, maintainOffset=True)[0]
    if mode != "point":
        cmds.setAttr(constraint + ".interpType", 2)
    holder = holder or driven
    plug = attributes.add_attr(holder, attr, "float", default=default, minimum=0.0, maximum=1.0)
    weights = common.constraint_weight_plugs(constraint)
    cmds.connectAttr(nodes.reverse(plug, name=naming.compose(base + attr.title(), side, "reverse")), weights[0])
    cmds.connectAttr(plug, weights[1])
    return plug
