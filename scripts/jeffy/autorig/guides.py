"""Guide system - the placement stage of the auto-rigger.

Each component is represented in the scene by a *guide root* (a group with
the component type, name, side, parent and settings stored as attributes)
and one *marker* per guide position::

    guides_GRP
    `-- L_arm_guide            (componentType, componentName, componentSide,
        |                       parentOutput + one attribute per setting)
        `-- L_arm_clavicle_GDE
            `-- L_arm_shoulder_GDE
                `-- ...

Settings are real attributes on the guide root, so they are editable in the
channel box / attribute editor.
"""

import json

from maya import cmds

from jeffy.controls import shapes
from jeffy.core import attributes, color, dag, fileio, mathlib, naming, transform
from jeffy.geometry import curves

GUIDES_GROUP = "guides_GRP"
ROOT_ATTR = "jeffyGuideRoot"
MARKER_ATTR = "jeffyGuideLabel"
SETTINGS_ATTR = "jeffySettingKeys"
TEMPLATE_TYPE = "jeffy_guide_template"


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------
def guides_group():
    if cmds.objExists(GUIDES_GROUP):
        return GUIDES_GROUP
    return cmds.createNode("transform", name=GUIDES_GROUP, skipSelect=True)


def _marker(name, position, size, side, parent):
    marker = shapes.create_shape("sphere", name=name, size=size)
    color.set_color(marker, color.side_color(side, secondary=False))
    cmds.xform(marker, worldSpace=True, translation=position)
    if parent:
        marker = cmds.parent(marker, parent)[0]
    attributes.lock_hide(marker, ("r", "s", "v"))
    return marker


def _settings_attr_type(value):
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "string"


def set_settings(root, settings):
    """Create/update one attribute per setting on the guide root."""
    keys = json.loads(attributes.get_string(root, SETTINGS_ATTR) or "[]")
    for key, value in settings.items():
        attr_type = _settings_attr_type(value)
        plug = "%s.%s" % (root, key)
        if not cmds.attributeQuery(key, node=root, exists=True):
            attributes.add_attr(root, key, attr_type, keyable=False, channel_box=attr_type != "string",
                                default=None if attr_type == "string" else value)
        if attr_type == "string":
            cmds.setAttr(plug, value if not isinstance(value, (list, dict)) else json.dumps(value), type="string")
        else:
            cmds.setAttr(plug, value)
        if key not in keys:
            keys.append(key)
    attributes.set_string(root, SETTINGS_ATTR, json.dumps(keys))


def get_settings(root):
    keys = json.loads(attributes.get_string(root, SETTINGS_ATTR) or "[]")
    result = {}
    for key in keys:
        plug = "%s.%s" % (root, key)
        if cmds.objExists(plug):
            result[key] = cmds.getAttr(plug)
    return result


def create_component_guide(component_type, name, side, guide_definitions, positions=None, settings=None,
                           parent_output="", size=1.0):
    """Create a guide root + markers.

    :param guide_definitions: ``[(label, default_position, parent_label), ...]``
    :param positions: optional ``{label: position}`` overriding the defaults
    """
    positions = positions or {}
    full = "%s_%s" % (side, name)
    root = cmds.createNode("transform", name=naming.unique_name(full + "_guide"), parent=guides_group(),
                           skipSelect=True)
    attributes.add_attr(root, ROOT_ATTR, "bool", default=True, keyable=False)
    for key, value in (("componentType", component_type), ("componentName", name), ("componentSide", side),
                       ("parentOutput", parent_output or "")):
        attributes.set_string(root, key, value)
    set_settings(root, settings or {})
    attributes.add_attr(root, "guideSize", "float", default=size, minimum=0.01, keyable=False, channel_box=True)

    markers = {}
    lines_group = cmds.createNode("transform", name=naming.unique_name(full + "_guideLines"), parent=root,
                                  skipSelect=True)
    for label, default, parent_label in guide_definitions:
        position = positions.get(label, default)
        parent = markers.get(parent_label, root)
        marker = _marker(naming.unique_name("%s_%s_GDE" % (full, label)), position, size, side, parent)
        attributes.set_string(marker, MARKER_ATTR, label)
        markers[label] = marker
        if parent_label in markers:
            line = curves.create_connector_line(markers[parent_label], marker,
                                                name="%s_%s_guideLine" % (full, label), parent=lines_group)
            cmds.setAttr(line + ".overrideEnabled", 1)
            cmds.setAttr(line + ".overrideDisplayType", 2)
    attributes.lock_hide(lines_group, ("t", "r", "s"), hide=False)
    return root


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def get_guide_roots():
    roots = cmds.ls("*.%s" % ROOT_ATTR, "*:*.%s" % ROOT_ATTR, objectsOnly=True) or []
    return sorted(set(roots))


def get_markers(root):
    """``{label: marker}`` for a guide root."""
    result = {}
    for node in cmds.listRelatives(root, allDescendents=True, type="transform", fullPath=True) or []:
        if cmds.attributeQuery(MARKER_ATTR, node=node, exists=True):
            result[attributes.get_string(node, MARKER_ATTR)] = node
    return result


def get_positions(root):
    return {label: tuple(transform.get_position(marker)) for label, marker in get_markers(root).items()}


def get_info(root):
    """Everything needed to rebuild a component guide."""
    return {
        "type": attributes.get_string(root, "componentType"),
        "name": attributes.get_string(root, "componentName"),
        "side": attributes.get_string(root, "componentSide"),
        "parent": attributes.get_string(root, "parentOutput"),
        "settings": get_settings(root),
        "positions": get_positions(root),
        "size": cmds.getAttr(root + ".guideSize") if cmds.objExists(root + ".guideSize") else 1.0,
    }


def find_root(component_full_name):
    for root in get_guide_roots():
        info_name = "%s_%s" % (attributes.get_string(root, "componentSide"),
                               attributes.get_string(root, "componentName"))
        if info_name == component_full_name:
            return root
    return None


def root_of(node):
    """Guide root of any marker/node under it."""
    current = dag.long_name(node)
    while current:
        if cmds.attributeQuery(ROOT_ATTR, node=current, exists=True):
            return current
        current = dag.get_parent(current)
    return None


def set_parent_output(root, output):
    attributes.set_string(root, "parentOutput", output or "")


# ---------------------------------------------------------------------------
# Mirroring
# ---------------------------------------------------------------------------
def mirror_reference(reference):
    """``'L_arm.hand'`` -> ``'R_arm.hand'`` (centre references unchanged)."""
    if not reference:
        return reference
    component, _, output = reference.partition(".")
    side, _, name = component.partition("_")
    return "%s_%s.%s" % (naming.mirror_side(side), name, output) if output else reference


def mirror_guide(root, axis="x"):
    """Create/update the opposite side guide of a component.

    Returns the mirrored guide root (``None`` for centre components).
    """
    from jeffy.autorig import components

    info = get_info(root)
    side = naming.mirror_side(info["side"])
    if side == info["side"]:
        return None
    positions = {label: mathlib.reflect(pos, axis) for label, pos in info["positions"].items()}
    full = "%s_%s" % (side, info["name"])
    existing = find_root(full)
    if existing:
        markers = get_markers(existing)
        for label, position in positions.items():
            if label in markers:
                cmds.xform(markers[label], worldSpace=True, translation=position)
        set_settings(existing, info["settings"])
        set_parent_output(existing, mirror_reference(info["parent"]))
        return existing
    component_class = components.get(info["type"])
    definitions = component_class.guide_definitions(info["settings"])
    return create_component_guide(info["type"], info["name"], side, definitions, positions, info["settings"],
                                  mirror_reference(info["parent"]), info["size"])


def mirror_all(source_side="L", axis="x"):
    result = []
    for root in get_guide_roots():
        if attributes.get_string(root, "componentSide") == source_side:
            result.append(mirror_guide(root, axis))
    return result


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
def save_template(path, roots=None):
    roots = roots or get_guide_roots()
    data = {"type": TEMPLATE_TYPE, "version": fileio.FORMAT_VERSION, "components": [get_info(r) for r in roots]}
    return fileio.write_json(path, data, precision=4)


def load_template(data_or_path, replace=False, offset=(0.0, 0.0, 0.0), scale=1.0):
    """Create guides from a template file/dict. Returns the guide roots."""
    from jeffy.autorig import components

    data = fileio.read_json(data_or_path) if isinstance(data_or_path, str) else data_or_path
    if replace:
        delete_guides()
    roots = []
    for info in data["components"]:
        component_class = components.get(info["type"])
        settings = dict(component_class.SETTINGS)
        settings.update(info.get("settings", {}))
        positions = {label: mathlib.add(mathlib.scale(pos, scale), offset)
                     for label, pos in info.get("positions", {}).items()}
        definitions = component_class.guide_definitions(settings)
        roots.append(create_component_guide(info["type"], info["name"], info["side"], definitions, positions,
                                            settings, info.get("parent", ""), info.get("size", 1.0) * scale))
    return roots


def delete_guides():
    if cmds.objExists(GUIDES_GROUP):
        cmds.delete(GUIDES_GROUP)


def set_guides_visible(state=True):
    if cmds.objExists(GUIDES_GROUP):
        cmds.setAttr(GUIDES_GROUP + ".visibility", state)
