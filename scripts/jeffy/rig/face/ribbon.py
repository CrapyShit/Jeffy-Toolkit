"""Face ribbons for lips, brows, cheek lines, nasolabial folds...

A NURBS ribbon follows the edge loop; one follicle joint per vertex rides on
it (skin the mesh to them) and a few controls, skinned to the ribbon, shape
it. Compared with a curve rig the joints also get the ribbon's orientation,
so rotating / twisting a control rolls the lip or brow, and the deformation
stays smooth and fluid between the controls.

::

    from jeffy.rig.face import ribbon
    ribbon.build_face_ribbon(edges=cmds.ls(sl=True, flatten=True), name="upperLip", num_controls=5)
"""

from maya import cmds

from jeffy.controls.control import Control
from jeffy.core import mathlib
from jeffy.rig import ribbon as ribbon_rig
from jeffy.rig.face import common as face_common
from jeffy.rig.face import curve_rig


def build_face_ribbon(edges=None, points=None, name="lip", side=None, num_controls=5, num_joints=None,
                      width=None, up_vector=(0.0, 1.0, 0.0), control_parent=None, systems_parent=None,
                      size=0.3, color_value=None):
    """Build a face ribbon from an edge loop (``edges``) or world ``points``.

    :param num_joints: skin joints along the ribbon (default: one per vertex)
    :param width: ribbon width (default 10% of its length)
    :param up_vector: world direction the ribbon width spreads along (Y for
        lips and brows: the ribbon then faces forward)
    :param control_parent: what the controls follow (a head follow group)
    :returns: dict with ``main``, ``controls``, ``joints``, ``surface``,
        ``follicles`` and ``group``
    """
    points = [tuple(p) for p in (points if points is not None else curve_rig.ordered_points(edges))]
    if len(points) < 3:
        raise ValueError("Select an edge loop of at least 3 vertices")
    if points[0][0] > points[-1][0]:  # always -X to +X
        points.reverse()
    length = sum(mathlib.distance(a, b) for a, b in zip(points, points[1:]))
    main = Control.create(name + "Main", side=side, shape="square", size=size * 2.0, axis="z",
                          parent=control_parent, position=mathlib.centroid(points), offsets=("zero",),
                          color_value=color_value)
    result = ribbon_rig.build_ribbon(points, name=name, side=side, num_joints=num_joints or len(points),
                                     num_controls=max(2, int(num_controls)), width=width or length * 0.1,
                                     up_vector=up_vector, control_parent=main.node, systems_parent=systems_parent,
                                     shape="circle", size=size, axis="z", scale_node=control_parent,
                                     color_value=color_value)
    for ctl in result["controls"]:
        ctl.set_parent_tag(main.node)
    result["main"] = main
    face_common.store(main.node, {"kind": "ribbon", "surface": result["surface"], "joints": result["joints"],
                                  "controls": [c.node for c in result["controls"]]})
    return result


def corner_controls(main):
    """First and last controls of a face ribbon or curve rig (the corners)."""
    _main, data = face_common.find_rig(main)
    if not data or not data.get("controls"):
        raise ValueError("%s is not the Main control of a face ribbon / curve rig" % main)
    controls = data["controls"]
    return [c for c in (controls[0], controls[-1]) if cmds.objExists(c)]
