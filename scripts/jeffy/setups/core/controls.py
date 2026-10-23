"""Belt controls: ``ZRO > OFF > CTL`` with side colours and setup links.

* ``ZRO`` holds the rest pose. Setups that follow a parent or have spaces
  drive it through its ``offsetParentMatrix`` (its own channels are zeroed).
* ``OFF`` is free for the user (set driven keys, extra offsets).
* ``CTL`` is the animator control. It stores its rest world matrix
  (``jeffyRest``), its key in the setup (``jeffyKey``) and its space role
  (``jeffySpaceRole``: ``world``, ``root``, ``cog``, ``chest``...).
"""

from maya import cmds

from jeffy.controls.control import Control
from jeffy.core import attributes, matrix
from jeffy.setups.core import tag as tag_module

OFFSETS = ("zero", "offset")
KEY_ATTR = "jeffyKey"
ROLE_ATTR = "jeffySpaceRole"
REST_ATTR = "jeffyRest"


def create(setup, key, label, shape="circle", size=1.0, axis="x", parent=None, match=None, world_matrix=None,
           position=None, lock=("v",), secondary=False, color=None, role=None, side=None):
    """Create a control for ``setup`` and register it under ``key``.

    :param label: name part (``L_<label>_CTL``)
    :param match: node whose world transform the control takes
    :param world_matrix: or an explicit world matrix (16 floats)
    :param position: or only a world position (world orientation)
    :param side: side of this control (default: the setup's side)
    """
    ctl = Control.create(label, side=side or setup.side, shape=shape, size=size, axis=axis,
                         parent=parent or setup.controls_group, match=match, position=position, lock=None,
                         offsets=OFFSETS, secondary=secondary, color_value=color)
    if world_matrix is not None:
        matrix.set_world_matrix(ctl.zero, world_matrix, scale=False)
    attributes.set_string(ctl.node, KEY_ATTR, key)
    cmds.setAttr("%s.%s" % (ctl.node, KEY_ATTR), lock=True)
    if role:
        set_role(ctl.node, role)
    store_rest(ctl.node)
    tag_module.link(setup.tag, ctl.node)
    setup.register_control(key, ctl.node)
    if lock:
        attributes.lock_hide(ctl.node, lock)
    return ctl


def store_rest(node):
    """Remember the current world matrix as the node's rest pose."""
    plug = attributes.add_attr(node, REST_ATTR, "matrix")
    cmds.setAttr(plug, lock=False)
    matrix.set_matrix_attr(plug, matrix.get_world_matrix(node))
    cmds.setAttr(plug, lock=True)
    return plug


def rest_matrix(node):
    """Stored rest world matrix of ``node`` (its current one if none was stored)."""
    if cmds.attributeQuery(REST_ATTR, node=node, exists=True):
        return list(cmds.getAttr("%s.%s" % (node, REST_ATTR)))
    return matrix.get_world_matrix(node)


def set_role(node, role):
    attributes.set_string(node, ROLE_ATTR, role)


def role_of(node):
    return attributes.get_string(node, ROLE_ATTR) or None


def key_of(node):
    return attributes.get_string(node, KEY_ATTR) or None


def zero_of(node):
    """Top group above a belt control (``ZRO``), or the node itself."""
    try:
        return Control(node).zero
    except ValueError:
        return node


def size_from_length(length, factor, size_option):
    """Control size from a joint length (never zero)."""
    return max(length * factor, 1e-3) * size_option
