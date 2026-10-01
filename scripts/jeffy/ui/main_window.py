"""The main (dockable) Jeffy Toolkit window."""

import importlib

from jeffy import TOOLKIT_NAME, __version__
from jeffy.core import logger, settings
from jeffy.ui.qt import QtCore, QtWidgets, delete_workspace_control, dockable_base, maya_main_window

LOG = logger.get_logger("ui")
OBJECT_NAME = "jeffyToolkitWindow"

#: (module, class) of every tab, in display order
PAGES = (
    ("jeffy.ui.pages.controls_page", "ControlsPage"),
    ("jeffy.ui.pages.joints_page", "JointsPage"),
    ("jeffy.ui.pages.rigging_page", "RiggingPage"),
    ("jeffy.ui.pages.deform_page", "DeformPage"),
    ("jeffy.ui.pages.attributes_page", "AttributesPage"),
    ("jeffy.ui.pages.naming_page", "NamingPage"),
    ("jeffy.ui.pages.autorig_page", "AutoRigPage"),
    ("jeffy.ui.pages.animation_page", "AnimationPage"),
    ("jeffy.ui.pages.utilities_page", "UtilitiesPage"),
)

_MIXIN = dockable_base()
_BASES = (QtWidgets.QWidget,) if _MIXIN is object else (_MIXIN, QtWidgets.QWidget)
_STATE = {"window": None}


class JeffyToolkitWindow(*_BASES):
    def __init__(self, parent=None):
        super(JeffyToolkitWindow, self).__init__(parent=parent or maya_main_window())
        self.setObjectName(OBJECT_NAME)
        self.setWindowTitle("%s %s" % (TOOLKIT_NAME, __version__))
        self.setWindowFlags(QtCore.Qt.Window)
        self.setMinimumSize(380, 520)
        self.resize(460, 820)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("<b>%s</b> <span style='color:#888'>v%s</span>" % (TOOLKIT_NAME, __version__))
        header.addWidget(title)
        header.addStretch(1)
        reload_button = QtWidgets.QPushButton("Reload")
        reload_button.setToolTip("Reload every toolkit module (development)")
        reload_button.clicked.connect(self._reload)
        header.addWidget(reload_button)
        layout.addLayout(header)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        layout.addWidget(self.tabs)
        for module_name, class_name in PAGES:
            try:
                module = importlib.import_module(module_name)
                page = getattr(module, class_name)()
                self.tabs.addTab(page, page.TITLE)
            except Exception as error:  # a broken page must not break the window
                LOG.exception("Could not build page %s: %s", class_name, error)
                placeholder = QtWidgets.QLabel("Page failed to load:\n%s" % error)
                placeholder.setWordWrap(True)
                self.tabs.addTab(placeholder, class_name.replace("Page", ""))
        last = settings.get("ui_last_tab", 0)
        if isinstance(last, int) and 0 <= last < self.tabs.count():
            self.tabs.setCurrentIndex(last)
        self.tabs.currentChanged.connect(lambda index: settings.set("ui_last_tab", index))

    def _reload(self):
        import jeffy

        QtCore.QTimer.singleShot(0, lambda: jeffy.reload_toolkit(show_window=True))


def close():
    window = _STATE.get("window")
    if window is not None:
        try:
            window.close()
            window.deleteLater()
        except RuntimeError:
            pass
    _STATE["window"] = None
    delete_workspace_control(OBJECT_NAME)


def show(dockable=True):
    """Open the toolkit (a single instance)."""
    close()
    window = JeffyToolkitWindow()
    _STATE["window"] = window
    if _MIXIN is not object:
        window.show(dockable=dockable, floating=True)
    else:
        window.show()
    return window
