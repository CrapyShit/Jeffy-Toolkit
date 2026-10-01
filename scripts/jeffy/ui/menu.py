"""The "Jeffy" menu in Maya's main menu bar."""

from maya import cmds

from jeffy import TOOLKIT_NAME, __version__

MENU_NAME = "jeffyToolkitMenu"


def _act(name, *args, **kwargs):
    """Menu command calling ``jeffy.ui.actions.<name>`` (imported lazily)."""

    def command(*_unused):
        from jeffy.ui import actions

        getattr(actions, name)(*args, **kwargs)

    return command


def _show(*_unused):
    import jeffy

    jeffy.show()


def _reload(*_unused):
    import jeffy

    jeffy.reload_toolkit()


def _about(*_unused):
    cmds.confirmDialog(title=TOOLKIT_NAME, message="%s %s\nA Maya rigging toolkit.\n\nimport jeffy; jeffy.show()"
                       % (TOOLKIT_NAME, __version__), button=["OK"])


MENU = [
    ("Controls", [
        ("Create Control On Selection", _act("create_controls", shape="circle", axis="x")),
        ("Create Cube Control", _act("create_controls", shape="cube")),
        ("Replace Shape: Circle", _act("replace_shapes", "circle", None, "x")),
        ("Mirror Shapes L <> R", _act("mirror_shapes")),
        ("Copy Shape First > Rest", _act("copy_shape")),
        ("Scale Shapes Up", _act("scale_shapes", 1.25)),
        ("Scale Shapes Down", _act("scale_shapes", 0.8)),
        (None, None),
        ("Add Offset Group", _act("add_offset_group")),
        ("Bake To Offset Parent Matrix", _act("bake_offset_parent_matrix")),
        ("Match Transforms", _act("match_transforms")),
        ("Mirror Transforms", _act("mirror_transforms")),
    ]),
    ("Joints", [
        ("Joints At Selection (chain)", _act("joints_at_selection", True)),
        ("Joint At Center Of Selection", _act("joints_at_selection", False, True)),
        ("Insert Joint", _act("insert_joints", 1)),
        ("Orient Joints (plane, X aim / Y up)", _act("orient_joints", "x", "y", "plane")),
        ("Orient Joints (world up)", _act("orient_joints", "x", "y", "world")),
        ("Orient To World", _act("orient_to_world")),
        ("Freeze Joint Rotations", _act("freeze_joint_rotations")),
        ("Zero End Orients", _act("zero_end_orients")),
        ("Planarize Chain", _act("planarize_chain")),
        ("Mirror Joints (behavior, L_ > R_)", _act("mirror_joints")),
        ("Toggle Local Axes", _act("toggle_local_axes", True)),
        ("Label Joints", _act("label_joints")),
    ]),
    ("Rigging", [
        ("FK Chain", _act("build_fk")),
        ("IK Chain (stretch, soft)", _act("build_ik")),
        ("IK/FK Limb", _act("build_ikfk")),
        ("Spline IK", _act("build_spline")),
        ("Ribbon", _act("build_ribbon")),
        ("Twist Joints", _act("build_twist")),
        ("Space Switch (control, then targets)", _act("add_space_switch")),
        ("Matrix Constraint", _act("matrix_constraint")),
        ("Rivet / Attach (follicle)", _act("attach_to_geometry", "follicle")),
        ("Pose Reader", _act("create_pose_reader")),
        ("Rig Structure", _act("create_rig_structure")),
    ]),
    ("Skin", [
        ("Bind Skin", _act("bind_skin")),
        ("Export Weights...", _act("export_skin_weights")),
        ("Import Weights...", _act("import_skin_weights")),
        ("Copy Skin", _act("copy_skin")),
        ("Mirror Skin +X > -X", _act("mirror_skin", "x", True)),
        ("Prune Weights", _act("prune_weights")),
        ("Limit To 4 Influences", _act("limit_influences", 4)),
        ("Remove Unused Influences", _act("remove_unused_influences")),
        ("Rebind At Current Pose", _act("rebind_at_current_pose")),
        (None, None),
        ("Copy Vertex Weights", _act("copy_vertex_weights")),
        ("Paste Vertex Weights", _act("paste_vertex_weights")),
        ("Smooth Weights", _act("smooth_weights")),
    ]),
    ("Deformers", [
        ("Soft Selection Cluster", _act("soft_selection_cluster")),
        ("Wrap (driver last)", _act("create_wrap")),
        ("Extract Blendshape Targets", _act("extract_blendshape_targets")),
        ("Mirror Blendshape Target", _act("mirror_blendshape_target")),
        ("Split Blendshape Target", _act("split_blendshape_target")),
        ("Proxies From Skin", _act("proxies_from_skin")),
    ]),
    ("Animate", [
        ("Reset Controls", _act("reset_controls")),
        ("Mirror Pose", _act("mirror_pose")),
        ("Flip Pose", _act("flip_pose")),
        ("IK/FK Match + Switch", _act("ikfk_switch")),
        ("Select All Controls", _act("select_all_controls")),
    ]),
    ("Auto-Rig", [
        ("Biped Template", _act("create_template", "biped")),
        ("Mirror Guides", _act("mirror_guides")),
        ("Build Rig", _act("build_rig")),
        ("Delete Rig", _act("delete_rig")),
        ("Rebuild Rig", _act("rebuild_rig")),
    ]),
    ("Scene", [
        ("Rig Check", _act("run_checks")),
        ("Clean Scene", _act("clean_scene")),
        ("Remove Namespaces", _act("remove_namespaces")),
        ("Make Names Unique", _act("make_names_unique")),
        ("Scene Report", _act("scene_report")),
    ]),
]


def install():
    """(Re)create the menu. Does nothing in batch mode."""
    if cmds.about(batch=True):
        return None
    uninstall()
    menu = cmds.menu(MENU_NAME, label="Jeffy", parent="MayaWindow", tearOff=True)
    cmds.menuItem(label="Open Jeffy Toolkit", command=_show, parent=menu)
    cmds.menuItem(divider=True, parent=menu)
    for title, entries in MENU:
        sub = cmds.menuItem(label=title, subMenu=True, tearOff=True, parent=menu)
        for label_text, command in entries:
            if label_text is None:
                cmds.menuItem(divider=True, parent=sub)
            else:
                cmds.menuItem(label=label_text, command=command, parent=sub)
    cmds.menuItem(divider=True, parent=menu)
    cmds.menuItem(label="Create Shelf", command=lambda *_: __import__("jeffy").install_shelf(), parent=menu)
    cmds.menuItem(label="Reload Toolkit", command=_reload, parent=menu)
    cmds.menuItem(label="About", command=_about, parent=menu)
    return menu


def uninstall():
    if cmds.menu(MENU_NAME, exists=True):
        cmds.deleteUI(MENU_NAME, menu=True)
