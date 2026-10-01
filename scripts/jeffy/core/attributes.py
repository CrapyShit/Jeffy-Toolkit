"""Attribute helpers: creation, locking, proxies, reordering, transfer..."""

from maya import cmds

from jeffy.core import logger

LOG = logger.get_logger("attributes")

TRANSFORM_ATTRS = ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz", "v")
COMPOUND_SHORTCUTS = {
    "t": ("tx", "ty", "tz"),
    "translate": ("tx", "ty", "tz"),
    "r": ("rx", "ry", "rz"),
    "rotate": ("rx", "ry", "rz"),
    "s": ("sx", "sy", "sz"),
    "scale": ("sx", "sy", "sz"),
    "jo": ("jointOrientX", "jointOrientY", "jointOrientZ"),
}

SEPARATOR_NICE_NAME = "__________"


def expand(attrs):
    """Expand compound shortcuts: ``['t', 'rx']`` -> ``['tx', 'ty', 'tz', 'rx']``."""
    if isinstance(attrs, str):
        attrs = [attrs]
    result = []
    for attr in attrs:
        for item in COMPOUND_SHORTCUTS.get(attr, (attr,)):
            if item not in result:
                result.append(item)
    return result


def plug(node, attr):
    return "%s.%s" % (node, attr)


def split_plug(full):
    node, _, attr = full.partition(".")
    return node, attr


def has_attr(node, attr):
    return cmds.attributeQuery(attr.split("[")[0].split(".")[0], node=node, exists=True) and cmds.objExists(
        plug(node, attr)
    )


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------
_TYPE_ALIASES = {
    "float": "double",
    "double": "double",
    "int": "long",
    "long": "long",
    "bool": "bool",
    "boolean": "bool",
    "enum": "enum",
    "string": "string",
    "matrix": "matrix",
    "message": "message",
    "vector": "double3",
    "double3": "double3",
    "float3": "float3",
    "color": "float3",
    "angle": "doubleAngle",
    "doubleAngle": "doubleAngle",
    "distance": "doubleLinear",
    "doubleLinear": "doubleLinear",
}


def add_attr(
    node,
    name,
    attr_type="float",
    default=None,
    minimum=None,
    maximum=None,
    keyable=True,
    channel_box=False,
    enum_names=None,
    nice_name=None,
    lock=False,
    multi=False,
):
    """Add (or return the existing) attribute and return the full plug.

    ``attr_type`` can be any of ``float``, ``int``, ``bool``, ``enum``,
    ``string``, ``matrix``, ``message``, ``vector``, ``color``, ``angle``,
    ``distance``. ``enum_names`` can be a list or a ``"a:b:c"`` string.
    """
    full = plug(node, name)
    if cmds.attributeQuery(name, node=node, exists=True):
        return full

    maya_type = _TYPE_ALIASES.get(attr_type, attr_type)
    kwargs = {"longName": name}
    if nice_name:
        kwargs["niceName"] = nice_name
    if multi:
        kwargs["multi"] = True

    if maya_type in ("string", "matrix"):
        kwargs["dataType"] = maya_type
        cmds.addAttr(node, **kwargs)
    elif maya_type in ("double3", "float3"):
        child_type = "double" if maya_type == "double3" else "float"
        suffixes = ("R", "G", "B") if attr_type == "color" else ("X", "Y", "Z")
        if attr_type == "color":
            kwargs["usedAsColor"] = True
        cmds.addAttr(node, attributeType=maya_type, **kwargs)
        for i, sfx in enumerate(suffixes):
            child_kwargs = {"longName": name + sfx, "attributeType": child_type, "parent": name}
            if default is not None:
                child_kwargs["defaultValue"] = default[i]
            cmds.addAttr(node, **child_kwargs)
        if keyable:
            for sfx in suffixes:
                cmds.setAttr(plug(node, name + sfx), keyable=True)
        return full
    else:
        kwargs["attributeType"] = maya_type
        if maya_type == "enum":
            names = enum_names or ["off", "on"]
            kwargs["enumName"] = names if isinstance(names, str) else ":".join(names)
        if default is not None and maya_type not in ("message",):
            kwargs["defaultValue"] = default
        if minimum is not None:
            kwargs["minValue"] = minimum
        if maximum is not None:
            kwargs["maxValue"] = maximum
        if maya_type != "message":
            kwargs["keyable"] = keyable
        cmds.addAttr(node, **kwargs)

    if maya_type not in ("message", "matrix", "string") and not keyable and channel_box:
        cmds.setAttr(full, channelBox=True)
    if default is not None and maya_type == "string":
        cmds.setAttr(full, default, type="string")
    if lock:
        cmds.setAttr(full, lock=True)
    return full


def add_separator(node, label="settings"):
    """Add a locked enum attribute used as a visual separator in the channel box."""
    name = "sep_" + label.replace(" ", "_")
    index = 0
    candidate = name
    while cmds.attributeQuery(candidate, node=node, exists=True):
        index += 1
        candidate = "%s%d" % (name, index)
    cmds.addAttr(
        node,
        longName=candidate,
        niceName=SEPARATOR_NICE_NAME,
        attributeType="enum",
        enumName=label.upper(),
    )
    full = plug(node, candidate)
    cmds.setAttr(full, channelBox=True)
    cmds.setAttr(full, lock=True)
    return full


def add_message(node, name, target=None, multi=False):
    """Add a message attribute and optionally connect ``target.message`` to it."""
    full = add_attr(node, name, "message", multi=multi)
    if target:
        if multi:
            index = len(cmds.getAttr(full, multiIndices=True) or [])
            cmds.connectAttr(target + ".message", "%s[%d]" % (full, index), force=True)
        else:
            cmds.connectAttr(target + ".message", full, force=True)
    return full


def get_message(node, name):
    """Return nodes connected to a (multi) message attribute."""
    if not cmds.attributeQuery(name, node=node, exists=True):
        return []
    return cmds.listConnections(plug(node, name), source=True, destination=False) or []


def set_string(node, name, value):
    add_attr(node, name, "string")
    cmds.setAttr(plug(node, name), value or "", type="string")


def get_string(node, name, default=""):
    if not cmds.attributeQuery(name, node=node, exists=True):
        return default
    value = cmds.getAttr(plug(node, name))
    return value if value is not None else default


def add_proxy(source_plug, node, name=None):
    """Create a proxy attribute on ``node`` that mirrors ``source_plug``.

    Proxy attributes appear on several controls but drive one value - great
    for IK/FK switches exposed on every limb control.
    """
    source_node, source_attr = split_plug(source_plug)
    long_name = name or cmds.attributeQuery(source_attr, node=source_node, longName=True)
    if cmds.attributeQuery(long_name, node=node, exists=True):
        return plug(node, long_name)
    cmds.addAttr(node, longName=long_name, proxy=source_plug)
    return plug(node, long_name)


# ---------------------------------------------------------------------------
# Lock / hide
# ---------------------------------------------------------------------------
def lock_hide(nodes, attrs=TRANSFORM_ATTRS, lock=True, hide=True):
    """Lock and/or hide attributes (compound shortcuts allowed)."""
    if isinstance(nodes, str):
        nodes = [nodes]
    for node in nodes:
        for attr in expand(attrs):
            if not cmds.attributeQuery(attr, node=node, exists=True):
                continue
            full = plug(node, attr)
            if lock:
                cmds.setAttr(full, lock=True)
            if hide:
                cmds.setAttr(full, keyable=False, channelBox=False)


def unlock_show(nodes, attrs=TRANSFORM_ATTRS, keyable=True):
    if isinstance(nodes, str):
        nodes = [nodes]
    for node in nodes:
        for attr in expand(attrs):
            if not cmds.attributeQuery(attr, node=node, exists=True):
                continue
            full = plug(node, attr)
            cmds.setAttr(full, lock=False)
            if keyable:
                cmds.setAttr(full, keyable=True)
            else:
                cmds.setAttr(full, channelBox=True)


def lock_hide_all_except(node, keep=()):
    """Lock & hide every transform attribute except the ones in ``keep``."""
    keep = set(expand(keep))
    lock_hide(node, [a for a in TRANSFORM_ATTRS if a not in keep])


def get_keyable(node):
    return cmds.listAttr(node, keyable=True, unlocked=True) or []


def get_channel_box_attrs(node):
    keyable = cmds.listAttr(node, keyable=True) or []
    non_keyable = cmds.listAttr(node, channelBox=True) or []
    return keyable + [a for a in non_keyable if a not in keyable]


def selected_channel_box_attrs():
    """Attributes highlighted in the channel box (main, shape, history...)."""
    result = []
    for flag in ("selectedMainAttributes", "selectedShapeAttributes", "selectedHistoryAttributes",
                 "selectedOutputAttributes"):
        attrs = cmds.channelBox("mainChannelBox", query=True, **{flag: True}) or []
        result.extend(a for a in attrs if a not in result)
    return result


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------
def get_default(node, attr):
    """Default value of an attribute (user defined or builtin)."""
    try:
        values = cmds.attributeQuery(attr, node=node, listDefault=True)
    except RuntimeError:
        return None
    if not values:
        return None
    return values[0] if len(values) == 1 else values


def set_default(node, attr, value):
    """Change the default value of a user defined attribute."""
    cmds.addAttr(plug(node, attr), edit=True, defaultValue=value)


def is_settable(node, attr):
    full = plug(node, attr)
    if not cmds.objExists(full):
        return False
    return cmds.getAttr(full, settable=True)


def reset(nodes, attrs=None, user_defined=True):
    """Reset keyable attributes to their default values.

    Locked or connected attributes are skipped silently.
    """
    if isinstance(nodes, str):
        nodes = [nodes]
    for node in nodes:
        names = expand(attrs) if attrs else (cmds.listAttr(node, keyable=True, unlocked=True) or [])
        if not user_defined:
            user = set(cmds.listAttr(node, userDefined=True) or [])
            names = [n for n in names if n not in user]
        for attr in names:
            if not is_settable(node, attr):
                continue
            default = get_default(node, attr)
            if default is None or isinstance(default, (list, tuple)):
                continue
            try:
                cmds.setAttr(plug(node, attr), default)
            except RuntimeError:
                LOG.debug("Could not reset %s.%s", node, attr)


def get_values(node, attrs=None):
    """``{attr: value}`` for keyable (or given) attributes."""
    names = expand(attrs) if attrs else (cmds.listAttr(node, keyable=True) or [])
    result = {}
    for attr in names:
        full = plug(node, attr)
        if not cmds.objExists(full):
            continue
        value = cmds.getAttr(full)
        if isinstance(value, list):
            continue  # skip compound values
        result[attr] = value
    return result


def set_values(node, values, skip_locked=True):
    for attr, value in values.items():
        if skip_locked and not is_settable(node, attr):
            continue
        try:
            cmds.setAttr(plug(node, attr), value)
        except RuntimeError:
            LOG.debug("Could not set %s.%s", node, attr)


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------
def connect(source, destination, force=True):
    """Connect two plugs; skips when already connected."""
    if cmds.isConnected(source, destination):
        return
    cmds.connectAttr(source, destination, force=force)


def set_or_connect(value, destination):
    """Connect if ``value`` is a plug string, otherwise set the value."""
    if isinstance(value, str):
        connect(value, destination)
    elif isinstance(value, (list, tuple)):
        if len(value) == 16:
            cmds.setAttr(destination, *value, type="matrix")
        else:
            cmds.setAttr(destination, *value)
    elif value is not None:
        cmds.setAttr(destination, value)


def get_driver(full_plug):
    """Source plug driving ``full_plug`` (or ``None``)."""
    sources = cmds.listConnections(full_plug, source=True, destination=False, plugs=True, skipConversionNodes=True)
    return sources[0] if sources else None


def get_driven(full_plug):
    return cmds.listConnections(full_plug, source=False, destination=True, plugs=True, skipConversionNodes=True) or []


def disconnect(full_plug, inputs=True, outputs=False):
    """Break connections on a plug."""
    if inputs:
        source = cmds.listConnections(full_plug, source=True, destination=False, plugs=True)
        for src in source or []:
            cmds.disconnectAttr(src, full_plug)
    if outputs:
        for dst in cmds.listConnections(full_plug, source=False, destination=True, plugs=True) or []:
            cmds.disconnectAttr(full_plug, dst)


def break_connections(nodes, attrs=TRANSFORM_ATTRS):
    """Disconnect inputs (keys, constraints ...) from attributes, keeping values."""
    if isinstance(nodes, str):
        nodes = [nodes]
    for node in nodes:
        for attr in expand(attrs):
            full = plug(node, attr)
            if not cmds.objExists(full):
                continue
            value = cmds.getAttr(full)
            disconnect(full)
            if cmds.getAttr(full, settable=True) and not isinstance(value, list):
                cmds.setAttr(full, value)


# ---------------------------------------------------------------------------
# Transfer / copy / reorder
# ---------------------------------------------------------------------------
def get_attr_data(node, attr):
    """Serializable description of a user defined attribute."""
    full = plug(node, attr)
    attr_type = cmds.getAttr(full, type=True)
    data = {
        "name": attr,
        "type": attr_type,
        "nice_name": cmds.attributeQuery(attr, node=node, niceName=True),
        "keyable": cmds.getAttr(full, keyable=True),
        "channel_box": cmds.getAttr(full, channelBox=True),
        "locked": cmds.getAttr(full, lock=True),
    }
    if attr_type == "enum":
        data["enum_names"] = cmds.attributeQuery(attr, node=node, listEnum=True)[0]
    if attr_type not in ("message", "TdataCompound", "matrix", "string", "double3", "float3"):
        data["default"] = get_default(node, attr)
        if cmds.attributeQuery(attr, node=node, minExists=True):
            data["min"] = cmds.attributeQuery(attr, node=node, minimum=True)[0]
        if cmds.attributeQuery(attr, node=node, maxExists=True):
            data["max"] = cmds.attributeQuery(attr, node=node, maximum=True)[0]
        data["value"] = cmds.getAttr(full)
    elif attr_type == "string":
        data["value"] = cmds.getAttr(full) or ""
    return data


def create_from_data(node, data):
    """Re-create an attribute from :func:`get_attr_data` output."""
    type_map = {"double": "float", "long": "int", "short": "int", "bool": "bool", "enum": "enum",
                "string": "string", "message": "message", "doubleAngle": "angle",
                "doubleLinear": "distance", "float": "float", "matrix": "matrix"}
    attr_type = type_map.get(data["type"], "float")
    full = add_attr(
        node,
        data["name"],
        attr_type,
        default=data.get("default"),
        minimum=data.get("min"),
        maximum=data.get("max"),
        keyable=data.get("keyable", True),
        channel_box=data.get("channel_box", False),
        enum_names=data.get("enum_names"),
        nice_name=data.get("nice_name"),
    )
    if "value" in data and data["value"] is not None:
        if attr_type == "string":
            cmds.setAttr(full, data["value"], type="string")
        elif not cmds.getAttr(full, lock=True):
            cmds.setAttr(full, data["value"])
    if data.get("locked"):
        cmds.setAttr(full, lock=True)
    return full


def user_attrs(node):
    """User defined attributes in channel box order (no compound children)."""
    attrs = cmds.listAttr(node, userDefined=True) or []
    result = []
    for attr in attrs:
        parent = cmds.attributeQuery(attr, node=node, listParent=True)
        if parent:
            continue
        result.append(attr)
    return result


def copy_attrs(source, targets, attrs=None, connect_to_source=False, move_connections=False):
    """Recreate user attributes of ``source`` on ``targets``.

    * ``connect_to_source`` - the source attribute drives the new attribute.
    * ``move_connections`` - outgoing connections of the source attribute are
      moved to the new attribute (source attribute is then deleted - a true
      "transfer").
    """
    if isinstance(targets, str):
        targets = [targets]
    attrs = attrs or user_attrs(source)
    created = []
    for target in targets:
        for attr in attrs:
            data = get_attr_data(source, attr)
            new_plug = create_from_data(target, data)
            created.append(new_plug)
            source_plug = plug(source, attr)
            if connect_to_source:
                connect(source_plug, new_plug)
            if move_connections:
                for dst in cmds.listConnections(source_plug, source=False, destination=True, plugs=True) or []:
                    cmds.connectAttr(new_plug, dst, force=True)
                driver = get_driver(source_plug)
                if driver:
                    cmds.connectAttr(driver, new_plug, force=True)
        if move_connections:
            for attr in attrs:
                full = plug(source, attr)
                cmds.setAttr(full, lock=False)
                cmds.deleteAttr(full)
    return created


def move_attr(node, attr, direction=1):
    """Move a user defined attribute up (-1) or down (+1) in the channel box."""
    attrs = user_attrs(node)
    if attr not in attrs:
        raise ValueError("%s is not a user defined attribute of %s" % (attr, node))
    index = attrs.index(attr)
    new_index = max(0, min(len(attrs) - 1, index + direction))
    if new_index == index:
        return
    new_order = list(attrs)
    new_order.pop(index)
    new_order.insert(new_index, attr)
    reorder_attrs(node, new_order)


def reorder_attrs(node, order):
    """Reorder user defined attributes so they follow ``order``.

    Every attribute from the first difference onward is rebuilt at the end of
    the list (values, limits, lock state and connections are preserved).
    Compound attributes cannot be reordered.
    """
    current = user_attrs(node)
    order = [a for a in order if a in current] + [a for a in current if a not in order]
    first_diff = 0
    while first_diff < len(order) and order[first_diff] == current[first_diff]:
        first_diff += 1
    to_rebuild = order[first_diff:]
    for attr in to_rebuild:
        if cmds.attributeQuery(attr, node=node, listChildren=True):
            raise ValueError("Cannot reorder compound attribute %s.%s" % (node, attr))
    for attr in to_rebuild:
        full = plug(node, attr)
        data = get_attr_data(node, attr)
        incoming = get_driver(full)
        outgoing = cmds.listConnections(full, source=False, destination=True, plugs=True) or []
        cmds.setAttr(full, lock=False)
        cmds.deleteAttr(full)
        locked = data.pop("locked", False)
        new_plug = create_from_data(node, data)
        if incoming:
            cmds.connectAttr(incoming, new_plug, force=True)
        for destination in outgoing:
            cmds.connectAttr(new_plug, destination, force=True)
        if locked:
            cmds.setAttr(new_plug, lock=True)
