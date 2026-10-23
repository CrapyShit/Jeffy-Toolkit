"""A "Jeff" shelf: the window and the everyday utilities."""

from maya import cmds, mel

SHELF_NAME = "Jeff"

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
        cmds.shelfButton(parent=shelf, label=annotation, annotation=annotation, image="commandButton.png",
                         imageOverlayLabel=overlay, command=command, sourceType="python")
    return shelf
