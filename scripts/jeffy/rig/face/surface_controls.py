"""Controls that ride on the face mesh and drive a joint.

::

    from jeffy.rig.face import surface_controls
    surface_controls.build_surface_control("head_GEO", (1.2, 15.3, 2.0), "cheek", side="L")

The control sits on the mesh (uvPin or follicle), so it follows the skin when
the jaw opens, the cheek puffs, a blendshape fires... It drives its own joint
(skin the mesh to it). An inverse group under the control cancels the double
transform: the control moves the joint, the joint moves the skin, the skin
moves the control's rivet, and the inverse group takes that motion back out,
so the control never runs away from the cursor.
"""

from maya import cmds

from jeffy.controls.control import Control
from jeffy.core import mathlib, matrix, naming, nodes
from jeffy.joints import tools as joint_tools
from jeffy.rig import attach, common
from jeffy.rig.face import common as face_common


def build_surface_control(mesh, position, name="face", side=None, joint=None, joint_parent=None,
                          control_parent=None, size=0.3, shape="sphere", method="uvPin", color_value=None):
    """One on-face control driving ``joint`` (created when None).

    :param mesh: the face mesh the control rides on (usually the skinned
        head, so the control follows the skin)
    :param position: world position (snapped to the mesh)
    :param joint_parent: parent of a new joint (e.g. the head joint)
    :param control_parent: parent of the rivet group (e.g. a head control
        group); the rivet keeps its own position on the mesh
    :returns: dict with ``control``, ``joint``, ``pin`` and ``rivet``
    """
    pin = common.create_group(naming.compose(name + "Pin", side, "group"), parent=control_parent)
    cmds.xform(pin, worldSpace=True, translation=position)
    rivet = attach.attach_to_geometry(pin, mesh, method=method, maintain_offset=True,
                                      name=face_common.label(name, side))

    ctl = Control.create(name, side=side, shape=shape, size=size, axis="z", parent=pin,
                         offsets=("zero", "offset"), color_value=color_value)
    cmds.xform(ctl.zero, objectSpace=True, translation=(0, 0, 0), rotation=(0, 0, 0))
    inverse = ctl.last_offset
    # cancel the double transform: the inverse group undoes the control's own
    # motion, so the control only moves with the skin (once)
    cmds.connectAttr(ctl.node + ".inverseMatrix", inverse + ".offsetParentMatrix", force=True)

    if joint is None:
        joint = joint_tools.create_joint(naming.compose(name, side, "joint"), parent=joint_parent)
        cmds.xform(joint, worldSpace=True, translation=position)
    drive_joint(ctl.node, joint)
    return {"control": ctl, "joint": joint, "pin": pin, "rivet": rivet}


def drive_joint(control, joint):
    """Move ``joint`` the way ``control`` moves in its own space.

    ``joint.offsetParentMatrix = R^-1 * control.matrix * R`` where ``R`` is
    the control's rest frame relative to the joint's parent, so the joint
    keeps its rest pose and moves along the control's axes.
    """
    if cmds.listConnections(joint + ".offsetParentMatrix", source=True, destination=False):
        raise ValueError("%s is already driven through its offsetParentMatrix" % joint)
    control_world = matrix.get_world_matrix(control)
    parent_inverse = cmds.getAttr(joint + ".parentInverseMatrix[0]")
    rest = mathlib.mult(control_world, parent_inverse)
    base = naming.short_name(joint)
    node = nodes.create("multMatrix", naming.compose(base + "Drive", None, "mult_matrix"))
    matrix.set_matrix_attr(node + ".matrixIn[0]", mathlib.inverse(rest))
    cmds.connectAttr(control + ".matrix", node + ".matrixIn[1]")
    matrix.set_matrix_attr(node + ".matrixIn[2]", rest)
    cmds.connectAttr(node + ".matrixSum", joint + ".offsetParentMatrix", force=True)
    return node
