"""Jeffy Toolkit installer - drag and drop this file into a Maya viewport.

It writes a Maya *module* file (``jeffy_toolkit.mod``) into your user modules
folder that points at this repository, so:

* the toolkit loads automatically in every future Maya session,
* updating is just ``git pull`` (or replacing the folder) - no reinstall,
* uninstalling is deleting the ``.mod`` file (see :func:`uninstall`).

The toolkit is also loaded immediately, the "Jeffy" menu is created and the
window opens.
"""

import os
import sys

MODULE_NAME = "JeffyToolkit"
MOD_FILE = "jeffy_toolkit.mod"


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _modules_dir():
    from maya import cmds

    path = os.path.join(cmds.internalVar(userAppDir=True), "modules")
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def _version(root):
    namespace = {}
    path = os.path.join(root, "scripts", "jeffy", "version.py")
    try:
        with open(path) as handle:
            exec(handle.read(), namespace)
        return namespace.get("__version__", "1.0.0")
    except (IOError, OSError):
        return "1.0.0"


def install(open_window=True):
    from maya import cmds

    root = _repo_root().replace("\\", "/")
    scripts = root + "/scripts"
    mod_path = os.path.join(_modules_dir(), MOD_FILE)
    with open(mod_path, "w") as handle:
        handle.write("+ %s %s %s\n" % (MODULE_NAME, _version(root), root))
        handle.write("PYTHONPATH +:= scripts\n")

    # load right away (no restart needed)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    for name in [n for n in sys.modules if n == "jeffy" or n.startswith("jeffy.")]:
        del sys.modules[name]
    import jeffy

    jeffy.install_menu()
    if open_window:
        jeffy.show()
    cmds.inViewMessage(assistMessage="<hl>Jeffy Toolkit %s</hl> installed" % jeffy.__version__,
                       position="topCenter", fade=True)
    print("[Jeffy] Module file written to %s" % mod_path)
    return mod_path


def uninstall():
    """Remove the module file (restart Maya afterwards)."""
    mod_path = os.path.join(_modules_dir(), MOD_FILE)
    if os.path.isfile(mod_path):
        os.remove(mod_path)
    try:
        from jeffy.ui import menu

        menu.uninstall()
    except Exception:
        pass
    return mod_path


def onMayaDroppedPythonFile(*_args):  # noqa: N802 - name required by Maya
    """Called by Maya when this file is dropped into a viewport."""
    install()


if __name__ == "__main__":
    try:
        install()
    except ImportError:
        print("Run this file inside Maya (drag and drop it into a viewport).")
