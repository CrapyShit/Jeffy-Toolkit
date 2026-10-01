"""Naming tab: renamer."""

from jeffy.ui import actions
from jeffy.ui import widgets as w


class NamingPage(w.Page):
    TITLE = "Naming"

    def build(self):
        rename = self.section("Rename")
        self.pattern = w.line_edit("", "L_finger_##_JNT  (# = padded number)")
        self.start = w.spin(1, 0, 100000, 0, 1)
        rename.add(w.row(("Name", self.pattern), ("Start", self.start)))
        rename.add(w.button("Rename Selection (in order)", lambda: actions.rename_sequential(
            self.pattern.text().strip(), self.start.value())))

        replace = self.section("Search & Replace")
        self.search = w.line_edit("", "search")
        self.replace = w.line_edit("", "replace")
        replace.add(w.row(("Search", self.search), ("Replace", self.replace)))
        self.hierarchy = w.check("Hierarchy", False)
        self.regex = w.check("Regex", False)
        replace.add(w.row(self.hierarchy, self.regex, w.button("Replace", lambda: actions.search_replace(
            self.search.text(), self.replace.text(), self.hierarchy.isChecked(), self.regex.isChecked()))))

        fix = self.section("Prefix / Suffix")
        self.prefix = w.line_edit("", "prefix")
        fix.add(w.row(self.prefix, w.button("Add Prefix", lambda: actions.add_prefix(self.prefix.text()))))
        self.suffix = w.line_edit("", "suffix")
        fix.add(w.row(self.suffix, w.button("Add Suffix", lambda: actions.add_suffix(self.suffix.text()))))
        self.first = w.spin(0, 0, 100, 0, 1)
        self.last = w.spin(0, 0, 100, 0, 1)
        fix.add(w.row(("Remove first", self.first), ("last", self.last),
                      w.button("Remove", lambda: actions.remove_characters(self.first.value(), self.last.value()))))

        tools = self.section("Tools")
        tools.add(w.grid([
            w.button("Auto Suffix", actions.auto_suffix, "Add _JNT/_GEO/_CTL/_GRP... from the node type"),
            w.button("Fix Shape Names", actions.fix_shape_names),
            w.button("Mirror Names (L<>R)", actions.mirror_names),
            w.button("Make Names Unique", actions.make_names_unique),
            w.button("Select Mirror", lambda: actions.select_mirror(False)),
            w.button("Add Mirror To Sel.", lambda: actions.select_mirror(True)),
        ], 3))
