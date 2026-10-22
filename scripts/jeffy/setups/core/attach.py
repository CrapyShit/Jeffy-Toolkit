"""Auto-attach and spaces (matrix based, rebuilt whenever the rig changes).

A setup declares *anchors* while it builds: the top ``ZRO`` groups that must
follow something outside the setup (its parent setup, the root, the
chest...). An anchor lists space *roles*:

``parent``  the output driving the closest driven joint above the setup
            (arm -> clavicle output); the rig's root control when none
``world``   the rig's Global control
``root``    the rig's Root control
``self:k``  the control ``k`` of the same setup (e.g. ``self:ik`` for a pole)
other       a control with that space role in the rig (``cog``, ``hips``,
            ``chest``, ``head``...), skipped when the rig has none

:func:`refresh` resolves the roles and rebuilds the anchor networks. It runs
after every build and delete, so the build order of setups does not matter:
an arm built before the spine re-attaches to the spine once it exists.

Anchor kinds: ``parent`` (full follow, one space at a time), ``orient``
(position follows the first space, rotation the chosen one), ``point``
(the opposite). The ``ZRO`` channels are zeroed and the whole pose goes to
its ``offsetParentMatrix``, so the controls stay clean.
"""

from maya import cmds

from jeffy.core import attributes, mathlib, matrix, naming, transform
from jeffy.setups.core import controls, scene
from jeffy.setups.core import tag as tag_module
from jeffy.setups.core.schema import SetupError

KINDS = ("parent", "orient", "point")
#: on a control: name of the space enum attribute this module manages
MANAGED_ATTR = "jeffySpaceAttr"
SEPARATOR = "sep_space"


# ---------------------------------------------------------------------------
# Target resolution
# ---------------------------------------------------------------------------
def parent_target(setup):
    """Output (or control) the setup attaches to; ``None`` without a rig."""
    joint = setup.attach_joint()
    own = set(setup.family_tags())
    if joint and cmds.objExists(joint):
        for candidate in [joint] + scene.ancestors(joint):
            output = scene.output_driving(candidate)
            if output and tag_module.linked_tag(output) not in own:
                return output
    rig = setup.rig
    if rig is not None:
        return rig.outputs.get("root") or rig.controls.get("root")
    return None


def _role_control(setup, role):
    rig = setup.rig
    own = set(setup.family_tags())
    for other in scene.all_setups(rig=rig) if rig is not None else []:
        if other.tag in own:
            continue
        for node in other.controls.values():
            if controls.role_of(node) == role:
                return node
    return None


def resolve(setup, role):
    """``(label, node)`` of a space role, or ``None`` when it does not exist."""
    rig = setup.rig
    if role == "parent":
        node = parent_target(setup)
        return ("parent", node) if node else None
    if role in ("world", "root"):
        if rig is None:
            return None
        node = rig.controls.get("global" if role == "world" else "root")
        return (role, node) if node else None
    if role.startswith("self:"):
        key = role.split(":", 1)[1]
        node = setup.controls.get(key)
        return (key, node) if node else None
    node = _role_control(setup, role)
    return (role, node) if node else None


def targets_of(setup, definition):
    custom = definition.get("custom")
    result = []
    seen = set()
    if custom:
        for label, node in custom.get("targets", []):
            node = usable_target(node)
            if node and node not in seen:
                result.append((label, node))
                seen.add(node)
        return result
    for role in definition.get("spaces", []):
        found = resolve(setup, role)
        if found and found[1] not in seen:
            result.append(found)
            seen.add(found[1])
    return result


def usable_target(node):
    """Bind joints are replaced by the output driving them (no skeleton dependency)."""
    if not node or not cmds.objExists(node):
        return None
    if cmds.nodeType(node) == "joint":
        return scene.output_driving(node) or node
    return node


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------
def clear(setup):
    """Delete the anchor networks of a setup."""
    for node in tag_module.get_nodes(setup.tag, "attach"):
        if cmds.objExists(node):
            cmds.delete(node)
    tag_module.set_nodes(setup.tag, "attach", [])


def refresh(setup):
    """Rebuild every anchor of ``setup`` (keeps the chosen spaces by label)."""
    clear(setup)
    created = []
    for definition, zero, control in setup.anchors():
        if not zero or not cmds.objExists(zero):
            continue
        created.extend(_build_anchor(setup, definition, zero, control))
    tag_module.set_nodes(setup.tag, "attach", created)
    return created


def refresh_rig(rig):
    """Refresh every setup of ``rig`` (after a build or a delete)."""
    if rig is None or not cmds.objExists(rig.tag):
        return
    for setup in scene.all_setups(rig=rig):
        if setup.TYPE != "rig_base" and setup.anchors():
            refresh(setup)


def _new(node_type, name):
    return cmds.createNode(node_type, name=naming.unique_name(name), skipSelect=True)


def _build_anchor(setup, definition, zero, control):
    created = []
    custom = definition.get("custom") or {}
    kind = custom.get("kind") or definition.get("kind", "parent")
    attr = custom.get("attr") if custom else definition.get("attr")
    default = custom.get("default") if custom else definition.get("default")
    rest = definition["rest"]
    targets = targets_of(setup, definition)
    base = naming.strip_namespace(zero)
    if base.endswith("_ZRO"):
        base = base[:-4]

    transform.reset(zero)
    parent_inverse = matrix.parent_inverse_plug(zero)

    if not targets:
        local = rest
        if parent_inverse:
            local = mathlib.mult(rest, mathlib.inverse(cmds.getAttr(zero + ".parentMatrix[0]")))
        _disconnect_opm(zero)
        matrix.set_matrix_attr(zero + ".offsetParentMatrix", local)
        return created

    spaces = []
    for label, node in targets:
        offset = mathlib.mult(rest, mathlib.inverse(controls.rest_matrix(node)))
        mm = _new("multMatrix", "%s_%sSpace_MM" % (base, label))
        created.append(mm)
        matrix.set_matrix_attr(mm + ".matrixIn[0]", offset)
        cmds.connectAttr(node + ".worldMatrix[0]", mm + ".matrixIn[1]")
        spaces.append(mm + ".matrixSum")

    labels = [label for label, _node in targets]
    switch_plug = None
    if attr and control and len(targets) > 1:
        switch_plug = _ensure_enum(control, attr, labels, default)
    elif control:
        _drop_enum(control)

    if switch_plug:
        choice = _new("choice", "%s_space_CHC" % base)
        created.append(choice)
        cmds.connectAttr(switch_plug, choice + ".selector")
        for index, plug in enumerate(spaces):
            cmds.connectAttr(plug, "%s.input[%d]" % (choice, index))
        chosen = choice + ".output"
    else:
        chosen = spaces[0]

    result = chosen
    if kind in ("orient", "point") and switch_plug:
        blend = _new("blendMatrix", "%s_%sSpace_BM" % (base, kind))
        created.append(blend)
        cmds.connectAttr(spaces[0], blend + ".inputMatrix")
        cmds.connectAttr(chosen, blend + ".target[0].targetMatrix")
        cmds.setAttr(blend + ".target[0].weight", 1.0)
        cmds.setAttr(blend + ".target[0].translateWeight", 0.0 if kind == "orient" else 1.0)
        cmds.setAttr(blend + ".target[0].rotateWeight", 1.0 if kind == "orient" else 0.0)
        cmds.setAttr(blend + ".target[0].scaleWeight", 0.0)
        cmds.setAttr(blend + ".target[0].shearWeight", 0.0)
        result = blend + ".outputMatrix"

    _disconnect_opm(zero)
    if parent_inverse:
        local = _new("multMatrix", "%s_attach_MM" % base)
        created.append(local)
        cmds.connectAttr(result, local + ".matrixIn[0]")
        cmds.connectAttr(parent_inverse, local + ".matrixIn[1]")
        result = local + ".matrixSum"
    cmds.connectAttr(result, zero + ".offsetParentMatrix", force=True)
    return created


def _disconnect_opm(zero):
    plug = zero + ".offsetParentMatrix"
    for source in cmds.listConnections(plug, source=True, destination=False, plugs=True) or []:
        cmds.disconnectAttr(source, plug)


def _ensure_enum(control, attr, labels, default):
    """Create / update the space enum on ``control``, keeping the current label."""
    previous = attributes.get_string(control, MANAGED_ATTR)
    if previous and previous != attr:
        _drop_enum(control)
    plug = "%s.%s" % (control, attr)
    names = ":".join(labels)
    if cmds.attributeQuery(attr, node=control, exists=True):
        old = (cmds.attributeQuery(attr, node=control, listEnum=True) or [""])[0].split(":")
        current = old[cmds.getAttr(plug)] if cmds.getAttr(plug) < len(old) else None
        cmds.addAttr(plug, edit=True, enumName=names)
        if current in labels and not cmds.listConnections(plug, source=True, destination=False):
            cmds.setAttr(plug, labels.index(current))
    else:
        index = labels.index(default) if default in labels else 0
        if not cmds.attributeQuery(SEPARATOR, node=control, exists=True):
            attributes.add_separator(control, "space")
        cmds.addAttr(control, longName=attr, attributeType="enum", enumName=names, keyable=True,
                     defaultValue=index)
        cmds.setAttr(plug, index)
    attributes.set_string(control, MANAGED_ATTR, attr)
    return plug


def _drop_enum(control):
    """Remove the space enum this module created on ``control`` (if any)."""
    attr = attributes.get_string(control, MANAGED_ATTR)
    if attr and cmds.attributeQuery(attr, node=control, exists=True):
        cmds.deleteAttr(control, attribute=attr)
    if cmds.attributeQuery(MANAGED_ATTR, node=control, exists=True):
        attributes.set_string(control, MANAGED_ATTR, "")


# ---------------------------------------------------------------------------
# Animation
# ---------------------------------------------------------------------------
def space_attr(control):
    """Name of the space enum of ``control`` (``space`` unless the Spaces tool renamed it)."""
    return attributes.get_string(control, MANAGED_ATTR) or "space"


def space_labels(control, attr=None):
    attr = attr or space_attr(control)
    if not cmds.attributeQuery(attr, node=control, exists=True):
        return []
    return (cmds.attributeQuery(attr, node=control, listEnum=True) or [""])[0].split(":")


def switch(control, space, attr=None, key=False):
    """Change the space of ``control`` without moving it (seamless switch)."""
    attr = attr or space_attr(control)
    labels = space_labels(control, attr)
    if not labels:
        raise SetupError("%s has no '%s' attribute" % (naming.short_name(control), attr))
    index = space if isinstance(space, int) else (labels.index(space) if space in labels else -1)
    if index < 0 or index >= len(labels):
        raise SetupError("%s has no space %r (spaces: %s)" % (naming.short_name(control), space, ", ".join(labels)))
    world = matrix.get_world_matrix(control)
    plug = "%s.%s" % (control, attr)
    cmds.setAttr(plug, index)
    matrix.set_world_matrix(control, world, scale=False)
    if key:
        cmds.setKeyframe(plug)
        cmds.setKeyframe(control, attribute=["translate", "rotate"])
    return labels[index]
