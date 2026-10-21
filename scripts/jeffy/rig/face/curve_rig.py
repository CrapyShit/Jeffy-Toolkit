"""Curve rigs for lips, brows, eyelids, cheeks, nasolabial folds...

::

    from jeffy.rig.face import curve_rig
    curve_rig.build_curve_rig(edges=cmds.ls(sl=True, flatten=True), name="upperLip", num_controls=5)
    curve_rig.build_curve_rig(edges=lid_edges, name="upperLid", side="L", center="L_eye_JNT")

* A *high* curve goes through every vertex of the edge loop; one joint
  follows each vertex (skin the mesh to them).
* A *low* curve with a few controls deforms the high curve through a wire.
* With a ``center`` (eyelids: the eye joint / pivot) each joint is the tip of
  a small chain from the centre, aimed at the curve, so the lid slides
  around the eyeball instead of going through it.
"""

from maya import cmds

from jeffy.controls.control import Control
from jeffy.core import mathlib, naming, nodes, transform
from jeffy.geometry import curves
from jeffy.joints import tools as joint_tools
from jeffy.rig import common
from jeffy.rig.face import common as face_common


def ordered_points(edges):
    """World positions of the vertices of an edge loop, in loop order."""
    curve = curves.curve_from_edges(edges, name="faceTmp_CRV", degree=1)
    points = curves.get_cv_positions(curve)
    cmds.delete(curve)
    cleaned = []
    for point in points:
        if not cleaned or mathlib.distance(point, cleaned[-1]) > 1e-5:
            cleaned.append(tuple(point))
    if len(cleaned) > 3 and mathlib.distance(cleaned[0], cleaned[-1]) < 1e-5:  # closed loop
        cleaned.pop()
    return cleaned


def build_curve_rig(edges=None, points=None, name="lip", side=None, num_controls=5, center=None, up_object=None,
                    control_parent=None, joint_parent=None, systems_parent=None, size=0.3, shape="circle",
                    color_value=None):
    """Build the rig from an edge loop (``edges``) or world ``points``.

    :param center: node at the rotation centre (eyelids); joints aim from it
    :param up_object: up node for the aimed joints (default: a locator above
        the centre)
    :param control_parent: what the controls and curves follow (head)
    :param joint_parent: parent of the joints (head joint); default a group
    :returns: dict with ``main``, ``controls``, ``joints`` (the skin joints),
        ``high``, ``low``, ``wire`` and ``group``
    """
    points = [tuple(p) for p in (points if points is not None else ordered_points(edges))]
    if len(points) < 3:
        raise ValueError("Select an edge loop of at least 3 vertices")
    if points[0][0] > points[-1][0]:  # always build from -X to +X (right to left side)
        points.reverse()
    num_controls = max(2, min(int(num_controls), len(points)))

    # groups --------------------------------------------------------------------
    systems = common.create_group(naming.compose(name + "Rig", side, "group"), parent=systems_parent,
                                  visible=False)
    main = Control.create(name + "Main", side=side, shape="square", size=size * 2.0, axis="z",
                          parent=control_parent, position=mathlib.centroid(points), offsets=("zero",),
                          color_value=color_value)
    curve_group = common.create_group(naming.compose(name + "Curves", side, "group"), parent=control_parent,
                                      visible=False)
    cmds.xform(curve_group, objectSpace=True, translation=(0, 0, 0), rotation=(0, 0, 0))

    # curves --------------------------------------------------------------------
    high = curves.curve_from_points(points, name=naming.compose(name + "High", side, "curve"), degree=1,
                                    through=False)
    high = cmds.parent(high, curve_group)[0]
    samples = curves.positions_along(high, num_controls)
    low = curves.curve_from_points(samples, name=naming.compose(name + "Low", side, "curve"),
                                   degree=min(3, num_controls - 1), through=False)
    low = cmds.parent(low, curve_group)[0]
    low_shape = cmds.listRelatives(low, shapes=True)[0]

    # controls drive the low curve CVs (in the curve group's space) ------------
    controls = []
    for i, position in enumerate(samples):
        ctl = Control.create("%s%02d" % (name, i + 1), side=side, shape=shape, size=size, axis="z",
                             parent=main.node, position=position, offsets=("zero", "sdk"),
                             color_value=color_value, secondary=True)
        ctl.set_parent_tag(main.node)
        local = nodes.mult_matrix([ctl.node + ".worldMatrix[0]", curve_group + ".worldInverseMatrix[0]"],
                                  name=naming.compose("%s%02dCv" % (name, i + 1), side, "mult_matrix"))
        decompose = nodes.decompose_matrix(local, name=naming.compose("%s%02dCv" % (name, i + 1), side,
                                                                      "decompose_matrix"))
        cmds.connectAttr(decompose + ".outputTranslate", "%s.controlPoints[%d]" % (low_shape, i), force=True)
        controls.append(ctl)

    wire, base = face_common.wire(high, low, name=face_common.label(name, side, "WIRE"))
    if base and cmds.listRelatives(base, parent=True) != [curve_group]:
        cmds.parent(base, curve_group)

    # joints --------------------------------------------------------------------
    if joint_parent is None:
        joint_parent = common.create_group(naming.compose(name + "Joints", side, "group"), parent=systems_parent)
    up = up_object
    if center and not up:
        center_pos = transform.get_position(center)
        up = common.create_locator(naming.compose(name + "Up", side, "locator"), parent=control_parent,
                                   position=(center_pos[0], center_pos[1] + size * 10.0, center_pos[2]))
    joints = []
    count = len(points)
    for i, point in enumerate(points):
        fraction = i / float(count - 1)
        label = "%s%02d" % (name, i + 1)
        if center:
            chain = joint_tools.create_chain([transform.get_position(center), point], name=label + "Base",
                                             side=side, parent=joint_parent)
            base_joint, tip = chain
            tip = cmds.rename(tip, naming.unique_name(naming.compose(label, side, "joint")))
            target = common.create_locator(naming.compose(label + "Aim", side, "locator"), parent=systems)
            curves.attach_to_curve(target, high, param=fraction, percent=True)
            cmds.aimConstraint(target, base_joint, maintainOffset=True, aimVector=(1, 0, 0), upVector=(0, 1, 0),
                               worldUpType="object", worldUpObject=up)
            joints.append(naming.short_name(tip))
        else:
            joint = joint_tools.create_joint(naming.compose(label, side, "joint"), parent=joint_parent,
                                             position=point)
            curves.attach_to_curve(joint, high, param=fraction, percent=True)
            joints.append(joint)

    result = {"main": main, "controls": controls, "joints": joints, "high": high, "low": low, "wire": wire,
              "group": systems, "curves": curve_group}
    face_common.store(main.node, {"high": high, "low": low, "curves": curve_group, "joints": joints,
                                  "controls": [c.node for c in controls]})
    return result
