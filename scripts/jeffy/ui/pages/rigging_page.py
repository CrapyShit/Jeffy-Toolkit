"""Rigging tab: FK, IK, IK/FK, spline, ribbon, twist, foot, spaces, attach..."""

from jeffy.ui import actions
from jeffy.ui import widgets as w


class RiggingPage(w.Page):
    TITLE = "Rigging"

    def build(self):
        structure = self.section("Rig Structure", expanded=False)
        self.rig_name = w.line_edit("character")
        self.rig_size = w.spin(10.0, 0.01, 10000.0, 2, 1.0)
        structure.add(w.row(("Name", self.rig_name), ("Size", self.rig_size),
                            w.button("Create Structure", lambda: actions.create_rig_structure(
                                self.rig_name.text() or "character", self.rig_size.value()))))

        common = self.section("Chain Options")
        self.size_box = w.spin(1.0, 0.001, 10000.0, 3, 0.25, "Control size")
        self.stretch = w.check("Stretch", True)
        self.soft = w.check("Soft IK", True)
        self.pin = w.check("Pin (elbow/knee lock)", True)
        self.pole = w.spin(1.0, 0.0, 100.0, 2, 0.1, "Pole vector distance (x chain length)")
        common.add(w.row(("Size", self.size_box), ("Pole dist.", self.pole)))
        common.add(w.row(self.stretch, self.soft, self.pin))

        limbs = self.section("FK / IK")
        self.fk_connect = w.combo(["constraint", "matrix", "none"], "constraint")
        limbs.add(w.row(("FK drive", self.fk_connect),
                        w.button("FK Chain", lambda: actions.build_fk(size=self.size_box.value(),
                                                                      connect=self.fk_connect.currentText()),
                                 "Select a chain (root, or root + end)")))
        limbs.add(w.grid([
            w.button("IK Chain", lambda: actions.build_ik(self.stretch.isChecked(), self.soft.isChecked(),
                                                          self.pin.isChecked(), self.pole.value(),
                                                          self.size_box.value()),
                     "Select start and end joints"),
            w.button("IK/FK Limb", lambda: actions.build_ikfk(self.stretch.isChecked(), self.soft.isChecked(),
                                                              self.pin.isChecked(), self.pole.value(),
                                                              self.size_box.value()),
                     "Select start and end joints of a 3 joint limb"),
            w.button("IK/FK Match + Switch", lambda: actions.ikfk_switch(False),
                     "Snap the selected limb to the other mode"),
        ], 3))

        spline = self.section("Spline IK / Ribbon", expanded=False)
        self.spline_controls = w.spin(3, 2, 50, 0, 1)
        self.volume = w.check("Volume", True)
        spline.add(w.row(("Controls", self.spline_controls), self.volume,
                         w.button("Spline IK", lambda: actions.build_spline(
                             self.spline_controls.value(), self.stretch.isChecked(), self.volume.isChecked(),
                             self.size_box.value()), "Select start and end joints")))
        self.ribbon_joints = w.spin(5, 2, 100, 0, 1)
        self.ribbon_controls = w.spin(3, 2, 50, 0, 1)
        self.ribbon_name = w.line_edit("ribbon")
        spline.add(w.row(("Joints", self.ribbon_joints), ("Controls", self.ribbon_controls),
                         ("Name", self.ribbon_name)))
        spline.add(w.button("Ribbon Between Selection", lambda: actions.build_ribbon(
            self.ribbon_joints.value(), self.ribbon_controls.value(), None, self.ribbon_name.text() or "ribbon"),
            "Select two or more objects in order"))

        twist = self.section("Twist / Foot / Fingers", expanded=False)
        self.twist_count = w.spin(3, 1, 20, 0, 1)
        self.twist_mode = w.combo(["forward", "reverse"], "forward",
                                  "forward: forearm style, reverse: upper arm style")
        twist.add(w.row(("Twist joints", self.twist_count), ("Mode", self.twist_mode),
                        w.button("Create Twist", lambda: actions.build_twist(self.twist_count.value(),
                                                                             self.twist_mode.currentText()),
                                 "Select start and end joints")))
        twist.add(w.button("Reverse Foot", actions.build_reverse_foot,
                           "Select in order: IK control, IK end target, ankle, ball, toe, heel locator, inner "
                           "locator, outer locator"))
        twist.add(w.button("Finger Controls", lambda: actions.build_fingers(self.size_box.value()),
                           "Select finger root joints (and optionally the control receiving the attributes)"))

        spaces = self.section("Spaces / Constraints", expanded=False)
        self.space_mode = w.combo(["parent", "orient", "point"], "parent")
        self.space_method = w.combo(["constraint", "matrix"], "constraint")
        self.space_attr = w.line_edit("space")
        spaces.add(w.row(("Mode", self.space_mode), ("Method", self.space_method), ("Attr", self.space_attr)))
        spaces.add(w.button("Add Space Switch", lambda: actions.add_space_switch(
            self.space_mode.currentText(), self.space_method.currentText(), self.space_attr.text() or "space"),
            "Select the control first, then the space targets"))
        self.space_name = w.line_edit("world", "space label or index")
        self.space_key = w.check("Key", False)
        spaces.add(w.row(self.space_name, self.space_key, w.button("Switch Space (seamless)", self._switch_space)))
        self.mo = w.check("Maintain offset", True)
        spaces.add(w.row(self.mo, w.button("Matrix Constraint", lambda: actions.matrix_constraint(
            self.mo.isChecked()), "Driver first, then driven"),
            w.button("Remove Matrix Con.", actions.remove_matrix_constraint)))

        attach = self.section("Attach / Misc", expanded=False)
        self.attach_method = w.combo(["follicle", "uvPin"], "follicle")
        attach.add(w.row(("Method", self.attach_method),
                         w.button("Attach / Rivet", lambda: actions.attach_to_geometry(
                             self.attach_method.currentText()),
                             "Select components, or objects then the mesh last")))
        self.eye_distance = w.spin(30.0, 0.1, 10000.0, 2, 1.0)
        attach.add(w.row(("Aim distance", self.eye_distance),
                         w.button("Eye / Look-at Rig", lambda: actions.build_eye_rig(self.eye_distance.value()),
                                  "Select eye joints")))
        self.reader_angle = w.spin(60.0, 1.0, 180.0, 1, 5.0)
        attach.add(w.row(("Cone angle", self.reader_angle),
                         w.button("Pose Reader", lambda: actions.create_pose_reader(self.reader_angle.value()),
                                  "Select joints posed in the target pose")))
        attach.add(w.grid([
            w.button("Dynamic Chain (nHair)", actions.create_dynamic_chain, "Select a driven joint chain"),
            w.button("Connector Line", actions.connector_line, "Line between two objects (pole vector style)"),
        ], 2))

        expression = self.section("Expression To Nodes", expanded=False)
        expression.add(w.label("Write math, get utility nodes (no expression node). Example:\n"
                               "jaw_JNT.rz = clamp(jaw_CTL.ty, -1, 5) * -10\n"
                               "box.tx = ctl.flag > 0.5 ? ctl.tx : lerp(0, 10, ctl.blend)"))
        from jeffy.ui.qt import QtWidgets

        self.expression = QtWidgets.QPlainTextEdit()
        self.expression.setMinimumHeight(80)
        expression.add(self.expression)
        expression.add(w.button("Build Network", lambda: actions.build_expression(self.expression.toPlainText())))

    def _switch_space(self):
        value = self.space_name.text().strip()
        actions.switch_space(int(value) if value.isdigit() else value, self.space_key.isChecked())
