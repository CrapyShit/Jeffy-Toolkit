# Setup Belt

Status: **stage 1 built**: the framework, the window, Rig Base, FK Chain,
IK/FK Limb and Spaces. Stages 2 and 3 are planned below.

## Quick start

1. Build your bind skeleton (joints only, named like `L_upperArm_JNT`). Bend
   elbows and knees slightly so the IK knows which way they bend.
2. Open the belt: Jeffy menu > *Open Setup Belt*, the **BELT** shelf button, or
   `import jeffy; jeffy.show_setup_belt()`.
3. **Rig Base**: load your root joint, build. (Other tools offer to create it
   when it is missing.)
4. Pick a tool, select the joints, press `[<]` on the first slot (selecting
   several joints in order fills the next slots too), set the options, then
   **Build**. *Preview* first if you want to move the guides (pole, settings
   control).
5. **SCENE > Setups** lists everything. Double click a setup to edit it and
   **Rebuild**, delete it, snap IK/FK or switch spaces without popping.

Python:

```python
from jeffy.setups.tools.rig_base import RigBase
from jeffy.setups.tools.fk_chain import FkChain
from jeffy.setups.tools.ikfk_limb import IkFkLimb, toggle
from jeffy.setups.tools.spaces import Spaces

RigBase.build(root_joint="C_root_JNT", name="hero")
FkChain.build(start="L_clavicle_JNT")                     # builds R_ too (mirror=True)
arm = IkFkLimb.build(start="L_shoulder_JNT", mid="L_elbow_JNT", end="L_wrist_JNT", name="arm")
leg = IkFkLimb.build(start="L_hip_JNT", mid="L_knee_JNT", end="L_ankle_JNT", name="leg", knee="no-flip")
Spaces.build(control="L_armIK_CTL", targets=["C_root_CTL", "C_global_CTL"], mode="parent")
arm = arm.rebuild(options={"game_safe": True})            # layers on top are rebuilt too
toggle("L_armIK_CTL", key=True)                            # IK/FK snap + switch
arm.delete()                                               # joints back to their rest pose
```

Tests in real Maya: `mayapy tests/in_maya/run.py` (headless, builds every tool
on a test skeleton).

## Decisions made while building stage 1

- The **skeleton group follows the Global control**. Global scale reaches
  every joint, driven or not, and the bind joints keep a scale of 1. Keep
  *Put skeleton in rig* on.
- The **Global and Root controls** sit directly under `{name}_RIG`, next to
  the four groups, so *controlsVis* hides the setups' controls but never the
  Global control.
- The **hidden IK chain has its own planar orientation** (X down the bone, Z
  on the bend axis). Fixed offsets map it back to your joints, so pin, pole
  and snapping are exact whatever the orientation of your skeleton.
- The **Spaces** tool can also rename the enum (*Attribute* option). Deleting
  the layer brings the default `space` enum back.
- The belt sizes controls from your joint lengths (the *Control size* option
  multiplies that). The main window's *Rig scale* does not apply.

## What it is

A separate, dockable **Jeffy Setup Belt** window: a belt of setup tools for
rigging by hand. You build the bind skeleton yourself (no controls, no
setups). Then each tool turns the joints you give it into one clean, complete
setup. Tools **stack**: a layer tool (ribbon, reverse foot, hand poses...)
builds on top of a setup that already exists.

It is not an auto-rigger and has no body-part templates or recipes. The
existing Jeffy window and its tabs stay as they are. The belt reuses the
toolkit's core (naming, attributes, control shapes, math) but not the old rig
builders, which use constraints.

## Decisions

| Topic | Decision |
|---|---|
| Window | Separate dockable window. Tool list on the left, the selected tool's panel on the right |
| Giving joints | Named slots filled by hand: select a joint, press `[<]`. Nothing is guessed |
| Placement | **Preview** shows guide locators at their default positions; you move them; **Build** uses them |
| Wiring | Matrix-based: `offsetParentMatrix`, `blendMatrix`, `aimMatrix`, `pickMatrix`, `multMatrix`, `uvPin`. **No constraint nodes** (IK handles are the only solver nodes) |
| Bind skeleton | Hidden IK and FK chains blend into it. Its translate/rotate/scale channels are driven; nothing is parented under it or re-parented, and joint orients are never changed |
| Per-build toggles | **Game safe**, **Bendy**, **Squash & stretch** (on the tools where they apply) |
| Naming | `L_upperArm_JNT` style. Side and name come from the first joint and can be edited. Created nodes: `{side}_{name}{Part}_{TYPE}` |
| Controls | `ZRO` + `OFF` group above every control. `ZRO` takes attach/space matrices, `OFF` is free for your own SDKs. Side colours from the toolkit (L blue, R red, C yellow) |
| Twist | The tools create twist joints (Twist layer). The Ribbon layer has its own deform joints |
| Linking | Auto-attach to the setup above in the joint hierarchy, plus default spaces |
| Mirror | A **Mirror** checkbox builds the other side from `L_`/`R_` names |
| Management | **Setup list**, plus **Rebuild with new options** |
| Clavicle | Plain FK (no auto clavicle) |
| Delivery | Three stages. Each one is tested headless in Maya 2027 before you test it in Maya |

## How stacking works

### Setup tag
Every build creates one hidden `network` node, `{side}_{name}_SETUP`, holding:

- type, version, side, name, and options (JSON)
- **slots**: the joints you gave it
- **outputs**: one transform per joint whose world matrix is that joint's final
  pose. Bind joints follow outputs; other setups and layers read outputs.
- **controls**, **settings control**, top groups, and guide positions
- **parent setup** and **layers** (setups stacked on it)

A layer's panel has one **Base setup** slot. Pick *any* control of a setup and
the tool reads everything else from the tag: joints, side, name, outputs, and
where its attributes go.

### Rig layout
```
{name}_RIG
  C_global_ZRO > OFF > C_global_CTL      global scale, visibility / display switches
    C_root_ZRO > OFF > C_root_CTL
  {name}_controls_GRP     one group per setup (controls only)
  {name}_systems_GRP      hidden: IK chains, outputs, systems
  {name}_skeleton_GRP     your skeleton (joint values untouched), follows the Global control
  {name}_geometry_GRP
```
The **Rig Base** tool makes this. If you build another tool first, the
window offers to create a Rig Base.

### Auto-attach and default spaces
- When a setup is built, its top `ZRO` follows the output of the setup that
  drives the parent joint (arm -> clavicle output, clavicle -> chest...). If
  no setup drives it, the `ZRO` follows the Rig Base root control.
- **Order between base setups doesn't matter.** Building the spine after the
  arms re-attaches the arms to it and refreshes their spaces.
- Controls carry a **space role** (`world`, `root`, `cog`, `hips`, `chest`,
  `head`...). Default spaces are found by walking up the setup tree:

| Control | Default spaces |
|---|---|
| Limb IK control (hand/foot) | world, root, COG, chest/hips, parent setup |
| Pole vector | world, root, IK control, limb root |
| Limb FK top control | orient: parent, chest/hips, root, world |
| Head | orient: neck, chest, COG, world |
| Eye target | head, world |

The **Spaces** tool edits them later, on any control.

### Order rules, delete and rebuild
- A layer refuses to build on the wrong base, with a clear message (for example
  "Reverse Foot needs an IK/FK Limb setup").
- **Delete**: removes every node of the setup and puts the bind joints back to
  the rest pose stored at build. If layers are stacked on it, a dialog lists
  them; confirming deletes them too.
- **Rebuild with new options**: load a setup from the setup list, change
  options or guides, press **Rebuild**. Layers on top rebuild after it with
  their own stored options. Control shapes you edited by hand are *not* kept.
- Every Build, Rebuild or Delete is one undo step.

### Game safe
- **On**: stretch moves child joints along the bone (translate). Bind joints
  never get scale. Ribbon deform joints are parented inside the bind
  hierarchy so they export.
- **Off**: scale-based stretch and squash are allowed on bind joints. Ribbon
  joints live in their own group.

## The window

```
+------------+------------------------------------+
| BUILD      | IK/FK LIMB                         |
|  Rig Base  |  Name [arm     ]  Side [L v]       |
|  FK Chain  |  -- Joints ----------------------  |
| >IK/FK     |  Start [L_shoulder_JNT  ] [<]      |
|  Spline    |  Mid   [L_elbow_JNT     ] [<]      |
|  Aim       |  End   [L_wrist_JNT     ] [<]      |
|  Jaw/Hinge |  -- Options ---------------------  |
| LAYERS     |  [x] Stretch  [x] Soft IK  [x] Pin |
|  Ribbon    |  Knee (o) Pole  ( ) No-flip        |
|  Twist     |  [ ] Game safe   [x] Mirror        |
|  Foot      |  -- Controls --------------------  |
|  Hand      |  Size [1.0]  Colour [side]         |
|  Lids      |                                    |
|  Spaces    |  [Preview]  [Build]  [Delete]      |
| SCENE      |                                    |
|  Setups    |                                    |
+------------+------------------------------------+
```

- Panels are generated from each tool's slot and option list, so every tool
  looks and behaves the same.
- **Setups** (scene list): a tree of setups and their layers. Click one to load
  it back into its panel. It also has Select controls, Rebuild, Delete,
  IK/FK match and seamless space switch.
- Opens from the Jeffy menu (*Open Setup Belt*), the **BELT** shelf button, or
  `jeffy.show_setup_belt()`.
- Every tool is also a Python class, for example
  `IkFkLimb.build(start=..., mid=..., end=..., stretch=True)`.

## Tools

### Base tools (build on joints)

**1. Rig Base**
- Slots: root joint (optional).
- Creates: the rig layout above, **Global** control (global scale) and **Root**
  control. Global holds visibility (controls, joints, geo) and geo display
  (normal / template / reference).

**2. FK Chain**: clavicle, simple chains, props, the base for fingers and toes
- Slots: Start, End (any number of joints between; End empty = one joint).
- Options:
  - orient isolation (follow parent / world)
  - master control that bends the whole chain
  - FK stretch (length attributes)
  - control on the last joint on/off
  - lock translate

**3. IK/FK Limb**: arms, legs
- Slots: Start (shoulder/hip), Mid (elbow/knee), End (wrist/ankle).
- Guides: pole position, settings control position.
- Options:
  - stretch, soft IK, pin to pole
  - knee/elbow mode: **pole vector** or **no-flip** (`kneeTwist` attribute)
  - IK control orientation (world / joint)
  - upper/lower length multipliers
  - game safe, mirror
- Creates:
  - FK controls, IK control, pole and connector line
  - settings control with `ikFk` (also a proxy attribute on every limb control)
  - hidden IK and FK chains blended by `blendMatrix`
- Animation: seamless IK->FK / FK->IK snap, with an option to key it.

**4. Spline IK/FK**: spine, neck, tail, tentacle
- Modes:
  - **Spine**: slots Pelvis (optional), Start, End.
  - **Neck**: slots Neck start, Neck end, Head.
  - **Chain**: slots Start, End.
- Inside: a hidden NURBS ribbon with `uvPin` (stable twist, no flipping).
- Spine:
  - **COG** moves everything; **hips** rotate the pelvis on their own.
  - Hips, mid and chest IK controls, with an FK control layer on top.
- Neck: mid bend control, neck stretch, head orient isolation (neck / chest /
  COG / world).
- Chain (tail/tentacle):
  - IK and FK with a switch, any number of IK and FK controls.
  - **Wave** attributes (amplitude, wavelength, speed/offset, falloff),
    built from native `sin` nodes, no expressions.
- All modes: squash & stretch with a stretch amount, and volume preservation
  with a falloff along the chain.

**5. Aim**: eyes, also pistons and look-at parts
- Slots: aim joints (a list, 2 eyes or more), Head (optional).
- Guides: target distance.
- Options: aim/up axis (detected, can be overridden), FK override on each
  eye, `aim` on/off per eye.
- Creates: master target, one target per joint, `aimMatrix` network. Space:
  head / world.

**6. Jaw / Hinge**: jaw, also prop lids and doors
- Slots: Jaw joint, Chin/end joint (optional, places the control), Head
  (optional).
- Options: open / side / forward, with clamps so it can't go too far, and an
  `open` attribute.

### Layer tools (build on a setup)

**7. Ribbon** (bendy)
- Base: an IK/FK Limb or a FK Chain with 2+ segments.
- Options: deform joints per segment (default 5), bend controls (mid-upper,
  elbow/knee, mid-lower), twist distribution, squash & stretch, game safe.
- Creates: ribbon surfaces with `uvPin`, its **own deform joints**, and the
  bendy controls' visibility on the limb's settings control.
- You skin to the ribbon joints instead of the limb joints.

**8. Twist**
- Base: a limb setup, or two joints directly.
- Options: count per segment; forward (forearm: twist from the end) or reverse
  (upper arm: counter twist from the start).
- Creates: twist joints parented under the segment start, driven by no-flip
  swing/twist extraction.
- Refuses a segment that already has a Ribbon (the ribbon handles twist there).

**9. Reverse Foot**
- Base: an IK/FK Limb. Slots: Ball, Toe tip (the ankle comes from the limb).
- Guides: heel, inner bank, outer bank and toe tip pivots, placed on the ground
  automatically. Move them, then Build.
- Attributes on the IK control: `roll`, `rollBreak`, `rollStraight`, `bank`,
  `heelTwist`, `ballTwist`, `toeTwist`, `toeTap`.
- Also: **on-ground pivot controls** you can grab (visibility toggle), and a
  ball FK control for FK mode.
- The limb's IK handle moves under the foot pivots automatically.

**10. Hand / Finger poses** (also toes)
- Base: a limb (or the wrist joint).
- Slots: a list of finger roots (`[+ Add selected]`), with a *metacarpal* and a
  *thumb* checkbox per row.
- Creates:
  - FK controls per phalanx
  - a **master control** per finger that bends the whole finger
  - metacarpal controls
  - a hand control with `curl`, `spread`, `fist`, `relax`, `cup` and per-finger
    curl
- Pose attributes drive an extra `POSE` group on finger controls
  (`ZRO > POSE > OFF > CTL`), so `OFF` stays yours.
- Option: per-finger **IK/FK for contact** (IK tip control, space hand /
  world).

**11. Fleshy Lids**
- Base: an Aim setup.
- Slots: upper and lower lid joints per eye.
- Lids follow the eye rotation by `eyeFollow` attributes (up/down, side).

**12. Spaces**
- Slots: control, targets (a list, pre-filled with the default candidates).
- Options: parent / orient / point, attribute name, labels, default space.
- Uses `ZRO` `offsetParentMatrix`. Has a seamless switch button, with an
  option to key it.

## Code layout

```
scripts/jeffy/setups/
    core/      schema.py (slots, options), tag.py (setup tag), base.py (Setup class: build/delete/rebuild/mirror),
               scene.py (registry, queries), controls.py (ZRO/OFF controls), drive.py (joint-orient-aware
               matrix driving of bind joints), attach.py (auto-attach + spaces), guides.py
    tools/     rig_base, fk_chain, ikfk_limb, spaces   (stage 2-3: ribbon, twist, foot, spline, hand, aim, jaw, lids)
scripts/jeffy/ui/setup_belt/
               window.py, panel.py (built from each tool's schema), setup_list.py, common.py
tests/test_setups.py   pure-Python tests (schema, registry, window offscreen), run in CI
tests/in_maya/         headless builds in mayapy on a generated test skeleton: mayapy tests/in_maya/run.py
```

## Testing (before each stage reaches you)

Each tool is built headless in Maya 2027 on a generated test biped. The tests
check that:

- there are **no constraint nodes**
- bind joints don't move at build (no pop)
- IK/FK snap matches both ways
- stretch, soft IK and pin values are right
- mirror gives matching sides
- delete leaves the skeleton exactly as it was
- rebuild with new options keeps the stacked layers

## Stages

1. **Foundation** (built): setup tag, Setup class, controls, matrix driving,
   auto-attach and spaces, guides, delete/rebuild; window, panels, setup
   list; **Rig Base, FK Chain, IK/FK Limb, Spaces**.
2. **Ribbon, Twist, Reverse Foot**.
3. **Spline IK/FK** (spine, neck, tail), **Hand**, **Aim**, **Jaw / Hinge**,
   **Fleshy Lids**.

You test each stage in Maya before the next one starts.
