"""Test configuration.

Maya is not available outside of Maya, so a *fake* ``maya`` package made of
``MagicMock`` objects is installed before the toolkit is imported. This lets
every module be imported (catching syntax/import errors) and the pure Python
parts (math, naming, parsing, weights, symmetry...) be tested for real.
"""

import os
import sys
import types
from unittest import mock

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _install_fake_maya():
    existing = sys.modules.get("maya")
    if existing is not None and not getattr(existing, "_jeffy_fake", False):
        return  # running inside mayapy - use the real thing

    def package(name):
        module = types.ModuleType(name)
        module.__path__ = []
        module._jeffy_fake = True
        sys.modules[name] = module
        return module

    maya = package("maya")
    api = package("maya.api")
    maya.api = api
    for name in ("cmds", "mel", "utils", "OpenMayaUI", "standalone"):
        fake = mock.MagicMock(name="maya." + name)
        setattr(maya, name, fake)
        sys.modules["maya." + name] = fake
    for name in ("OpenMaya", "OpenMayaAnim", "OpenMayaUI"):
        fake = mock.MagicMock(name="maya.api." + name)
        setattr(api, name, fake)
        sys.modules["maya.api." + name] = fake
    # No main window (like batch mode) - wrapping a fake pointer would crash Qt.
    maya.OpenMayaUI.MQtUtil.mainWindow.return_value = None
    # maya.app.general.mayaMixin is intentionally missing: the UI falls back to
    # a plain QWidget window.


_install_fake_maya()


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """Keep user settings written by the toolkit out of the real home folder."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    yield
