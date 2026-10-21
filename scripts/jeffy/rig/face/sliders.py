"""Slider controls and face boards for blendshape faces.

::

    from jeffy.rig.face import sliders
    s = sliders.create_slider("smile", side="L", mode="vertical")
    sliders.connect(s["control"], "up", "face_BS", "L_smile")
    sliders.sliders_from_blendshape("face_BS")      # one slider per target

A slider is a handle (the control) inside a frame. The handle is limited to
the frame and its position is turned into 0..1 output attributes on the
control: ``up``, ``down`` (vertical), ``right``, ``left`` (horizontal).
Connect them to anything (blendshape weights, set driven keys...).
"""

from maya import cmds

from jeffy.controls.control import Control
from jeffy.core import attributes, naming, nodes
from jeffy.geometry import curves
from jeffy.rig import common

MODES = ("vertical", "horizontal", "square")
DIRECTIONS = ("up", "down", "right", "left")


def _frame(name, side, x_range, y_range, pad, parent):
    (x0, x1), (y0, y1) = x_range, y_range
    points = [(x0 - pad, y0 - pad, 0), (x1 + pad, y0 - pad, 0), (x1 + pad, y1 + pad, 0), (x0 - pad, y1 + pad, 0),
              (x0 - pad, y0 - pad, 0)]
    frame = curves.curve_from_points(points, name=naming.compose(name + "Frame", side, "curve"), degree=1,
                                     through=False)
    frame = cmds.parent(frame, parent, relative=True)[0]
    cmds.setAttr(frame + ".overrideEnabled", 1)
    cmds.setAttr(frame + ".overrideDisplayType", 2)  # reference: visible, not selectable
    return frame


def create_slider(name, side=None, mode="vertical", two_sided=True, size=1.0, parent=None, position=None,
                  color_value=None, label=None):
    """Create a slider; returns ``{"control", "group", "frame", "outputs"}``.

    :param mode: ``vertical``, ``horizontal`` or ``square`` (2D)
    :param two_sided: the handle goes both ways (up and down); otherwise
        only up / right (0..1)
    :param label: text shown above the slider (None: no text)
    """
    if mode not in MODES:
        raise ValueError("mode must be one of %s" % (MODES,))
    low = -size if two_sided else 0.0
    use_x = mode in ("horizontal", "square")
    use_y = mode in ("vertical", "square")
    x_range = (low, size) if use_x else (0.0, 0.0)
    y_range = (low, size) if use_y else (0.0, 0.0)

    group = common.create_group(naming.compose(name + "Slider", side, "group"), parent=parent)
    if position is not None:
        cmds.xform(group, worldSpace=True, translation=position)
    _frame(name, side, x_range, y_range, size * 0.25, group)
    ctl = Control.create(name, side=side, shape="circle", size=size * 0.2, axis="z", parent=group,
                         offsets=("zero",), lock=("r", "s", "v"), color_value=color_value)
    cmds.xform(ctl.zero, objectSpace=True, translation=(0, 0, 0), rotation=(0, 0, 0))
    locked = ["tz"] + ([] if use_x else ["tx"]) + ([] if use_y else ["ty"])
    attributes.lock_hide(ctl.node, locked)
    limits = {}
    if use_x:
        limits.update(translationX=x_range, enableTranslationX=(1, 1))
    if use_y:
        limits.update(translationY=y_range, enableTranslationY=(1, 1))
    cmds.transformLimits(ctl.node, **limits)

    attributes.add_separator(ctl.node, "outputs")
    outputs = {}
    directions = []
    if use_y:
        directions += [("up", "translateY", size)] + ([("down", "translateY", -size)] if two_sided else [])
    if use_x:
        directions += [("right", "translateX", size)] + ([("left", "translateX", -size)] if two_sided else [])
    for direction, attr, end in directions:
        value = nodes.remap("%s.%s" % (ctl.node, attr), 0.0, end, 0.0, 1.0,
                            name=naming.compose(name + direction.title(), side, "utility"))
        plug = attributes.add_attr(ctl.node, direction, "float", keyable=False, channel_box=True)
        cmds.connectAttr(value, plug)
        outputs[direction] = plug

    if label:
        from jeffy.controls import shapes

        text = shapes.text_curves(label, name=naming.compose(name + "Label", side, "curve"))
        text = cmds.parent(text, group, relative=False)[0]
        top = (y_range[1] if use_y else 0.0) + size * 0.45
        cmds.xform(text, objectSpace=True, translation=(x_range[0] - size * 0.25, top, 0),
                   scale=(size * 0.25, size * 0.25, size * 0.25))
        cmds.setAttr(text + ".overrideEnabled", 1)
        cmds.setAttr(text + ".overrideDisplayType", 2)
    return {"control": ctl, "group": group, "outputs": outputs}


def connect(control, direction, blendshape, target):
    """Drive a blendshape ``target`` (alias or index) from a slider direction."""
    from jeffy.deformers import blendshape as bs

    if direction not in DIRECTIONS:
        raise ValueError("direction must be one of %s" % (DIRECTIONS,))
    source = "%s.%s" % (control, direction)
    if not cmds.attributeQuery(direction, node=control, exists=True):
        raise ValueError("%s has no %r output (wrong slider mode?)" % (control, direction))
    index = bs.target_index(blendshape, target)
    cmds.connectAttr(source, "%s.weight[%d]" % (blendshape, index), force=True)
    return source


def sliders_from_blendshape(blendshape, name="face", parent=None, size=1.0, columns=6, labels=True,
                            position=(0.0, 0.0, 0.0)):
    """A face board: one slider per blendshape target, already connected.

    Targets named ``<base>Up`` / ``<base>Down`` (or ``_up`` / ``_dn`` ...)
    share one two-sided slider; every other target gets a one-sided slider.
    Targets already driven by something are skipped.
    Returns ``{"group", "sliders": {label: slider}}``.
    """
    from jeffy.deformers import blendshape as bs

    targets = []
    for index, alias in bs.get_targets(blendshape):
        plug = "%s.weight[%d]" % (blendshape, index)
        if cmds.listConnections(plug, source=True, destination=False):
            continue
        targets.append(alias)
    pairs = _pair_targets(targets)

    board = common.create_group(naming.compose(name + "Board", None, "group"), parent=parent)
    cmds.xform(board, worldSpace=True, translation=position)
    sliders = {}
    spacing = size * 3.0
    for i, (label, up, down) in enumerate(pairs):
        row, column = divmod(i, columns)
        result = create_slider(_safe(label), mode="vertical", two_sided=down is not None, size=size,
                               parent=board, label=label if labels else None)
        cmds.xform(result["group"], objectSpace=True, translation=(column * spacing, -row * spacing * 1.3, 0))
        connect(result["control"].node, "up", blendshape, up)
        if down:
            connect(result["control"].node, "down", blendshape, down)
        sliders[label] = result
    return {"group": board, "sliders": sliders}


_UP = ("Up", "_up", "_Up", "_UP", "Open", "_open")
_DOWN = ("Down", "_dn", "_down", "_Down", "_DN", "Dn", "Close", "_close")


def _split(target, suffixes):
    """``(base, suffix)`` when ``target`` ends with one of ``suffixes``."""
    for suffix in suffixes:
        if target.endswith(suffix) and len(target) > len(suffix):
            return target[: -len(suffix)], suffix
    return None, None


def _pair_targets(targets):
    """``[(label, up_target, down_target_or_None)]`` keeping target order."""
    remaining = list(targets)
    result = []
    for target in targets:
        if target not in remaining:
            continue
        remaining.remove(target)
        pair = None
        for mine, other in ((_UP, _DOWN), (_DOWN, _UP)):
            base, _suffix = _split(target, mine)
            if base is None:
                continue
            partner = next((c for c in remaining if c.startswith(base) and c[len(base):] in other), None)
            if partner:
                pair = (base, target, partner) if mine is _UP else (base, partner, target)
                remaining.remove(partner)
                break
        result.append(pair or (target, target, None))
    return result


def _safe(label):
    cleaned = "".join(c if c.isalnum() else "_" for c in label).strip("_")
    return cleaned or "slider"
