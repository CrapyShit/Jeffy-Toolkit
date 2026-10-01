"""Dynamic (overlap) chains driven by an nHair simulation.

The animator FK chain drives a *start curve*; nHair simulates an *output
curve* that drives a spline IK *dynamic chain*. The bind joints blend between
the FK and the dynamic chain with a ``dynamics`` attribute::

    from jeffy.rig import dynamics
    dynamics.create_dynamic_chain(fk_joints, bind_joints=bind, name="tail",
                                  side="C", attr_holder="C_tail01_CTL")

The nodes are created and wired manually so nothing depends on the current
selection or on MEL procedures.
"""

from maya import cmds

from jeffy.core import attributes, naming, nodes
from jeffy.geometry import curves
from jeffy.joints import tools as joint_tools
from jeffy.rig import common


def _get_nucleus(name="jeffy_nucleus"):
    existing = cmds.ls(type="nucleus") or []
    if existing:
        return existing[0]
    nucleus = cmds.createNode("nucleus", name=naming.unique_name(name), skipSelect=True)
    cmds.connectAttr("time1.outTime", nucleus + ".currentTime")
    return nucleus


def _next_index(plug):
    indices = cmds.getAttr(plug, multiIndices=True) or []
    return (max(indices) + 1) if indices else 0


def create_dynamic_chain(driver_joints, bind_joints=None, name="dynamic", side=None, attr_holder=None,
                         systems_parent=None, point_lock="base"):
    """Create an nHair driven dynamic chain.

    :param driver_joints: chain posed by the animator (e.g. FK driven)
    :param bind_joints: optional chain to blend between driver and dynamics
    :param attr_holder: node receiving the dynamic attributes
    :param point_lock: ``base``, ``tip``, ``both`` or ``none``
    :returns: dict with ``dynamic_joints``, ``hair_system``, ``follicle``,
        ``nucleus``, ``start_curve``, ``output_curve`` and ``group``
    """
    lock_value = {"none": 0, "base": 1, "tip": 2, "both": 3}[point_lock]
    group = common.create_group(naming.compose(name + "Dynamics", side, "group"), parent=systems_parent,
                                visible=False)
    # simulation nodes work in world space - never inherit the rig transforms
    cmds.setAttr(group + ".inheritsTransform", 0)

    # start curve skinned to the driver chain ----------------------------------
    start_curve = curves.curve_from_joints(driver_joints, name=naming.compose(name + "Start", side, "curve"),
                                           degree=3)
    cmds.skinCluster(driver_joints + [start_curve], toSelectedBones=True, maximumInfluences=2,
                     name=naming.compose(name + "Start", side, "skin_cluster"))

    # follicle -----------------------------------------------------------------
    follicle_shape = cmds.createNode("follicle", name=naming.unique_name(naming.compose(name, side, "follicle")
                                                                         + "Shape"), skipSelect=True)
    follicle = cmds.listRelatives(follicle_shape, parent=True)[0]
    follicle = cmds.rename(follicle, naming.unique_name(naming.compose(name, side, "follicle")))
    follicle_shape = cmds.listRelatives(follicle, shapes=True)[0]
    follicle = cmds.parent(follicle, group)[0]
    start_curve = cmds.parent(start_curve, follicle)[0]
    start_shape = cmds.listRelatives(start_curve, shapes=True, noIntermediate=True)[0]
    cmds.connectAttr(start_shape + ".local", follicle_shape + ".startPosition")
    cmds.connectAttr(start_curve + ".worldMatrix[0]", follicle_shape + ".startPositionMatrix")
    cmds.setAttr(follicle_shape + ".restPose", 1)
    cmds.setAttr(follicle_shape + ".startDirection", 1)
    cmds.setAttr(follicle_shape + ".pointLock", lock_value)
    cmds.setAttr(follicle_shape + ".degree", 3)

    # hair system + nucleus ------------------------------------------------------
    hair_shape = cmds.createNode("hairSystem", name=naming.unique_name(naming.compose(name, side, "utility")
                                                                       + "_hairSystemShape"), skipSelect=True)
    hair = cmds.listRelatives(hair_shape, parent=True)[0]
    hair = cmds.rename(hair, naming.unique_name(naming.compose(name + "HairSystem", side, "utility")))
    hair_shape = cmds.listRelatives(hair, shapes=True)[0]
    hair = cmds.parent(hair, group)[0]
    nucleus = _get_nucleus()
    cmds.connectAttr("time1.outTime", hair_shape + ".currentTime")
    index = _next_index(nucleus + ".inputActive")
    cmds.connectAttr(hair_shape + ".currentState", "%s.inputActive[%d]" % (nucleus, index))
    cmds.connectAttr(hair_shape + ".startState", "%s.inputActiveStart[%d]" % (nucleus, index))
    cmds.connectAttr("%s.outputObjects[%d]" % (nucleus, index), hair_shape + ".nextState")
    cmds.connectAttr(nucleus + ".startFrame", hair_shape + ".startFrame")
    cmds.setAttr(hair_shape + ".active", 1)
    cmds.connectAttr(follicle_shape + ".outHair", hair_shape + ".inputHair[0]")
    cmds.connectAttr(hair_shape + ".outputHair[0]", follicle_shape + ".currentPosition")

    # output curve ----------------------------------------------------------------
    out_shape = cmds.createNode("nurbsCurve", name=naming.unique_name(naming.compose(name + "Output", side,
                                                                                     "curve") + "Shape"),
                                skipSelect=True)
    out_curve = cmds.listRelatives(out_shape, parent=True)[0]
    out_curve = cmds.rename(out_curve, naming.unique_name(naming.compose(name + "Output", side, "curve")))
    out_shape = cmds.listRelatives(out_curve, shapes=True)[0]
    out_curve = cmds.parent(out_curve, group)[0]
    cmds.connectAttr(follicle_shape + ".outCurve", out_shape + ".create")

    # dynamic joint chain on the output curve ----------------------------------
    dyn_joints = joint_tools.duplicate_chain(driver_joints[0], driver_joints[-1], search="_JNT",
                                             replace="_DYN_JNT", parent=group)
    handle, effector = cmds.ikHandle(startJoint=dyn_joints[0], endEffector=dyn_joints[-1],
                                     solver="ikSplineSolver", curve=out_curve, createCurve=False,
                                     parentCurve=False, simplifyCurve=False,
                                     name=naming.compose(name + "Dyn", side, "ik_handle"))
    cmds.rename(effector, naming.compose(name + "Dyn", side, "effector"))
    cmds.parent(handle, group)
    parent = cmds.listRelatives(driver_joints[0], parent=True)
    if parent:
        cmds.parentConstraint(parent[0], dyn_joints[0], maintainOffset=True)

    # attributes -----------------------------------------------------------------
    holder = attr_holder or hair
    attributes.add_separator(holder, "dynamics")
    blend = attributes.add_attr(holder, "dynamics", "float", default=1.0 if bind_joints else 0.0, minimum=0.0,
                                maximum=1.0)
    enable = attributes.add_attr(holder, "simulate", "bool", default=True)
    cmds.connectAttr(enable, nucleus + ".enable", force=True)
    for attr, default, target in (
        ("startCurveAttract", 0.1, "startCurveAttract"),
        ("stiffness", 0.15, "stiffness"),
        ("damp", 0.1, "damp"),
        ("drag", 0.05, "drag"),
        ("mass", 1.0, "mass"),
    ):
        plug = attributes.add_attr(holder, "dyn" + attr[0].upper() + attr[1:], "float", default=default,
                                   minimum=0.0)
        cmds.connectAttr(plug, "%s.%s" % (hair_shape, target), force=True)
    start = attributes.add_attr(holder, "dynStartFrame", "float", default=cmds.playbackOptions(query=True,
                                                                                                 minTime=True))
    cmds.connectAttr(start, nucleus + ".startFrame", force=True)

    if bind_joints:
        reverse = nodes.reverse(blend)
        for bind, drv, dyn in zip(bind_joints, driver_joints, dyn_joints):
            constraint = cmds.parentConstraint(drv, dyn, bind, maintainOffset=False)[0]
            cmds.setAttr(constraint + ".interpType", 2)
            weights = common.constraint_weight_plugs(constraint)
            cmds.connectAttr(reverse, weights[0])
            cmds.connectAttr(blend, weights[1])

    return {
        "dynamic_joints": dyn_joints,
        "hair_system": hair,
        "follicle": follicle,
        "nucleus": nucleus,
        "start_curve": start_curve,
        "output_curve": out_curve,
        "handle": handle,
        "group": group,
    }
