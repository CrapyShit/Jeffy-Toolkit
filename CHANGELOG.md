# Changelog

All notable changes to the Jeffy Toolkit are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
