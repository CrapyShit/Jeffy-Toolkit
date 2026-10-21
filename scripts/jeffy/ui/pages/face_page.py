"""Face tab, in rig building order: lips / brows / lids, jaw and follows,
on-face controls, then blendshapes (sliders, face board, channel drivers)."""

from jeffy.ui import actions
from jeffy.ui import widgets as w


class FacePage(w.Page):
    TITLE = "Face"

    def build(self):
        self.face_size = w.spin(0.3, 0.001, 1000.0, 3, 0.05, "Control size (times the global rig scale)")
        self.layout_.addWidget(w.row(("Size", self.face_size)))

        # lips / brows / lids ---------------------------------------------------
        lines = self.section("Lips / Brows / Lids")
        self.line_name = w.line_edit("upperLip", "name (upperLip, lowerLip, L_brow, upperLid...)")
        self.line_controls = w.spin(5, 2, 50, 0, 1)
        lines.add(w.row(("Name", self.line_name), ("Controls", self.line_controls)))
        lines.add(w.button("Face Ribbon From Edge Loop", lambda: actions.build_face_ribbon(
            self.line_name.text(), self.line_controls.value(), self.face_size.value()),
            "Lips, brows, cheek lines, folds. Select an edge loop and optionally the head joint (the rig "
            "follows it). A ribbon follows the loop with one skin joint per vertex; a few controls under a Main "
            "control shape it, and their rotations roll / twist the lip or brow."))
        self.curve_aim = w.check("Aim from center (eyelids)", False,
                                 "Joints rotate around the selected eye joint so lids slide over the eyeball")
        lines.add(w.row(self.curve_aim, w.button("Curve Rig From Edge Loop", lambda: actions.build_face_curve_rig(
            self.line_name.text(), self.line_controls.value(), self.face_size.value(), self.curve_aim.isChecked()),
            "Eyelids (with 'Aim from center' and the eye joint selected after the loop), or lips that need a "
            "seal. One joint per vertex follows a curve driven by the controls.")))
        self.blink_height = w.spin(0.2, 0.0, 1.0, 2, 0.05, "Where the lids meet: 0 upper lid, 1 lower lid")
        lines.add(w.row(("Blink height", self.blink_height), w.button(
            "Eyelid Blink", lambda: actions.build_eyelid_blink(self.blink_height.value()),
            "Select the upper lid curve rig's Main control, the lower lid's Main control and optionally the "
            "control receiving 'blink' / 'blinkHeight'. Both need the same number of controls.")))
        self.seal_height = w.spin(0.5, 0.0, 1.0, 2, 0.05, "Where the lips meet: 0 upper lip, 1 lower lip")
        lines.add(w.row(("Seal height", self.seal_height), w.button(
            "Lip Seal", lambda: actions.build_lip_seal(self.seal_height.value()),
            "Select the upper lip curve rig's Main control, the lower lip's Main control and optionally the "
            "control receiving 'seal' / 'sealHeight' (lips pressed together whatever the jaw does).")))

        # jaw and follows ----------------------------------------------------------
        follows = self.section("Jaw / Follow")
        follows.add(w.button("Jaw", lambda: actions.build_face_jaw(self.face_size.value() * 3.0),
                             "Select the jaw joint, then optionally the upper lip and lower lip Main controls. "
                             "The lower lip follows the jaw, the upper lip a little, the corners halfway "
                             "(lowerLipFollow, upperLipFollow, cornerFollow on the jaw control)."))
        self.follow_percent = w.spin(0.5, 0.0, 1.0, 2, 0.05, "Default follow amount (animatable afterwards)")
        self.follow_mode = w.combo(["parent", "orient", "point"], "parent")
        follows.add(w.row(("Amount", self.follow_percent), self.follow_mode, w.button(
            "Partial Follow", lambda: actions.add_partial_follow(self.follow_percent.value(),
                                                                 self.follow_mode.currentText()),
            "Select the driver, then the controls that follow it (cheeks after a lip corner, nose after the "
            "upper lip...). Adds a 0..1 'follow' attribute on each control.")))
        self.fleshy_percent = w.spin(0.3, 0.0, 1.0, 2, 0.05, "How much the lids follow the eye")
        follows.add(w.row(("Amount", self.fleshy_percent), w.button(
            "Fleshy Eyes", lambda: actions.add_fleshy_eyes(self.fleshy_percent.value()),
            "Select the eye joint (or eye control), then the lid Main controls: the lids rotate with the eye "
            "around its centre ('eyeFollow' attribute).")))

        # on-face controls ---------------------------------------------------------
        surface = self.section("On-Face Controls", expanded=False)
        self.surface_name = w.line_edit("face", "name")
        self.surface_method = w.combo(["uvPin", "follicle"], "uvPin", "uvPin needs Maya 2020+")
        surface.add(w.row(("Name", self.surface_name), self.surface_method, w.button(
            "On-Face Controls", lambda: actions.build_surface_controls(
                self.surface_name.text(), self.face_size.value(), self.surface_method.currentText()),
            "Select vertices (one control each) or existing joints, then the face mesh last. Each control "
            "rides on the mesh and drives a joint, with no double transform. Skin the mesh to the joints "
            "(the mesh needs UVs).")))

        # blendshapes ----------------------------------------------------------------
        shapes = self.section("Blendshapes", expanded=False)
        self.board_columns = w.spin(6, 1, 50, 0, 1)
        shapes.add(w.row(("Columns", self.board_columns), w.button(
            "Face Board From Blendshape", lambda: actions.face_board_from_blendshape(
                self.face_size.value() * 3.0, self.board_columns.value()),
            "Select the mesh (or the blendShape node): one labelled slider per target, already connected. "
            "Pairs like browUp / browDown share one two-sided slider. Driven targets are skipped.")))
        self.slider_name = w.line_edit("smile", "slider name")
        self.slider_mode = w.combo(["vertical", "horizontal", "square"], "vertical",
                                   "square: 2D slider (up/down + left/right)")
        self.slider_two = w.check("Two sided", True, "Handle goes both ways (up and down outputs)")
        shapes.add(w.row(("Name", self.slider_name), self.slider_mode, self.slider_two))
        shapes.add(w.button("Create Slider", lambda: actions.create_face_slider(
            self.slider_name.text(), self.slider_mode.currentText(), self.slider_two.isChecked(),
            self.face_size.value() * 3.0),
            "A handle limited to its frame with 0..1 outputs on the control: up, down, right, left. "
            "Created at the selection (or the origin)."))
        self.connect_direction = w.combo(["up", "down", "right", "left"], "up")
        self.connect_target = w.line_edit("", "blendshape target")
        shapes.add(w.row(self.connect_direction, ("Target", self.connect_target), w.button(
            "Connect Slider", lambda: actions.connect_face_slider(self.connect_direction.currentText(),
                                                                  self.connect_target.text()),
            "Select the slider control, then the mesh (or blendShape node)")))
        self.channel_attr = w.line_edit("translateY", "attribute")
        self.channel_min = w.spin(0.0, -10000.0, 10000.0, 3, 0.1)
        self.channel_max = w.spin(1.0, -10000.0, 10000.0, 3, 0.1)
        self.channel_target = w.line_edit("", "blendshape target")
        shapes.add(w.row(("Attr", self.channel_attr), ("From", self.channel_min), ("To", self.channel_max)))
        shapes.add(w.row(("Target", self.channel_target), w.button(
            "Connect Channel", lambda: actions.connect_channel_to_target(
                self.channel_attr.text().strip(), self.channel_min.value(), self.channel_max.value(),
                self.channel_target.text()),
            "Select any control (an on-face control, a brow control...), then the mesh: its attribute "
            "drives the target from 'From' (0) to 'To' (1), clamped - no set driven keys.")))
