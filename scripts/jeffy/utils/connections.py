"""Connection tools and set driven key (SDK) utilities."""

from maya import cmds

from jeffy.core import attributes, fileio, naming

SDK_CURVE_TYPES = ("animCurveUL", "animCurveUA", "animCurveUU", "animCurveUT")


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------
def connect_one_to_many(source_plug, targets, attr=None):
    """Connect ``source_plug`` to ``attr`` (default: same name) on targets."""
    attr = attr or source_plug.split(".", 1)[1]
    connected = []
    for target in targets:
        destination = "%s.%s" % (target, attr)
        if cmds.objExists(destination):
            cmds.connectAttr(source_plug, destination, force=True)
            connected.append(destination)
    return connected


def connect_selected(attrs=("translate", "rotate", "scale"), target_attrs=None):
    """First selected node drives the others for each attribute."""
    selection = cmds.ls(selection=True) or []
    if len(selection) < 2:
        raise ValueError("Select a driver then one or more driven nodes")
    driver, driven = selection[0], selection[1:]
    target_attrs = target_attrs or attrs
    for source_attr, target_attr in zip(attrs, target_attrs):
        connect_one_to_many("%s.%s" % (driver, source_attr), driven, target_attr)


def list_connections(node, incoming=True, outgoing=True):
    """``[(source_plug, destination_plug), ...]`` of a node (no conversions)."""
    result = []
    if incoming:
        pairs = cmds.listConnections(node, source=True, destination=False, plugs=True, connections=True,
                                     skipConversionNodes=True) or []
        result.extend((src, dst) for dst, src in zip(pairs[::2], pairs[1::2]))
    if outgoing:
        pairs = cmds.listConnections(node, source=False, destination=True, plugs=True, connections=True,
                                     skipConversionNodes=True) or []
        result.extend((src, dst) for src, dst in zip(pairs[::2], pairs[1::2]))
    return result


def transfer_connections(source, target, incoming=True, outgoing=True):
    """Move connections from ``source`` to the same attributes on ``target``."""
    moved = []
    for src, dst in list_connections(source, incoming, outgoing):
        if dst.startswith(source + "."):
            new_dst = target + dst[len(source):]
            if cmds.objExists(new_dst):
                cmds.connectAttr(src, new_dst, force=True)
                cmds.disconnectAttr(src, dst)
                moved.append((src, new_dst))
        elif src.startswith(source + "."):
            new_src = target + src[len(source):]
            if cmds.objExists(new_src):
                cmds.connectAttr(new_src, dst, force=True)
                moved.append((new_src, dst))
    return moved


def break_selected(attrs=None):
    for node in cmds.ls(selection=True) or []:
        attributes.break_connections(node, attrs or attributes.TRANSFORM_ATTRS)


# ---------------------------------------------------------------------------
# Set driven keys
# ---------------------------------------------------------------------------
def set_driven_keys(driver_plug, driven_plug, keys, in_tangent="linear", out_tangent="linear",
                    pre_infinity="constant", post_infinity="constant"):
    """Create driven keys from ``[(driver_value, driven_value), ...]``."""
    for driver_value, value in keys:
        cmds.setDrivenKeyframe(driven_plug, currentDriver=driver_plug, driverValue=driver_value, value=value,
                               inTangentType=in_tangent, outTangentType=out_tangent)
    curve = _curve_for(driven_plug, driver_plug)
    if curve:
        cmds.setInfinity(curve, preInfinite=pre_infinity, postInfinite=post_infinity)
    return curve


def _curve_for(driven_plug, driver_plug):
    for curve in get_sdk_curves(driven_plug.split(".")[0]):
        info = _curve_info(curve)
        if info and info["driven"] == driven_plug and info["driver"] == driver_plug:
            return curve
    return None


def get_sdk_curves(node):
    """Driven key curves feeding ``node`` (also through blendWeighted nodes)."""
    curves = []
    sources = cmds.listConnections(node, source=True, destination=False, skipConversionNodes=True) or []
    for source in sources:
        node_type = cmds.nodeType(source)
        if node_type in SDK_CURVE_TYPES:
            curves.append(source)
        elif node_type == "blendWeighted":
            for curve in cmds.listConnections(source, source=True, destination=False,
                                              skipConversionNodes=True) or []:
                if cmds.nodeType(curve) in SDK_CURVE_TYPES:
                    curves.append(curve)
    return list(dict.fromkeys(curves))


def _curve_info(curve):
    drivers = cmds.listConnections(curve + ".input", source=True, destination=False, plugs=True,
                                   skipConversionNodes=True) or []
    driven = cmds.listConnections(curve + ".output", source=False, destination=True, plugs=True,
                                  skipConversionNodes=True) or []
    if not drivers or not driven:
        return None
    target = driven[0]
    if cmds.nodeType(target.split(".")[0]) == "blendWeighted":
        outputs = cmds.listConnections(target.split(".")[0] + ".output", source=False, destination=True,
                                       plugs=True, skipConversionNodes=True) or []
        if not outputs:
            return None
        target = outputs[0]
    return {"driver": drivers[0], "driven": target}


def get_sdk_data(node):
    """Serializable description of every driven key on ``node``."""
    data = []
    for curve in get_sdk_curves(node):
        info = _curve_info(curve)
        if not info:
            continue
        driver_values = cmds.keyframe(curve, query=True, floatChange=True) or []
        values = cmds.keyframe(curve, query=True, valueChange=True) or []
        in_tangents = cmds.keyTangent(curve, query=True, inTangentType=True) or []
        out_tangents = cmds.keyTangent(curve, query=True, outTangentType=True) or []
        data.append({
            "driver": info["driver"],
            "driven": info["driven"],
            "keys": [list(k) for k in zip(driver_values, values, in_tangents, out_tangents)],
            "pre": cmds.setInfinity(curve, query=True, preInfinite=True)[0],
            "post": cmds.setInfinity(curve, query=True, postInfinite=True)[0],
        })
    return data


def apply_sdk_data(data, search=None, replace=None, invert_attrs=(), driver_search=None, driver_replace=None):
    """Recreate driven keys from :func:`get_sdk_data` output.

    ``search``/``replace`` rename the driven node, ``driver_search`` /
    ``driver_replace`` the driver, ``invert_attrs`` negates driven values of
    those attributes (useful when mirroring).
    """
    created = []
    for entry in data:
        driven = entry["driven"]
        driver = entry["driver"]
        if search is not None:
            driven = driven.replace(search, replace)
        if driver_search is not None:
            driver = driver.replace(driver_search, driver_replace)
        if not cmds.objExists(driven) or not cmds.objExists(driver):
            continue
        attr = driven.split(".", 1)[1]
        invert = attr in invert_attrs or naming.short_name(attr) in invert_attrs
        for driver_value, value, in_tangent, out_tangent in entry["keys"]:
            cmds.setDrivenKeyframe(driven, currentDriver=driver, driverValue=driver_value,
                                   value=-value if invert else value, inTangentType=in_tangent,
                                   outTangentType=out_tangent)
        curve = _curve_for(driven, driver)
        if curve:
            cmds.setInfinity(curve, preInfinite=entry["pre"], postInfinite=entry["post"])
            created.append(curve)
    return created


def copy_sdk(source, target, driver_search=None, driver_replace=None):
    data = get_sdk_data(source)
    return apply_sdk_data(data, search=source, replace=target, driver_search=driver_search,
                          driver_replace=driver_replace)


def mirror_sdk(nodes, invert_attrs=("translateX", "rotateY", "rotateZ")):
    """Copy driven keys to the mirrored nodes (L_ <-> R_), mirroring drivers."""
    created = []
    for node in nodes:
        target = naming.find_mirror_node(node)
        if not target:
            continue
        for entry in get_sdk_data(node):
            driver_node = entry["driver"].split(".")[0]
            mirrored_driver = naming.mirror_name(driver_node)
            created.extend(apply_sdk_data([entry], search=node, replace=target, invert_attrs=invert_attrs,
                                          driver_search=driver_node, driver_replace=mirrored_driver))
    return created


def export_sdk(nodes, path):
    data = {naming.strip_namespace(n): get_sdk_data(n) for n in nodes}
    return fileio.write_json(path, {"type": "jeffy_sdk", "version": fileio.FORMAT_VERSION, "nodes": data})


def import_sdk(path):
    data = fileio.read_json(path)
    created = []
    for entries in data["nodes"].values():
        created.extend(apply_sdk_data(entries))
    return created


def delete_sdk(nodes):
    curves = []
    for node in nodes:
        curves.extend(get_sdk_curves(node))
    if curves:
        cmds.delete(curves)
    return curves
