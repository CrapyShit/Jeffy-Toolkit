"""IK/FK limbs with blending and seamless matching (snapping).

``build_ikfk_limb`` duplicates the bind chain into an FK and an IK chain,
builds both systems and blends the bind joints. A *settings* control (gear)
follows the end of the limb and holds the ``ikFk`` switch (0 = FK, 1 = IK).

Matching::

    from jeffy.rig import ikfk
    ikfk.match_fk_to_ik("L_arm_settings_CTL")   # FK snaps onto IK, switches to FK
    ikfk.match_ik_to_fk("L_arm_settings_CTL")   # IK snaps onto FK, switches to IK
    ikfk.toggle("L_arm_settings_CTL")           # match + switch to the other mode
"""

from maya import cmds

from jeffy.controls.control import Control
from jeffy.core import attributes, mathlib, matrix, naming, nodes, transform
from jeffy.joints import tools as joint_tools
from jeffy.rig import common, fk, ik

SWITCH_ATTR = "ikFk"
META_PREFIX = "jeffyIkFk_"


def build_ikfk_limb(
    joints,
    name="limb",
    side=None,
    parent=None,
    control_parent=None,
    systems_parent=None,
    size=1.0,
    fk_shape="circle",
    ik_shape="cube",
    stretch=True,
    soft=True,
    pin=True,
    pole_distance=1.0,
    orient_ik_control="world",
    default_mode=0.0,
    settings_offset=(0.0, 0.0, 0.0),
    orient_end=True,
):
    """Build a complete IK/FK limb on ``joints`` (bind chain, root -> end).

    :param parent: node the limb root follows (e.g. clavicle control/joint)
    :param control_parent: where the IK controls live (e.g. the local control)
    :returns: dict with ``settings``, ``fk``, ``ik``, ``fk_joints``,
        ``ik_joints``, ``switch`` and ``group``
    """
    group = common.create_group(naming.compose(name + "Rig", side, "group"), parent=systems_parent)
    fk_joints = joint_tools.duplicate_chain(joints[0], joints[-1], search="_JNT", replace="_FK_JNT")
    ik_joints = joint_tools.duplicate_chain(joints[0], joints[-1], search="_JNT", replace="_IK_JNT")
    for chain in (fk_joints, ik_joints):
        chain[0] = cmds.parent(chain[0], group)[0]
        cmds.setAttr(chain[0] + ".visibility", 0)
    fk_joints = [naming.short_name(j) for j in fk_joints]
    ik_joints = [naming.short_name(j) for j in ik_joints]

    # The duplicated chains must follow the limb parent.
    if parent:
        cmds.parentConstraint(parent, fk_joints[0], maintainOffset=True)
        cmds.parentConstraint(parent, ik_joints[0], maintainOffset=True)

    # FK -------------------------------------------------------------------
    fk_parent_grp = common.create_group(naming.compose(name + "FK", side, "group"),
                                        parent=control_parent)
    if parent:
        cmds.parentConstraint(parent, fk_parent_grp, maintainOffset=True)
        cmds.scaleConstraint(parent, fk_parent_grp, maintainOffset=True)
    fk_result = fk.build_fk_chain(fk_joints, name=name + "FK", side=side, shape=fk_shape, size=size,
                                  parent=fk_parent_grp, axis=common.primary_axis(fk_joints[1]).lstrip("-"))

    # IK -------------------------------------------------------------------
    ik_result = ik.build_ik(ik_joints, name=name, side=side, parent=parent or group,
                            control_parent=control_parent, systems_parent=group, stretch=stretch, soft=soft,
                            pin=pin, pole_distance=pole_distance, ik_shape=ik_shape, size=size,
                            orient_control=orient_ik_control, orient_end=orient_end)

    # settings control -----------------------------------------------------
    settings = Control.create(name + "Settings", side=side, shape="gear", size=size * 0.35,
                              parent=control_parent, match=joints[-1], lock=("t", "r", "s", "v"),
                              color_value="white")
    zero = settings.zero
    cmds.parentConstraint(joints[-1], zero, maintainOffset=True)
    if any(settings_offset):
        transform.reset(zero)
        cmds.xform(settings.node, relative=True, objectSpace=True, translation=settings_offset)
    switch = attributes.add_attr(settings.node, SWITCH_ATTR, "float", default=default_mode, minimum=0.0,
                                 maximum=1.0)

    # blend ----------------------------------------------------------------
    reverse = nodes.reverse(switch, name=naming.compose(name + "IkFk", side, "reverse"))
    for bind, fk_joint, ik_joint in zip(joints, fk_joints, ik_joints):
        constraint = cmds.parentConstraint(fk_joint, ik_joint, bind, maintainOffset=False)[0]
        cmds.setAttr(constraint + ".interpType", 2)
        weights = common.constraint_weight_plugs(constraint)
        cmds.connectAttr(reverse, weights[0])
        cmds.connectAttr(switch, weights[1])
        blend_scale = cmds.createNode("blendColors", name=naming.unique_name(naming.short_name(bind) + "_scale_BLD"),
                                      skipSelect=True)
        cmds.connectAttr(ik_joint + ".scale", blend_scale + ".color1")
        cmds.connectAttr(fk_joint + ".scale", blend_scale + ".color2")
        cmds.connectAttr(switch, blend_scale + ".blender")
        cmds.connectAttr(blend_scale + ".output", bind + ".scale", force=True)

    # visibility -----------------------------------------------------------
    fk_vis = nodes.condition(switch, "<", 1.0, 1.0, 0.0, name=naming.compose(name + "FkVis", side, "condition"))
    ik_vis = nodes.condition(switch, ">", 0.0, 1.0, 0.0, name=naming.compose(name + "IkVis", side, "condition"))
    cmds.connectAttr(fk_vis, fk_result["zero"] + ".visibility")
    cmds.connectAttr(ik_vis, ik_result["ik_control"].zero + ".visibility")
    if ik_result["pole_control"]:
        cmds.connectAttr(ik_vis, ik_result["pole_control"].zero + ".visibility")

    # proxy switch on every limb control for convenience
    for ctl in [c.node for c in fk_result["controls"]] + [ik_result["ik_control"].node] + (
            [ik_result["pole_control"].node] if ik_result["pole_control"] else []):
        attributes.add_proxy(switch, ctl)

    _store_meta(settings.node, joints, fk_joints, ik_joints, fk_result, ik_result)
    return {
        "settings": settings,
        "fk": fk_result,
        "ik": ik_result,
        "fk_joints": fk_joints,
        "ik_joints": ik_joints,
        "switch": switch,
        "group": group,
    }


# ---------------------------------------------------------------------------
# Meta data
# ---------------------------------------------------------------------------
def _store_meta(settings, joints, fk_joints, ik_joints, fk_result, ik_result):
    def store(key, items):
        plug = attributes.add_attr(settings, META_PREFIX + key, "message", multi=True)
        for i, item in enumerate(items):
            cmds.connectAttr(item + ".message", "%s[%d]" % (plug, i), force=True)

    store("bind", joints)
    store("fkJoints", fk_joints)
    store("ikJoints", ik_joints)
    store("fkControls", [c.node for c in fk_result["controls"]])
    ik_ctl = ik_result["ik_control"].node
    store("ikControl", [ik_ctl])
    if ik_result["pole_control"]:
        store("poleControl", [ik_result["pole_control"].node])
    # IK control relative to the IK end joint (for IK -> FK matching)
    offset = mathlib.mult(matrix.get_world_matrix(ik_ctl), mathlib.inverse(matrix.get_world_matrix(ik_joints[-1])))
    plug = attributes.add_attr(settings, META_PREFIX + "ikOffset", "matrix")
    matrix.set_matrix_attr(plug, offset)
    distance = mathlib.distance(transform.get_position(ik_joints[len(ik_joints) // 2]),
                                transform.get_position(ik_result["pole_control"].node)) if ik_result[
        "pole_control"] else 1.0
    attributes.add_attr(settings, META_PREFIX + "poleDistance", "float", default=distance, keyable=False)


def _meta(settings, key):
    plug = "%s.%s%s" % (settings, META_PREFIX, key)
    if not cmds.objExists(plug):
        return []
    result = []
    for index in cmds.getAttr(plug, multiIndices=True) or []:
        result.extend(cmds.listConnections("%s[%d]" % (plug, index), source=True, destination=False) or [])
    return result


def find_settings(node):
    """Return the settings control of the limb ``node`` belongs to."""
    if cmds.attributeQuery(META_PREFIX + "bind", node=node, exists=True):
        return node
    if cmds.attributeQuery(SWITCH_ATTR, node=node, exists=True):
        source = attributes.get_driver("%s.%s" % (node, SWITCH_ATTR))
        if source:
            candidate = source.split(".")[0]
            if cmds.attributeQuery(META_PREFIX + "bind", node=candidate, exists=True):
                return candidate
        # proxy attributes report the original attribute's node
        for candidate in cmds.listConnections("%s.%s" % (node, SWITCH_ATTR), source=True, destination=True) or []:
            if cmds.attributeQuery(META_PREFIX + "bind", node=candidate, exists=True):
                return candidate
    for candidate in cmds.listConnections(node + ".message", source=False, destination=True) or []:
        if cmds.attributeQuery(META_PREFIX + "bind", node=candidate, exists=True):
            return candidate
    return None


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
def match_fk_to_ik(settings, switch=True, key=False):
    """Snap the FK controls onto the current IK pose (and switch to FK)."""
    settings = find_settings(settings) or settings
    fk_controls = _meta(settings, "fkControls")
    fk_joints = _meta(settings, "fkJoints")
    ik_joints = _meta(settings, "ikJoints")
    for ctl, fk_joint, ik_joint in zip(fk_controls, fk_joints, ik_joints):
        relative = mathlib.mult(matrix.get_world_matrix(ctl), mathlib.inverse(matrix.get_world_matrix(fk_joint)))
        target = mathlib.mult(relative, matrix.get_world_matrix(ik_joint))
        matrix.set_world_matrix(ctl, target, scale=False)
    if switch:
        cmds.setAttr("%s.%s" % (settings, SWITCH_ATTR), 0.0)
    if key:
        cmds.setKeyframe(fk_controls + ["%s.%s" % (settings, SWITCH_ATTR)])


def match_ik_to_fk(settings, switch=True, key=False):
    """Snap the IK control and pole vector onto the current FK pose."""
    settings = find_settings(settings) or settings
    ik_ctl = _meta(settings, "ikControl")[0]
    pole = (_meta(settings, "poleControl") or [None])[0]
    fk_joints = _meta(settings, "fkJoints")
    offset = cmds.getAttr("%s.%sikOffset" % (settings, META_PREFIX))
    target = mathlib.mult(offset, matrix.get_world_matrix(fk_joints[-1]))
    if cmds.objExists(ik_ctl + ".pin") and attributes.is_settable(ik_ctl, "pin"):
        cmds.setAttr(ik_ctl + ".pin", 0)
    if cmds.objExists(ik_ctl + ".twist") and attributes.is_settable(ik_ctl, "twist"):
        cmds.setAttr(ik_ctl + ".twist", 0)
    matrix.set_world_matrix(ik_ctl, target, scale=False)
    if pole:
        distance = cmds.getAttr("%s.%spoleDistance" % (settings, META_PREFIX))
        positions = [transform.get_position(j) for j in fk_joints]
        mid = positions[len(positions) // 2]
        chain_length = sum(mathlib.distance(a, b) for a, b in zip(positions, positions[1:]))
        factor = distance / chain_length if chain_length else 1.0
        cmds.xform(pole, worldSpace=True,
                   translation=mathlib.pole_vector_position(positions[0], mid, positions[-1], factor))
    if switch:
        cmds.setAttr("%s.%s" % (settings, SWITCH_ATTR), 1.0)
    if key:
        cmds.setKeyframe([ik_ctl] + ([pole] if pole else []) + ["%s.%s" % (settings, SWITCH_ATTR)])


def toggle(node, key=False):
    """Match and switch to the other mode (based on the current switch value)."""
    settings = find_settings(node)
    if not settings:
        raise ValueError("%s is not part of an IK/FK limb" % node)
    if cmds.getAttr("%s.%s" % (settings, SWITCH_ATTR)) >= 0.5:
        match_fk_to_ik(settings, key=key)
    else:
        match_ik_to_fk(settings, key=key)
    return settings


def toggle_selected(key=False):
    done = []
    for node in cmds.ls(selection=True) or []:
        settings = find_settings(node)
        if settings and settings not in done:
            toggle(settings, key=key)
            done.append(settings)
    return done
