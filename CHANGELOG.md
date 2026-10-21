# Changelog

All notable changes to the Jeffy Toolkit are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **Reverse Foot** is now one click (Rigging tab > Twist / Foot / Fingers,
  menu *Rigging*, or `jeffy.rig.foot.build_reverse_foot_auto`): select the
  leg IK control, then the foot joints (ankle, ball, toe [, toe end] - or
  just the ankle).
  - It creates the reverse chain itself: heel behind the ankle on the
    ground, toe tip on the ground, then ball and ankle on the foot joints.
  - It adds the bank pivots and the roll / bank / twist / toe tap
    attributes, and builds the other side when the `L_` / `R_` names match.
  - Bind joints of an IK/FK limb are swapped for their IK joints.
  - Optional after the joints: a heel locator, or heel, inner and outer
    locators.
  - The previous buttons stay as *Reverse Foot (locators)* and
    *Reverse Foot From Chain*.
- **Reverse Foot From Chain** (Rigging tab > Twist / Foot / Fingers, menu
  *Rigging*, or `jeffy.rig.foot.build_reverse_foot_from_chain`): select the
  leg IK control, then the first joint of your own reverse chain
  (heel > toe tip > ball > ankle).
  - The base ankle, ball and toe are found from the reverse joints'
    positions (joints named `IK` win when several chains overlap). The leg
    IK target is found under the IK control.
  - The reverse joints keep their orientation: the roll and twist networks
    rotate them around the foot's side and up axes through quaternions.
  - Inner and outer bank pivots are created on each side of the ball (or
    select your own); move their `ZRO` groups to adjust them.
  - *Both sides* builds the other foot too when the `L_` / `R_` names match.
  - Same attributes as *Reverse Foot*: `roll`, `rollBreak`, `rollStraight`,
    `bank`, `heelTwist`, `toeTwist`, `ballTwist`, `toeTap`.
- **Face tab** (and a *Face* menu), with the Python API in `jeffy.rig.face`:
  - *Create Slider*: a handle limited to its frame (vertical, horizontal or
    2D square) with 0..1 `up` / `down` / `right` / `left` outputs on the
    control. *Connect* drives a blendshape target from one direction.
  - *Face Board From Blendshape*: one labelled slider per target, already
    connected. Pairs such as `browUp` / `browDown` share one two-sided
    slider; targets that are already driven are skipped.
  - *On-Face Controls*: select vertices (or existing joints), then the face
    mesh. Each control rides on the mesh (uvPin or follicle) and drives a
    joint. An inverse group cancels the double transform, so the control
    stays under the cursor once the mesh is skinned to the joints.
  - *Curve Rig From Edge Loop* for lips, brows, eyelids and folds: one joint
    per vertex follows a curve, deformed by a wire from a few controls under
    a main control. With *Aim from center* the joints rotate around the eye
    joint so lids slide over the eyeball.
  - *Eyelid Blink*: `blink` and `blinkHeight` on top of an upper and a lower
    lid curve rig. The lids meet on a line that follows the animated lid
    controls.
- **Spline IK/FK Switch** (Rigging tab > Spline IK, menu *Rigging*, or
  `jeffy.rig.spline.build_spline_ikfk`): spline IK and FK chains with an
  `ikFk` switch on a settings gear (0 FK, 1 IK), like the IK/FK limbs.
  The IK controls drive the curve through tangent points, so rotating any of
  them - the middle ones too - bends the curve (`tangentLength` sets how far
  it reaches). The first and last controls twist the chain and the last
  joint follows the last control's rotation. It replaces the first
  *Hybrid Spline IK/FK*, which was broken (see Fixed).
- **IK/FK Fingers** (Rigging tab > Twist / Foot / Fingers, menu *Rigging*, or
  `jeffy.rig.fingers.build_finger_ikfk`) for contact poses (hands on a table,
  a wall, a prop). Each finger gets FK controls, an IK solved to the tip with
  a pole vector, and an `ikFk` switch. The IK control's `space` switch picks
  `hand` (follows the hand) or `world` (the tip stays on the contact point
  while the hand moves). Select the hand control last to also get one
  `<finger>IkFk` attribute per finger on it.
- **Rig scale**: a global multiplier for the size of every control the
  toolkit builds, so the default shapes fit any character size in the scene.
  Set it in the *Rig scale* field at the top of the window (every tab uses it)
  or with `jeffy.set_rig_scale(0.1)`; it is saved between sessions. It scales
  the size given to each tool (controls, rig structure, FK, IK, IK/FK, spline,
  ribbon, eye rig, fingers, dynamic chain, every Flexible Rig setup) and the
  offsets that follow that size, plus the auto-rig template guides. Auto-rig
  controls already follow the guide lengths, so they scale with the guides.
  Existing controls are not changed. The Python builders (`jeffy.rig...`)
  still take `size` as given.

### Fixed
- **Reverse Foot**: the ankle was driven twice, by the leg IK's orient
  constraint and by an extra ankle -> ball IK handle. The handle is now only
  made when the ankle has no orient constraint.
- **Hybrid Spline IK/FK** raised `Cycle on '..._BM.outputMatrix'` and did not
  evaluate properly: the root FK control's `offsetParentMatrix` was computed
  from its own `parentInverseMatrix`. Replaced by *Spline IK/FK Switch*.
- The same hidden cycle in **matrix constraints**, the **matrix space switch**
  and **uvPin rivets** (also used by the face *On-Face Controls*): they now
  use the parent's `worldInverseMatrix` (or `worldMatrix`). A test walks every
  `offsetParentMatrix` network to keep it that way.
- Maya 2026 warnings `Legacy node type 'multDoubleLinear' detected`: the
  toolkit creates `multDL` / `addDL` in Maya 2026 and later.
- **IK Chain, IK/FK Limb and every auto-rig template** crashed while creating
  the pole vector line (`setAttr: No object matches name:
  |..._CRV|..._CRVShape.overrideEnabled`). The line's shape was stored as a
  full DAG path before the curve was reparented, so the path no longer
  existed. Everything after that point was never built: the IK handle was not
  constrained (the IK did not move) and the bind joints were not connected to
  the FK/IK chains.
- A tool that crashes now undoes its own partial build instead of leaving half
  a rig in the scene, and says so in the viewport.
- **Finger Controls**: controls were named `L_index0101_CTL` (the joint number
  was repeated).
- **Ribbon** button: the ribbon now follows the selected objects ("Attach to
  selection", on by default) instead of floating on its own.
- **IK/FK limbs** (window and auto-rig arm/leg): the IK root joint was parent
  constrained, which blocked the IK solver from rotating it, and the FK root
  joint had two parent constraints (limb parent + FK control) so it only
  followed its control halfway. Both chains now follow the parent through a
  group.
- **Dynamic chain** button: it built a simulated copy that drove nothing. It now
  adds FK controls and blends the selected joints between FK and the
  simulation (`dynamics` attribute on the first FK control).
- **Dynamic chains**: the simulated chain root was constrained, blocking the
  spline solver. The auto-rig chain component (dynamic mode) had the same
  double constraint as the FK root.
- **FK chain, Spline IK, Eye Rig, Finger Controls** buttons: controls were
  created at world and stayed behind when the rest of the rig moved. They now
  follow the parent of the selected chain.
- **Reverse Foot** button: the hidden IK end target no longer has to be
  selected; it is found under the IK control.

### Added
- **Flexible Rig tools** (antCGi "Create a Flexible Rig" course setups), under
  the new **Advanced** tab of each Rigging section and in a *Flexible Rig*
  menu. They are built exactly like the course scenes, next to the existing
  tools that behave differently:
  - *Create Flexible Structure*: `<name>_GRP` with a master control carrying
    `Skeleton / Geometry / Deformers / Rig_Systems` visibility switches.
  - *Flexible IK/FK Limb*: IK, FK and scale chains, `IK_FK_Switch` on a
    global control that follows the end joint, a reverse node for the FK
    weights, rotate order XZY on the IK control and distance based scaleX
    stretch (condition + divide, rest length measured on the scale chain).
  - *Bind Helper Joints*: elbow/wrist helpers point blended between IK and FK.
  - *Flexible Spine*: COG, hips and one direct FK control per spine joint.
  - *Flexible Fingers*: FK finger controls in a hand group following the
    wrist.
  - *Flexible Ribbon*: 9 follicle joints on a surface skinned to 5 control
    joints (aimed upper/lower controls, extra knots at the elbow), a sine and
    twist blendshape layer driven from the limb control (`SineBlend`,
    `SineAmplitude`, `SineWavelength`, `SineOrientation`, `SineOffset`,
    `TwistBlend`, `TwistOffset`), `Toon_Controls` and an optional elbow/wrist
    *Crease Fix* (single chain IK fix joints added to the skin at zero weight).
  - *Flexible Reverse Foot*: heel/inner/outer/end/ball/ankle pivots and the
    course roll and bank networks built from utility nodes only (`Roll`,
    `Bank`, `HeelTwist`, `ToeTwist`, `ToeTap`, plus `ToeFlex`, `RollBack`,
    `RollEnd`, `BankAmount`, `ToeStraightAngle` settings).
  - 10 *Flexible Rig* control shapes in the shape library.
- `tests/test_flexible_rig.py` builds each of them and checks the wiring and
  the roll, bank and stretch values against the course.
- `tests/fakemaya.py`: a scene-aware fake `maya.cmds` (real DAG paths,
  attributes, connections, constraints and Maya's errors) and
  `tests/test_rig_builds.py`, which runs every rigging button and every
  auto-rig template end to end and checks the wiring.

## [1.0.0] - 2026-10-01

First release.

### Added
- **Core**: configurable naming convention and renaming tools, attribute
  helpers (add/lock/proxy/reorder/copy/transfer), transform and matrix helpers
  (joint-orient aware world matrix setting, offsetParentMatrix zeroing), a pure
  Python math library, utility node helpers, an expression-to-node-network
  compiler, undo/tool decorators, colours, settings and JSON IO.
- **Controls**: 55 procedural shapes, `Control` class with offset groups and
  metadata, shape tools (replace, copy, mirror, scale, rotate, combine, text,
  user library, export/import).
- **Joints**: creation (selection, curves, insert, duplicate chain), an orient
  tool with world/plane/object/keep up modes, rotate axes, freeze rotations,
  planarize, mirror, labels and display helpers.
- **Geometry**: mesh, curve and surface helpers, spatial hash, symmetry maps,
  proxy geometry from skin weights and capsule proxies.
- **Rig**: structure, FK, IK (stretch, soft IK, pin), IK/FK limbs with
  seamless matching, space switching (constraint or matrix) with seamless
  switching, twist extraction and twist joints, spline IK with volume,
  ribbons, reverse foot, finger poses, eye rigs, rivets (follicle/uvPin),
  matrix constraints, pose readers and nHair dynamic chains.
- **Deformers**: skin weights IO (index/position), copy/mirror, prune, limit,
  smooth, vertex copy/paste/average, move weights, rebind at current pose;
  blendshape extract/mirror/symmetrize/split/transfer and weights IO; generic
  deformer weights IO/mirror, soft-selection clusters, wraps, delta mush.
- **Utils**: pose tools (mirror/flip/save/load/bind pose), baking and FBX
  export skeleton, connections and set driven key tools, selection helpers,
  scene cleanup and a rig validator with 23 checks.
- **Auto-rigger**: guide system, components (root, spine, neck, arm, leg,
  hand, chain, eyes, jaw, control), builder, templates (biped, simple biped,
  biped with tail, prop).
- **UI**: dockable window with nine tabs, Jeffy menu, shelf, drag-and-drop
  installer and startup script.
- MIT license.
- **Development**: pytest suite running without Maya, `tools/check_maya_api.py`
  validating Maya command flags against `maya-stubs`, ruff config and GitHub
  Actions CI.

[Unreleased]: https://github.com/CrapyShit/Jeffy-Toolkit/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/CrapyShit/Jeffy-Toolkit/releases/tag/v1.0.0
