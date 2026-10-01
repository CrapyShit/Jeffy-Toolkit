"""UI wiring tests: every action referenced by the UI exists, and the whole
window can be built offscreen (with a fake Maya)."""

import ast
import os

import pytest

from jeffy.ui import actions

UI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "jeffy", "ui")


def _referenced_actions():
    names = set()
    for root, _dirs, files in os.walk(UI_DIR):
        for filename in files:
            if not filename.endswith(".py") or filename == "actions.py":
                continue
            path = os.path.join(root, filename)
            with open(path) as handle:
                source = handle.read()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                # actions.<name>
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and \
                        node.value.id == "actions":
                    names.add((filename, node.attr))
                # _act("<name>", ...) in the menu
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_act":
                    names.add((filename, node.args[0].value))
            if filename == "shelf.py":
                for chunk in source.split("actions.")[1:]:
                    names.add((filename, chunk.split("(")[0]))
    return sorted(names)


@pytest.mark.parametrize("filename,name", _referenced_actions())
def test_action_exists(filename, name):
    assert hasattr(actions, name), "%s references missing action %s" % (filename, name)
    assert getattr(getattr(actions, name), "tool_label", None), "%s is not decorated with @tool" % name


def test_window_builds_offscreen():
    qt = pytest.importorskip("jeffy.ui.qt")
    app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
    from jeffy.ui import main_window

    window = main_window.JeffyToolkitWindow()
    titles = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert titles == ["Controls", "Joints", "Rigging", "Deform", "Attributes", "Naming", "Auto-Rig", "Animate",
                      "Utilities"]
    for index in range(window.tabs.count()):
        page = window.tabs.widget(index)
        assert not isinstance(page, qt.QtWidgets.QLabel), "page %d failed" % index
        # widgets stored on pages must not shadow Qt methods (e.g. self.size)
        shadowed = [name for name, value in vars(page).items()
                    if isinstance(value, qt.QtCore.QObject) and hasattr(qt.QtWidgets.QScrollArea, name)]
        assert not shadowed, "%s shadows Qt attributes: %s" % (type(page).__name__, shadowed)
    window.close()
    del app


def test_shape_icons_render():
    pytest.importorskip("jeffy.ui.qt")
    from jeffy.controls import library
    from jeffy.ui import qt, widgets

    app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
    for name in library.SHAPES:
        assert not widgets.shape_icon(name).isNull()
    del app
