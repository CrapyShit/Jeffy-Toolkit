"""UI wiring tests: every action referenced by the menu, the shelf and the
Utilities panel exists (the window itself is built in ``test_setups``)."""

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


def test_shape_icons_render():
    pytest.importorskip("jeffy.ui.qt")
    from jeffy.controls import library
    from jeffy.ui import qt, widgets

    app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
    for name in library.SHAPES:
        assert not widgets.shape_icon(name).isNull()
    del app


def test_theme_eye_states_and_banner():
    qt = pytest.importorskip("jeffy.ui.qt")
    app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
    from jeffy.ui import theme

    for state in theme.STATES:
        image = theme.eye_pixmap(64, state).toImage()
        centre_row = [qt.QtGui.QColor.fromRgba(image.pixel(x, 32)) for x in range(64)]
        assert any(color.alpha() > 0 for color in centre_row), state
    banner = theme.EyeBanner("INVENTORY", "v0")
    banner.resize(600, banner.height())
    for state in theme.STATES:
        theme.set_state(state)
        assert theme.state() == state
        assert not banner.grab().isNull()
    theme.set_state(theme.IDLE)
    with pytest.raises(ValueError):
        theme.set_state("nope")
    assert "%(" not in theme.stylesheet()
    assert app is not None
