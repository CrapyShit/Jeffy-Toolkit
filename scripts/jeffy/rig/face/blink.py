"""Eyelid blink on top of two curve rigs (upper and lower lid).

::

    from jeffy.rig.face import blink, curve_rig
    upper = curve_rig.build_curve_rig(edges=..., name="upperLid", side="L", center="L_eye_JNT")
    lower = curve_rig.build_curve_rig(edges=..., name="lowerLid", side="L", center="L_eye_JNT")
    blink.build_blink(upper["main"].node, lower["main"].node, attr_holder="L_eye_CTL")

``blink`` (0..1) closes both lids. They meet on a *blink line* that follows
the animated lid controls; ``blinkHeight`` (0 upper lid ... 1 lower lid) sets
where it sits. The blink line is a blend of the upper and lower low curves,
each lid's high curve gets a blendshape towards a copy wired to that line.
"""

from maya import cmds

from jeffy.core import attributes, naming, nodes
from jeffy.rig.face import common as face_common


def _data(node):
    main, data = face_common.find_rig(node)
    if not data:
        raise ValueError("%s is not part of a face curve rig (select the rig's Main control)" % node)
    if "low" not in data:
        raise ValueError("%s is a face ribbon: blink / lip seal need curve rigs (Curve Rig From Edge Loop)" % node)
    return main, data


def build_blink(upper, lower, attr_holder=None, name="blink", side=None, height=0.2, attr="blink",
                height_attr="blinkHeight"):
    """Add ``blink`` / ``blinkHeight`` to ``attr_holder`` (default: the upper rig's main control).

    :param upper: any node of the upper lid curve rig (its main control)
    :param lower: any node of the lower lid curve rig
    :param attr, height_attr: attribute names (``seal`` / ``sealHeight`` to
        seal lips: see :func:`build_lip_seal`)
    :returns: dict with the ``blink`` and ``height`` plugs and the blink ``curve``
    """
    upper_main, up = _data(upper)
    _lower_main, low = _data(lower)
    holder = attr_holder or upper_main
    if len(up["controls"]) != len(low["controls"]):
        raise ValueError("The upper and lower lid rigs need the same number of controls")

    attributes.add_separator(holder, attr)
    blink = attributes.add_attr(holder, attr, "float", default=0.0, minimum=0.0, maximum=1.0)
    blink_height = attributes.add_attr(holder, height_attr, "float", default=height, minimum=0.0, maximum=1.0)

    # blink line: (1 - height) * upper + height * lower
    line = face_common.clean_duplicate(up["low"], naming.compose(name + "Line", side, "curve"))
    line_bs = cmds.blendShape(up["low"], low["low"], line, name=naming.compose(name + "Line", side, "blendshape"))[0]

    targets = {}
    for key, data, weights in (("upper", up, (1.0, 0.0)), ("lower", low, (0.0, 1.0))):
        # the wire base is captured with the line sitting on this lid, so the
        # copy moves by how far the line is from that lid
        cmds.setAttr(line_bs + ".weight[0]", weights[0])
        cmds.setAttr(line_bs + ".weight[1]", weights[1])
        target = face_common.clean_duplicate(data["high"], naming.compose(name + key.title(), side, "curve"))
        face_common.wire(target, line, name=face_common.label(name + key.title(), side, "WIRE"))
        bs = cmds.blendShape(target, data["high"], frontOfChain=True,
                             name=naming.compose(name + key.title(), side, "blendshape"))[0]
        cmds.connectAttr(blink, bs + ".weight[0]")
        targets[key] = target
    cmds.connectAttr(nodes.reverse(blink_height, name=naming.compose(name + "Height", side, "reverse")),
                     line_bs + ".weight[0]", force=True)
    cmds.connectAttr(blink_height, line_bs + ".weight[1]", force=True)
    return {"blink": blink, "height": blink_height, "curve": line, "targets": targets}


def build_lip_seal(upper, lower, attr_holder=None, name="lipSeal", side=None, height=0.5):
    """Seal the lips (``seal`` / ``sealHeight``) on two lip curve rigs: the
    same network as the blink, the lips meet on a line between them."""
    return build_blink(upper, lower, attr_holder=attr_holder, name=name, side=side, height=height, attr="seal",
                       height_attr="sealHeight")
