"""Auto-Rig tab: templates, components, guides and building."""

from maya import cmds

from jeffy.ui import actions
from jeffy.ui import widgets as w
from jeffy.ui.qt import QtCore, QtWidgets


class AutoRigPage(w.Page):
    TITLE = "Auto-Rig"

    def build(self):
        from jeffy.autorig import components, templates

        start = self.section("1. Guides")
        self.template = w.combo(templates.list_templates(), "biped")
        self.scale = w.spin(1.0, 0.01, 100.0, 2, 0.1, "Template scale (1 = 180 cm character)")
        start.add(w.row(("Template", self.template), ("Scale", self.scale),
                        w.button("Create Template", lambda: (actions.create_template(
                            self.template.currentText(), self.scale.value()), self.refresh()))))
        types = sorted(components.available())
        self.component_type = w.combo(types, "chain")
        self.component_name = w.line_edit("", "name (default from type)")
        self.component_side = w.combo(["C", "L", "R"], "C")
        start.add(w.row(("Type", self.component_type), ("Name", self.component_name),
                        ("Side", self.component_side)))
        self.parent_output = w.line_edit("", "parent output e.g. C_spine.chest")
        start.add(w.row(("Parent", self.parent_output), w.button("Add Component", self._add_component)))
        start.add(w.grid([
            w.button("Set Parent On Selected", lambda: (actions.set_guide_parent(self.parent_output.text()),
                                                        self.refresh())),
            w.button("Mirror Guides", lambda: (actions.mirror_guides(), self.refresh()),
                     "Selected components, or every left component when nothing is selected"),
            w.button("Show / Hide Guides", actions.toggle_guides),
            w.button("Save Guides...", actions.save_guides),
            w.button("Load Guides...", lambda: (actions.load_guides(True), self.refresh())),
            w.button("Refresh List", self.refresh),
        ], 3))

        listing = self.section("Components In Scene")
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Component", "Type", "Parent"])
        self.tree.setMinimumHeight(160)
        self.tree.itemClicked.connect(self._select_item)
        listing.add(self.tree)

        build = self.section("2. Build")
        self.rig_name = w.line_edit("character")
        build.add(w.row(("Rig name", self.rig_name)))
        build.add(w.grid([
            w.button("Build Rig", lambda: actions.build_rig(self.rig_name.text() or "character"), height=34),
            w.button("Rebuild", lambda: actions.rebuild_rig(self.rig_name.text() or "character"), height=34),
            w.button("Delete Rig", actions.delete_rig, height=34),
            w.button("Restore Guides From Rig", lambda: (actions.restore_guides(), self.refresh())),
            w.button("Run Rig Check", actions.run_checks),
        ], 3))
        build.add(w.label("Workflow: create a template, move the left + centre guide markers onto your mesh, "
                          "Mirror Guides, Build. Tweak the guides and Rebuild at any time. Component options are "
                          "attributes on each *_guide group (Channel Box)."))
        self.refresh()

    def refresh(self):
        from jeffy.autorig import guides

        self.tree.clear()
        try:
            roots = guides.get_guide_roots()
        except Exception:
            roots = []
        for root in roots:
            info = guides.get_info(root)
            item = QtWidgets.QTreeWidgetItem(["%s_%s" % (info["side"], info["name"]), info["type"],
                                              info["parent"] or "-"])
            item.setData(0, QtCore.Qt.UserRole, root)
            self.tree.addTopLevelItem(item)
        for column in range(3):
            self.tree.resizeColumnToContents(column)

    def _select_item(self, item, _column):
        root = item.data(0, QtCore.Qt.UserRole)
        if root and cmds.objExists(root):
            cmds.select(root)

    def _add_component(self):
        actions.add_component(self.component_type.currentText(), name=self.component_name.text().strip() or None,
                              side=self.component_side.currentText(),
                              parent_output=self.parent_output.text().strip())
        self.refresh()
