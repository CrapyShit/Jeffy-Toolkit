"""Generic chain component - tails, tentacles, ears, antennas, hair...

Modes: ``fk``, ``spline`` (spline IK with stretch/volume) and ``dynamic``
(FK + nHair overlap blended on the bind joints).
"""

from maya import cmds

from jeffy.autorig import components
from jeffy.autorig.components.base import Component
from jeffy.core import mathlib
from jeffy.joints import tools as joint_tools
from jeffy.rig import dynamics, fk, spline

MODES = ("fk", "spline", "dynamic")


@components.register
class ChainComponent(Component):
    TYPE = "chain"
    DESCRIPTION = "Generic joint chain with FK, spline IK or dynamic (nHair) modes."
    DEFAULT_NAME = "tail"
    SETTINGS = {"count": 6, "mode": "fk", "spline_controls": 3, "shape": "circle", "up_axis": "y"}

    @classmethod
    def guide_definitions(cls, settings=None):
        count = int((settings or {}).get("count", cls.SETTINGS["count"]))
        definitions = []
        parent = None
        for i in range(max(2, count)):
            label = "c%02d" % (i + 1)
            definitions.append((label, (0.0, 95.0, -8.0 - 8.0 * i), parent))
            parent = label
        return definitions

    def _labels(self):
        return [d[0] for d in self.guide_definitions(self.settings)]

    def build_skeleton(self, parent):
        labels = self._labels()
        positions = [self.position(label) for label in labels]
        up = mathlib.axis_vector(str(self.setting("up_axis")))
        self.joints = self.create_chain(labels, positions, parent=parent, up_mode="world", world_up=up)
        self.bind_joints = list(self.joints)

    def build_rig(self):
        mode = str(self.setting("mode"))
        if mode not in MODES:
            raise ValueError("%s: mode must be one of %s" % (self.full_name, MODES))
        positions = [self.position(label) for label in self._labels()]
        length = sum(mathlib.distance(a, b) for a, b in zip(positions, positions[1:]))
        size = length / max(1, len(positions)) * 0.6
        shape = str(self.setting("shape"))

        if mode == "spline":
            result = spline.build_spline_ik(self.joints, name=self.name, side=self.side,
                                            num_controls=max(2, int(self.setting("spline_controls"))),
                                            control_parent=self.controls_group, systems_parent=self.systems_group,
                                            shape=shape, size=size)
            controls = result["controls"]
            base = controls[0]
            for ctl in controls[1:]:
                cmds.parent(ctl.zero, base.node)
        elif mode == "dynamic":
            driver = joint_tools.duplicate_chain(self.joints[0], self.joints[-1], search="_JNT",
                                                 replace="_FKD_JNT", parent=self.systems_group)
            _rig_parent, parent_joint = self.parent_nodes()
            if parent_joint:
                cmds.parentConstraint(parent_joint, driver[0], maintainOffset=True)
            result = fk.build_fk_chain(driver, name=self.name, side=self.side, shape=shape, size=size, axis="x",
                                       parent=self.controls_group)
            controls = result["controls"]
            dynamics.create_dynamic_chain(driver, bind_joints=self.joints, name=self.name, side=self.side,
                                          attr_holder=controls[0].node, systems_parent=self.systems_group)
        else:
            result = fk.build_fk_chain(self.joints, name=self.name, side=self.side, shape=shape, size=size,
                                       axis="x", parent=self.controls_group, skip_last=True)
            controls = result["controls"]
        self.register_controls(controls)
        self.add_output("base", controls[0].node, self.joints[0])
        self.add_output("end", controls[-1].node, self.joints[-1])
