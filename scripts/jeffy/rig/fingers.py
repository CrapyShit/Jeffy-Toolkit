"""Finger / hand controls with attribute driven poses (curl, fist, spread...).

Every finger control gets an ``SDK`` group between its zero group and the
control, so animators can still pose the fingers on top of the attributes.
"""

from maya import cmds

from jeffy.core import attributes, naming, nodes
from jeffy.rig import common, fk

DEGREES_PER_UNIT = 9.0  # attribute value 10 -> 90 degrees


def build_fingers(
    finger_chains,
    side=None,
    attr_holder=None,
    control_parent=None,
    size=0.3,
    curl_axis="z",
    spread_axis="y",
    shape="circle",
    skip_last=True,
    curl_sign=-1.0,
    color_value=None,
    base_index=None,
):
    """FK finger controls plus pose attributes.

    :param finger_chains: ``{"index": [joints...], "thumb": [...]}`` (ordered
        dict or list of ``(name, joints)`` pairs, thumb first ideally)
    :param attr_holder: control receiving the hand attributes (``fist``,
        ``spread``, ``relax``, ``<finger>Curl``)
    :param curl_axis: local joint axis fingers curl around
    :param curl_sign: flips the curl direction (depends on joint orientation)
    :param base_index: ``{finger: index}`` of the first control driven by the
        attributes (e.g. 1 to skip metacarpal controls); default 0
    :returns: dict ``{"controls": {finger: [Control]}, "attributes": {...}}``
    """
    if isinstance(finger_chains, dict):
        finger_chains = list(finger_chains.items())
    holder = attr_holder
    attrs = {}
    if holder:
        attributes.add_separator(holder, "fingers")
        attrs["fist"] = attributes.add_attr(holder, "fist", "float", default=0.0, minimum=-10.0, maximum=10.0)
        attrs["spread"] = attributes.add_attr(holder, "spread", "float", default=0.0, minimum=-10.0, maximum=10.0)
        attrs["relax"] = attributes.add_attr(holder, "relax", "float", default=0.0, minimum=-10.0, maximum=10.0)

    controls = {}
    non_thumb = [name for name, _chain in finger_chains if "thumb" not in name.lower()]
    center = (len(non_thumb) - 1) / 2.0
    for finger, joints in finger_chains:
        result = fk.build_fk_chain(joints, name=finger, side=side, shape=shape, size=size,
                                   axis=common.primary_axis(joints[1]).lstrip("-") if len(joints) > 1 else "x",
                                   parent=control_parent, offsets=("zero", "sdk"), skip_last=skip_last,
                                   color_value=color_value, secondary=True)
        ctls = result["controls"]
        controls[finger] = ctls
        if not holder:
            continue
        curl = attributes.add_attr(holder, finger + "Curl", "float", default=0.0, minimum=-10.0, maximum=10.0)
        attrs[finger + "Curl"] = curl
        is_thumb = "thumb" in finger.lower()
        total = nodes.add(curl, attrs["fist"], name=naming.compose(finger + "Curl", side, "utility"))
        scaled = nodes.multiply(total, DEGREES_PER_UNIT * curl_sign)
        # relax: progressive curl, pinky most
        if not is_thumb and finger in non_thumb:
            index = non_thumb.index(finger)
            relax_weight = (index + 1) / float(len(non_thumb)) * DEGREES_PER_UNIT * curl_sign
            relax = nodes.multiply(attrs["relax"], relax_weight)
            scaled = nodes.add(scaled, relax)
        first = (base_index or {}).get(finger, 0)
        for i, ctl in enumerate(ctls):
            if i < first:
                continue
            sdk = ctl.last_offset
            if is_thumb and i == first:
                # thumb base curls less
                cmds.connectAttr(nodes.multiply(scaled, 0.3), "%s.rotate%s" % (sdk, curl_axis.upper()), force=True)
            else:
                cmds.connectAttr(scaled, "%s.rotate%s" % (sdk, curl_axis.upper()), force=True)
        if not is_thumb and finger in non_thumb and len(ctls) > first:
            factor = (non_thumb.index(finger) - center) * 2.0
            spread = nodes.multiply(attrs["spread"], factor)
            cmds.connectAttr(spread, "%s.rotate%s" % (ctls[first].last_offset, spread_axis.upper()), force=True)
    return {"controls": controls, "attributes": attrs}
