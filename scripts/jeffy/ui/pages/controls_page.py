"""Controls tab: create controls, edit shapes, colours and offset groups."""

from jeffy.core import settings
from jeffy.ui import actions
from jeffy.ui import widgets as w


class ControlsPage(w.Page):
    TITLE = "Controls"

    def build(self):
        # ---------------------------------------------------------- create
        create = self.section("Create")
        self.gallery = create.add(w.ShapeGallery())
        self.gallery.select_shape(settings.get("control_shape", "circle"))
        self.size_box = w.spin(settings.get("control_size", 1.0), 0.001, 10000.0, 3, 0.25)
        self.axis = w.combo(w.AXES, settings.get("control_axis", "x"), "Axis the shape faces")
        self.line_width = w.spin(settings.get("control_line_width", 2.0), -1.0, 20.0, 1, 0.5,
                                 "Curve thickness (-1 = Maya preference)")
        create.add(w.row(("Size", self.size_box), ("Axis", self.axis), ("Line", self.line_width)))
        self.zero = w.check("ZRO group", True)
        self.offset = w.check("OFF group", False)
        self.sdk = w.check("SDK group", False)
        create.add(w.row(self.zero, self.offset, self.sdk))
        self.constrain = w.check("Constrain selection", False, "Parent + scale constrain each object to its control")
        self.hierarchy = w.check("Keep hierarchy", True, "Parent controls like the selected objects")
        create.add(w.row(self.constrain, self.hierarchy))
        self.color = None
        self.color_label = w.label("Colour: side default")
        palette = w.ColorPalette()
        palette.colorPicked.connect(self._color_picked)
        create.add(self.color_label)
        create.add(palette)
        create.add(w.button("Create Control(s) on Selection", self._create,
                            "One control per selected object (or one at the origin)", height=32))

        # ---------------------------------------------------------- edit
        edit = self.section("Edit Shapes")
        edit.add(w.grid([
            w.button("Replace Shape", lambda: actions.replace_shapes(self._shape(), None, self.axis.currentText()),
                     "Swap the shape of selected controls (keeps size & colour)"),
            w.button("Copy Shape", lambda: actions.copy_shape(False), "First selected -> others"),
            w.button("Mirror Shapes", lambda: actions.mirror_shapes("x"), "L_ -> R_ (or R_ -> L_) across X"),
            w.button("Scale +", lambda: actions.scale_shapes(1.25)),
            w.button("Scale -", lambda: actions.scale_shapes(0.8)),
            w.button("Set Line Width", lambda: actions.set_line_width(self.line_width.value())),
            w.button("Rotate X 90", lambda: actions.rotate_shapes((90, 0, 0))),
            w.button("Rotate Y 90", lambda: actions.rotate_shapes((0, 90, 0))),
            w.button("Rotate Z 90", lambda: actions.rotate_shapes((0, 0, 90))),
            w.button("Combine Curves", actions.combine_curves, "Parent all curve shapes under the first"),
            w.button("Reset Colour", actions.reset_color_selected),
            w.button("Tag As Controls", actions.tag_as_controls, "Make existing curves toolkit controls"),
        ], 3))

        # ---------------------------------------------------------- library
        lib = self.section("Library / Text", expanded=False)
        self.shape_name = w.line_edit("", "Shape name (defaults to node name)")
        lib.add(w.row(self.shape_name, w.button("Save Selected To Library", self._save_shape)))
        lib.add(w.row(w.button("Export Shapes...", actions.export_shapes),
                      w.button("Import Shapes...", actions.import_shapes),
                      w.button("Refresh Gallery", self.gallery.refresh)))
        self.text = w.line_edit("TEXT", "Text")
        lib.add(w.row(self.text, w.button("Create Text Control", lambda: actions.create_text_control(
            self.text.text() or "TEXT"))))

        # ---------------------------------------------------------- offsets
        offsets = self.section("Offsets / Transforms", expanded=False)
        offsets.add(w.grid([
            w.button("Add Offset Group", lambda: actions.add_offset_group("OFF")),
            w.button("Bake To OPM", actions.bake_offset_parent_matrix,
                     "Move local transform to offsetParentMatrix (zero out without groups)"),
            w.button("Unbake OPM", actions.unbake_offset_parent_matrix),
            w.button("Match Transforms", actions.match_transforms, "Snap selection to the last selected"),
            w.button("Reset Transforms", actions.reset_transforms),
            w.button("Freeze Transforms", actions.freeze_transforms),
            w.button("Mirror Transforms", actions.mirror_transforms, "Mirror world transform to L/R counterpart"),
            w.button("Locator At Selection", actions.locators_at_selection),
            w.button("Locator At Center", lambda: actions.locators_at_selection(True)),
        ], 3))

    # ------------------------------------------------------------------
    def _shape(self):
        return self.gallery.current_shape() or "circle"

    def _color_picked(self, value):
        self.color = value
        self.color_label.setText("Colour: %s" % (value,))
        actions.color_selected(value)

    def _create(self):
        offsets = [key for key, box in (("zero", self.zero), ("offset", self.offset), ("sdk", self.sdk))
                   if box.isChecked()]
        settings.set("control_shape", self._shape(), save_now=False)
        settings.set("control_size", self.size_box.value(), save_now=False)
        settings.set("control_axis", self.axis.currentText())
        actions.create_controls(shape=self._shape(), size=self.size_box.value(), axis=self.axis.currentText(),
                                color_value=self.color, offsets=offsets, constrain=self.constrain.isChecked(),
                                hierarchy=self.hierarchy.isChecked(), line_width=self.line_width.value())

    def _save_shape(self):
        actions.save_shape_to_library(self.shape_name.text() or None)
        self.gallery.refresh()

