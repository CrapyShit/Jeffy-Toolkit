"""A "Jeff" shelf: the window and the everyday utilities."""

import os

from maya import cmds, mel

SHELF_NAME = "Jeff"
#: the green eye (icons/jeffy_eye.png, made by tools/make_icons.py)
EYE_ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "icons", "jeffy_eye.png").replace("\\", "/")

BUTTONS = [
    ("JEFF", "Open Jeff Inventory", "import jeffy; jeffy.show()"),
    ("MIR", "Mirror control shapes L <> R", "from jeffy.ui import actions; actions.mirror_shapes()"),
    ("SKN>", "Export skin weights", "from jeffy.ui import actions; actions.export_skin_weights()"),
    (">SKN", "Import skin weights", "from jeffy.ui import actions; actions.import_skin_weights()"),
]


def install():
    if cmds.about(batch=True):
        return None
    top = mel.eval("$jeffyTmp = $gShelfTopLevel")
    if cmds.shelfLayout(SHELF_NAME, exists=True):
        cmds.deleteUI(SHELF_NAME, layout=True)
    shelf = cmds.shelfLayout(SHELF_NAME, parent=top)
    for overlay, annotation, command in BUTTONS:
        if overlay == "JEFF" and os.path.isfile(EYE_ICON):
            cmds.shelfButton(parent=shelf, label=annotation, annotation=annotation, image=EYE_ICON,
                             command=command, sourceType="python")
            continue
        cmds.shelfButton(parent=shelf, label=annotation, annotation=annotation, image="commandButton.png",
                         imageOverlayLabel=overlay, command=command, sourceType="python")
    return shelf
