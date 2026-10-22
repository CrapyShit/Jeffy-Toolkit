"""Spaces: choose what a top control can follow, switched by its ``space`` enum (or the attribute you name).

Every setup already gives its top controls default spaces (an IK control:
root, world, COG, chest, parent...). This layer replaces them for one control
with your own list of targets and a mode:

* ``parent``: the control follows the chosen target completely,
* ``orient``: it stays attached to the first target, only its rotation
  follows the chosen one,
* ``point``: the opposite.

Deleting the layer gives the control its default spaces back. Use
:func:`jeffy.setups.core.attach.switch` (or the belt's switch button) to change
space without the control jumping.
"""

import re

from maya import cmds

from jeffy.core import naming
from jeffy.setups.core import attach, scene
from jeffy.setups.core import tag as tag_module
from jeffy.setups.core.base import Setup
from jeffy.setups.core.schema import NODE, NODES, Option, SetupError, Slot


@scene.register
class Spaces(Setup):
    TYPE = "spaces"
    LABEL = "Spaces"
    CATEGORY = "layer"
    ORDER = 90
    DESCRIPTION = ("Replace the spaces of a top control (IK, pole, FK top, master...) with your own targets. "
                   "The control gets a 'space' enum; switch it without popping from the Setups list.")
    SLOTS = (
        Slot("control", "Control", kind=NODE, tip="A top control of a setup (IK control, pole, FK top control...)"),
        Slot("targets", "Targets", kind=NODES,
             tip="Spaces in enum order: controls, outputs or bind joints (joints are replaced by the output "
                 "driving them). 'Load current' fills the control's current spaces."),
    )
    OPTIONS = (
        Option("mode", "Mode", "parent", choices=("parent", "orient", "point"),
               tip="parent: follow the target completely.\norient: stay on the first target, rotate with the "
                   "chosen one.\npoint: rotate with the first target, move with the chosen one."),
        Option("attr", "Attribute", "space", tip="Name of the enum attribute on the control"),
        Option("labels", "Labels", "", tip="Enum labels, comma separated (empty: from the target names)"),
        Option("default", "Default space", "", tip="Label used at first (empty: the first target)"),
    )
    HAS_GROUPS = False

    @classmethod
    def resolve_name_side(cls, slots, options, name=None, side=None):
        control = slots.get("control")
        parsed = naming.parse(control) if control else {"name": "", "side": None}
        name = naming.legalize(str(name or (parsed["name"] + "Spaces")).strip()).strip("_") or "spaces"
        if not side or side == "auto":
            side = parsed["side"] or naming.side_from_name(control or "") or naming.SIDE_CENTER
        return name, side

    @classmethod
    def validate(cls, slots, options):
        base = cls.find_base(slots)
        control = slots["control"]
        if base.anchor_index(control) is None:
            raise SetupError("%s has no spaces. Pick a top control of a setup (IK control, pole, FK top control, "
                             "master...)." % naming.short_name(control))
        for layer in base.layers():
            if isinstance(layer, Spaces) and layer.slot_node("control") == control:
                raise SetupError("%s already has %s: rebuild or delete it" % (naming.short_name(control),
                                                                               layer.describe()))
        family = set(base.family_tags())
        for target in slots.get("targets") or []:
            if target == control:
                raise SetupError("A control cannot be its own space")
            if not cmds.objectType(target, isAType="transform"):
                raise SetupError("%s is not a transform" % target)
            owner = scene.find_setup(target)
            used = attach.usable_target(target)
            if owner is not None and owner.tag in family and used not in base.controls.values():
                raise SetupError("%s is driven by %s itself (it would loop). Use a control or another setup."
                                 % (naming.short_name(target), base.describe()))
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", options.get("attr") or ""):
            raise SetupError("Attribute: '%s' is not a valid attribute name" % options.get("attr"))
        labels = _labels(slots.get("targets") or [], options.get("labels"))
        if options.get("default") and options["default"] not in labels:
            raise SetupError("Default space '%s' is not one of: %s" % (options["default"], ", ".join(labels)))

    @classmethod
    def rig_lookup_node(cls, slots):
        return slots.get("control")

    def build_setup(self):
        base = self.base
        control = self.slot_node("control")
        targets = self.slot_nodes("targets")
        labels = _labels(targets, self.option("labels"))
        index = base.anchor_index(control)
        custom = {"kind": self.option("mode"), "attr": self.option("attr"),
                  "targets": [[label, node] for label, node in zip(labels, targets)],
                  "default": self.option("default") or labels[0]}
        base.set_anchor_custom(index, custom)
        tag_module.set_data(self.tag, "anchor_index", index)

    def before_delete(self):
        base = self.base
        index = tag_module.get_data(self.tag, "anchor_index")
        if base is not None and cmds.objExists(base.tag) and index is not None:
            base.set_anchor_custom(index, None)


def _labels(targets, text):
    """Enum labels from ``text`` (comma separated) or from the target names (unique)."""
    given = [part.strip() for part in (text or "").split(",") if part.strip()]
    result = []
    for index, target in enumerate(targets):
        label = given[index] if index < len(given) else naming.parse(target)["name"] or naming.strip_namespace(target)
        label = re.sub(r"[^A-Za-z0-9_]", "_", label) or "space%d" % index
        candidate, number = label, 2
        while candidate in result:
            candidate = "%s%d" % (label, number)
            number += 1
        result.append(candidate)
    return result


def current_targets(control):
    """Nodes the control's anchor currently follows (to pre-fill the targets)."""
    setup = scene.find_setup(control)
    if setup is None:
        raise SetupError("%s is not part of a setup" % control)
    index = setup.anchor_index(control)
    if index is None:
        raise SetupError("%s has no spaces" % control)
    definition, _zero, _ctl = setup.anchors()[index]
    return [node for _label, node in attach.targets_of(setup, definition)]


def switch(control, space, key=False):
    """Seamless space switch (keeps the control where it is)."""
    return attach.switch(control, space, key=key)
