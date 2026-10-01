"""Spine component: COG, hips, FK spine and a stretchy spline IK on top."""

from maya import cmds

from jeffy.autorig import components
from jeffy.autorig.components.base import Component
from jeffy.controls import shapes
from jeffy.controls.control import Control
from jeffy.core import mathlib, matrix
from jeffy.geometry import curves
from jeffy.rig import common, spline


@components.register
class SpineComponent(Component):
    TYPE = "spine"
    DESCRIPTION = "COG + hips + FK/IK spline spine with stretch and volume."
    DEFAULT_NAME = "spine"
    GUIDES = [
        ("hips", (0.0, 98.0, 0.0), None),
        ("spine1", (0.0, 108.0, 0.5), "hips"),
        ("spine2", (0.0, 121.0, 0.0), "spine1"),
        ("chest", (0.0, 135.0, -1.0), "spine2"),
    ]
    SETTINGS = {"joint_count": 5, "fk_controls": 3, "stretch": True, "volume": True}

    def _guide_points(self):
        return [self.position(label) for label in ("hips", "spine1", "spine2", "chest")]

    def build_skeleton(self, parent):
        points = self._guide_points()
        temp = curves.curve_from_points(points, name="jeffy_spineTmp_CRV", degree=3, through=True)
        try:
            positions = curves.positions_along(temp, max(3, int(self.setting("joint_count"))))
        finally:
            cmds.delete(temp)
        labels = ["%02d" % (i + 1) for i in range(len(positions))]
        self.spine_joints = self.create_chain(labels, positions, parent=parent, up_mode="world",
                                              world_up=(0.0, 0.0, 1.0))
        # pelvis shares the orientation of the first spine joint
        self.pelvis = self.create_joint("pelvis", positions[0], parent=parent)
        matrix.set_joint_orient_from_matrix(self.pelvis, matrix.get_world_matrix(self.spine_joints[0]))
        self.spine_joints[0] = cmds.parent(self.spine_joints[0], self.pelvis)[0]
        self.bind_joints = [self.pelvis] + self.spine_joints

    def build_rig(self):
        points = self._guide_points()
        length = sum(mathlib.distance(a, b) for a, b in zip(points, points[1:]))
        joints = self.spine_joints

        cog = Control.create("cog", side=self.side, shape="cog", size=length * 0.6, parent=self.controls_group,
                             position=points[0], color_value="yellow")
        hips = Control.create("hips", side=self.side, shape="hip", size=length * 0.35, axis="x", parent=cog.node,
                              match=self.pelvis, color_value="light_yellow")
        cmds.parentConstraint(hips.node, self.pelvis, maintainOffset=True)

        # FK chain
        fk_count = max(1, int(self.setting("fk_controls")))
        fk_indices = [int(round(i)) for i in mathlib.distribute(fk_count, 0, len(joints) - 2)] if fk_count > 1 \
            else [0]
        fk_controls = []
        current = cog.node
        for i, index in enumerate(fk_indices):
            ctl = Control.create("%sFK%02d" % (self.name, i + 1), side=self.side, shape="circle",
                                 size=length * 0.4, axis="x", parent=current, match=joints[index],
                                 color_value="yellow")
            ctl.set_parent_tag(current)
            fk_controls.append(ctl)
            current = ctl.node

        # Spline IK
        result = spline.build_spline_ik(joints, name=self.name, side=self.side, num_controls=3,
                                        control_parent=self.controls_group, systems_parent=self.systems_group,
                                        shape="circle", size=length * 0.45, up_axis="y",
                                        stretch=bool(self.setting("stretch")), volume=bool(self.setting("volume")))
        ik_hips, ik_mid, ik_chest = result["controls"]
        cmds.parent(ik_hips.zero, hips.node)
        cmds.parent(ik_chest.zero, fk_controls[-1].node)
        cmds.parent(ik_mid.zero, cog.node)
        constraint = cmds.parentConstraint(ik_hips.node, ik_chest.node, ik_mid.zero, maintainOffset=True)[0]
        cmds.setAttr(constraint + ".interpType", 2)
        shapes.replace_shape(ik_chest.node, "chest", size=length * 0.3, axis="x")
        common.hide(result["group"])

        self.register_controls([cog, hips] + fk_controls + [ik_hips, ik_mid, ik_chest])
        self.add_output("cog", cog.node, self.pelvis)
        self.add_output("hips", hips.node, self.pelvis)
        self.add_output("chest", ik_chest.node, joints[-1])
        self.add_output("base", fk_controls[0].node, joints[0])
