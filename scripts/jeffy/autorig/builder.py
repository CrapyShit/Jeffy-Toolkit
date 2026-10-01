"""Builds a rig from the guides in the scene.

::

    from jeffy.autorig import templates, builder
    templates.create("biped")            # place guides (adjust them in the viewport)
    builder.build(name="hero")            # build the rig
    builder.delete_rig()                  # back to guides
"""

import json

from maya import cmds

from jeffy.autorig import components, guides
from jeffy.core import attributes, logger, mathlib, naming
from jeffy.rig import structure as rig_structure

LOG = logger.get_logger("autorig")

GUIDE_DATA_ATTR = "jeffyGuideData"


class RigContext(object):
    """Shared state while building: structure and built components."""

    def __init__(self, structure, components_by_name):
        self.structure = structure
        self.components = components_by_name

    def resolve(self, reference, requester=None):
        """``"C_spine.chest"`` -> ``(rig_node, joint)`` (``(None, None)`` if missing)."""
        if not reference:
            root = self.components.get("C_root")
            if root is not None and root is not requester and "root" in root.outputs:
                return root.outputs["root"]
            if requester is not None and requester.TYPE == "root":
                return None, None
            return self.structure.local_ctl, None
        component_name, _, output = reference.partition(".")
        component = self.components.get(component_name)
        if component is None:
            LOG.warning("Unknown parent component %s", component_name)
            return self.structure.local_ctl, None
        if output not in component.outputs:
            LOG.warning("%s has no output %r (available: %s)", component_name, output,
                        ", ".join(sorted(component.outputs)))
            return self.structure.local_ctl, None
        return component.outputs[output]

    def output_node(self, reference):
        component_name, _, output = reference.partition(".")
        component = self.components.get(component_name)
        if component and output in component.outputs:
            return component.outputs[output][0]
        return None


def collect_components(roots=None):
    """Instantiate components from guide roots (in dependency order)."""
    roots = roots or guides.get_guide_roots()
    if not roots:
        raise ValueError("No guides in the scene - create a template or add components first")
    instances = {}
    for root in roots:
        info = guides.get_info(root)
        component_class = components.get(info["type"])
        instance = component_class.from_guide(root)
        if instance.full_name in instances:
            raise ValueError("Two components are named %s" % instance.full_name)
        instances[instance.full_name] = instance
    return sort_components(instances)


def sort_components(instances):
    """Topological sort: parents before children (root first)."""
    ordered = []
    visiting = set()

    def visit(name):
        if name in ordered:
            return
        if name in visiting:
            raise ValueError("Cyclic component parenting around %s" % name)
        visiting.add(name)
        component = instances[name]
        parent_name = component.parent_output.partition(".")[0]
        if parent_name and parent_name in instances:
            visit(parent_name)
        elif not parent_name and component.TYPE != "root" and "C_root" in instances:
            visit("C_root")
        visiting.discard(name)
        ordered.append(name)

    for name in sorted(instances, key=lambda n: (instances[n].TYPE != "root", n)):
        visit(name)
    return [instances[name] for name in ordered]


def _rig_size(component_list):
    points = []
    for component in component_list:
        points.extend(component.positions.values())
    if not points:
        return 10.0
    mins, maxs = mathlib.bounding_box(points)
    height = max(maxs[i] - mins[i] for i in range(3))
    return max(height * 0.25, 1.0)


def build(name="character", roots=None, hide_guides=True, create_sets=True, lock=True):
    """Build a rig from the guides. Returns the :class:`RigStructure`."""
    component_list = collect_components(roots)
    guide_data = [guides.get_info(r) for r in (roots or guides.get_guide_roots())]
    structure = rig_structure.create(name, size=_rig_size(component_list))
    by_name = {c.full_name: c for c in component_list}
    context = RigContext(structure, by_name)

    for component in component_list:
        LOG.info("Building %s (%s)", component.full_name, component.TYPE)
        try:
            component.build(context)
        except Exception:
            LOG.error("Failed while building %s", component.full_name)
            raise
    for component in component_list:
        component.post_build(context)

    if create_sets:
        _create_sets(name, component_list)
    attributes.set_string(structure.rig, GUIDE_DATA_ATTR, json.dumps(guide_data))
    cmds.setAttr(structure.rig + "." + GUIDE_DATA_ATTR, lock=True)
    if lock:
        from jeffy.utils import scene

        scene.set_historical_interest(structure.rig, 0)
    if hide_guides:
        guides.set_guides_visible(False)
    try:
        from jeffy.utils import pose

        pose.store_bind_pose([ctl.node for c in component_list for ctl in c.controls if hasattr(ctl, "node")])
    except Exception as error:  # bind pose storage is a convenience only
        LOG.warning("Could not store bind pose: %s", error)
    cmds.select(clear=True)
    LOG.info("Rig %s built with %d components", name, len(component_list))
    return structure


def _create_sets(name, component_list):
    controls = []
    joints = []
    for component in component_list:
        controls.extend(ctl.node for ctl in component.controls if hasattr(ctl, "node"))
        joints.extend(component.bind_joints)
    structure_controls = []
    for rig in rig_structure.find(name):
        structure_controls.extend([rig.global_ctl, rig.local_ctl])
    controls_set = cmds.sets(structure_controls + controls, name=naming.unique_name("%s_controls_SET" % name))
    skin_set = cmds.sets([j for j in joints if cmds.objExists(j)],
                         name=naming.unique_name("%s_skinJoints_SET" % name))
    return controls_set, skin_set


def find_rigs():
    return rig_structure.find()


def delete_rig(name=None, show_guides=True):
    """Delete built rigs (keeps geometry under the geometry group)."""
    for structure in rig_structure.find(name):
        geometry = structure.geometry
        if geometry:
            children = cmds.listRelatives(geometry, children=True, fullPath=True) or []
            if children:
                cmds.parent(children, world=True)
        sets = cmds.ls("%s_controls_SET*" % structure.name, "%s_skinJoints_SET*" % structure.name, type="objectSet")
        if sets:
            cmds.delete(sets)
        cmds.delete(structure.rig)
    if show_guides:
        guides.set_guides_visible(True)


def rebuild(name="character"):
    """Delete the rig and build it again from the (edited) guides."""
    delete_rig(name)
    return build(name)


def restore_guides(rig=None):
    """Re-create guides from the data stored on a built rig."""
    structures = rig_structure.find() if rig is None else [rig_structure.RigStructure(rig)]
    if not structures:
        raise ValueError("No rig found")
    raw = attributes.get_string(structures[0].rig, GUIDE_DATA_ATTR)
    if not raw:
        raise ValueError("The rig has no stored guide data")
    return guides.load_template({"components": json.loads(raw)}, replace=True)


def add_component(component_type, name=None, side=None, parent_output="", settings=None, size=None):
    """Create guides for a new component (e.g. from the UI)."""
    component_class = components.get(component_type)
    component = component_class(name=name, side=side, settings=settings, parent_output=parent_output,
                                size=size or 1.0)
    return component.create_guide()
