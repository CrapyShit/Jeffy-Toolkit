"""Small helpers shared by the face tools."""

from maya import cmds

from jeffy.core import attributes, dag, naming

META_ATTR = "jeffyFaceRig"


def label(name, side=None, suffix=None):
    """``L_name_SUF`` style name for nodes without a naming type key."""
    return "_".join(part for part in (side, name, suffix) if part)


def wire(curve, driver, name, dropoff=1000.0):
    """Deform ``curve`` with the wire ``driver``; returns ``(wire, base)``.

    The large drop off makes every point follow the driver fully.
    """
    node = cmds.wire(curve, wire=driver, name=naming.unique_name(name), dropoffDistance=(0, dropoff))[0]
    base = cmds.listConnections(node + ".baseWire[0]", source=True, destination=False) or []
    if base and cmds.objectType(base[0], isAType="shape"):
        base = [dag.get_parent(base[0])]
    return node, base[0] if base else None


def clean_duplicate(node, name):
    """Duplicate a (deformed) curve without its hidden original shape."""
    copy = cmds.duplicate(node, name=naming.unique_name(name))[0]
    for shape in cmds.listRelatives(copy, shapes=True, fullPath=True) or []:
        if cmds.getAttr(shape + ".intermediateObject"):
            cmds.delete(shape)
    return copy


def store(node, data):
    """Remember the parts of a face rig on its main control."""
    import json

    attributes.set_string(node, META_ATTR, json.dumps(data))


def load(node):
    import json

    raw = attributes.get_string(node, META_ATTR)
    return json.loads(raw) if raw else None


def find_rig(node):
    """Return ``(main_node, data)`` of the face rig ``node`` belongs to."""
    current = node
    while current:
        if cmds.attributeQuery(META_ATTR, node=current, exists=True):
            return current, load(current)
        current = dag.get_parent(current)
    return None, None
