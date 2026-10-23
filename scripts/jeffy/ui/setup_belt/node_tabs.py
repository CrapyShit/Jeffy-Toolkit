"""One Node Editor tab per setup, showing only that setup's main nodes.

Building a setup creates a tab named after it (``L_arm_IkFkLimb``) with the
nodes from :func:`jeffy.setups.core.graph.setup_nodes`, laid out left to right
by dependency. Rebuilding replaces the tab in place; deleting the setup closes
it. Turn it off with :func:`set_enabled` (or the checkbox in SCENE > Setups).

Layout: ``nodeEditor -dotFormat <file>`` with a graphviz ``plain`` file built
from :func:`graph.layout` (no Graphviz install needed). When Maya refuses it,
the editor's own ``-layout``. The tabs are found through the editor's tab bar
(Qt); the node items themselves are never touched from Python (Maya rebuilds
them, and moving stale items can crash it).

The Maya specific calls live in :class:`MayaNodeEditor`; tests swap in a fake
editor through :data:`BACKEND` (mayapy has no Node Editor).
"""

import os
import tempfile

from maya import cmds, mel

from jeffy.core import logger, settings
from jeffy.setups.core import graph

LOG = logger.get_logger("node_tabs")
ENABLED_KEY = "belt_node_tabs"
#: the editor in use; ``None``: the real Node Editor (created on demand, UI sessions only)
BACKEND = None
#: index of tabs closed by a delete, so a rebuild puts the new tab back where it was
_CLOSED = {}


def enabled():
    return bool(settings.get(ENABLED_KEY, True))


def set_enabled(value):
    settings.set(ENABLED_KEY, bool(value))


def backend():
    """The editor to use, or ``None`` (batch session without a test backend)."""
    global BACKEND
    if BACKEND is not None:
        return BACKEND
    if cmds.about(batch=True) or not hasattr(cmds, "nodeEditor"):
        return None
    BACKEND = MayaNodeEditor()
    return BACKEND


# ---------------------------------------------------------------------------
# Hooks (called by Setup.create / Setup._delete_self)
# ---------------------------------------------------------------------------
def on_built(setup):
    editor = backend()
    if editor is None or not enabled():
        return None
    return show(setup, editor)


def on_deleted(setup):
    editor = backend()
    if editor is None:
        return None
    return remove(graph.tab_name(setup), editor)


def show(setup, editor=None):
    """Create (or replace) the setup's tab. Returns its name."""
    editor = editor or backend()
    name = graph.tab_name(setup)
    index = editor.find_tab(name)
    if index is not None:
        editor.close_tab(index)
    else:
        index = _CLOSED.pop(name, -1)
    editor.create_tab(index, name)
    positions = graph.layout(setup)
    editor.add_nodes(list(positions))
    editor.place(positions, graph.plain_format(positions, graph.edges(setup)))
    return name


def remove(name, editor=None):
    """Close the tab ``name`` (remembering its place for a rebuild)."""
    editor = editor or backend()
    index = editor.find_tab(name)
    if index is None:
        return False
    editor.close_tab(index)
    _CLOSED[name] = index
    return True


# ---------------------------------------------------------------------------
# The real Node Editor
# ---------------------------------------------------------------------------
class MayaNodeEditor(object):
    """Tabs of Maya's Node Editor (``nodeEditor`` command + its Qt widgets)."""

    def __init__(self):
        self._editor = None

    @property
    def editor(self):
        if self._editor and cmds.nodeEditor(self._editor, exists=True):
            return self._editor
        panels = cmds.getPanel(scriptType="nodeEditorPanel") or []
        if not panels:
            mel.eval("NodeEditorWindow")
            panels = cmds.getPanel(scriptType="nodeEditorPanel") or []
        for panel in panels:
            candidate = panel + "NodeEditorEd"
            if cmds.nodeEditor(candidate, exists=True):
                self._editor = candidate
                return candidate
        raise RuntimeError("No Node Editor found")

    # tabs ---------------------------------------------------------------
    def _with_tab_bar(self, callback):
        """Call ``callback(tab_bar)`` with the editor's own tab bar (``None`` if not found).

        The editor widget is a tab widget whose last tab is "+". Maya deletes and
        recreates these widgets, so every Python wrapper is dropped right after
        use: a cached wrapper could point at a deleted object later.
        """
        from maya import OpenMayaUI as omui

        from jeffy.ui.qt import QtWidgets, invalidate, isValid, wrapInstance

        pointer = omui.MQtUtil.findControl(self.editor)
        if pointer is None:
            return callback(None)
        widget = wrapInstance(int(pointer), QtWidgets.QWidget)
        bars = widget.findChildren(QtWidgets.QTabBar)
        try:
            for bar in bars:
                parent = bar.parentWidget() if isValid(bar) else None
                if parent is not None and parent.objectName() == widget.objectName():
                    return callback(bar)
            return callback(None)
        finally:
            for wrapper in bars + [widget]:
                try:
                    invalidate(wrapper)
                except Exception:
                    pass

    def tab_names(self):
        return self._with_tab_bar(lambda bar: [bar.tabText(i) for i in range(bar.count())] if bar else [])

    def find_tab(self, name):
        names = self.tab_names()
        return names.index(name) if name in names else None

    def create_tab(self, index, name):
        real_tabs = len([text for text in self.tab_names() if text])  # the "+" tab has no text
        if index is None or index < 0 or index > real_tabs:
            index = -1
        cmds.nodeEditor(self.editor, edit=True, createTab=(index, name))  # also makes it the active tab

    def close_tab(self, index):
        cmds.nodeEditor(self.editor, edit=True, closeTab=index)

    # content --------------------------------------------------------------
    def add_nodes(self, nodes):
        wanted = set(nodes)
        for node in nodes:
            cmds.nodeEditor(self.editor, edit=True, addNode=node)
        _process_events()  # the editor fills its graph (and getNodeList) on the next UI events
        # addNode brings a transform's shape along (control curves...): keep only the setup's nodes
        for shown in cmds.nodeEditor(self.editor, query=True, getNodeList=True) or []:
            if (cmds.ls(shown) or [shown])[0] not in wanted:
                cmds.nodeEditor(self.editor, edit=True, removeNode=shown)

    def place(self, positions, plain):
        # Positions go through dotFormat only: moving the editor's Qt items from Python is not safe
        # (Maya rebuilds them and the stale wrappers can crash it).
        # -dotFormat reads a graphviz "plain" *file* (the query writes the graph to a file too)
        handle, path = tempfile.mkstemp(prefix="jeffy_", suffix=".plain")
        try:
            with os.fdopen(handle, "w") as stream:
                stream.write(plain)
            _process_events()  # the nodes must exist in the graph before they can be placed
            cmds.nodeEditor(self.editor, edit=True, dotFormat=path.replace("\\", "/"))
        except (RuntimeError, TypeError, OSError) as error:
            LOG.warning("Node Editor dotFormat refused (%s): using its automatic layout", error)
            cmds.nodeEditor(self.editor, edit=True, layout=True)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        _process_events()
        cmds.nodeEditor(self.editor, edit=True, frameAll=True)


def _process_events():
    from jeffy.ui.qt import QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is not None:
        for _ in range(3):
            app.processEvents()
