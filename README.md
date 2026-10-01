# Jeffy Toolkit

**A rigging toolkit for Autodesk Maya, written in Python.** It covers the
everyday rigging tools (controls, joints, renaming, attributes, skinning) and
more advanced systems: stretchy/soft IK, IK/FK with seamless matching, space
switching, spline and ribbon rigs, no-flip twist, reverse feet, matrix
constraints, an expression-to-node compiler, rig validation and a modular
guide-based auto-rigger.

Everything works three ways: a dockable **window**, a **Jeffy menu** and
**shelf** in Maya, and a plain **Python API** for your own scripts and
pipelines.

| | |
|---|---|
| Maya | 2022 – 2026+ (Python 3.7+, PySide2 or PySide6) |
| Platforms | Windows, macOS, Linux |
| Size | ~15k lines, 850+ public functions/classes, 155 one-click tools |
| Status | `1.0.0`. See [CHANGELOG](CHANGELOG.md) and [ROADMAP](docs/ROADMAP.md) |
| License | [MIT](LICENSE) |

---

## Installation

### Drag and drop (recommended)

1. Clone or download this repository somewhere permanent:
   `git clone https://github.com/CrapyShit/Jeffy-Toolkit.git`
2. Drag `install/drag_and_drop_install.py` into a Maya viewport.

The installer writes a Maya module file (`jeffy_toolkit.mod`) that points to
the repository, creates the **Jeffy** menu and opens the toolkit. From then on
the toolkit loads in every Maya session. To update, run `git pull` (or replace
the folder). No reinstall is needed.

### Manual

Create `<maya app dir>/modules/jeffy_toolkit.mod` containing:

```
+ JeffyToolkit 1.0.0 /path/to/Jeffy-Toolkit
PYTHONPATH +:= scripts
```

Alternatively, add `/path/to/Jeffy-Toolkit/scripts` to `PYTHONPATH`. Then, in Maya:

```python
import jeffy
jeffy.install_menu()   # "Jeffy" main menu
jeffy.install_shelf()  # optional "Jeffy" shelf
jeffy.show()           # the toolkit window
```

### Uninstall

Delete `jeffy_toolkit.mod` from your user `modules` folder, or run
`drag_and_drop_install.uninstall()`.

---

## Quick start

```python
import jeffy
jeffy.show()
```

The window has nine tabs:

| Tab | What's inside |
|---|---|
| **Controls** | Shape gallery (55 shapes + your own library), create controls on selection with offset groups, colours (index or RGB), replace / copy / mirror / scale / rotate shapes, line width, text controls, offsetParentMatrix zeroing |
| **Joints** | Joints at selection / on curves, insert / split, duplicate chains, a full orient tool (any aim/up axis, world / plane / object / keep up modes), rotate axes ±90, freeze rotations, planarize chains, mirror, labels, display |
| **Rigging** | Rig structure, FK, IK (stretch, soft IK, pin), IK/FK limbs with matching, spline IK (stretch, volume, advanced twist), ribbons, twist joints, reverse foot, finger poses, space switches, matrix constraints, follicle/uvPin rivets, eye rigs, pose readers, nHair dynamic chains, expression-to-nodes |
| **Deform** | Bind, export/import weights (by index or position), copy/mirror skin, prune, limit influences, remove unused, rebind at current pose, vertex copy/paste/average/smooth, move weights, blendshape extract/mirror/split/symmetrize/transfer, soft-selection clusters, wraps, deformer weight IO/mirror, proxy geometry |
| **Attributes** | Add attributes and separators, lock/hide grid, proxy attributes, reorder (move up/down), reset to defaults, copy/transfer attributes, connections, set driven key copy/mirror/export |
| **Naming** | Sequential `##` renamer, search & replace (regex), prefix/suffix, trim, auto suffix by type, fix shape names, mirror names, make unique |
| **Auto-Rig** | Templates (biped, simple biped, biped + tail, prop), components, guide mirroring, save/load guides, build / rebuild / delete |
| **Animate** | Reset, bind pose, mirror/flip pose, save/load poses, IK/FK and space switching, bake, export skeleton, FBX export |
| **Utilities** | Scene cleanup (namespaces, unknown nodes/plugins, Turtle, empty groups), rig locking, scene report, and the **Rig Check** validator with auto-fixes |

---

## Feature highlights

### Controls
- 55 procedurally generated shapes (2D, arrows, 3D, pins, rig-specific
  shapes such as COG, master, foot, hand, hips, chest). Circles are true
  radius-1 periodic cubics.
- `Control` objects carry their offset groups (`ZRO`/`OFF`/`SDK`/`SPC`), side
  colour, controller tag and metadata, so tools can find and edit them later.
- Shape tools: replace (keeps colour and size), mirror L↔R in world space,
  copy, scale/rotate CVs, combine, text curves, save to a personal library,
  export/import shapes and colours per rig.

### Joints
- `orient_joints`: any aim/up axes including negatives. Up vectors can come from
  the world, an object, the chain's bending plane (consistent normals along the
  chain), or the current orientation. Children keep their world transforms.
- Planarize chains, rotate local axes, freeze rotations into joint orient, label
  joints for left/right skin mirroring, insert/split joints, joints on curves
  by arc length.

### Rig building blocks (`jeffy.rig`)
- **IK** with a single node network for stretch plus **soft IK** (no pop at full
  extension), elbow/knee **pin**, length multipliers, and global-scale awareness
  that measures world scale, so it works at any rig scale.
- **IK/FK** limbs with blended bind chain, proxy switch attribute on every
  control, and **seamless matching** both ways (`ikfk.toggle(control)`).
- **Space switching** via constraint (parent/orient/point) or the Maya 2020+
  matrix `choice` method, with **seamless switching** that keeps the pose and
  can key it.
- **Twist**: quaternion swing/twist extraction (no flipping), forearm-style
  and upper-arm (counter twist) distributions.
- **Spline IK** spines/tails with advanced twist, stretch and a volume
  preservation profile. **Ribbons** with follicles, bend controls and global
  scale.
- **Reverse foot** with heel/ball/toe roll (break and straighten angles),
  bank that detects inner/outer automatically, twists and toe tap.
- **Matrix constraints** (offsetParentMatrix, joint-orient aware), blendMatrix
  and aimMatrix constraints.
- **Rivets** with follicles or uvPin, **pose readers** for correctives,
  **nHair dynamic chains** wired without MEL or selection tricks.
- **Expression → nodes**: write `jaw_JNT.rz = clamp(jaw_CTL.ty, -1, 5) * -10`
  and get a utility-node network (constant folding included) instead of a slow
  expression node.

### Deformers
- Skin weights through `MFnSkinCluster` (fast), JSON files with sparse
  weights, influences and positions. Import **by vertex index or world
  position** onto different topology, with influence remapping.
- Limit influences, prune, smooth (respects locked influences), copy/paste/
  average vertex weights, move weights between joints, rebind at current pose,
  combine skinned meshes.
- Blendshapes: extract targets (optionally live-connected), mirror, symmetrize
  or split L/R with a smooth falloff using symmetry maps, transfer to other
  topology through a wrap, and target weight IO.
- Clusters from **soft selection**, wraps without MEL, deformer weight
  export/import/mirror, delta mush/tension, deformer ordering and envelopes.

### Auto-rigger (`jeffy.autorig`)
Guide-based and modular. Components: `root`, `spine`, `neck`, `arm`, `leg`,
`hand`, `chain` (FK / spline / dynamic), `eyes`, `jaw`, `control`. Guides
store options as channel-box attributes, mirror left to right, save as JSON
templates, and are re-created from a built rig. See [docs/autorig.md](docs/autorig.md).

```python
from jeffy.autorig import templates, guides, builder
templates.create("biped")      # place the guides
guides.mirror_all("L")         # after adjusting the left side
builder.build("hero")          # build
builder.rebuild("hero")        # after tweaking guides
```

### Validation (`jeffy.utils.checks`)
23 checks, most with auto-fix: duplicate names, namespaces, unknown nodes and
plugins, Turtle leftovers, display layers, expressions, scene units, top-level
nodes, construction history, unused orig shapes, unfrozen geometry, shape names,
negative scale, controls not zeroed, keyed controls, missing controller tags,
joint rotations, joint scale, visible IK handles, skin max influences, unused
bind poses and empty groups. Adding a check is a ~10 line class.

---

## Scripting examples

```python
from jeffy.controls.control import Control
from jeffy.rig import ikfk, space_switch
from jeffy.deformers import skin

ctl = Control.create("arm", side="L", shape="circle", axis="x", size=3, match="L_arm_JNT",
                     offsets=("zero", "offset"))
limb = ikfk.build_ikfk_limb(["L_upArm_JNT", "L_foreArm_JNT", "L_hand_JNT"], name="arm", side="L",
                            parent="L_clavicle_JNT")
space_switch.create(limb["ik"]["ik_control"].node, [("world", "C_global_CTL"), ("chest", "C_chest_CTL")])

skin.export_weights("body_GEO", "/tmp/body.json")
skin.import_weights("body_v2_GEO", "/tmp/body.json", method="position")
```

More in [docs/api.md](docs/api.md).

---

## Repository layout

```
install/drag_and_drop_install.py   Maya installer (module file)
scripts/userSetup.py               builds the menu at Maya startup
scripts/jeffy/
    core/        naming, attributes, transforms, matrices, math, nodes, expression, undo/tool decorators
    controls/    shape library, Control class, shape tools
    joints/      creation/editing and orientation
    geometry/    mesh, curves, surfaces, symmetry, spatial hash, proxies
    rig/         FK, IK, IK/FK, spaces, twist, spline, ribbon, foot, fingers, aim, attach, ...
    deformers/   skin, blendshape, generic deformers, pure weight math
    utils/       pose, bake/export, connections/SDK, selection, scene, checks
    autorig/     guides, components, builder, templates
    ui/          Qt window + pages, menu, shelf, actions
tests/           pytest suite (runs without Maya)
tools/           check_maya_api.py (validates every cmds flag against maya-stubs)
docs/            guides and roadmap
```

## Development

```bash
pip install pytest ruff maya-stubs PySide6-Essentials
ruff check .
python tools/check_maya_api.py scripts install   # every cmds.<command>(flag=...) is validated
QT_QPA_PLATFORM=offscreen python -m pytest
```

The tests run outside of Maya. A fake `maya` package lets every module
import, the pure Python parts (math, naming, expression parser, weights,
symmetry, spatial queries, shape data, auto-rig definitions) are tested for
real, and the whole Qt window is built offscreen. CI runs all of this on
Python 3.9 to 3.11. See [CONTRIBUTING.md](CONTRIBUTING.md) for conventions and
the release process.

Inside Maya, `jeffy.reload_toolkit()` (or the **Reload** button) reloads every
module while you develop.

> The automated tests can't run Maya itself. Scene-modifying code is
> validated statically (`cmds` commands and flags, OpenMaya names, call
> signatures), but it's still new, so test new rigs on a copy of your scene and
> report issues.

## License

Released under the [MIT License](LICENSE).
