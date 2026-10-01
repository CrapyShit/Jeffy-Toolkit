"""A "Jeffy" shelf with the most used tools."""

from maya import cmds, mel

SHELF_NAME = "Jeffy"

BUTTONS = [
    ("JEFFY", "Open Jeffy Toolkit", "import jeffy; jeffy.show()"),
    ("CTL", "Create control on selection", "from jeffy.ui import actions; actions.create_controls()"),
    ("ORI", "Orient joints (plane)", "from jeffy.ui import actions; actions.orient_joints(up_mode='plane')"),
    ("FK", "FK chain on selection", "from jeffy.ui import actions; actions.build_fk()"),
    ("IKFK", "IK/FK limb on selection", "from jeffy.ui import actions; actions.build_ikfk()"),
    ("SPC", "Space switch: control then targets", "from jeffy.ui import actions; actions.add_space_switch()"),
    ("MIR", "Mirror control shapes", "from jeffy.ui import actions; actions.mirror_shapes()"),
    ("SKN>", "Export skin weights", "from jeffy.ui import actions; actions.export_skin_weights()"),
    (">SKN", "Import skin weights", "from jeffy.ui import actions; actions.import_skin_weights()"),
    ("SWAP", "IK/FK match + switch", "from jeffy.ui import actions; actions.ikfk_switch()"),
    ("RST", "Reset controls", "from jeffy.ui import actions; actions.reset_controls()"),
    ("CHK", "Rig check", "from jeffy.ui import actions; actions.run_checks()"),
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
