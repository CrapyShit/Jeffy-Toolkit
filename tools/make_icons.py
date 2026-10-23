"""Render the Jeff Inventory icons into ``icons/`` (no Maya needed).

::

    python tools/make_icons.py

Writes the green eye (the *loading* state: lime, with the sigil) on a black
tile: ``jeffy_eye.png`` (32 px, the shelf button) and larger copies, plus the
three states on their own (``jeffy_eye_idle.png``...).
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main():
    from jeffy.ui.qt import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from jeffy.ui import theme

    folder = os.path.join(ROOT, "icons")
    if not os.path.isdir(folder):
        os.makedirs(folder)
    written = []
    for size, name in ((32, "jeffy_eye.png"), (64, "jeffy_eye_64.png"), (128, "jeffy_eye_128.png"),
                       (256, "jeffy_eye_256.png")):
        path = os.path.join(folder, name)
        theme.eye_pixmap(size, theme.LOADING).save(path)
        written.append(path)
    for state in theme.STATES:
        path = os.path.join(folder, "jeffy_eye_%s.png" % state)
        theme.eye_pixmap(128, state).save(path)
        written.append(path)
    for path in written:
        print(os.path.relpath(path, ROOT))
    del app


if __name__ == "__main__":
    main()
