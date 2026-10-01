# Auto-rigger guide

The auto-rigger builds a full rig from **guides**: small spheres you place on
your character. It is modular. A rig is a set of **components** (spine, arm,
leg...) that attach to each other through named **outputs**.

## Workflow

1. **Create guides**: *Auto-Rig* tab, pick a template, then **Create Template**
   (or `templates.create("biped")`). Templates are authored for a ~180 cm,
   Y-up character facing +Z, with its left side on +X. Use *Scale* for other sizes.
2. **Fit the guides**: move the markers of the **left** side and the centre
   onto your mesh. Markers are parented, so moving a parent moves its children.
3. **Mirror**: click **Mirror Guides** with nothing selected to mirror every left
   component to the right, or select guides to mirror only those.
4. **Options**: select a component's `*_guide` group. Its options are attributes
   in the Channel Box (twist joint count, stretch, default IK/FK, finger list...).
5. **Build**: enter a rig name and click **Build Rig**.
6. **Iterate**: change guides or options, then **Rebuild**. Skinned geometry
   parented under the rig's `geometry_GRP` is kept when the rig is deleted.

Guides can be saved and loaded as JSON (**Save/Load Guides**). Every built rig
also stores its guides, so **Restore Guides From Rig** recreates them even if
they were deleted.

## Components

| Type | Guides | Outputs | Notes |
|---|---|---|---|
| `root` | root | `root`, `global` | root joint driven by the local control |
| `spine` | hips, spine1, spine2, chest | `cog`, `hips`, `chest`, `base` | COG, hips, FK spine + stretchy spline IK (volume, advanced twist) |
| `neck` | neck, head, head_end | `head`, `neck` | FK neck, head with `follow` orient space (neck / chest / world) |
| `arm` | clavicle, shoulder, elbow, wrist, hand_end | `hand`, `clavicle`, `shoulder` | IK/FK with stretch, soft IK, pin, twist joints, IK/pole/FK spaces |
| `leg` | hip, knee, ankle, ball, toe, heel, foot_in, foot_out | `foot`, `ball`, `toe` | IK/FK + reverse foot (roll, bank, twists, toe tap) |
| `hand` | per finger (`thumb01`...) | `fingers` | FK fingers + fist/spread/relax/per-finger curl attributes |
| `chain` | `c01`...`cNN` | `base`, `end` | modes: `fk`, `spline`, `dynamic` (nHair) |
| `eyes` | left, right, aim | `aim` | aim controls with head/world spaces |
| `jaw` | jaw, chin | `jaw` | jaw control with the pivot at the hinge |
| `control` | control | `control` | single control (props), optional joint |

Parents are written `"<side>_<name>.<output>"`, e.g. `C_spine.chest`. Set a
component's parent in the *Parent* field and click **Set Parent On Selected**.

## Conventions of the built rig

- Hierarchy: `<name>_RIG > geometry_GRP / skeleton_GRP / controls_GRP / systems_GRP / extras_GRP`.
- `C_global_CTL` holds `globalScale` and the display switches (geometry
  normal/template/reference, skeleton, controls, systems visibility).
- Right side joints are **behaviour mirrored**: identical rotation values on
  both sides give mirrored motion, which is what pose mirroring expects.
- All controls get a `space`/`follow` attribute when relevant, plus a stored
  bind pose (Animate tab, **Go To Bind Pose**).
- Two sets are created: `<name>_controls_SET` and `<name>_skinJoints_SET` (bind
  these joints).

## Scripting

```python
from jeffy.autorig import builder, guides, templates

templates.create("biped_with_tail")
builder.add_component("chain", name="ear", side="L", parent_output="C_neck.head",
                      settings={"count": 3})
guides.mirror_all("L")
rig = builder.build("creature")
print(rig.global_ctl, rig.skeleton)
```

See `CONTRIBUTING.md` for writing your own component.
