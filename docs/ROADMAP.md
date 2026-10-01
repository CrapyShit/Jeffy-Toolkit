# Roadmap

Ideas for future updates, roughly by priority. Open an issue or a PR to
reshuffle.

## 1.1: hardening
- [ ] Validate every system inside Maya 2022/2024/2025/2026 and turn the findings
      into regression tests with `mayapy` (a `tests/maya/` suite run locally).
- [ ] Undoable fast skin weight setting through a tiny scripted plugin command.
- [ ] Guide orientation markers (up vectors) for limbs and fingers.
- [ ] Settings dialog for the naming convention (studio presets).

## 1.2: auto-rig
- [ ] Bendy (ribbon) option for arms and legs.
- [ ] Quadruped leg component (3 segment IK, spring solver option).
- [ ] Face components: brows, lids (blink / smart blink), lips, cheeks.
- [ ] Component space presets editable on the guides.
- [ ] Post-build Python hooks stored on the guides (custom scripts).

## 1.3: deformation
- [ ] Skin weight layers / per-influence painting helpers.
- [ ] RBF pose interpolator wrapper (poseInterpolator / custom).
- [ ] Corrective shape sculpt workflow (invert deformation).
- [ ] Weight transfer by UV.

## 1.4: animator tools
- [ ] Picker UI generated from the rig.
- [ ] Pose library with thumbnails.
- [ ] Space switch / IK-FK bake over frame ranges.

## Ideas backlog
- Game export presets (Unreal / Unity naming, root motion).
- Rig diff tool (compare two rig versions).
- Batch rig build from the command line (`mayapy`).
