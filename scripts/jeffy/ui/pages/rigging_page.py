"""Rigging tab: FK, IK, IK/FK, spline, ribbon, twist, foot, spaces, attach..."""

from jeffy.ui import actions
from jeffy.ui import widgets as w


class RiggingPage(w.Page):
    TITLE = "Rigging"

    def build(self):
        structure = self.section("Rig Structure", expanded=False)
        self.rig_name = w.line_edit("character")
        self.rig_size = w.spin(10.0, 0.01, 10000.0, 2, 1.0)
        basic = w.row(("Name", self.rig_name), ("Size", self.rig_size),
                      w.button("Create Structure", lambda: actions.create_rig_structure(
                          self.rig_name.text() or "character", self.rig_size.value())))
        self.flex_name = w.line_edit("Robot")
        advanced = w.column(
            w.label("Flexible Rig master: controls + systems under the master; skeleton, models and deformers "
                    "outside it. VIZ switches: Skeleton, Geometry, Deformers, Rig_Systems. Flexible tools put "
                    "their parts in these groups."),
            w.row(("Name", self.flex_name), w.button("Create Flexible Structure", lambda: actions.
                                                     create_flexible_structure(self.flex_name.text() or "Robot",
                                                                               self.rig_size.value()))))
        structure.add(w.tabs(("Basic", basic), ("Advanced", advanced)))

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
        limbs_basic = w.column(
            w.row(("FK drive", self.fk_connect),
                  w.button("FK Chain", lambda: actions.build_fk(size=self.size_box.value(),
                                                                connect=self.fk_connect.currentText()),
                           "Select a chain (root, or root + end)")),
            w.grid([
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
        self.flex_stretch = w.check("Stretch (scaleX)", True)
        self.flex_pole = w.spin(0.0, 0.0, 100.0, 2, 0.1, "0 = pole control on the middle joint (course)")
        self.flex_ik_orient = w.combo(["joint", "world"], "joint", "IK control orientation")
        self.flex_pelvis = w.check("Pelvis selected first", True)
        limbs_advanced = w.column(
            w.label("Flexible Rig (antCGi) setups: IK_FK_Switch + reverse node on a global control, "
                    "condition/divide stretch on scaleX, chains following the root control."),
            w.row(self.flex_stretch, ("Pole dist.", self.flex_pole), ("IK orient", self.flex_ik_orient)),
            w.grid([
                w.button("Flexible IK/FK Limb", lambda: actions.build_flexible_limb(
                    self.flex_stretch.isChecked(), self.flex_pole.value(), self.size_box.value(),
                    self.flex_ik_orient.currentText()),
                    "Select the start and end bind joints (3 or more: ball/toe joints are blended too)"),
                w.button("Bind Helper Joints", actions.add_flexible_bind_helpers,
                         "Select the limb's global control: adds non-rotating elbow/wrist bind joints "
                         "following IK/FK (clean stretch weighting)"),
            ], 2),
            w.row(self.flex_pelvis, w.button("Flexible Spine (COG / hips)", lambda: actions.build_flexible_spine(
                self.size_box.value(), self.flex_pelvis.isChecked()),
                "Select the pelvis joint, then the first and last spine joints: one control per joint, "
                "COG drives the first, hips drive the pelvis")))
        limbs.add(w.tabs(("Basic", limbs_basic), ("Advanced", limbs_advanced)))

        spline = self.section("Spline IK / Ribbon", expanded=False)
        self.spline_controls = w.spin(3, 2, 50, 0, 1)
        self.volume = w.check("Volume", True)
        spline.add(w.row(("Controls", self.spline_controls), self.volume,
                         w.button("Spline IK", lambda: actions.build_spline(
                             self.spline_controls.value(), self.stretch.isChecked(), self.volume.isChecked(),
                             self.size_box.value()), "Select start and end joints")))
        spline.add(w.button("Spline IK/FK Switch", lambda: actions.build_spline_ikfk(
            self.spline_controls.value(), self.stretch.isChecked(), self.volume.isChecked(),
            self.size_box.value()),
            "Select start and end joints. Spline IK controls and FK controls with an 'ikFk' switch on the "
            "settings gear (0 FK, 1 IK). Rotating any IK control, the middle ones too, bends the curve "
            "('tangentLength' on each control sets how far)."))
        self.ribbon_joints = w.spin(5, 2, 100, 0, 1)
        self.ribbon_controls = w.spin(3, 2, 50, 0, 1)
        self.ribbon_name = w.line_edit("ribbon")
        self.ribbon_attach = w.check("Attach to selection", True)
        ribbon_basic = w.column(
            w.row(("Joints", self.ribbon_joints), ("Controls", self.ribbon_controls), ("Name", self.ribbon_name),
                  self.ribbon_attach),
            w.button("Ribbon Between Selection", lambda: actions.build_ribbon(
                self.ribbon_joints.value(), self.ribbon_controls.value(), None,
                self.ribbon_name.text() or "ribbon", self.ribbon_attach.isChecked()),
                "Select two or more objects in order. With 'Attach to selection', the ribbon follows the first "
                "and last objects. Skin your mesh to the ribbon's own joints."))
        self.flex_ribbon_joints = w.spin(9, 3, 101, 0, 2)
        self.flex_ribbon_deform = w.check("Sine / twist", True)
        self.flex_ribbon_crease = w.check("Crease fix", True)
        self.flex_ribbon_end = w.combo(["point", "parent"], "point", "End follows the end joint by point "
                                                                     "(arms) or parent (legs)")
        ribbon_advanced = w.column(
            w.label("Flexible Rig (antCGi) ribbon: 5 control joints (root/upper/middle/lower/end) with aim "
                    "setup, sine/twist blendshape layer and Toon_Controls on the holder, crease isoparms."),
            w.row(("Joints", self.flex_ribbon_joints), self.flex_ribbon_deform, self.flex_ribbon_crease,
                  ("End", self.flex_ribbon_end)),
            w.grid([
                w.button("Flexible Ribbon", lambda: actions.build_flexible_ribbon(
                    self.flex_ribbon_joints.value(), self.size_box.value(), self.flex_ribbon_deform.isChecked(),
                    self.flex_ribbon_crease.isChecked(), self.flex_ribbon_end.currentText()),
                    "Select start, middle and end joints (and optionally the control receiving the attributes; "
                    "a Flexible Limb's global control is used automatically)"),
                w.button("Add Crease Fix", actions.add_flexible_crease_fix,
                         "Select a Flexible Ribbon: elbow/wrist fix joints (single chain IK) added to its skin"),
            ], 2))
        spline.add(w.tabs(("Basic", ribbon_basic), ("Advanced", ribbon_advanced)))

        twist = self.section("Twist / Foot / Fingers", expanded=False)
        self.twist_count = w.spin(3, 1, 20, 0, 1)
        self.twist_mode = w.combo(["forward", "reverse"], "forward",
                                  "forward: forearm style, reverse: upper arm style")
        twist.add(w.row(("Twist joints", self.twist_count), ("Mode", self.twist_mode),
                        w.button("Create Twist", lambda: actions.build_twist(self.twist_count.value(),
                                                                             self.twist_mode.currentText()),
                                 "Select start and end joints")))
        self.foot_mirror = w.check("Both sides", True, "Also build the other side (L_ <-> R_ names)")
        foot_basic = w.column(
            w.button("Reverse Foot", actions.build_reverse_foot,
                     "Select in order: IK control, ankle, ball, toe (IK joints), heel locator, inner "
                     "locator, outer locator. The IK end target is found automatically (or select it second)."),
            w.row(self.foot_mirror, w.button("Reverse Foot From Chain", lambda: actions.build_reverse_foot_from_chain(
                self.foot_mirror.isChecked()),
                "Select the leg IK control, then the reverse chain's first joint (heel > toe tip > ball > ankle, "
                "ankle and ball on the base foot joints). Optional: the IK ankle joint, then inner and outer bank "
                "pivots (default: on each side of the ball, move their ZRO groups to adjust). Builds the other "
                "side too when L_/R_ names match.")),
            w.button("Finger Controls", lambda: actions.build_fingers(self.size_box.value()),
                     "Select finger root joints (and optionally the control receiving the attributes)"),
            w.button("IK/FK Fingers (contact)", lambda: actions.build_finger_ikfk(self.size_box.value(),
                                                                                  self.stretch.isChecked()),
                     "Select finger root joints (the first joint that bends, not the metacarpal), optionally "
                     "then the hand control. Each finger gets FK, an IK to the tip and an ikFk switch. Set the "
                     "IK control's 'space' to world to keep the tip on a contact point while the hand moves. "
                     "Fingers should be slightly bent in the bind pose so the IK knows which way to bend."))
        self.flex_tips = w.check("Tip controls", True)
        foot_advanced = w.column(
            w.label("Flexible Rig (antCGi): node based foot (Roll, Bank, HeelTwist, ToeTwist, ToeTap + "
                    "ToeFlex, RollBack, RollEnd, BankAmount, ToeStraightAngle) and plain FK fingers following "
                    "the wrist."),
            w.button("Flexible Reverse Foot", actions.build_flexible_foot,
                     "Select in order: IK control, ankle, ball, toe (IK joints), heel, inner and outer locators. "
                     "Everything under the IK control moves under the ankle pivot. Foot must point down +Z."),
            w.row(self.flex_tips, w.button("Flexible Fingers", lambda: actions.build_flexible_fingers(
                self.size_box.value() * 0.3, self.flex_tips.isChecked()), "Select finger root joints")))
        twist.add(w.tabs(("Basic", foot_basic), ("Advanced", foot_advanced)))

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
                                  "Select joints posed in the target pose. Connect the reader's weight to a corrective "
                                  "blendshape target")))
        attach.add(w.grid([
            w.button("Dynamic Chain (nHair)", actions.create_dynamic_chain,
                     "Select a bind joint chain: FK controls + nHair overlap drive it "
                     "('dynamics' attribute on the first control)"),
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
