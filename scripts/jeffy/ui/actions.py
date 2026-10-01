"""Selection based entry points used by the window, the menu and the shelf.

Every function is wrapped with :func:`jeffy.core.decorators.tool`: one undo
step, friendly warnings for bad selections and no exception leaking into Qt.
They can be called from scripts or shelf buttons too::

    from jeffy.ui import actions
    actions.create_controls(shape="cube", size=2)
"""

import os

from maya import cmds

from jeffy.core import decorators, naming
from jeffy.core.decorators import ToolError, tool


def _selection(minimum=1, node_type=None, flatten=False, ordered=False):
    kwargs = {"flatten": flatten}
    if ordered:
        kwargs["orderedSelection"] = True
    else:
        kwargs["selection"] = True
    if node_type:
        kwargs["type"] = node_type
    nodes = cmds.ls(**kwargs) or []
    if len(nodes) < minimum:
        raise ToolError("Select at least %d %s" % (minimum, node_type or "object(s)"))
    return nodes


def _file_dialog(mode="save", caption="File", file_filter="JSON (*.json)", start=None):
    from jeffy.core import fileio, settings

    start = start or settings.get("last_export_dir") or fileio.scene_dir()
    result = cmds.fileDialog2(fileMode=0 if mode == "save" else 1, caption=caption, fileFilter=file_filter,
                              startingDirectory=start, dialogStyle=2)
    if not result:
        return None
    settings.set("last_export_dir", os.path.dirname(result[0]))
    return result[0]


def _folder_dialog(caption="Folder"):
    from jeffy.core import fileio

    result = cmds.fileDialog2(fileMode=3, caption=caption, startingDirectory=fileio.scene_dir(), dialogStyle=2)
    return result[0] if result else None


# ===========================================================================
# Controls
# ===========================================================================
@tool("Create Controls")
def create_controls(shape="circle", size=1.0, axis="x", color_value=None, offsets=("zero",), constrain=False,
                    hierarchy=True, line_width=None):
    from jeffy.controls import control, shapes

    selection = cmds.ls(selection=True, transforms=True) or []
    if not selection:
        ctl = control.Control.create("control", shape=shape, size=size, axis=axis, color_value=color_value,
                                     offsets=offsets, line_width=line_width)
        cmds.select(ctl.node)
        return [ctl]
    controls = control.create_on_nodes(selection, shape=shape, size=size, axis=axis, offsets=offsets,
                                       parent_hierarchy=hierarchy, color_value=color_value)
    for ctl, node in zip(controls, selection):
        if line_width:
            shapes.set_line_width(ctl.node, line_width)
        if constrain:
            cmds.parentConstraint(ctl.node, node, maintainOffset=True)
            cmds.scaleConstraint(ctl.node, node, maintainOffset=True)
    cmds.select([c.node for c in controls])
    return controls


@tool("Replace Shape")
def replace_shapes(shape="circle", size=None, axis="y"):
    from jeffy.controls import shapes

    shapes.replace_shape(_selection(), shape, size=size, axis=axis)


@tool("Set Color")
def color_selected(color_value):
    from jeffy.core import color

    color.set_color(_selection(), color_value)


@tool("Reset Color")
def reset_color_selected():
    from jeffy.core import color

    color.reset_color(_selection())


@tool("Mirror Shapes")
def mirror_shapes(axis="x"):
    from jeffy.controls import shapes

    selection = _selection()
    done = shapes.mirror_shapes(selection, axis)
    if not done:
        raise ToolError("No L_/R_ counterpart found for the selection")
    decorators.message("Mirrored %d shape(s)" % len(done))


@tool("Copy Shape")
def copy_shape(world=False):
    from jeffy.controls import shapes

    selection = _selection(2)
    shapes.copy_shape(selection[0], selection[1:], world=world)


@tool("Scale Shapes")
def scale_shapes(factor=1.25):
    from jeffy.controls import shapes

    shapes.scale_shapes(_selection(), factor)


@tool("Rotate Shapes")
def rotate_shapes(rotation=(90, 0, 0)):
    from jeffy.controls import shapes

    shapes.rotate_shapes(_selection(), rotation)


@tool("Line Width")
def set_line_width(width=2.0):
    from jeffy.controls import shapes

    shapes.set_line_width(_selection(), width)


@tool("Combine Curves")
def combine_curves():
    from jeffy.controls import shapes

    result = shapes.combine(_selection(2))
    cmds.select(result)


@tool("Save Shape")
def save_shape_to_library(name=None):
    from jeffy.controls import shapes

    selection = _selection(1)
    path = shapes.save_to_library(selection[0], name)
    decorators.message("Saved shape to %s" % path)
    return path


@tool("Text Control")
def create_text_control(text="TEXT", font="Arial"):
    from jeffy.controls import shapes

    node = shapes.text_curves(text, name=naming.legalize(text) + "_CTL", font=font)
    cmds.select(node)
    return node


@tool("Tag Controls")
def tag_as_controls():
    from jeffy.controls import control

    control.tag_as_control(_selection())


@tool("Add Offset Group")
def add_offset_group(suffix="OFF"):
    from jeffy.core import transform

    groups = []
    for node in _selection():
        groups.extend(transform.add_offset_groups(node, [suffix]))
    cmds.select(groups)


@tool("Bake To Offset Parent Matrix")
def bake_offset_parent_matrix():
    from jeffy.core import transform

    transform.bake_to_offset_parent_matrix(_selection())


@tool("Unbake Offset Parent Matrix")
def unbake_offset_parent_matrix():
    from jeffy.core import transform

    transform.unbake_offset_parent_matrix(_selection())


@tool("Export Shapes")
def export_shapes():
    from jeffy.controls import shapes

    path = _file_dialog("save", "Export control shapes")
    if path:
        shapes.export_shapes(path, _selection())


@tool("Import Shapes")
def import_shapes():
    from jeffy.controls import shapes

    path = _file_dialog("open", "Import control shapes")
    if path:
        shapes.import_shapes(path, cmds.ls(selection=True) or None)


# ===========================================================================
# Transforms
# ===========================================================================
@tool("Match Transforms")
def match_transforms(translate=True, rotate=True, scale=False):
    from jeffy.core import transform

    selection = _selection(2)
    for node in selection[:-1]:
        transform.match(node, selection[-1], translate, rotate, scale)


@tool("Reset Transforms")
def reset_transforms():
    from jeffy.core import transform

    transform.reset(_selection())


@tool("Freeze Transforms")
def freeze_transforms():
    from jeffy.core import transform

    transform.freeze(_selection())


@tool("Mirror Transforms")
def mirror_transforms(axis="x", mode="behavior"):
    from jeffy.core import transform

    for node in _selection():
        transform.mirror(node, axis=axis, mode=mode)


@tool("Locator At Selection")
def locators_at_selection(center=False):
    from jeffy.core import transform

    selection = _selection(flatten=False)
    result = [transform.locator_at_center(selection)] if center else transform.locators_at(selection)
    cmds.select(result)


# ===========================================================================
# Joints
# ===========================================================================
@tool("Joints At Selection")
def joints_at_selection(chain=False, center=False, name="joint"):
    from jeffy.joints import tools as joint_tools

    joints = joint_tools.joints_at_selection(_selection(ordered=True), name=name, chain=chain, center=center)
    cmds.select(joints)


@tool("Joints On Curve")
def joints_on_curve(count=5, name="curve"):
    from jeffy.joints import tools as joint_tools

    curve = _selection(1)[0]
    joints = joint_tools.joints_on_curve(curve, count=count, name=name)
    cmds.select(joints)


@tool("Insert Joints")
def insert_joints(count=1):
    from jeffy.joints import tools as joint_tools

    created = []
    for joint in _selection(1, "joint"):
        created.extend(joint_tools.insert_joints(joint, count))
    cmds.select(created)


@tool("Duplicate Chain")
def duplicate_chain(search="_JNT", replace="_DUP_JNT"):
    from jeffy.joints import tools as joint_tools

    selection = _selection(1, "joint")
    end = selection[1] if len(selection) > 1 else None
    cmds.select(joint_tools.duplicate_chain(selection[0], end, search=search, replace=replace))


@tool("Mirror Joints")
def mirror_joints(axis="x", behavior=True, search="L_", replace="R_"):
    from jeffy.joints import tools as joint_tools

    cmds.select(joint_tools.mirror_joints(_selection(1, "joint"), axis, behavior, search, replace))


@tool("Orient Joints")
def orient_joints(aim_axis="x", up_axis="y", up_mode="world", world_up=(0, 1, 0), end_mode="parent",
                  hierarchy=True):
    from jeffy.joints import orient

    selection = _selection(1, "joint")
    up_object = None
    if up_mode == "object":
        objects = cmds.ls(selection=True) or []
        if len(objects) < 2:
            raise ToolError("Select the joints then the up object last")
        up_object = objects[-1]
        selection = [s for s in selection if s != up_object]
    orient.orient_joints(selection, aim_axis=aim_axis, up_axis=up_axis, up_mode=up_mode, world_up=world_up,
                         up_object=up_object, end_mode=end_mode, hierarchy=hierarchy)
    cmds.select(selection)


@tool("Orient To World")
def orient_to_world():
    from jeffy.joints import orient

    orient.orient_to_world(_selection(1, "joint"))


@tool("Rotate Joint Axes")
def rotate_joint_axes(rotation=(90, 0, 0)):
    from jeffy.joints import orient

    orient.rotate_axes(_selection(1, "joint"), rotation)


@tool("Freeze Joint Rotations")
def freeze_joint_rotations():
    from jeffy.joints import orient

    orient.freeze_rotations(_selection(1, "joint"))


@tool("Zero End Orients")
def zero_end_orients():
    from jeffy.joints import tools as joint_tools

    selection = _selection(1, "joint")
    joints = []
    for joint in selection:
        joints.append(joint)
        joints.extend(cmds.listRelatives(joint, allDescendents=True, type="joint", fullPath=True) or [])
    joint_tools.zero_end_orients(joints)


@tool("Planarize Chain")
def planarize_chain():
    from jeffy.core import dag
    from jeffy.joints import tools as joint_tools

    selection = _selection(1, "joint")
    chain = dag.get_chain(selection[0], selection[1] if len(selection) > 1 else None)
    joint_tools.planarize_chain(chain)


@tool("Joint Radius")
def set_joint_radius(radius=1.0):
    from jeffy.joints import tools as joint_tools

    joint_tools.set_radius(_selection(1, "joint"), radius)


@tool("Toggle Local Axes")
def toggle_local_axes(hierarchy=False):
    from jeffy.joints import tools as joint_tools

    selection = _selection()
    nodes = list(selection)
    if hierarchy:
        for node in selection:
            nodes.extend(cmds.listRelatives(node, allDescendents=True, type="joint", fullPath=True) or [])
    joint_tools.set_local_axes_visible(nodes)


@tool("Joint Draw Style")
def set_draw_style(style="bone"):
    from jeffy.joints import tools as joint_tools

    joint_tools.set_draw_style(_selection(1, "joint"), style)


@tool("Label Joints")
def label_joints():
    from jeffy.joints import tools as joint_tools

    selection = _selection(1, "joint")
    joints = list(selection)
    for joint in selection:
        joints.extend(cmds.listRelatives(joint, allDescendents=True, type="joint") or [])
    joint_tools.label_joints(joints)


@tool("Segment Scale Compensate")
def segment_scale_compensate(state=False):
    from jeffy.joints import tools as joint_tools

    joint_tools.set_segment_scale_compensate(_selection(1, "joint"), state)


@tool("Select End Joints")
def select_end_joints():
    from jeffy.joints import tools as joint_tools

    cmds.select(joint_tools.get_end_joints(_selection(1, "joint")))


@tool("Set Preferred Angles")
def set_preferred_angles():
    from jeffy.joints import tools as joint_tools

    joint_tools.set_preferred_angles(_selection(1, "joint"))


# ===========================================================================
# Rigging
# ===========================================================================
def _chain_from_selection(minimum=2):
    from jeffy.core import dag

    selection = cmds.ls(selection=True, type="joint") or []
    if not selection:
        raise ToolError("Select joints")
    if len(selection) == 1:
        chain = dag.get_chain(selection[0])
    elif len(selection) == 2:
        chain = dag.get_chain(selection[0], selection[1])
    else:
        chain = selection
    chain = [naming.short_name(j) for j in chain]
    if len(chain) < minimum:
        raise ToolError("The chain needs at least %d joints" % minimum)
    return chain


def _name_side(joint, default="limb"):
    parsed = naming.parse(joint)
    return parsed["name"] or default, parsed["side"]


@tool("Create Rig Structure")
def create_rig_structure(name="character", size=10.0):
    from jeffy.rig import structure

    result = structure.create(name, size)
    cmds.select(result.rig)
    return result


@tool("FK Chain")
def build_fk(shape="circle", size=1.0, connect="constraint", skip_last=False):
    from jeffy.rig import fk

    chain = _chain_from_selection(1)
    result = fk.build_fk_chain(chain, shape=shape, size=size, connect=connect, skip_last=skip_last)
    cmds.select(result["zero"])


@tool("IK Chain")
def build_ik(stretch=True, soft=True, pin=True, pole_distance=1.0, size=1.0):
    from jeffy.rig import ik

    chain = _chain_from_selection(3)
    name, side = _name_side(chain[0])
    parent = (cmds.listRelatives(chain[0], parent=True) or [None])[0]
    result = ik.build_ik(chain, name=name, side=side, stretch=stretch, soft=soft, pin=pin,
                         pole_distance=pole_distance, size=size, parent=parent)
    cmds.select(result["ik_control"].node)


@tool("IK/FK Limb")
def build_ikfk(stretch=True, soft=True, pin=True, pole_distance=1.0, size=1.0, ik_count=None):
    from jeffy.rig import ikfk

    chain = _chain_from_selection(3)
    name, side = _name_side(chain[0])
    parent = (cmds.listRelatives(chain[0], parent=True) or [None])[0]
    result = ikfk.build_ikfk_limb(chain, name=name, side=side, parent=parent, stretch=stretch, soft=soft, pin=pin,
                                  pole_distance=pole_distance, size=size, ik_count=ik_count)
    cmds.select(result["settings"].node)


@tool("Spline IK")
def build_spline(controls=3, stretch=True, volume=True, size=1.0):
    from jeffy.rig import spline

    chain = _chain_from_selection(3)
    name, side = _name_side(chain[0], "spline")
    result = spline.build_spline_ik(chain, name=name, side=side, num_controls=controls, stretch=stretch,
                                    volume=volume, size=size)
    cmds.select([c.node for c in result["controls"]])


@tool("Ribbon")
def build_ribbon(joints=5, controls=3, width=None, name="ribbon"):
    from jeffy.rig import ribbon

    selection = _selection(2, ordered=True)
    result = ribbon.build_ribbon(selection, name=name, side=naming.side_from_name(selection[0]),
                                 num_joints=joints, num_controls=controls, width=width)
    cmds.select([c.node for c in result["controls"]])


@tool("Twist Joints")
def build_twist(count=3, mode="forward"):
    from jeffy.rig import twist

    selection = _selection(2, "joint")
    joints = twist.create_twist_joints(selection[0], selection[1], count=count, mode=mode)
    cmds.select(joints)


@tool("Reverse Foot")
def build_reverse_foot():
    from jeffy.core import transform
    from jeffy.rig import foot

    selection = _selection(8, ordered=True)
    ik_ctl, end_target, ankle, ball, toe, heel, inner, outer = selection[:8]
    foot.build_reverse_foot(ik_ctl, end_target, ankle, ball, toe, transform.get_position(heel),
                            transform.get_position(inner), transform.get_position(outer),
                            name=_name_side(ankle, "foot")[0], side=naming.side_from_name(ankle))


@tool("Space Switch")
def add_space_switch(mode="parent", method="constraint", attr="space"):
    from jeffy.rig import space_switch

    selection = _selection(2, ordered=True)
    control, targets = selection[0], selection[1:]
    spaces = [(naming.parse(t)["name"] or naming.strip_namespace(t), t) for t in targets]
    space_switch.create(control, spaces, attr=attr, mode=mode, method=method)
    cmds.select(control)


@tool("Switch Space")
def switch_space(space, key=False):
    from jeffy.rig import space_switch

    if not space_switch.switch_selected(space, key=key):
        raise ToolError("No selected control has a %r space" % (space,))


@tool("Matrix Constraint")
def matrix_constraint(maintain_offset=True, translate=True, rotate=True, scale=True):
    from jeffy.rig import matrix_constraints

    selection = _selection(2)
    for driven in selection[1:]:
        matrix_constraints.matrix_constraint(selection[0], driven, maintain_offset, translate, rotate, scale)


@tool("Remove Matrix Constraint")
def remove_matrix_constraint():
    from jeffy.rig import matrix_constraints

    for node in _selection():
        matrix_constraints.remove_matrix_constraint(node)


@tool("Attach To Geometry")
def attach_to_geometry(method="follicle"):
    from jeffy.rig import attach

    selection = _selection(1)
    if not any("." in item for item in selection) and len(selection) < 2:
        raise ToolError("Select objects then the mesh/surface last (or select components)")
    cmds.select(attach.rivets_on_selection(method=method))


@tool("Eye Rig")
def build_eye_rig(distance=30.0):
    from jeffy.rig import aim

    selection = _selection(1)
    result = aim.build_eye_rig(selection, distance=distance)
    cmds.select(result["master"].node)


@tool("Pose Reader")
def create_pose_reader(angle=60.0, axis="x"):
    from jeffy.rig import pose_reader

    readers = [pose_reader.create_cone_reader(j, axis=axis, cone_angle=angle) for j in _selection(1)]
    cmds.select(readers)


@tool("Dynamic Chain")
def create_dynamic_chain():
    from jeffy.rig import dynamics

    chain = _chain_from_selection(3)
    name, side = _name_side(chain[0], "dynamic")
    result = dynamics.create_dynamic_chain(chain, name=name, side=side)
    cmds.select(result["hair_system"])


@tool("Finger Controls")
def build_fingers(size=0.5):
    from jeffy.core import dag
    from jeffy.rig import fingers

    selection = _selection(1, ordered=True)
    holder = None
    roots = [s for s in selection if cmds.nodeType(s) == "joint"]
    others = [s for s in selection if cmds.nodeType(s) != "joint"]
    if others:
        holder = others[0]
    chains = [(naming.parse(r)["name"] or naming.short_name(r), [naming.short_name(j) for j in dag.get_chain(r)])
              for r in roots]
    fingers.build_fingers(chains, side=naming.side_from_name(roots[0]), attr_holder=holder, size=size)


@tool("Connector Line")
def connector_line():
    from jeffy.geometry import curves

    selection = _selection(2)
    cmds.select(curves.create_connector_line(selection[0], selection[1]))


@tool("Build Expression")
def build_expression(text):
    from jeffy.core import expression

    try:
        targets = expression.build(text)
    except expression.ExpressionError as error:
        raise ToolError(str(error)) from error
    decorators.message("Built network for %d target(s)" % len(targets))
    return targets


# ===========================================================================
# Skinning / deformers
# ===========================================================================
def _meshes():
    selection = cmds.ls(selection=True, transforms=True) or []
    meshes = [s for s in selection if cmds.listRelatives(s, shapes=True, type=["mesh", "nurbsCurve",
                                                                                "nurbsSurface"])]
    if not meshes:
        raise ToolError("Select skinned geometry")
    return meshes


@tool("Bind Skin")
def bind_skin(max_influences=4, method="closest"):
    from jeffy.deformers import skin

    joints = cmds.ls(selection=True, type="joint") or []
    meshes = [m for m in (cmds.ls(selection=True, transforms=True) or []) if m not in joints]
    if not joints or not meshes:
        raise ToolError("Select joints and meshes")
    skin.bind(meshes, joints, max_influences=max_influences, method=method)


@tool("Export Skin Weights")
def export_skin_weights():
    from jeffy.deformers import skin

    meshes = _meshes()
    if len(meshes) == 1:
        path = _file_dialog("save", "Export skin weights")
        if path:
            skin.export_weights(meshes[0], path)
    else:
        folder = _folder_dialog("Export skin weights to folder")
        if folder:
            skin.export_selected(folder)


@tool("Import Skin Weights")
def import_skin_weights(method="auto"):
    from jeffy.deformers import skin

    meshes = _meshes()
    if len(meshes) == 1:
        path = _file_dialog("open", "Import skin weights")
        if path:
            skin.import_weights(meshes[0], path, method=method)
    else:
        folder = _folder_dialog("Import skin weights from folder")
        if folder:
            skin.import_selected(folder, method=method)


@tool("Copy Skin")
def copy_skin():
    from jeffy.deformers import skin

    meshes = _meshes()
    if len(meshes) < 2:
        raise ToolError("Select the source mesh then the target meshes")
    skin.copy_skin(meshes[0], meshes[1:])


@tool("Mirror Skin")
def mirror_skin(axis="x", positive_to_negative=True):
    from jeffy.deformers import skin

    skin.mirror_skin(_meshes(), axis, positive_to_negative)


@tool("Prune Weights")
def prune_weights(threshold=0.01):
    from jeffy.deformers import skin

    skin.prune(_meshes(), threshold)


@tool("Limit Influences")
def limit_influences(max_influences=4):
    from jeffy.deformers import skin

    skin.limit_influences(_meshes(), max_influences)


@tool("Remove Unused Influences")
def remove_unused_influences():
    from jeffy.deformers import skin

    removed = skin.remove_unused_influences(_meshes())
    decorators.message("Removed %d influence(s)" % len(removed))


@tool("Rebind At Current Pose")
def rebind_at_current_pose():
    from jeffy.deformers import skin

    skin.rebind_at_current_pose(_meshes())


@tool("Go To Bind Pose")
def go_to_bind_pose():
    from jeffy.deformers import skin

    skin.go_to_bind_pose(cmds.ls(selection=True, transforms=True) or None)


@tool("Copy Vertex Weights")
def copy_vertex_weights():
    from jeffy.deformers import skin

    weights = skin.copy_vertex_weights()
    decorators.message("Copied weights of %d influence(s)" % len(weights))


@tool("Paste Vertex Weights")
def paste_vertex_weights():
    from jeffy.deformers import skin

    skin.paste_vertex_weights()


@tool("Average Vertex Weights")
def average_vertex_weights():
    from jeffy.deformers import skin

    skin.average_vertex_weights()


@tool("Smooth Weights")
def smooth_weights(iterations=2, strength=0.5):
    from jeffy.deformers import skin

    skin.smooth_weights(iterations=iterations, strength=strength)


@tool("Move Weights")
def move_weights():
    """Select the source joint, the target joint, then the mesh (or vertices)."""
    from jeffy.deformers import skin

    selection = _selection(3, ordered=True, flatten=False)
    source, target = selection[0], selection[1]
    rest = selection[2:]
    components = [r for r in rest if "." in r]
    mesh = rest[0].split(".")[0] if rest else None
    skin.move_weights(mesh, source, target, components=components or None)


@tool("Select Influences")
def select_influences():
    from jeffy.deformers import skin

    skin.select_influences(_meshes())


@tool("Select Influenced Vertices")
def select_influenced_vertices():
    from jeffy.deformers import skin

    joints = _selection(1, "joint")
    skin.select_influenced_vertices(joints[0])


@tool("Unbind Skin")
def unbind_skin(keep_history=False):
    from jeffy.deformers import skin

    skin.unbind(_meshes(), keep_history)


@tool("Combine Skinned Meshes")
def combine_skinned(name="combined_GEO"):
    from jeffy.deformers import skin

    cmds.select(skin.combine_skinned(_meshes(), name))


@tool("Skin Info")
def skin_info():
    from jeffy.deformers import skin

    lines = []
    for mesh in _meshes():
        info = skin.skin_info(mesh)
        lines.append("%s: %s" % (mesh, ", ".join("%s=%s" % item for item in sorted(info.items()))))
    print("\n".join(lines))
    decorators.message("Skin info printed in the Script Editor")
    return lines


@tool("Skinning Method")
def set_skinning_method(method="linear"):
    from jeffy.deformers import skin

    skin.set_skinning_method(_meshes(), method)


@tool("Add Blendshape Targets")
def add_blendshape_targets():
    from jeffy.deformers import blendshape

    blendshape.add_targets_from_selection()


@tool("Extract Blendshape Targets")
def extract_blendshape_targets(connect=False):
    from jeffy.deformers import blendshape

    meshes = _meshes()
    for mesh in meshes:
        for bs in blendshape.find_blendshapes(mesh):
            blendshape.extract_targets(bs, connect=connect)


@tool("Mirror Blendshape Target")
def mirror_blendshape_target(axis="x"):
    from jeffy.deformers import blendshape

    selection = _selection(2)
    base, targets = selection[0], selection[1:]
    cmds.select([blendshape.mirror_target(base, t, axis=axis) for t in targets])


@tool("Split Blendshape Target")
def split_blendshape_target(falloff=2.0, axis="x"):
    from jeffy.deformers import blendshape

    selection = _selection(2)
    base, targets = selection[0], selection[1:]
    result = []
    for target in targets:
        result.extend(blendshape.split_target(base, target, axis=axis, falloff=falloff))
    cmds.select(result)


@tool("Symmetrize Blendshape Target")
def symmetrize_blendshape_target(axis="x", positive_to_negative=True):
    from jeffy.deformers import blendshape
    from jeffy.geometry import symmetry

    selection = _selection(2)
    direction = symmetry.POSITIVE_TO_NEGATIVE if positive_to_negative else symmetry.NEGATIVE_TO_POSITIVE
    cmds.select([blendshape.symmetrize_target(selection[0], t, axis, direction) for t in selection[1:]])


@tool("Transfer Blendshapes")
def transfer_blendshapes():
    from jeffy.deformers import blendshape

    selection = _selection(2)
    blendshape.transfer_blendshapes(selection[0], selection[1])


@tool("Soft Selection Cluster")
def soft_selection_cluster(name="soft_CLS"):
    from jeffy.deformers import utils as deformer_utils

    _cluster, handle = deformer_utils.cluster_from_soft_selection(name)
    cmds.select(handle)


@tool("Wrap")
def create_wrap():
    from jeffy.deformers import utils as deformer_utils

    selection = _selection(2)
    driver = selection[-1]
    for driven in selection[:-1]:
        deformer_utils.create_wrap(driver, driven)


@tool("Delta Mush")
def create_delta_mush():
    from jeffy.deformers import utils as deformer_utils

    deformer_utils.create_delta_mush(_meshes())


@tool("Toggle Deformers")
def toggle_deformers():
    from jeffy.deformers import utils as deformer_utils

    for mesh in _meshes():
        deformer_utils.toggle_deformers(mesh)


@tool("Mirror Deformer Weights")
def mirror_deformer_weights(axis="x", positive_to_negative=True):
    from jeffy.deformers import utils as deformer_utils
    from jeffy.geometry import symmetry

    direction = symmetry.POSITIVE_TO_NEGATIVE if positive_to_negative else symmetry.NEGATIVE_TO_POSITIVE
    selection = cmds.ls(selection=True) or []
    deformers = [s for s in selection if cmds.objectType(s, isAType="geometryFilter")]
    meshes = [s for s in selection if s not in deformers]
    if not deformers:
        raise ToolError("Select a deformer (and optionally the deformed mesh)")
    for deformer in deformers:
        deformer_utils.mirror_deformer_weights(deformer, meshes[0] if meshes else None, axis, direction)


@tool("Export Deformer Weights")
def export_deformer_weights():
    from jeffy.deformers import utils as deformer_utils

    deformer = _selection(1)[0]
    path = _file_dialog("save", "Export deformer weights")
    if path:
        deformer_utils.export_deformer_weights(deformer, path)


@tool("Import Deformer Weights")
def import_deformer_weights():
    from jeffy.deformers import utils as deformer_utils

    deformer = _selection(1)[0]
    path = _file_dialog("open", "Import deformer weights")
    if path:
        deformer_utils.import_deformer_weights(deformer, path)


@tool("Proxies From Skin")
def proxies_from_skin():
    from jeffy.geometry import proxy

    cmds.select(proxy.proxies_from_skin(_meshes()))


@tool("Capsule Proxies")
def capsule_proxies():
    from jeffy.geometry import proxy

    selection = _selection(1, "joint")
    joints = list(selection)
    for joint in selection:
        joints.extend(cmds.listRelatives(joint, allDescendents=True, type="joint") or [])
    cmds.select(proxy.capsule_proxies(joints))


# ===========================================================================
# Attributes / connections
# ===========================================================================
@tool("Add Attribute")
def add_attribute(name, attr_type="float", default=None, minimum=None, maximum=None, enum_names=None,
                  keyable=True):
    from jeffy.core import attributes

    if not name:
        raise ToolError("Enter an attribute name")
    for node in _selection():
        attributes.add_attr(node, name, attr_type, default=default, minimum=minimum, maximum=maximum,
                            enum_names=enum_names, keyable=keyable, channel_box=not keyable)


@tool("Add Separator")
def add_separator(label="settings"):
    from jeffy.core import attributes

    for node in _selection():
        attributes.add_separator(node, label)


@tool("Lock Hide")
def lock_hide(attrs, lock=True, hide=True):
    from jeffy.core import attributes

    attributes.lock_hide(_selection(), attrs, lock=lock, hide=hide)


@tool("Unlock Show")
def unlock_show(attrs):
    from jeffy.core import attributes

    attributes.unlock_show(_selection(), attrs)


@tool("Proxy Attribute")
def add_proxy_attribute():
    from jeffy.core import attributes

    selection = _selection(2)
    attrs = attributes.selected_channel_box_attrs()
    if not attrs:
        raise ToolError("Select an attribute in the channel box (on the first selected node)")
    for attr in attrs:
        for node in selection[1:]:
            attributes.add_proxy("%s.%s" % (selection[0], attr), node)


@tool("Move Attribute")
def move_attribute(direction=-1):
    from jeffy.core import attributes

    attrs = attributes.selected_channel_box_attrs()
    if not attrs:
        raise ToolError("Select user attributes in the channel box")
    ordered = list(reversed(attrs)) if direction > 0 else list(attrs)
    for node in _selection():
        for attr in ordered:
            long_name = cmds.attributeQuery(attr, node=node, longName=True)
            attributes.move_attr(node, long_name, direction)


@tool("Reset Attributes")
def reset_attributes():
    from jeffy.core import attributes

    attributes.reset(_selection())


@tool("Copy Attributes")
def copy_attributes(connect=False, move=False):
    from jeffy.core import attributes

    selection = _selection(2)
    attrs = attributes.selected_channel_box_attrs() or None
    attributes.copy_attrs(selection[0], selection[1:], attrs, connect_to_source=connect, move_connections=move)


@tool("Connect Attributes")
def connect_attributes(attrs=("translate", "rotate", "scale")):
    from jeffy.utils import connections

    connections.connect_selected(attrs)


@tool("Connect Channel Box Attributes")
def connect_channel_box_attributes():
    from jeffy.core import attributes
    from jeffy.utils import connections

    selection = _selection(2)
    attrs = attributes.selected_channel_box_attrs()
    if not attrs:
        raise ToolError("Select attributes in the channel box")
    for attr in attrs:
        connections.connect_one_to_many("%s.%s" % (selection[0], attr), selection[1:])


@tool("Break Connections")
def break_connections():
    from jeffy.core import attributes

    attrs = attributes.selected_channel_box_attrs() or attributes.TRANSFORM_ATTRS
    attributes.break_connections(_selection(), attrs)


@tool("Transfer Connections")
def transfer_connections():
    from jeffy.utils import connections

    selection = _selection(2)
    connections.transfer_connections(selection[0], selection[1])


@tool("Copy Driven Keys")
def copy_driven_keys():
    from jeffy.utils import connections

    selection = _selection(2)
    for target in selection[1:]:
        connections.copy_sdk(selection[0], target)


@tool("Mirror Driven Keys")
def mirror_driven_keys():
    from jeffy.utils import connections

    connections.mirror_sdk(_selection())


@tool("Export Driven Keys")
def export_driven_keys():
    from jeffy.utils import connections

    nodes = _selection()
    path = _file_dialog("save", "Export driven keys")
    if path:
        connections.export_sdk(nodes, path)


@tool("Import Driven Keys")
def import_driven_keys():
    from jeffy.utils import connections

    path = _file_dialog("open", "Import driven keys")
    if path:
        connections.import_sdk(path)


# ===========================================================================
# Naming
# ===========================================================================
@tool("Rename")
def rename_sequential(pattern, start=1):
    if not pattern:
        raise ToolError("Enter a name pattern (use # for numbers)")
    selection = _selection(ordered=True)
    if len(selection) == 1 and "#" not in pattern:
        cmds.rename(selection[0], naming.legalize(pattern))
        return
    naming.rename_sequential(selection, pattern if "#" in pattern else pattern + "_##", start)


@tool("Search Replace")
def search_replace(search, replace, hierarchy=False, use_regex=False):
    nodes = _selection()
    if hierarchy:
        nodes = nodes + (cmds.listRelatives(nodes, allDescendents=True, fullPath=True, type="transform") or [])
    naming.search_replace(nodes, search, replace, use_regex)


@tool("Add Prefix")
def add_prefix(prefix):
    naming.add_prefix(_selection(), prefix)


@tool("Add Suffix")
def add_suffix(suffix):
    naming.add_suffix(_selection(), suffix)


@tool("Remove Characters")
def remove_characters(first=0, last=0):
    naming.remove_characters(_selection(), first, last)


@tool("Auto Suffix")
def auto_suffix():
    naming.auto_suffix(_selection())


@tool("Fix Shape Names")
def fix_shape_names():
    naming.fix_shape_names(cmds.ls(selection=True) or None)


@tool("Mirror Names")
def mirror_names():
    naming.mirror_rename(_selection())


@tool("Make Names Unique")
def make_names_unique():
    renamed = naming.make_names_unique()
    decorators.message("Renamed %d node(s)" % len(renamed))


# ===========================================================================
# Animation helpers
# ===========================================================================
@tool("Reset Controls")
def reset_controls():
    from jeffy.utils import pose

    pose.reset()


@tool("Store Bind Pose")
def store_bind_pose():
    from jeffy.utils import pose

    pose.store_bind_pose()


@tool("Controls Bind Pose")
def controls_bind_pose():
    from jeffy.utils import pose

    pose.go_to_bind_pose()


@tool("Mirror Pose")
def mirror_pose(axis="x"):
    from jeffy.utils import pose

    pose.mirror_pose(axis=axis)


@tool("Flip Pose")
def flip_pose(axis="x"):
    from jeffy.utils import pose

    pose.flip_pose(axis=axis)


@tool("Save Pose")
def save_pose():
    from jeffy.utils import pose

    path = _file_dialog("save", "Save pose")
    if path:
        pose.save_pose(path)


@tool("Load Pose")
def load_pose(blend=1.0):
    from jeffy.utils import pose

    path = _file_dialog("open", "Load pose")
    if path:
        pose.load_pose(path, blend=blend, controls=cmds.ls(selection=True) or None)


@tool("Select All Controls")
def select_all_controls():
    from jeffy.utils import pose

    selection = cmds.ls(selection=True) or []
    namespace = naming.get_namespace(selection[0]) if selection else None
    pose.select_controls(namespace or None)


@tool("Key Controls")
def key_controls():
    from jeffy.utils import pose

    pose.key_controls()


@tool("IK/FK Switch")
def ikfk_switch(key=False):
    from jeffy.rig import ikfk

    if not ikfk.toggle_selected(key=key):
        raise ToolError("Select a control of an IK/FK limb")


@tool("Bake Selected")
def bake_selected():
    from jeffy.utils import bake

    bake.bake(_selection())


@tool("Export Skeleton")
def create_export_skeleton():
    from jeffy.utils import bake

    root = _selection(1, "joint")[0]
    mapping = bake.create_export_skeleton(root, suffix="_EXP")
    cmds.select(list(mapping.values())[0])


@tool("Bake Skeleton")
def bake_skeleton():
    from jeffy.utils import bake

    bake.bake_skeleton(_selection(1, "joint")[0])


@tool("FBX Export")
def export_fbx():
    from jeffy.utils import bake

    nodes = _selection()
    path = _file_dialog("save", "Export FBX", "FBX (*.fbx)")
    if path:
        bake.export_fbx(nodes, path)


# ===========================================================================
# Scene
# ===========================================================================
@tool("Remove Namespaces")
def remove_namespaces():
    from jeffy.utils import scene

    removed = scene.remove_namespaces()
    decorators.message("Removed %d namespace(s)" % len(removed))


@tool("Clean Scene")
def clean_scene():
    from jeffy.utils import scene

    report = scene.clean_scene()
    decorators.message(", ".join("%s: %d" % (k, len(v)) for k, v in report.items()))


@tool("Delete Unused Nodes")
def delete_unused_nodes():
    from jeffy.utils import scene

    scene.delete_unused_nodes()


@tool("Delete Empty Groups")
def delete_empty_groups():
    from jeffy.utils import scene

    selection = cmds.ls(selection=True) or [None]
    deleted = scene.delete_empty_groups(selection[0])
    decorators.message("Deleted %d group(s)" % len(deleted))


@tool("Lock Rig")
def lock_rig(lock=True):
    from jeffy.utils import scene

    scene.lock_rig(_selection(1)[0], lock=lock)


@tool("Select Hierarchy")
def select_hierarchy(node_type="joint"):
    from jeffy.utils import selection

    selection.select_hierarchy(_selection(), node_type or None)


@tool("Select Mirror")
def select_mirror(add=False):
    from jeffy.utils import selection

    if not selection.select_mirror(_selection(), add=add):
        raise ToolError("No mirrored nodes found")


@tool("Scene Report")
def scene_report():
    from jeffy.utils import scene

    report = scene.scene_report()
    text = "\n".join("%-14s %s" % (k, v) for k, v in sorted(report.items()))
    print(text)
    decorators.message("Scene report printed in the Script Editor")
    return report


# ===========================================================================
# Auto-rig
# ===========================================================================
@tool("Create Template")
def create_template(name="biped", scale=1.0):
    from jeffy.autorig import templates

    roots = templates.create(name, scale=scale)
    cmds.select(clear=True)
    return roots


@tool("Add Component")
def add_component(component_type, name=None, side=None, parent_output=""):
    from jeffy.autorig import builder

    root = builder.add_component(component_type, name=name, side=side, parent_output=parent_output)
    cmds.select(root)
    return root


@tool("Mirror Guides")
def mirror_guides():
    from jeffy.autorig import guides

    roots = {guides.root_of(n) for n in cmds.ls(selection=True) or []}
    roots.discard(None)
    if roots:
        for root in roots:
            guides.mirror_guide(root)
    else:
        guides.mirror_all("L")


@tool("Set Guide Parent")
def set_guide_parent(output=""):
    from jeffy.autorig import guides

    roots = {guides.root_of(n) for n in cmds.ls(selection=True) or []}
    roots.discard(None)
    if not roots:
        raise ToolError("Select guides")
    for root in roots:
        guides.set_parent_output(root, output)


@tool("Build Rig")
def build_rig(name="character"):
    from jeffy.autorig import builder

    structure = builder.build(name)
    cmds.select(structure.global_ctl)
    return structure


@tool("Delete Rig")
def delete_rig():
    from jeffy.autorig import builder

    builder.delete_rig()


@tool("Rebuild Rig")
def rebuild_rig(name="character"):
    from jeffy.autorig import builder

    builder.rebuild(name)


@tool("Restore Guides")
def restore_guides():
    from jeffy.autorig import builder

    builder.restore_guides()


@tool("Save Guides")
def save_guides():
    from jeffy.autorig import guides

    path = _file_dialog("save", "Save guide template")
    if path:
        guides.save_template(path)


@tool("Load Guides")
def load_guides(replace=True):
    from jeffy.autorig import guides

    path = _file_dialog("open", "Load guide template")
    if path:
        guides.load_template(path, replace=replace)


@tool("Toggle Guides")
def toggle_guides():
    from jeffy.autorig import guides

    if cmds.objExists(guides.GUIDES_GROUP):
        guides.set_guides_visible(not cmds.getAttr(guides.GUIDES_GROUP + ".visibility"))


# ===========================================================================
# Checks
# ===========================================================================
@tool("Rig Check")
def run_checks():
    from jeffy.utils import checks

    text = checks.report()
    print(text)
    decorators.message("Rig check finished - see the Script Editor")
    return text
