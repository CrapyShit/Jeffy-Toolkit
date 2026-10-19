"""Course style rig hierarchy and master control (video 9)::

    <name>_GRP
      <name> master control (cyan)   VIZ: Skeleton, Geometry, Deformers, Rig_Systems
        controls
        systems                      hidden by default
      skeleton                       outside the master (follows by constraints)
      models
      deformers                      ribbons

The skeleton, models and deformers sit outside the master so nothing is
transformed twice. Flexible builders run from the UI put their parts in these
groups and connect the ``Deformers`` switch automatically.
"""

from maya import cmds

from jeffy.controls.control import Control
from jeffy.core import attributes, naming
from jeffy.rig.flexible import common

GROUPS = ("controls", "systems", "skeleton", "models", "deformers")


def create(name="Robot", size=10.0):
    """Create the hierarchy; returns a dict of the groups + ``master``."""
    top = cmds.createNode("transform", name=naming.unique_name(name + "_GRP"), skipSelect=True)
    master = Control.create(full_name=naming.unique_name(name), shape="master", size=size, axis="y", parent=top,
                            offsets=(), lock=("v",), color_value=common.MASTER_COLOR)
    groups = {}
    for key in GROUPS:
        parent = master.node if key in ("controls", "systems") else top
        groups[key] = cmds.createNode("transform", name=naming.unique_name(key), parent=parent, skipSelect=True)
    node = master.node
    attributes.add_separator(node, "viz")
    switches = {}
    for attr, target, default in (("Skeleton", "skeleton", False), ("Geometry", "models", True),
                                  ("Deformers", None, False), ("Rig_Systems", "systems", False)):
        switches[attr] = attributes.add_attr(node, attr, "bool", default=default, keyable=False, channel_box=True)
        if target:
            cmds.connectAttr(switches[attr], groups[target] + ".visibility")
    for group in [top] + list(groups.values()):
        common.lock_free(group)
    result = dict(groups, master=master, top=top, switches=switches)
    common.store(top, "structure", [node] + [groups[k] for k in GROUPS])
    return result


def find():
    """The first flexible structure in the scene as a dict (or ``None``)."""
    for top in cmds.ls("*.%sstructure" % common.META_PREFIX, objectsOnly=True) or []:
        items = common.fetch(top, "structure")
        if len(items) == len(GROUPS) + 1:
            result = dict(zip(GROUPS, items[1:]), master=items[0], top=top)
            result["deformers_switch"] = items[0] + ".Deformers"
            return result
    return None
