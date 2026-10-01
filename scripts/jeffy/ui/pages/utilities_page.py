"""Utilities tab: scene cleanup and the rig checker."""

from maya import cmds

from jeffy.ui import actions
from jeffy.ui import widgets as w
from jeffy.ui.qt import QtCore, QtGui, QtWidgets

STATUS_COLORS = {"ok": (90, 190, 90), "error": (230, 80, 80), "warning": (240, 180, 60), "info": (110, 170, 240)}


class UtilitiesPage(w.Page):
    TITLE = "Utilities"

    def build(self):
        scene = self.section("Scene")
        scene.add(w.grid([
            w.button("Remove Namespaces", actions.remove_namespaces),
            w.button("Clean Scene", actions.clean_scene, "Unknown nodes/plugins and Turtle leftovers"),
            w.button("Delete Unused Nodes", actions.delete_unused_nodes),
            w.button("Delete Empty Groups", actions.delete_empty_groups),
            w.button("Lock Rig", lambda: actions.lock_rig(True), "Select the rig top node"),
            w.button("Unlock Rig", lambda: actions.lock_rig(False)),
            w.button("Scene Report", actions.scene_report),
            w.button("Make Names Unique", actions.make_names_unique),
        ], 3))

        check = self.section("Rig Check")
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Check", "Issues"])
        self.tree.setMinimumHeight(260)
        self.tree.itemDoubleClicked.connect(self._select_issues)
        check.add(self.tree)
        check.add(w.grid([
            w.button("Run All Checks", self.run_checks),
            w.button("Fix Selected", self.fix_selected),
            w.button("Fix All", self.fix_all),
        ], 3))
        check.add(w.label("Double click a check to select its problem nodes."))
        self._results = []

    def run_checks(self):
        from jeffy.utils import checks

        self._results = checks.run_all()
        self.tree.clear()
        for result in self._results:
            status = "ok" if result.passed else result.check.severity
            item = QtWidgets.QTreeWidgetItem([result.check.label, str(len(result.issues))])
            rgb = STATUS_COLORS.get(status, (200, 200, 200))
            item.setForeground(0, QtGui.QBrush(QtGui.QColor(*rgb)))
            tooltip = result.check.description or result.check.label
            if result.check.fixable:
                tooltip += "\n(auto fix available)"
            item.setToolTip(0, tooltip)
            item.setData(0, QtCore.Qt.UserRole, result.check.name)
            for issue in result.issues[:200]:
                child = QtWidgets.QTreeWidgetItem([str(issue), ""])
                item.addChild(child)
            self.tree.addTopLevelItem(item)
        self.tree.resizeColumnToContents(0)

    def _result_for(self, item):
        while item.parent():
            item = item.parent()
        name = item.data(0, QtCore.Qt.UserRole)
        for result in self._results:
            if result.check.name == name:
                return result
        return None

    def _select_issues(self, item, _column):
        result = self._result_for(item)
        if not result:
            return
        nodes = [i for i in result.issues if isinstance(i, str) and cmds.objExists(i)]
        if nodes:
            cmds.select(nodes, replace=True)

    def fix_selected(self):
        from jeffy.core import decorators

        with decorators.undo_chunk("Fix Checks"):
            for item in self.tree.selectedItems():
                result = self._result_for(item)
                if result and not result.passed:
                    result.check.fix(result.issues)
        self.run_checks()

    def fix_all(self):
        from jeffy.core import decorators
        from jeffy.utils import checks

        with decorators.undo_chunk("Fix All Checks"):
            checks.fix_all(self._results or None)
        self.run_checks()
