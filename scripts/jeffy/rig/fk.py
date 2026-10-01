"""FK chains."""

from maya import cmds

from jeffy.controls.control import Control
from jeffy.core import naming
from jeffy.rig import matrix_constraints

CONNECT_MODES = ("constraint", "matrix", "none")


def _name_from_joint(joint):
    parsed = naming.parse(joint)
    return parsed["name"] or naming.strip_namespace(joint), parsed["side"]


def build_fk_chain(
    joints,
    name=None,
    side=None,
    shape="circle",
    size=1.0,
    axis="x",
    color_value=None,
    parent=None,
    connect="constraint",
    scale=True,
    lock=("v",),
    offsets=("zero",),
    skip_last=False,
    secondary=False,
):
    """Create a hierarchy of FK controls driving ``joints``.

    :param name: base name; ``None`` derives each control name from its joint
    :param connect: ``constraint`` (parent + scale constraints), ``matrix``
        (offsetParentMatrix based, Maya 2020+) or ``none``
    :param skip_last: do not create a control for the last joint (end joint)
    :returns: dict with ``controls`` (list of :class:`Control`), ``zero`` and
        ``constraints``
    """
    if connect not in CONNECT_MODES:
        raise ValueError("connect must be one of %s" % (CONNECT_MODES,))
    targets = list(joints[:-1] if skip_last else joints)
    controls = []
    constraints = []
    current_parent = parent
    for i, joint in enumerate(targets):
        if name:
            ctl_name = "%s%02d" % (name, i + 1) if len(targets) > 1 else name
            ctl_side = side
        else:
            ctl_name, joint_side = _name_from_joint(joint)
            ctl_side = side or joint_side
        ctl = Control.create(
            ctl_name,
            side=ctl_side,
            shape=shape,
            size=size,
            axis=axis,
            color_value=color_value,
            offsets=offsets,
            parent=current_parent,
            match=joint,
            lock=lock,
            secondary=secondary,
        )
        if controls:
            ctl.set_parent_tag(controls[-1].node)
        if connect == "constraint":
            constraints.append(cmds.parentConstraint(ctl.node, joint, maintainOffset=True)[0])
            if scale:
                constraints.append(cmds.scaleConstraint(ctl.node, joint, maintainOffset=True)[0])
        elif connect == "matrix":
            matrix_constraints.matrix_constraint(ctl.node, joint, maintain_offset=True, scale=scale)
        controls.append(ctl)
        current_parent = ctl.node
    return {
        "controls": controls,
        "zero": controls[0].zero if controls else None,
        "constraints": constraints,
    }


def fk_on_selection(shape="circle", size=1.0, axis="x", connect="constraint"):
    """Build an FK chain on the selected joint chain (first to last selected)."""
    from jeffy.core import dag

    selection = cmds.ls(selection=True, type="joint") or []
    if not selection:
        raise ValueError("Select joints")
    if len(selection) == 2:
        joints = [naming.short_name(j) for j in dag.get_chain(selection[0], selection[1])]
    elif len(selection) == 1:
        joints = [naming.short_name(j) for j in dag.get_chain(selection[0])]
    else:
        joints = selection
    return build_fk_chain(joints, shape=shape, size=size, axis=axis, connect=connect)
