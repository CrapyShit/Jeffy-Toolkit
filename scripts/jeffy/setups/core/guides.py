"""Guides: locators shown by *Preview* that you move before *Build*.

A tool lists its guide keys (``pole``, ``settings``...) and gives their
default world matrices. Preview creates one locator per key under
``jeffySetupGuides_GRP``; Build reads their positions, uses them and deletes
them. The positions used are stored on the setup tag so *Rebuild* keeps them.
"""

from maya import cmds

from jeffy.core import attributes, color, mathlib, matrix, naming

GROUP = "jeffySetupGuides_GRP"
TYPE_ATTR = "jeffyGuideType"
NAME_ATTR = "jeffyGuideName"
SIDE_ATTR = "jeffyGuideSide"
KEY_ATTR = "jeffyGuideKey"
GUIDE_COLOR = (1.0, 0.45, 0.0)


def _group():
    if not cmds.objExists(GROUP):
        cmds.createNode("transform", name=GROUP, skipSelect=True)
    return GROUP


def find(setup_type, name, side):
    """``{key: locator}`` of the preview guides of one setup."""
    result = {}
    if not cmds.objExists(GROUP):
        return result
    for node in cmds.listRelatives(GROUP, children=True, type="transform") or []:
        if not cmds.attributeQuery(KEY_ATTR, node=node, exists=True):
            continue
        if (attributes.get_string(node, TYPE_ATTR) == setup_type
                and attributes.get_string(node, NAME_ATTR) == name
                and (attributes.get_string(node, SIDE_ATTR) or None) == (side or None)):
            result[attributes.get_string(node, KEY_ATTR)] = node
    return result


def create(setup_type, name, side, defaults, size=1.0):
    """Create (or move back) the preview guides of a setup.

    :param defaults: ``{key: world matrix (16 floats) or position (3 floats)}``
    :returns: ``{key: locator}``
    """
    existing = find(setup_type, name, side)
    result = {}
    for key, value in defaults.items():
        locator = existing.get(key)
        if not locator:
            locator = cmds.spaceLocator(name=naming.unique_name(naming.compose(name + key[0].upper() + key[1:],
                                                                                side, "guide")))[0]
            locator = cmds.parent(locator, _group())[0]
            for attr, text in ((TYPE_ATTR, setup_type), (NAME_ATTR, name), (SIDE_ATTR, side or ""), (KEY_ATTR, key)):
                attributes.set_string(locator, attr, text)
            shape = cmds.listRelatives(locator, shapes=True)[0]
            for axis in "XYZ":
                cmds.setAttr("%s.localScale%s" % (shape, axis), size)
            color.set_color(locator, GUIDE_COLOR)
        if len(value) == 16:
            matrix.set_world_matrix(locator, value, scale=False)
        else:
            cmds.xform(locator, worldSpace=True, translation=value)
        result[key] = locator
    return result


def read(setup_type, name, side):
    """``{key: world matrix}`` of the preview guides (empty when none)."""
    return dict((key, matrix.get_world_matrix(node)) for key, node in find(setup_type, name, side).items())


def delete(setup_type, name, side):
    for node in find(setup_type, name, side).values():
        if cmds.objExists(node):
            cmds.delete(node)
    if cmds.objExists(GROUP) and not cmds.listRelatives(GROUP, children=True):
        cmds.delete(GROUP)


def position(value):
    """World position of a guide value (matrix or position)."""
    if value is None:
        return None
    if len(value) == 16:
        return tuple(mathlib.get_translation(value))
    return tuple(value)


def mirror(value, axis="x"):
    """Guide value mirrored across the YZ plane (or ``axis``)."""
    if value is None:
        return None
    if len(value) == 16:
        return mathlib.mirror_matrix(value, axis=axis, mode="behavior")
    return tuple(mathlib.reflect(value, axis=axis))
