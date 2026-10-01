"""Every module must import (with a fake Maya)."""

import importlib
import os
import pkgutil

import pytest

import jeffy

QT_AVAILABLE = True
try:  # pragma: no cover - depends on the environment (Qt needs system libs)
    from PySide6 import QtWidgets  # noqa: F401
except ImportError:  # pragma: no cover
    try:
        from PySide2 import QtWidgets  # noqa: F401
    except ImportError:
        QT_AVAILABLE = False


def _module_names():
    names = []
    for info in pkgutil.walk_packages(jeffy.__path__, prefix="jeffy."):
        names.append(info.name)
    return sorted(names)


MODULES = _module_names()


def test_found_modules():
    assert len(MODULES) > 60


@pytest.mark.parametrize("name", MODULES)
def test_import(name):
    if name.startswith("jeffy.ui.") and name not in ("jeffy.ui.actions", "jeffy.ui.menu", "jeffy.ui.shelf"):
        if not QT_AVAILABLE:
            pytest.skip("Qt not available")
    importlib.import_module(name)


def test_version():
    parts = jeffy.__version__.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts)
    assert jeffy.VERSION_INFO == tuple(int(p) for p in parts)


def test_changelog_mentions_version():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "CHANGELOG.md")) as handle:
        assert "[%s]" % jeffy.__version__ in handle.read()
