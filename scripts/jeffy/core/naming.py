"""Naming convention and renaming tools.

The default convention is ``{side}_{name}_{type}`` e.g. ``L_arm_CTL`` but it is
fully configurable through :class:`NamingConvention`::

    from jeffy.core import naming
    naming.compose("arm", side="L", node_type="control")   # 'L_arm_CTL'
    naming.mirror_name("L_arm_CTL")                         # 'R_arm_CTL'

The string helpers in this module are pure Python; only the functions that
rename scene nodes import ``maya.cmds`` lazily.
"""

import re

SIDE_LEFT = "L"
SIDE_RIGHT = "R"
SIDE_CENTER = "C"
SIDES = (SIDE_LEFT, SIDE_RIGHT, SIDE_CENTER)

#: Default type suffixes. Keys are used throughout the toolkit.
TYPE_SUFFIXES = {
    "joint": "JNT",
    "bind_joint": "JNT",
    "control": "CTL",
    "group": "GRP",
    "zero": "ZRO",
    "offset": "OFF",
    "sdk": "SDK",
    "space": "SPC",
    "locator": "LOC",
    "ik_handle": "IKH",
    "effector": "EFF",
    "curve": "CRV",
    "surface": "SRF",
    "mesh": "GEO",
    "cluster": "CLS",
    "follicle": "FOL",
    "constraint": "CON",
    "skin_cluster": "SKN",
    "blendshape": "BSH",
    "guide": "GDE",
    "utility": "UTL",
    "multiply_divide": "MD",
    "plus_minus": "PMA",
    "condition": "COND",
    "reverse": "REV",
    "blend": "BLD",
    "remap": "RMV",
    "clamp": "CLP",
    "distance": "DIST",
    "decompose_matrix": "DM",
    "compose_matrix": "CM",
    "mult_matrix": "MM",
    "blend_matrix": "BM",
    "aim_matrix": "AM",
    "pick_matrix": "PM",
    "uv_pin": "UVP",
    "set": "SET",
    "layer": "LYR",
}

#: Node type -> suffix key, used by :func:`auto_suffix`.
NODE_TYPE_TO_SUFFIX_KEY = {
    "joint": "joint",
    "mesh": "mesh",
    "nurbsCurve": "curve",
    "nurbsSurface": "surface",
    "locator": "locator",
    "ikHandle": "ik_handle",
    "ikEffector": "effector",
    "clusterHandle": "cluster",
    "follicle": "follicle",
    "parentConstraint": "constraint",
    "pointConstraint": "constraint",
    "orientConstraint": "constraint",
    "scaleConstraint": "constraint",
    "aimConstraint": "constraint",
    "poleVectorConstraint": "constraint",
    "skinCluster": "skin_cluster",
    "blendShape": "blendshape",
    "multiplyDivide": "multiply_divide",
    "plusMinusAverage": "plus_minus",
    "condition": "condition",
    "reverse": "reverse",
    "blendColors": "blend",
    "remapValue": "remap",
    "clamp": "clamp",
    "distanceBetween": "distance",
    "decomposeMatrix": "decompose_matrix",
    "composeMatrix": "compose_matrix",
    "multMatrix": "mult_matrix",
    "blendMatrix": "blend_matrix",
    "aimMatrix": "aim_matrix",
    "pickMatrix": "pick_matrix",
    "uvPin": "uv_pin",
    "objectSet": "set",
    "displayLayer": "layer",
}

#: Pairs of side tokens recognised by :func:`mirror_name` (order matters -
#: longer tokens are tried first).
MIRROR_PAIRS = (
    ("Left", "Right"),
    ("left", "right"),
    ("LEFT", "RIGHT"),
    ("Lf", "Rt"),
    ("lf", "rt"),
    ("Lt", "Rt"),
    ("L", "R"),
    ("l", "r"),
)


class NamingConvention(object):
    """Configurable naming template.

    ``template`` may use the tokens ``{side}``, ``{name}``, ``{index}`` and
    ``{type}``. Empty tokens (and the separators around them) are dropped.
    """

    def __init__(self, template="{side}_{name}_{type}", separator="_", suffixes=None, index_padding=2):
        self.template = template
        self.separator = separator
        self.suffixes = dict(TYPE_SUFFIXES)
        if suffixes:
            self.suffixes.update(suffixes)
        self.index_padding = index_padding

    # ------------------------------------------------------------------
    def suffix(self, node_type):
        """Return the suffix for a type key, or the value itself if unknown."""
        if not node_type:
            return ""
        return self.suffixes.get(node_type, node_type)

    def compose(self, name, side=None, node_type=None, index=None):
        tokens = {
            "side": side or "",
            "name": name or "",
            "index": "" if index is None else str(index).zfill(self.index_padding),
            "type": self.suffix(node_type),
        }
        result = self.template.format(**tokens)
        sep = re.escape(self.separator)
        result = re.sub("(%s)+" % sep, self.separator, result)
        return result.strip(self.separator)

    def parse(self, full_name):
        """Split a name into ``{'side', 'name', 'type'}`` (best effort).

        DAG paths and namespaces are ignored.
        """
        short = strip_namespace(full_name)
        parts = short.split(self.separator)
        side = None
        node_type = None
        if parts and parts[0] in SIDES:
            side = parts.pop(0)
        known_suffixes = set(self.suffixes.values())
        if len(parts) > 1 and parts[-1] in known_suffixes:
            node_type = parts.pop()
        return {"side": side, "name": self.separator.join(parts), "type": node_type}


#: The active convention. Replace it (``naming.CONVENTION = NamingConvention(...)``)
#: to change naming globally.
CONVENTION = NamingConvention()


def compose(name, side=None, node_type=None, index=None):
    """Compose a name with the active :data:`CONVENTION`."""
    return CONVENTION.compose(name, side=side, node_type=node_type, index=index)


def parse(full_name):
    return CONVENTION.parse(full_name)


def suffix(node_type):
    return CONVENTION.suffix(node_type)


# ---------------------------------------------------------------------------
# String helpers (pure Python)
# ---------------------------------------------------------------------------
def short_name(name):
    """``'|grp|ns:node'`` -> ``'ns:node'`` (DAG path stripped)."""
    return name.rsplit("|", 1)[-1]


def strip_namespace(name):
    """``'|grp|ns:node'`` -> ``'node'``."""
    return short_name(name).rsplit(":", 1)[-1]


def get_namespace(name):
    short = short_name(name)
    return short.rsplit(":", 1)[0] if ":" in short else ""


def side_from_name(name):
    """Guess the side token of a name (``'L'``, ``'R'``, ``'C'`` or ``None``)."""
    base = strip_namespace(name)
    parts = re.split(r"[_\W]", base)
    for token, side in (("L", SIDE_LEFT), ("R", SIDE_RIGHT), ("C", SIDE_CENTER), ("M", SIDE_CENTER)):
        if token in parts:
            return side
    lowered = base.lower()
    if lowered.startswith(("left", "lf_", "l_")) or "_left" in lowered:
        return SIDE_LEFT
    if lowered.startswith(("right", "rt_", "r_")) or "_right" in lowered:
        return SIDE_RIGHT
    return None


def mirror_side(side):
    return {SIDE_LEFT: SIDE_RIGHT, SIDE_RIGHT: SIDE_LEFT}.get(side, side)


def mirror_name(name, pairs=MIRROR_PAIRS):
    """Swap left/right tokens in a name.

    Tokens are only swapped when they are delimited by ``_``, ``|``, ``:``,
    a digit or the start/end of the string - so ``'L_arm_CTL'`` becomes
    ``'R_arm_CTL'`` but ``'Leg'`` stays ``'Leg'``. Camel case words
    (``'armLeft'``) are handled too. Both sides are swapped simultaneously,
    so ``'L_to_R'`` becomes ``'R_to_L'``. Returns the input unchanged when no
    token was found.
    """
    for left, right in pairs:
        swap = {left: right, right: left}
        pattern = r"(?:^|(?<=[_|:\d]))(%s|%s)(?=$|[_|:\d])" % (re.escape(left), re.escape(right))
        new, count = re.subn(pattern, lambda match, table=swap: table[match.group(1)], name)
        if count:
            return new
    swap = {"Left": "Right", "Right": "Left"}
    new, count = re.subn(r"(?<=[a-z0-9])(Left|Right)(?=[A-Z_\d]|$)", lambda match: swap[match.group(1)], name)
    return new if count else name


def increment_name(name):
    """``'arm'`` -> ``'arm1'``, ``'arm1'`` -> ``'arm2'``, ``'arm_09'`` -> ``'arm_10'``."""
    match = re.search(r"(\d+)$", name)
    if not match:
        return name + "1"
    digits = match.group(1)
    number = str(int(digits) + 1).zfill(len(digits))
    return name[: match.start(1)] + number


def expand_pattern(pattern, index):
    """Replace a run of ``#`` with a zero padded index: ``'arm_##_JNT'`` -> ``'arm_01_JNT'``."""
    match = re.search(r"#+", pattern)
    if not match:
        return "%s%d" % (pattern, index)
    padding = len(match.group(0))
    return pattern[: match.start()] + str(index).zfill(padding) + pattern[match.end():]


def legalize(name):
    """Turn any string into a valid Maya node name."""
    name = re.sub(r"[^A-Za-z0-9_:|]", "_", name.strip())
    if not name:
        return "node"
    if name[0].isdigit():
        name = "_" + name
    return name


def camel_case(*words):
    words = [w for w in words if w]
    if not words:
        return ""
    first = words[0]
    return first[0].lower() + first[1:] + "".join(w[0].upper() + w[1:] for w in words[1:])


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------
def unique_name(name):
    """Return ``name`` or a numbered variant that does not exist in the scene."""
    from maya import cmds

    if not cmds.objExists(name):
        return name
    candidate = increment_name(name)
    while cmds.objExists(candidate):
        candidate = increment_name(candidate)
    return candidate


def rename(node, new_name):
    """Rename a node and return its new (unique, short) name."""
    from maya import cmds

    if short_name(node) == new_name:
        return node
    return cmds.rename(node, legalize(new_name))


def _long_names_deepest_first(nodes):
    """Sort long names deepest first so renaming parents never breaks paths."""
    from maya import cmds

    longs = cmds.ls(nodes, long=True) or []
    return sorted(longs, key=lambda n: n.count("|"), reverse=True)


def add_prefix(nodes, prefix):
    from maya import cmds

    for node in _long_names_deepest_first(nodes):
        cmds.rename(node, prefix + short_name(node))


def add_suffix(nodes, suffix_text):
    from maya import cmds

    for node in _long_names_deepest_first(nodes):
        cmds.rename(node, short_name(node) + suffix_text)


def search_replace(nodes, search, replace, use_regex=False):
    from maya import cmds

    renamed = []
    for node in _long_names_deepest_first(nodes):
        old = short_name(node)
        new = re.sub(search, replace, old) if use_regex else old.replace(search, replace)
        if new != old and new:
            renamed.append(cmds.rename(node, legalize(new)))
    return renamed


def remove_characters(nodes, first=0, last=0):
    """Remove ``first`` characters from the start and ``last`` from the end."""
    from maya import cmds

    for node in _long_names_deepest_first(nodes):
        old = short_name(node)
        new = old[first: len(old) - last if last else None]
        if new and new != old:
            cmds.rename(node, legalize(new))


def rename_sequential(nodes, pattern, start=1, step=1):
    """Rename nodes in the given order using a ``#`` padded pattern.

    ``rename_sequential(sel, "L_finger_##_JNT")`` -> ``L_finger_01_JNT`` ...
    """
    from maya import cmds

    # Resolve to UUIDs first so the order is kept even when parents get renamed.
    uuids = cmds.ls(nodes, uuid=True) or []
    result = []
    for i, uuid in enumerate(uuids):
        node = cmds.ls(uuid, long=True)[0]
        result.append(cmds.rename(node, expand_pattern(pattern, start + i * step)))
    return result


def auto_suffix(nodes, convention=None):
    """Add the correct type suffix to nodes based on their (shape) type."""
    from maya import cmds

    convention = convention or CONVENTION
    known = set(convention.suffixes.values())
    result = []
    for node in _long_names_deepest_first(nodes):
        node_type = cmds.nodeType(node)
        if node_type == "transform":
            shapes = cmds.listRelatives(node, shapes=True, fullPath=True, noIntermediate=True) or []
            node_type = cmds.nodeType(shapes[0]) if shapes else "transform"
            if node_type == "nurbsCurve":
                node_type = "control_curve"
        key = NODE_TYPE_TO_SUFFIX_KEY.get(node_type)
        if node_type == "control_curve":
            key = "control"
        elif node_type == "transform":
            key = "group"
        if not key:
            continue
        sfx = convention.suffix(key)
        old = short_name(node)
        parts = old.split(convention.separator)
        if parts[-1] in known:
            parts = parts[:-1]
        new = convention.separator.join(parts + [sfx])
        if new != old:
            result.append(cmds.rename(node, new))
    return result


def fix_shape_names(nodes=None):
    """Rename shapes to ``<transform>Shape`` (``Shape1``, ``Shape2`` ...)."""
    from maya import cmds

    nodes = nodes if nodes is not None else cmds.ls(type="transform", long=True)
    renamed = []
    for node in cmds.ls(nodes, long=True) or []:
        shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
        base = short_name(node)
        visible = [s for s in shapes if not cmds.getAttr(s + ".intermediateObject")]
        for i, shape in enumerate(visible):
            target = "%sShape" % base if i == 0 else "%sShape%d" % (base, i)
            if short_name(shape) != target:
                renamed.append(cmds.rename(shape, target))
    return renamed


def mirror_rename(nodes):
    """Rename nodes to their mirrored name (``L_`` <-> ``R_``)."""
    from maya import cmds

    result = []
    for node in _long_names_deepest_first(nodes):
        old = short_name(node)
        new = mirror_name(old)
        if new != old:
            result.append(cmds.rename(node, new))
    return result


def find_mirror_node(node):
    """Return the mirrored scene node of ``node`` or ``None``."""
    from maya import cmds

    namespace = get_namespace(node)
    base = strip_namespace(node)
    mirrored = mirror_name(base)
    if mirrored == base:
        return None
    full = "%s:%s" % (namespace, mirrored) if namespace else mirrored
    matches = cmds.ls(full) or []
    return matches[0] if matches else None


def find_duplicate_names(nodes=None):
    """Return ``{short_name: [long names]}`` for non unique short names."""
    from maya import cmds

    nodes = cmds.ls(nodes, long=True) if nodes else cmds.ls(dagObjects=True, long=True)
    seen = {}
    for node in nodes or []:
        seen.setdefault(short_name(node), []).append(node)
    return {name: paths for name, paths in seen.items() if len(paths) > 1}


def make_names_unique(nodes=None):
    """Rename every node whose short name is shared with another node."""
    from maya import cmds

    renamed = []
    for name, paths in sorted(find_duplicate_names(nodes).items()):
        for path in sorted(paths, key=lambda p: p.count("|"), reverse=True)[:-1]:
            if cmds.objExists(path):
                renamed.append(cmds.rename(path, unique_name(increment_name(name))))
    return renamed
