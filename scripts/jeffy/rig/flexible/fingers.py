"""Course style fingers (video 5): plain FK controls following the wrist.

Differs from :mod:`jeffy.rig.fingers`: no SDK groups or curl/fist attributes,
every joint (tip included) gets a control, and all finger controls live in a
hand group that follows the wrist joint through a parent constraint.
"""

from maya import cmds

from jeffy.core import dag, naming, transform
from jeffy.rig.flexible import common


def build_fingers(roots, side=None, wrist=None, control_parent=None, size=0.3, shape="circle", include_tips=True):
    """FK controls for the finger chains starting at ``roots``.

    :param wrist: joint the hand group follows (default: parent of the first root)
    :returns: dict with ``group`` and ``controls`` ``{root: [Control, ...]}``
    """
    roots = [naming.short_name(r) for r in roots]
    if not roots:
        raise ValueError("Select finger root joints")
    side = side if side is not None else naming.side_from_name(roots[0])
    wrist = wrist or (cmds.listRelatives(roots[0], parent=True) or [None])[0]
    hand = common.group("handControls", side, parent=control_parent)
    if wrist:
        cmds.xform(hand, worldSpace=True, pivots=transform.get_position(wrist))
        cmds.parentConstraint(wrist, hand, maintainOffset=True)
    controls = {}
    for root in roots:
        chain = [naming.short_name(j) for j in dag.get_chain(root)]
        if not include_tips and len(chain) > 1:
            chain = chain[:-1]
        parent = hand
        ctls = []
        for joint in chain:
            label = naming.parse(joint)["name"] or naming.strip_namespace(joint)
            ctl = common.control(label, side, shape, size, "x", parent=parent, match=joint)
            if ctls:
                ctl.set_parent_tag(ctls[-1].node)
            cmds.parentConstraint(ctl.node, joint, maintainOffset=False)
            ctls.append(ctl)
            parent = ctl.node
        common.lock_free([c.zero for c in ctls])
        controls[root] = ctls
    return {"group": hand, "controls": controls}
