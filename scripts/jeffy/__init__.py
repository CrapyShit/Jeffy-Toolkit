"""Jeffy Toolkit - a rigging toolkit for Autodesk Maya.

Quick start (inside Maya)::

    import jeffy
    jeffy.show()            # open the toolkit window
    jeffy.install_menu()    # (re)build the "Jeffy" main menu

Everything in the toolkit is also usable as a plain Python API, e.g.::

    from jeffy.controls import control
    ctl = control.Control.create("arm", side="L", shape="circle", axis="x")

Sub packages
------------
core       naming, attributes, transforms, matrices, node helpers, undo ...
controls   control curve library and shape tools
joints     joint creation / orientation / mirroring tools
geometry   mesh, curve, surface, symmetry and proxy geometry helpers
rig        rig building blocks (FK, IK, IK/FK, spline, ribbon, foot, spaces ...)
deformers  skinning, blendshape and generic deformer tools
utils      pose, bake, scene cleanup, rig validation, connections ...
autorig    guide based modular auto-rigger
ui         Qt user interface, Maya menu and shelf
"""

from jeffy.version import VERSION_INFO, __version__  # noqa: F401

TOOLKIT_NAME = "Jeffy Toolkit"


def show(*args, **kwargs):
    """Open (or raise) the main Jeffy Toolkit window."""
    from jeffy.ui import main_window

    return main_window.show(*args, **kwargs)


def install_menu():
    """Create (or rebuild) the "Jeffy" menu in Maya's main menu bar."""
    from jeffy.ui import menu

    return menu.install()


def install_shelf():
    """Create (or rebuild) the "Jeffy" shelf."""
    from jeffy.ui import shelf

    return shelf.install()


def reload_toolkit(show_window=False):
    """Reload every ``jeffy`` module - handy while developing new tools.

    Closes the UI first so that no widget keeps references to stale classes.
    """
    import sys

    try:
        from jeffy.ui import main_window

        main_window.close()
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
