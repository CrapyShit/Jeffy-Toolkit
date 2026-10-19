"""Course style spine (video 4): no IK spline, one control per spine joint.

::

    cog > spine controls (each under the previous) ...
        > hips (separate branch: sways the pelvis without moving the chest)

The COG drives the first spine joint, every following spine joint gets its own
control, and the optional pelvis/root joint is driven by the hips control. All
joints are parent constrained with offset (the course's spine joints are not
aligned with their controls). Squash and stretch comes from moving controls.
"""

from maya import cmds

from jeffy.core import naming
from jeffy.rig.flexible import common


def _label(joint):
    return naming.parse(joint)["name"] or naming.strip_namespace(joint)


def build_direct_spine(spine_joints, pelvis=None, name="spine", side="C", control_parent=None, size=1.0,
                       shapes=None):
    """Build the direct spine on ``spine_joints`` (bottom -> top).

    :param pelvis: joint driven by the hips control (usually the root/pelvis)
    :returns: dict with ``cog``, ``hips`` (or None), ``controls`` (spine
        controls, the first one being the COG) and ``group``
    """
    spine_joints = [naming.short_name(j) for j in spine_joints]
    if not spine_joints:
        raise ValueError("Select spine joints")
    shapes = dict({"cog": "cog", "hips": "hip", "spine": "circle"}, **(shapes or {}))
    icons = common.group(name + "Controls", side, parent=control_parent)
    cog = common.control(name + "Cog", side, shapes["cog"], size * 1.5, "y", parent=icons, match=spine_joints[0],
                         match_rotation=False, lock=("s", "v"))
    cmds.parentConstraint(cog.node, spine_joints[0], maintainOffset=True)
    controls = [cog]
    parent = cog.node
    for joint in spine_joints[1:]:
        ctl = common.control(_label(joint), side, shapes["spine"], size, "y", parent=parent, match=joint,
                             match_rotation=False, lock=("s", "v"))
        ctl.set_parent_tag(parent)
        cmds.parentConstraint(ctl.node, joint, maintainOffset=True)
        controls.append(ctl)
        parent = ctl.node
    hips = None
    if pelvis:
        hips = common.control(name + "Hips", side, shapes["hips"], size * 1.2, "y", parent=cog.node,
                              match=pelvis, match_rotation=False, lock=("s", "v"))
        hips.set_parent_tag(cog.node)
        cmds.parentConstraint(hips.node, pelvis, maintainOffset=True)
    common.lock_free([c.zero for c in controls] + ([hips.zero] if hips else []))
    return {"cog": cog, "hips": hips, "controls": controls, "group": icons}
