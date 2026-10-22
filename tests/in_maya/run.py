"""Run the headless Maya tests with mayapy (real Maya, no pytest needed).

::

    "C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe" tests/in_maya/run.py
    mayapy tests/in_maya/run.py -k ikfk          # only tests whose name contains "ikfk"

Every ``test_*`` function of every ``test_*.py`` module in this folder runs
in a fresh scene. Exit code 1 when a test fails.
"""

import importlib
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for path in (os.path.join(ROOT, "scripts"), HERE):
    if path not in sys.path:
        sys.path.insert(0, path)


def _tests(pattern):
    for filename in sorted(os.listdir(HERE)):
        if not (filename.startswith("test_") and filename.endswith(".py")):
            continue
        module = importlib.import_module(filename[:-3])
        for name in sorted(vars(module)):
            func = getattr(module, name)
            if name.startswith("test_") and callable(func) and (not pattern or pattern in name):
                yield "%s.%s" % (filename[:-3], name), func


def main(argv):
    pattern = argv[argv.index("-k") + 1] if "-k" in argv else None
    # Widgets need a QApplication: create it before Maya (standalone only makes a QGuiApplication)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6 import QtWidgets
    except ImportError:  # Maya 2024 and older
        from PySide2 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["jeffy-tests"])
    import maya.standalone

    maya.standalone.initialize(name="python")
    from maya import cmds

    cmds.loadPlugin("matrixNodes", quiet=True)
    failures = []
    count = 0
    for name, func in _tests(pattern):
        count += 1
        cmds.file(new=True, force=True)
        start = time.time()
        try:
            func()
        except Exception:  # report every failure, keep going
            failures.append((name, traceback.format_exc()))
            print("FAIL %s (%.1fs)" % (name, time.time() - start))
        else:
            print("ok   %s (%.1fs)" % (name, time.time() - start))
        sys.stdout.flush()
    for name, trace in failures:
        print("\n==== %s ====\n%s" % (name, trace))
    print("\n%d tests, %d failed" % (count, len(failures)))
    sys.stdout.flush()
    cmds.file(new=True, force=True)
    maya.standalone.uninitialize()
    del app
    return 1 if failures else 0


if __name__ == "__main__":
    code = main(sys.argv[1:])
    os._exit(code)  # mayapy can hang on exit after standalone sessions
