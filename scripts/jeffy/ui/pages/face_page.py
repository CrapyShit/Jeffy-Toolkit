"""Face tab: sliders / face boards, on-face controls, curve rigs, blink."""

from jeffy.ui import actions
from jeffy.ui import widgets as w


class FacePage(w.Page):
    TITLE = "Face"

    def build(self):
        self.face_size = w.spin(0.3, 0.001, 1000.0, 3, 0.05, "Control size (times the global rig scale)")
        self.layout_.addWidget(w.row(("Size", self.face_size)))

        sliders = self.section("Sliders / Face Board")
        self.slider_name = w.line_edit("smile", "slider name")
        self.slider_mode = w.combo(["vertical", "horizontal", "square"], "vertical",
                                   "square: 2D slider (up/down + left/right)")
        self.slider_two = w.check("Two sided", True, "Handle goes both ways (up and down outputs)")
        sliders.add(w.row(("Name", self.slider_name), self.slider_mode, self.slider_two))
        sliders.add(w.button("Create Slider", lambda: actions.create_face_slider(
            self.slider_name.text(), self.slider_mode.currentText(), self.slider_two.isChecked(),
            self.face_size.value() * 3.0),
            "A handle limited to its frame with 0..1 outputs on the control: up, down, right, left. "
            "Created at the selection (or the origin)."))
        self.board_columns = w.spin(6, 1, 50, 0, 1)
        sliders.add(w.row(("Columns", self.board_columns), w.button(
            "Face Board From Blendshape", lambda: actions.face_board_from_blendshape(
                self.face_size.value() * 3.0, self.board_columns.value()),
            "Select the mesh (or the blendShape node): one labelled slider per target, already connected. "
            "Pairs like browUp / browDown share one two-sided slider. Driven targets are skipped.")))
        self.connect_direction = w.combo(["up", "down", "right", "left"], "up")
        self.connect_target = w.line_edit("", "blendshape target")
        sliders.add(w.row(self.connect_direction, ("Target", self.connect_target), w.button(
            "Connect", lambda: actions.connect_face_slider(self.connect_direction.currentText(),
                                                           self.connect_target.text()),
            "Select the slider control, then the mesh (or blendShape node)")))

        surface = self.section("On-Face Controls")
        self.surface_name = w.line_edit("face", "name")
        self.surface_method = w.combo(["uvPin", "follicle"], "uvPin", "uvPin needs Maya 2020+")
        surface.add(w.row(("Name", self.surface_name), self.surface_method, w.button(
            "On-Face Controls", lambda: actions.build_surface_controls(
                self.surface_name.text(), self.face_size.value(), self.surface_method.currentText()),
            "Select vertices (one control each) or existing joints, then the face mesh last. Each control "
            "rides on the mesh and drives a joint, with no double transform. Skin the mesh to the joints "
            "(the mesh needs UVs).")))

        curve = self.section("Curve Rigs (lips, brows, lids)")
        self.curve_name = w.line_edit("upperLip", "name")
        self.curve_controls = w.spin(5, 2, 50, 0, 1)
        self.curve_aim = w.check("Aim from center (eyelids)", False,
                                 "Joints rotate around the selected eye joint so lids slide over the eyeball")
        curve.add(w.row(("Name", self.curve_name), ("Controls", self.curve_controls)))
        curve.add(w.row(self.curve_aim, w.button("Curve Rig From Edge Loop", lambda: actions.build_face_curve_rig(
            self.curve_name.text(), self.curve_controls.value(), self.face_size.value(), self.curve_aim.isChecked()),
            "Select an edge loop (lip line, brow, lid edge) and optionally the head joint (the rig follows it) "
            "- or the eye joint with 'Aim from center'. One joint per vertex follows a curve driven by "
            "the controls; skin the mesh to the joints.")))
        self.blink_height = w.spin(0.2, 0.0, 1.0, 2, 0.05, "Where the lids meet: 0 upper lid, 1 lower lid")
        curve.add(w.row(("Blink height", self.blink_height), w.button(
            "Eyelid Blink", lambda: actions.build_eyelid_blink(self.blink_height.value()),
            "Select the upper lid rig's Main control, the lower lid's Main control and optionally the control "
            "receiving 'blink' / 'blinkHeight'. Both lid rigs need the same number of controls.")))
