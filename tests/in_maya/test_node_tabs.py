"""Node Editor tabs per setup (real Maya; the editor itself is faked: mayapy has no Node Editor).

The node collection, the dependency layout and the dotFormat text run for real
on built setups; the fake editor records the tabs the hooks create and close.
"""

from maya import cmds
from test_setups_stage1 import ARM, base

from jeffy.setups.core import graph, scene
from jeffy.setups.tools.fk_chain import FkChain
from jeffy.setups.tools.ikfk_limb import IkFkLimb
from jeffy.setups.tools.ribbon import Ribbon
from jeffy.ui.setup_belt import node_tabs


class FakeEditor(object):
    def __init__(self):
        self.tabs = []  # [name, nodes, plain]
        self.closed = []

    def find_tab(self, name):
        names = [tab[0] for tab in self.tabs]
        return names.index(name) if name in names else None

    def create_tab(self, index, name):
        tab = [name, [], None]
        if index is None or index < 0 or index >= len(self.tabs):
            self.tabs.append(tab)
        else:
            self.tabs.insert(index, tab)
        self.active = tab

    def close_tab(self, index):
        self.closed.append(self.tabs.pop(index)[0])

    def add_nodes(self, nodes):
        self.active[1].extend(nodes)

    def place(self, positions, plain):
        self.active[2] = plain
        self.positions = positions

    def tab(self, name):
        return self.tabs[self.find_tab(name)]


def with_fake_editor(func):
    def wrapper():
        editor = FakeEditor()
        node_tabs.BACKEND = editor
        node_tabs._CLOSED.clear()
        node_tabs.set_enabled(True)
        try:
            func(editor)
        finally:
            node_tabs.BACKEND = None
    wrapper.__name__ = func.__name__
    return wrapper


@with_fake_editor
def test_build_creates_a_tab_per_setup(editor):
    base()
    FkChain.build(start="L_clavicle_JNT", mirror=False)
    IkFkLimb.build(name="arm", mirror=False, **ARM)
    names = [tab[0] for tab in editor.tabs]
    assert names == ["C_hero_RigBase", "L_clavicle_FkChain", "L_arm_IkFkLimb"], names
    _name, nodes, plain = editor.tab("L_arm_IkFkLimb")
    # its own nodes only, not the whole scene
    assert "L_armIK_CTL" in nodes and "L_shoulder_JNT" in nodes and "L_wrist_JNT" in nodes
    assert not [n for n in nodes if n.startswith(("C_spine", "R_", "L_leg"))], nodes
    assert not [n for n in nodes if cmds.nodeType(n) in ("unitConversion", "nurbsCurve", "controller")]
    assert "C_root_CTL" in nodes, "inputs include what the setup follows (its spaces)"
    assert plain.startswith("graph ") and plain.rstrip().endswith("stop") and '"L_armIK_CTL"' in plain


@with_fake_editor
def test_layout_runs_left_to_right(editor):
    base()
    IkFkLimb.build(name="arm", mirror=False, **ARM)
    setup = scene.find_setup("L_armIK_CTL")
    roles = graph.setup_nodes(setup)
    positions = editor.positions
    column = dict((node, x) for node, (x, _y) in positions.items())
    inputs = [column[n] for n, r in roles.items() if r == "input"]
    systems = [column[n] for n, r in roles.items() if r == "system"]
    outputs = [column[n] for n, r in roles.items() if r == "output"]
    joints = [column[n] for n, r in roles.items() if r == "joint"]
    assert max(inputs) < min(systems) and max(inputs) < min(outputs), "inputs on the left"
    assert max(systems + outputs) < min(joints), "bind joints on the right"
    # every edge goes left to right; only a parent joint feeds back into its child's driving nodes
    for source, destination in graph.edges(setup):
        if roles[source] == "joint" or roles[source] == roles[destination] == "input":
            continue  # parent joint -> child driving nodes / proxy attributes between controls
        assert column[source] < column[destination], (source, destination)
    assert roles["L_shoulder_JNT"] == "joint" and roles["L_shoulderFK_CTL"] == "input"
    assert any(cmds.nodeType(n) == "blendMatrix" for n, r in roles.items() if r == "system")


@with_fake_editor
def test_rebuild_updates_and_delete_removes(editor):
    base()
    limb = IkFkLimb.build(name="arm", mirror=False, **ARM)
    Ribbon.build(base="L_armIK_CTL", mirror=False)
    order = [tab[0] for tab in editor.tabs]
    assert order == ["C_hero_RigBase", "L_arm_IkFkLimb", "L_armRibbon_Ribbon"], order
    before = list(editor.tab("L_arm_IkFkLimb")[1])
    limb = limb.rebuild(options={"knee": "no-flip"})
    order = [tab[0] for tab in editor.tabs]
    assert order == ["C_hero_RigBase", "L_arm_IkFkLimb", "L_armRibbon_Ribbon"], \
        "rebuilt tabs come back in place: %s" % order
    after = editor.tab("L_arm_IkFkLimb")[1]
    assert "L_armPole_CTL" in before and "L_armPole_CTL" not in after, "the tab shows the new build"
    limb.delete()
    assert [tab[0] for tab in editor.tabs] == ["C_hero_RigBase"], "deleting closes the tab (and its layer's)"


@with_fake_editor
def test_disabled_and_batch(editor):
    node_tabs.set_enabled(False)
    try:
        base()
        IkFkLimb.build(name="arm", mirror=False, **ARM)
        assert editor.tabs == []
    finally:
        node_tabs.set_enabled(True)
    node_tabs.BACKEND = None
    assert node_tabs.backend() is None, "mayapy (batch): no Node Editor, nothing happens"
    IkFkLimb.build(name="leg", mirror=False, start="L_hip_JNT", mid="L_knee_JNT", end="L_ankle_JNT")
