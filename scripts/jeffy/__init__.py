"""Jeff Inventory - stackable setup tools for Maya that rig the skeleton you built yourself.

Quick start (inside Maya)::

    import jeffy
    jeffy.show()            # open the Jeff Inventory window (the Setup Belt)
    jeffy.install_menu()    # (re)build the "Jeff Inventory" menu

Every tool is also a Python class (see :mod:`jeffy.setups`)::

    from jeffy.setups.tools.ikfk_limb import IkFkLimb
    IkFkLimb.build(start="L_shoulder_JNT", mid="L_elbow_JNT", end="L_wrist_JNT", name="arm")

Sub packages
------------
setups     the belt: framework (core) and tools (rig base, FK, IK/FK, spline, aim, hand, jaw, ribbon...)
core       naming, attributes, transforms, matrices, math, node helpers, undo
controls   control curve library and shape tools
joints     joint creation / orientation helpers used by the tools
geometry   curves, meshes and spatial queries
deformers  skin weights export / import
ui         the window, menu and shelf
"""

from jeffy.version import VERSION_INFO, __version__  # noqa: F401

TOOLKIT_NAME = "Jeff Inventory"


def show(*args, **kwargs):
    """Open (or raise) the Jeff Inventory window."""
    from jeffy.ui.setup_belt import window

    return window.show(*args, **kwargs)


#: older name, kept so existing shelf buttons and scripts keep working
show_setup_belt = show


def install_menu():
    """Create (or rebuild) the "Jeff Inventory" menu in Maya's main menu bar."""
    from jeffy.ui import menu

    return menu.install()


def install_shelf():
    """Create (or rebuild) the "Jeff" shelf."""
    from jeffy.ui import shelf

    return shelf.install()


def reload_toolkit(show_window=False):
    """Reload every ``jeffy`` module (development). Closes the window first."""
    import sys

    try:
        from jeffy.ui.setup_belt import window

        window.close()
    except Exception:  # pragma: no cover - UI may not be importable in batch
        pass

    names = sorted(name for name in sys.modules if name == "jeffy" or name.startswith("jeffy."))
    for name in names:
        del sys.modules[name]

    import jeffy as fresh

    fresh.install_menu()
    if show_window:
        fresh.show()
    return fresh
