"""Animate tab: rig testing helpers - poses, IK/FK, spaces, baking, export."""

from jeffy.ui import actions
from jeffy.ui import widgets as w


class AnimationPage(w.Page):
    TITLE = "Animate"

    def build(self):
        pose = self.section("Pose")
        pose.add(w.grid([
            w.button("Reset Controls", actions.reset_controls, "Selected controls, or all controls"),
            w.button("Go To Bind Pose", actions.controls_bind_pose),
            w.button("Store Bind Pose", actions.store_bind_pose),
            w.button("Mirror Pose", lambda: actions.mirror_pose("x"), "Selected controls -> other side"),
            w.button("Flip Pose", lambda: actions.flip_pose("x")),
            w.button("Select All Controls", actions.select_all_controls),
            w.button("Key Controls", actions.key_controls),
            w.button("Save Pose...", actions.save_pose),
            w.button("Load Pose...", lambda: actions.load_pose(1.0)),
        ], 3))

        switches = self.section("IK/FK & Spaces")
        self.key = w.check("Key the switch", False)
        switches.add(w.row(self.key, w.button("IK/FK Match + Switch", lambda: actions.ikfk_switch(
            self.key.isChecked()))))
        self.space = w.line_edit("world", "space label")
        switches.add(w.row(("Space", self.space), w.button("Switch Selected", lambda: actions.switch_space(
            self.space.text().strip(), self.key.isChecked()))))

        bake = self.section("Bake / Export", expanded=False)
        bake.add(w.grid([
            w.button("Bake Selected", actions.bake_selected),
            w.button("Create Export Skeleton", actions.create_export_skeleton,
                     "Select the root joint: a clean copy constrained to the rig"),
            w.button("Bake Skeleton", actions.bake_skeleton, "Bake the selected skeleton and remove constraints"),
            w.button("FBX Export...", actions.export_fbx),
        ], 2))
