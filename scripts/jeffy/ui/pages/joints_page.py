"""Joints tab: creation, orientation, mirroring and display."""

from jeffy.ui import actions
from jeffy.ui import widgets as w

UP_VECTORS = {"+X": (1, 0, 0), "-X": (-1, 0, 0), "+Y": (0, 1, 0), "-Y": (0, -1, 0), "+Z": (0, 0, 1),
              "-Z": (0, 0, -1)}


class JointsPage(w.Page):
    TITLE = "Joints"

    def build(self):
        create = self.section("Create")
        self.name = w.line_edit("joint", "Base name")
        self.chain = w.check("Chain", True, "Parent joints in selection order")
        self.center = w.check("Single at center", False)
        create.add(w.row(("Name", self.name), self.chain, self.center))
        create.add(w.button("Joints At Selection", lambda: actions.joints_at_selection(
            self.chain.isChecked(), self.center.isChecked(), self.name.text() or "joint"),
            "Objects or components (edge loops, vertices...)"))
        self.count = w.spin(5, 1, 500, 0, 1)
        create.add(w.row(("Count", self.count),
                         w.button("Joints On Curve", lambda: actions.joints_on_curve(self.count.value(),
                                                                                     self.name.text() or "curve")),
                         w.button("Insert Joints", lambda: actions.insert_joints(self.count.value()),
                                  "Split the selected joint(s) into equal segments")))
        self.search = w.line_edit("_JNT", "search")
        self.replace = w.line_edit("_DUP_JNT", "replace")
        create.add(w.row(("Search", self.search), ("Replace", self.replace),
                         w.button("Duplicate Chain", lambda: actions.duplicate_chain(self.search.text(),
                                                                                     self.replace.text()))))

        orient = self.section("Orient")
        self.aim = w.combo(w.AXES, "x")
        self.up = w.combo(w.AXES, "y")
        self.up_mode = w.combo(["world", "plane", "object", "keep"], "plane",
                               "plane: bending plane of the chain, object: select the up object last")
        self.world_up = w.combo(list(UP_VECTORS), "+Y")
        orient.add(w.row(("Aim", self.aim), ("Up", self.up)))
        orient.add(w.row(("Up mode", self.up_mode), ("World up", self.world_up)))
        self.end_mode = w.combo(["parent", "world", "keep"], "parent", "Orientation of end joints")
        self.hierarchy = w.check("Hierarchy", True)
        orient.add(w.row(("End joints", self.end_mode), self.hierarchy))
        orient.add(w.button("Orient Joints", self._orient, height=32))
        orient.add(w.grid([
            w.button("X +90", lambda: actions.rotate_joint_axes((90, 0, 0))),
            w.button("Y +90", lambda: actions.rotate_joint_axes((0, 90, 0))),
            w.button("Z +90", lambda: actions.rotate_joint_axes((0, 0, 90))),
            w.button("X -90", lambda: actions.rotate_joint_axes((-90, 0, 0))),
            w.button("Y -90", lambda: actions.rotate_joint_axes((0, -90, 0))),
            w.button("Z -90", lambda: actions.rotate_joint_axes((0, 0, -90))),
            w.button("Orient To World", actions.orient_to_world),
            w.button("Freeze Rotations", actions.freeze_joint_rotations, "Move rotate into jointOrient"),
            w.button("Zero End Orients", actions.zero_end_orients),
            w.button("Planarize Chain", actions.planarize_chain, "Snap the chain onto its plane"),
            w.button("Set Preferred Angles", actions.set_preferred_angles),
            w.button("Toggle Local Axes", lambda: actions.toggle_local_axes(True)),
        ], 3))

        mirror = self.section("Mirror", expanded=False)
        self.mirror_axis = w.combo(["x", "y", "z"], "x")
        self.behavior = w.check("Behavior", True)
        self.mirror_search = w.line_edit("L_")
        self.mirror_replace = w.line_edit("R_")
        mirror.add(w.row(("Axis", self.mirror_axis), self.behavior, ("Search", self.mirror_search),
                         ("Replace", self.mirror_replace)))
        mirror.add(w.button("Mirror Joints", lambda: actions.mirror_joints(
            self.mirror_axis.currentText(), self.behavior.isChecked(), self.mirror_search.text(),
            self.mirror_replace.text())))

        display = self.section("Display / Attributes", expanded=False)
        self.radius = w.spin(1.0, 0.001, 1000.0, 3, 0.25)
        display.add(w.row(("Radius", self.radius), w.button("Set Radius", lambda: actions.set_joint_radius(
            self.radius.value()))))
        self.draw_style = w.combo(["bone", "box", "none", "joint"], "bone")
        display.add(w.row(("Draw style", self.draw_style),
                          w.button("Set Draw Style", lambda: actions.set_draw_style(self.draw_style.currentText()))))
        display.add(w.grid([
            w.button("Label Joints", actions.label_joints, "Side/type labels from names (for mirroring skins)"),
            w.button("Select End Joints", actions.select_end_joints),
            w.button("Select Hierarchy", lambda: actions.select_hierarchy("joint")),
            w.button("Seg. Scale Comp. On", lambda: actions.segment_scale_compensate(True)),
            w.button("Seg. Scale Comp. Off", lambda: actions.segment_scale_compensate(False)),
            w.button("Capsule Proxies", actions.capsule_proxies, "Cylinders along the joints"),
        ], 3))

    def _orient(self):
        actions.orient_joints(aim_axis=self.aim.currentText(), up_axis=self.up.currentText(),
                              up_mode=self.up_mode.currentText(), world_up=UP_VECTORS[self.world_up.currentText()],
                              end_mode=self.end_mode.currentText(), hierarchy=self.hierarchy.isChecked())
