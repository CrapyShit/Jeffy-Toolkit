# Python API cookbook

Every tool in the window is a regular Python function. Library functions take
node names as arguments and never depend on the selection.

## Naming

```python
from jeffy.core import naming
naming.compose("arm", "L", "control")          # 'L_arm_CTL'
naming.mirror_name("L_arm_to_R_hand")          # 'R_arm_to_L_hand'
naming.rename_sequential(nodes, "L_finger_##_JNT")
naming.CONVENTION = naming.NamingConvention("{name}_{side}_{type}")  # studio convention
```

## Attributes

```python
from jeffy.core import attributes
attributes.add_separator("L_arm_CTL", "ik")
attributes.add_attr("L_arm_CTL", "stretch", "float", default=0, minimum=0, maximum=1)
attributes.lock_hide("L_arm_CTL", ["s", "v"])
attributes.add_proxy("L_armSettings_CTL.ikFk", "L_armIK_CTL")
attributes.move_attr("L_arm_CTL", "stretch", -1)   # move up in the channel box
```

## Controls and shapes

```python
from jeffy.controls.control import Control
from jeffy.controls import shapes

ctl = Control.create("head", side="C", shape="cube", size=12, match="C_head_JNT",
                     offsets=("zero", "space"), color_value=(1, 0.5, 0))
ctl.add_attr("follow", "enum", enum_names=["neck", "world"])
shapes.mirror_shapes(["L_arm_CTL", "L_leg_CTL"])
shapes.save_to_library("myShape_CTL", "my_shape")    # available in the gallery
```

## Joints

```python
from jeffy.joints import orient, tools
chain = tools.create_chain([(0, 0, 0), (10, 0, -1), (20, 0, 0)], name="arm", side="L")
orient.orient_joints(chain, aim_axis="x", up_axis="y", up_mode="plane")
tools.duplicate_chain(chain[0], chain[-1], search="_JNT", replace="_IK_JNT")
```

## Rigging

```python
from jeffy.rig import fk, ik, ikfk, space_switch, spline, ribbon, twist, foot, matrix_constraints

ik.build_ik(["L_upLeg_JNT", "L_knee_JNT", "L_ankle_JNT"], name="leg", side="L", stretch=True, soft=True)
limb = ikfk.build_ikfk_limb(arm_joints, name="arm", side="L", parent="L_clavicle_JNT")
ikfk.toggle(limb["settings"].node)                      # seamless switch
space_switch.create("L_armIK_CTL", [("world", "C_global_CTL"), ("chest", "C_chest_CTL")])
space_switch.switch("L_armIK_CTL", "chest", key=True)  # no pop
twist.create_twist_joints("L_foreArm_JNT", "L_hand_JNT", count=3, mode="forward")
matrix_constraints.matrix_constraint("driver", "driven")
```

## Expression to nodes

```python
from jeffy.core import expression
expression.build("""
    L_eyelid_JNT.rz = clamp(L_blink_CTL.ty, 0, 1) * -40
    C_jaw_JNT.rz    = C_jaw_CTL.ty > 0 ? 0 : C_jaw_CTL.ty * 15
    box.sx          = 1 + sin(time_LOC.rx) * 0.1
""")
```

Supported: `+ - * / ^`, unary `-`, parentheses, `a > b ? x : y`,
`clamp min max abs sqrt pow lerp reverse remap sin cos distance`, and the
constants `pi` and `e`. Constant parts are folded.

## Skinning

```python
from jeffy.deformers import skin
skin.bind(["body_GEO"], joints, max_influences=4)
skin.export_weights("body_GEO", "/path/body.json")
skin.import_weights("body_GEO", "/path/body.json", method="position", remap={"old_JNT": "new_JNT"})
skin.copy_skin("body_GEO", ["shirt_GEO"])
skin.mirror_skin("body_GEO", axis="x")
skin.limit_influences("body_GEO", 4)
skin.rebind_at_current_pose("body_GEO")
```

## Blendshapes and deformers

```python
from jeffy.deformers import blendshape, utils
blendshape.split_target("head_GEO", "smile_GEO", falloff=2.0)    # L_smile_GEO, R_smile_GEO
blendshape.mirror_target("head_GEO", "L_brow_up_GEO")            # R_brow_up_GEO
utils.cluster_from_soft_selection("cheek_CLS")
utils.mirror_deformer_weights("cheek_CLS", "head_GEO")
```

## Poses, baking, validation

```python
from jeffy.utils import pose, bake, checks
pose.mirror_pose(source_side="L")
pose.save_pose("/path/pose.json")
bake.bake_and_export("C_root_JNT", ["body_GEO"], "/path/anim.fbx")
print(checks.report())
checks.fix_all()
```
