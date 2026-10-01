"""Wireframe / outliner colour helpers.

Colours can be given as:

* an index of Maya's 32 colour palette (``13`` = red),
* a name from :data:`COLOR_NAMES` (``"red"``, ``"light_blue"`` ...),
* an RGB tuple in 0-1 range (``(1.0, 0.5, 0.0)``).
"""

from maya import cmds

#: Approximate RGB values of Maya's default index palette (for UI swatches).
INDEX_RGB = {
    0: (0.47, 0.47, 0.47),
    1: (0.0, 0.0, 0.0),
    2: (0.25, 0.25, 0.25),
    3: (0.6, 0.6, 0.6),
    4: (0.608, 0.0, 0.157),
    5: (0.0, 0.016, 0.376),
    6: (0.0, 0.0, 1.0),
    7: (0.0, 0.275, 0.098),
    8: (0.149, 0.0, 0.263),
    9: (0.784, 0.0, 0.784),
    10: (0.541, 0.282, 0.2),
    11: (0.247, 0.137, 0.122),
    12: (0.6, 0.149, 0.0),
    13: (1.0, 0.0, 0.0),
    14: (0.0, 1.0, 0.0),
    15: (0.0, 0.255, 0.6),
    16: (1.0, 1.0, 1.0),
    17: (1.0, 1.0, 0.0),
    18: (0.392, 0.863, 1.0),
    19: (0.263, 1.0, 0.639),
    20: (1.0, 0.69, 0.69),
    21: (0.894, 0.675, 0.475),
    22: (1.0, 1.0, 0.388),
    23: (0.0, 0.6, 0.329),
    24: (0.631, 0.416, 0.188),
    25: (0.62, 0.631, 0.188),
    26: (0.408, 0.631, 0.188),
    27: (0.188, 0.631, 0.365),
    28: (0.188, 0.631, 0.631),
    29: (0.188, 0.404, 0.631),
    30: (0.435, 0.188, 0.631),
    31: (0.631, 0.188, 0.416),
}

COLOR_NAMES = {
    "black": 1,
    "dark_gray": 2,
    "gray": 3,
    "dark_red": 4,
    "dark_blue": 5,
    "blue": 6,
    "dark_green": 7,
    "purple": 8,
    "magenta": 9,
    "brown": 10,
    "dark_brown": 11,
    "orange_red": 12,
    "red": 13,
    "green": 14,
    "navy": 15,
    "white": 16,
    "yellow": 17,
    "light_blue": 18,
    "aqua": 19,
    "pink": 20,
    "skin": 21,
    "light_yellow": 22,
    "sea_green": 23,
    "light_brown": 24,
    "olive": 25,
    "lime": 26,
    "teal_green": 27,
    "teal": 28,
    "steel_blue": 29,
    "violet": 30,
    "plum": 31,
}

#: Default colours per side - primary controls and secondary (detail) controls.
SIDE_COLORS = {"L": 6, "R": 13, "C": 17}
SIDE_SECONDARY_COLORS = {"L": 18, "R": 20, "C": 22}


def resolve(color):
    """Return either an ``int`` index or an RGB tuple from any colour spec."""
    if color is None:
        return None
    if isinstance(color, str):
        key = color.lower().replace(" ", "_")
        if key not in COLOR_NAMES:
            raise ValueError("Unknown colour name %r" % color)
        return COLOR_NAMES[key]
    if isinstance(color, (list, tuple)):
        if len(color) != 3:
            raise ValueError("RGB colours need 3 values")
        return tuple(float(c) for c in color)
    return int(color)


def side_color(side, secondary=False):
    table = SIDE_SECONDARY_COLORS if secondary else SIDE_COLORS
    return table.get(side, table["C"])


def _targets(node, shapes_only=True):
    if cmds.objectType(node, isAType="shape"):
        return [node]
    shapes = cmds.listRelatives(node, shapes=True, fullPath=True, noIntermediate=True) or []
    if shapes and shapes_only:
        return shapes
    return [node]


def set_color(nodes, color, shapes=True):
    """Set the wireframe override colour of nodes (applied on their shapes)."""
    value = resolve(color)
    if isinstance(nodes, str):
        nodes = [nodes]
    for node in nodes:
        for target in _targets(node, shapes):
            cmds.setAttr(target + ".overrideEnabled", 1)
            if isinstance(value, tuple):
                cmds.setAttr(target + ".overrideRGBColors", 1)
                cmds.setAttr(target + ".overrideColorRGB", *value)
            else:
                if cmds.attributeQuery("overrideRGBColors", node=target, exists=True):
                    cmds.setAttr(target + ".overrideRGBColors", 0)
                cmds.setAttr(target + ".overrideColor", value)


def get_color(node):
    """Return the colour of a node (index or RGB tuple) or ``None``."""
    for target in _targets(node) + [node]:
        if not cmds.getAttr(target + ".overrideEnabled"):
            continue
        if cmds.attributeQuery("overrideRGBColors", node=target, exists=True) and cmds.getAttr(
            target + ".overrideRGBColors"
        ):
            return tuple(cmds.getAttr(target + ".overrideColorRGB")[0])
        return cmds.getAttr(target + ".overrideColor")
    return None


def reset_color(nodes):
    if isinstance(nodes, str):
        nodes = [nodes]
    for node in nodes:
        for target in set(_targets(node) + [node]):
            if cmds.getAttr(target + ".overrideEnabled", lock=True):
                continue
            cmds.setAttr(target + ".overrideEnabled", 0)
            if cmds.attributeQuery("overrideRGBColors", node=target, exists=True):
                cmds.setAttr(target + ".overrideRGBColors", 0)


def set_outliner_color(nodes, rgb):
    """Colour the node's name in the Outliner (``None`` resets)."""
    if isinstance(nodes, str):
        nodes = [nodes]
    for node in nodes:
        if rgb is None:
            cmds.setAttr(node + ".useOutlinerColor", 0)
        else:
            cmds.setAttr(node + ".useOutlinerColor", 1)
            cmds.setAttr(node + ".outlinerColor", *rgb)


def rgb_of(color):
    """RGB tuple for any colour spec (useful for UI)."""
    value = resolve(color)
    if isinstance(value, tuple):
        return value
    return INDEX_RGB.get(value, (0.5, 0.5, 0.5))
