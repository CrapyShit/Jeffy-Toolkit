"""Qt compatibility (PySide6 for Maya 2025+, PySide2 before) and Maya helpers."""

try:  # Maya 2025+
    from PySide6 import QtCore, QtGui, QtWidgets  # noqa: F401
    from shiboken6 import wrapInstance

    QT_BINDING = "PySide6"
except ImportError:  # Maya 2017 - 2024
    from PySide2 import QtCore, QtGui, QtWidgets  # noqa: F401
    from shiboken2 import wrapInstance

    QT_BINDING = "PySide2"


def maya_main_window():
    """Maya's main window as a ``QWidget`` (``None`` in batch mode)."""
    try:
        from maya import OpenMayaUI as omui

        pointer = omui.MQtUtil.mainWindow()
        if pointer is None:
            return None
        return wrapInstance(int(pointer), QtWidgets.QWidget)
    except Exception:
        return None


def dockable_base():
    """``MayaQWidgetDockableMixin`` when available (inside Maya), else ``object``."""
    try:
        from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

        return MayaQWidgetDockableMixin
    except Exception:
        return object


def delete_workspace_control(name):
    try:
        from maya import cmds

        control = name + "WorkspaceControl"
        if cmds.workspaceControl(control, query=True, exists=True):
            cmds.workspaceControl(control, edit=True, close=True)
            cmds.deleteUI(control, control=True)
    except Exception:
        pass
