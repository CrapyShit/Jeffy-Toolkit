"""Course style ribbon limb (videos 6, 7 and 8).

Built between three joints (shoulder/elbow/wrist, hip/knee/ankle, or the spine's
lower/middle/upper joints)::

    <name>Deformers_GRP
      <name>Ribbon_GRP      surface, follicles + bind joints, sine/twist targets and handles
      root offset   <- parent  start joint      > root joint > upper aim point
      upper offset  <- point   root + middle joints
        upper aim   <- aim     middle joint (+X, object rotation up = upper aim point)
          upper control > upper joint
      middle offset <- parent  middle joint     > middle control > middle joint > lower aim point
      lower offset  <- point   end + middle joints
        lower aim   <- aim     middle joint (-X, object rotation up = lower aim point)
          lower control > lower joint
      end offset    <- point (or parent) end joint > end joint

* The surface (degree 3, 8 spans along the limb, isoparms inserted on each
  side of the middle for a crease) is skinned to the five control joints.
* Nine follicles carry the joints the mesh is skinned to.
* Two duplicates of the surface (``twist`` and ``sine``) are blendshape targets
  placed in front of the skin; a nonLinear twist and sine deform them. The
  holder control gets ``SineBlend``, ``SineAmplitude``, ``SineWavelength``,
  ``SineOrientation``, ``SineOffset``, ``TwistBlend``, ``TwistOffset`` and
  ``Toon_Controls`` (shows the upper/middle/lower controls).
* :func:`add_crease_fix` adds the elbow/knee fix joints of video 8.
"""

from maya import cmds

from jeffy.core import attributes, mathlib, matrix, naming, transform
from jeffy.geometry import surfaces
from jeffy.joints import orient
from jeffy.joints import tools as joint_tools
from jeffy.rig import attach
from jeffy.rig.flexible import common

FRONT = (0.0, 0.0, 1.0)


def _joint(name, side, parent, radius=None):
    joint = joint_tools.create_joint(naming.compose(name, side, "joint"), parent=parent, radius=radius)
    cmds.setAttr(joint + ".jointOrient", 0, 0, 0)
    for attr in ("translate", "rotate"):
        cmds.setAttr("%s.%s" % (joint, attr), 0, 0, 0)
    return joint


def _surface(points, name, side, width, spans, crease_offset):
    direction = mathlib.normalize(mathlib.sub(points[-1], points[0]))
    width_dir = mathlib.cross(direction, FRONT)
    if mathlib.length(width_dir) < 1e-4:  # limb pointing at the camera
        width_dir = mathlib.cross(direction, (0.0, 1.0, 0.0))
    surface = surfaces.ribbon_from_points(points, width=width, up_vector=mathlib.normalize(width_dir),
                                          name=naming.compose(name, side, "surface"), spans=spans, degree=3)
    if crease_offset:
        cmds.insertKnotSurface(surface, parameter=[0.5 - crease_offset, 0.5 + crease_offset], direction=0,
                               numberOfKnots=1, addKnots=True, constructionHistory=False, replaceOriginal=True)
    return surface


def _deformer_handle(handle, start, end, length):
    """Handle Y axis along the limb, scaled to half its length, at its centre."""
    y_axis = mathlib.normalize(mathlib.sub(end, start))
    x_axis = mathlib.cross(y_axis, FRONT)
    if mathlib.length(x_axis) < 1e-4:
        x_axis = mathlib.cross(y_axis, (0.0, 1.0, 0.0))
    x_axis = mathlib.normalize(x_axis)
    z_axis = mathlib.normalize(mathlib.cross(x_axis, y_axis))
    half = length / 2.0
    world = mathlib.from_axes(mathlib.scale(x_axis, half), mathlib.scale(y_axis, half), mathlib.scale(z_axis, half),
                              mathlib.midpoint(start, end))
    matrix.set_world_matrix(handle, world)


def build_ribbon_limb(start, middle, end, name="limb", side=None, holder=None, systems_parent=None, size=1.0,
                      joints=9, width_ratio=0.222, crease_offset=0.007, end_follow="point", deformers=True,
                      crease_fix=False, visibility_plug=None):
    """Build the course ribbon between ``start``, ``middle`` and ``end`` joints.

    :param holder: control receiving the deform / toon attributes (a new
        settings control is created at the middle when ``None``)
    :param joints: follicle joints (the course uses 9)
    :param crease_offset: U distance of the extra isoparms around the middle
        (0 = none)
    :param end_follow: ``point`` (arms in the course) or ``parent`` (legs)
    :param visibility_plug: e.g. the master's ``Deformers`` switch
    :returns: dict with ``surface``, ``follicles``, ``bind_joints``,
        ``control_joints`` (root, upper, middle, lower, end), ``controls``
        (upper, middle, lower), ``offsets``, ``holder``, ``group``...
    """
    start, middle, end = (naming.short_name(n) for n in (start, middle, end))
    p0, p1, p2 = (transform.get_position(n) for n in (start, middle, end))
    length = mathlib.distance(p0, p1) + mathlib.distance(p1, p2)
    half_spans = 4
    points = [mathlib.lerp_vector(p0, p1, t) for t in mathlib.distribute(half_spans + 1)][:-1] + \
             [mathlib.lerp_vector(p1, p2, t) for t in mathlib.distribute(half_spans + 1)]

    top = common.group(name + "Deformers", side, parent=systems_parent)
    ribbon_grp = common.group(name + "Ribbon", side, parent=top)
    if visibility_plug:
        cmds.connectAttr(visibility_plug, ribbon_grp + ".visibility")
    surface = _surface(points, name + "Ribbon", side, length * width_ratio, half_spans * 2, crease_offset)
    surface = cmds.parent(surface, ribbon_grp)[0]

    # follicles + bind joints ----------------------------------------------------
    follicle_grp = common.group(name + "Follicles", side, parent=ribbon_grp)
    follicles = attach.follicles_along_surface(surface, joints, name=naming.compose(name, side, ""),
                                               parent=follicle_grp)
    bind_joints = []
    for index, follicle in enumerate(follicles):
        joint = _joint("%sBind%02d" % (name, index + 1), side, follicle, radius=size * 0.3)
        bind_joints.append(joint)

    # sine / twist targets (duplicated before the skin) ---------------------------
    targets = {}
    if deformers:
        for key in ("twist", "sine"):
            dup = cmds.duplicate(surface, name=naming.unique_name(naming.compose(name + key.title(), side,
                                                                                  "surface")))[0]
            cmds.setAttr(dup + ".visibility", 0)
            targets[key] = dup

    # control joints -------------------------------------------------------------
    root_off = common.group(name + "RootOffset", side, parent=top, match=start)
    cmds.parentConstraint(start, root_off, maintainOffset=False)
    root_jnt = _joint(name + "Root", side, root_off, radius=size * 0.5)
    upper_point = common.group(name + "UpperAimPoint", side, parent=root_jnt)
    cmds.xform(upper_point, worldSpace=True, translation=p1)

    mid_off = common.group(name + "MiddleOffset", side, parent=top, match=middle)
    cmds.parentConstraint(middle, mid_off, maintainOffset=False)
    mid_ctl = common.control(name + "Middle", side, "circle", size, "x", parent=mid_off,
                             lock=("s", "v"))
    mid_jnt = _joint(name + "Middle", side, mid_ctl.node, radius=size * 0.5)
    lower_point = common.group(name + "LowerAimPoint", side, parent=mid_jnt)
    cmds.xform(lower_point, worldSpace=True, translation=p2)

    end_off = common.group(name + "EndOffset", side, parent=top, match=end)
    (cmds.parentConstraint if end_follow == "parent" else cmds.pointConstraint)(end, end_off, maintainOffset=False)
    end_jnt = _joint(name + "End", side, end_off, radius=size * 0.5)

    def between(label, target_a, aim_vector, up_point):
        offset = common.group(name + label + "Offset", side, parent=top, match=start)
        cmds.pointConstraint(target_a, mid_jnt, offset, maintainOffset=False)
        aim = common.group(name + label + "Aim", side, parent=offset)
        cmds.aimConstraint(mid_jnt, aim, aimVector=aim_vector, upVector=(0, 1, 0), worldUpType="objectrotation",
                           worldUpVector=(0, 1, 0), worldUpObject=up_point, maintainOffset=False)
        ctl = common.control(name + label, side, "circle", size * 0.8, "x", parent=aim, lock=("s", "v"))
        jnt = _joint(name + label, side, ctl.node, radius=size * 0.5)
        return offset, aim, ctl, jnt

    upper_off, upper_aim, upper_ctl, upper_jnt = between("Upper", root_jnt, (1, 0, 0), upper_point)
    lower_off, lower_aim, lower_ctl, lower_jnt = between("Lower", end_jnt, (-1, 0, 0), lower_point)
    control_joints = [root_jnt, upper_jnt, mid_jnt, lower_jnt, end_jnt]

    # skin + blendshape layer ----------------------------------------------------------
    skin = cmds.skinCluster(control_joints + [surface], toSelectedBones=True, maximumInfluences=2,
                            dropoffRate=4.0, name=naming.unique_name(naming.compose(name + "Ribbon", side,
                                                                                     "skin_cluster")))[0]
    holder = holder or common.control(name + "Settings", side, "gear", size * 0.4, "y", parent=top,
                                      position=mathlib.add(p1, (0.0, size * 2.0, 0.0)),
                                      lock=("t", "r", "s", "v")).node
    result = {"surface": surface, "follicles": follicles, "bind_joints": bind_joints,
              "control_joints": control_joints, "controls": [upper_ctl, mid_ctl, lower_ctl],
              "offsets": [root_off, upper_off, mid_off, lower_off, end_off], "aims": [upper_aim, lower_aim],
              "aim_points": [upper_point, lower_point], "skin": skin, "holder": holder, "group": top,
              "ribbon_group": ribbon_grp, "length": length, "targets": targets}
    if deformers:
        result.update(_deform_layer(result, name, side, p0, p2))
    attributes.add_separator(holder, "toon")
    toon = attributes.add_attr(holder, "Toon_Controls", "bool", default=False)
    for offset in (upper_off, mid_off, lower_off):
        cmds.connectAttr(toon, offset + ".visibility")
    if visibility_plug:
        for joint in control_joints:
            cmds.connectAttr(visibility_plug, joint + ".visibility")
    common.lock_free([upper_off, mid_off, lower_off, root_off, end_off], ("r", "s"))
    common.store(top, "ribbon", [surface, skin, holder, start, middle, end])
    common.store(top, "controlJoints", control_joints)
    common.store(top, "bindJoints", bind_joints)
    common.store(top, "controls", [upper_ctl.node, mid_ctl.node, lower_ctl.node])
    if crease_fix:
        result["crease_fix"] = add_crease_fix(result)
    return result


def _deform_layer(result, name, side, p0, p2):
    holder, surface, targets = result["holder"], result["surface"], result["targets"]
    blend = cmds.blendShape(targets["twist"], targets["sine"], surface, frontOfChain=True,
                            name=naming.unique_name(naming.compose(name + "Ribbon", side, "blendshape")))[0]
    sine, sine_handle = cmds.nonLinear(targets["sine"], type="sine",
                                       name=naming.unique_name(naming.compose(name + "Sine", side, "utility")))
    twist, twist_handle = cmds.nonLinear(targets["twist"], type="twist",
                                         name=naming.unique_name(naming.compose(name + "Twist", side, "utility")))
    handles = []
    for handle in (sine_handle, twist_handle):
        handle = cmds.parent(handle, result["ribbon_group"])[0]
        _deformer_handle(handle, p0, p2, result["length"])
        cmds.setAttr(handle + ".visibility", 0)
        handles.append(handle)
    sine_handle, twist_handle = handles
    cmds.setAttr(sine + ".dropoff", 1)
    cmds.setAttr(sine + ".lowBound", -1)
    cmds.setAttr(sine + ".highBound", 1)
    cmds.setAttr(twist + ".lowBound", -1)
    cmds.setAttr(twist + ".highBound", 1)

    attributes.add_separator(holder, "deform")
    plugs = {}
    for attr, kwargs in (("SineBlend", {"minimum": 0.0, "maximum": 1.0}), ("SineAmplitude", {"default": 1.0}),
                         ("SineWavelength", {"default": 5.0, "minimum": 0.001}), ("SineOrientation", {}),
                         ("SineOffset", {}), ("TwistBlend", {"minimum": 0.0, "maximum": 1.0}), ("TwistOffset", {})):
        plugs[attr] = attributes.add_attr(holder, attr, "float", **kwargs)
    cmds.connectAttr(plugs["TwistBlend"], blend + ".weight[0]")
    cmds.connectAttr(plugs["SineBlend"], blend + ".weight[1]")
    cmds.connectAttr(plugs["SineAmplitude"], sine + ".amplitude")
    cmds.connectAttr(plugs["SineWavelength"], sine + ".wavelength")
    cmds.connectAttr(plugs["SineOffset"], sine + ".offset")
    cmds.connectAttr(plugs["SineOrientation"], sine_handle + ".rotateY")
    cmds.connectAttr(plugs["TwistOffset"], twist + ".endAngle")
    return {"blendshape": blend, "sine": sine, "sine_handle": sine_handle, "twist": twist,
            "twist_handle": twist_handle}


def find_ribbon(node):
    owner = common.find_meta_owner(node, "ribbon")
    if owner:
        return naming.short_name(owner)
    for candidate in cmds.ls("*.%sribbon" % common.META_PREFIX, objectsOnly=True) or []:
        if node in (common.fetch(candidate, "ribbon") + common.fetch(candidate, "controls")):
            return candidate
    return None


def add_crease_fix(ribbon):
    """Elbow/knee crease fix of video 8.

    * An elbow fix joint under the middle control with an end joint toward the
      start; a single chain IK handle parented under the root control joint
      keeps it pointing at the shoulder whatever the controls do.
    * A wrist fix joint under the end offset pointing back at the middle, its
      IK handle under the middle control joint.
    * Both fix joints are added to the ribbon skin with zero weight (envelope
      off while adding, weights locked) - paint them around the crease.
    * An extra mesh joint under the follicle before the middle one, point
      constrained to the middle follicle joint (ball and socket area).

    ``ribbon`` is a :func:`build_ribbon_limb` result or its group.
    Returns a dict with ``elbow_fix``, ``wrist_fix``, ``handles`` and ``extra_joint``.
    """
    if isinstance(ribbon, dict):
        top = ribbon["group"]
    else:
        top = find_ribbon(ribbon) or ribbon
    if common.fetch(top, "creaseFix"):
        raise ValueError("%s already has a crease fix" % naming.short_name(top))
    surface, skin, _holder, start, middle, end = common.fetch(top, "ribbon")
    root_jnt, _upper, mid_jnt, _lower, end_jnt = common.fetch(top, "controlJoints")
    bind_joints = common.fetch(top, "bindJoints")
    mid_ctl = cmds.listRelatives(mid_jnt, parent=True)[0]
    end_off = cmds.listRelatives(end_jnt, parent=True)[0]
    p0, p1, p2 = (transform.get_position(n) for n in (start, middle, end))
    parsed = naming.parse(top)
    side = parsed["side"]
    base = (parsed["name"] or naming.short_name(top)).replace("Deformers", "")

    def fix_chain(label, parent, position, aim_at, handle_parent):
        fix = _joint(base + label + "Fix", side, parent)
        cmds.xform(fix, worldSpace=True, translation=position)
        tip = _joint(base + label + "FixEnd", side, fix)
        cmds.xform(tip, worldSpace=True, translation=aim_at)
        _aim_joint(fix, tip)
        handle, effector = cmds.ikHandle(startJoint=fix, endEffector=tip, solver="ikSCsolver",
                                         name=naming.unique_name(naming.compose(base + label + "Fix", side,
                                                                                "ik_handle")))
        cmds.rename(effector, naming.unique_name(naming.compose(base + label + "Fix", side, "effector")))
        handle = cmds.parent(handle, handle_parent)[0]
        cmds.setAttr(handle + ".visibility", 0)
        return fix, tip, handle

    elbow_fix, elbow_tip, elbow_handle = fix_chain("Elbow", mid_ctl, p1, p0, root_jnt)
    wrist_fix, wrist_tip, wrist_handle = fix_chain("Wrist", end_off, p2, p1, mid_jnt)

    envelope = cmds.getAttr(skin + ".envelope")
    cmds.setAttr(skin + ".envelope", 0)
    try:
        for joint in (elbow_fix, wrist_fix):
            cmds.skinCluster(skin, edit=True, addInfluence=joint, weight=0.0, lockWeights=True)
            cmds.setAttr(joint + ".lockInfluenceWeights", 0)
    finally:
        cmds.setAttr(skin + ".envelope", envelope)

    extra = None
    if len(bind_joints) >= 3:
        index = len(bind_joints) // 2
        extra = joint_tools.create_joint(naming.compose(base + "CreaseBind", side, "joint"),
                                         parent=bind_joints[index - 1])
        cmds.setAttr(extra + ".jointOrient", 0, 0, 0)
        cmds.pointConstraint(bind_joints[index], extra, maintainOffset=False)
    common.store(top, "creaseFix", [elbow_fix, wrist_fix, elbow_handle, wrist_handle, extra])
    return {"elbow_fix": elbow_fix, "wrist_fix": wrist_fix, "ends": [elbow_tip, wrist_tip],
            "handles": [elbow_handle, wrist_handle], "extra_joint": extra}


def _aim_joint(joint, child):
    """Aim ``joint``'s X axis at ``child`` (Y up, jointOrient), keeping the child in place."""
    orient.orient_joints([joint, child], aim_axis="x", up_axis="y", up_mode="world", world_up=(0, 1, 0),
                         hierarchy=False)
