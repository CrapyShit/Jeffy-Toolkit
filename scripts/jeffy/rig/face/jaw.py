"""Jaw control with lips following it.

::

    from jeffy.rig.face import jaw
    jaw.build_jaw("C_jaw_JNT", upper_lip="C_upperLipMain_CTL", lower_lip="C_lowerLipMain_CTL")

The jaw control rotates the jaw joint. With lip rigs (face ribbons or curve
rigs) the lower lip follows the jaw fully, the upper lip a little and the
lip corners halfway - each one an attribute on the jaw control
(``lowerLipFollow``, ``upperLipFollow``, ``cornerFollow``).
"""

from maya import cmds

from jeffy.controls.control import Control
from jeffy.core import attributes, dag
from jeffy.rig.face import follow
from jeffy.rig.face import ribbon as face_ribbon


def build_jaw(jaw_joint, name="jaw", side="C", head=None, control_parent=None, size=1.0, upper_lip=None,
              lower_lip=None, lower_follow=1.0, upper_follow=0.1, corner_follow=0.5, shape="circle",
              color_value=None):
    """Jaw control on ``jaw_joint`` and optional lip follow.

    :param head: the head-space node the lips follow at 0 (default: the jaw
        joint's parent)
    :param upper_lip, lower_lip: Main controls of the lip rigs
    :returns: dict with ``control`` and the follow attribute plugs
    """
    head = head or dag.get_parent(jaw_joint)
    ctl = Control.create(name, side=side, shape=shape, size=size,
                         axis="z", parent=control_parent, match=jaw_joint, offsets=("zero",),
                         lock=("s", "v"), color_value=color_value)
    cmds.parentConstraint(ctl.node, jaw_joint, maintainOffset=True)
    result = {"control": ctl, "plugs": {}}
    if not (upper_lip or lower_lip):
        return result
    if not head:
        raise ValueError("The lips need a head space: the jaw joint has no parent (pass head=...)")
    attributes.add_separator(ctl.node, "lips")
    jobs = []
    if lower_lip:
        jobs.append((lower_lip, "lowerLipFollow", lower_follow))
    if upper_lip:
        jobs.append((upper_lip, "upperLipFollow", upper_follow))
    for main, attr, default in jobs:
        result["plugs"][attr] = follow.add_follow(main, ctl.node, rest=head, holder=ctl.node, attr=attr,
                                                  default=default)
    corners = []
    for main in (upper_lip, lower_lip):
        if main:
            corners.extend(face_ribbon.corner_controls(main))
    if corners:
        plug = attributes.add_attr(ctl.node, "cornerFollow", "float", default=corner_follow, minimum=0.0,
                                   maximum=1.0)
        for corner in corners:
            corner_plug = follow.add_follow(corner, ctl.node, rest=head, holder=corner, attr="jawFollow",
                                            default=corner_follow)
            cmds.connectAttr(plug, corner_plug, force=True)
        result["plugs"]["cornerFollow"] = plug
    return result
