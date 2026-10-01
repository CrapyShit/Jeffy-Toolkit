# Contributing / maintaining the Jeffy Toolkit

This toolkit is meant to grow over time. This page explains where things go
and how to ship an update safely.

## Setup

```bash
git clone https://github.com/CrapyShit/Jeffy-Toolkit.git
cd Jeffy-Toolkit
pip install pytest ruff maya-stubs PySide6-Essentials
```

Inside Maya, install once with `install/drag_and_drop_install.py`. After
editing code, click **Reload** in the window (or run `jeffy.reload_toolkit()`).

## Checks to run before every commit

```bash
ruff check .                                   # style + common bugs
python tools/check_maya_api.py scripts install # every cmds flag exists
QT_QPA_PLATFORM=offscreen python -m pytest     # tests (no Maya needed)
```

CI runs the same three steps on every push.

## Conventions

- **Python 3.7 compatible** (Maya 2022). No walrus operator, no `match`, no
  `list[str]` annotations at runtime, no `str.removeprefix`.
- **Long flag names only** in `maya.cmds` calls (`maintainOffset=True`, not
  `mo=True`). `tools/check_maya_api.py` only knows long names, and they read better.
- `cmds` calls that may return `None` are guarded: `cmds.listRelatives(...) or []`.
- **Never depend on the selection** inside library functions. Pass nodes as
  arguments. Selection handling belongs in `jeffy/ui/actions.py`.
- Joints are created with `jeffy.joints.tools.create_joint` (never
  `cmds.joint`, which parents to the current selection).
- Names go through `jeffy.core.naming` (`naming.compose(name, side, type)`).
- Pure math lives in `jeffy.core.mathlib` / `jeffy.deformers.weights` /
  `jeffy.geometry.symmetry` so it can be unit tested.
- Every user-facing entry point is a function in `jeffy/ui/actions.py`
  decorated with `@tool("Label")`, which gives one undo chunk and friendly errors.

## Where to add things

| You want to add... | Put it in |
|---|---|
| a control shape | `controls/library.py` (`SHAPES` + `CATEGORIES`). Tests validate it automatically |
| a rigging system | a new module in `rig/`, an action in `ui/actions.py`, a button in `ui/pages/rigging_page.py` |
| a validation check | a `Check` subclass with `@register` in `utils/checks.py` |
| an auto-rig component | a module in `autorig/components/`, registered with `@components.register`, imported in `autorig/components/__init__.py::_load_builtins` |
| a template | `autorig/templates.py` (`TEMPLATES`) |
| a menu entry | `ui/menu.py` (`MENU`) |
| a shelf button | `ui/shelf.py` (`BUTTONS`) |

`tests/test_ui.py` fails if the menu, shelf or a page references an action
that doesn't exist.

### Writing an auto-rig component

```python
from jeffy.autorig import components
from jeffy.autorig.components.base import Component
from jeffy.controls.control import Control


@components.register
class WingComponent(Component):
    TYPE = "wing"
    DEFAULT_SIDE = "L"
    GUIDES = [("root", (20, 150, -10), None), ("mid", (60, 150, -15), "root"), ("tip", (100, 150, -20), "mid")]
    SETTINGS = {"feathers": 5}

    def build_skeleton(self, parent):
        positions = [self.position(label) for label in ("root", "mid", "tip")]
        self.joints = self.create_chain(["root", "mid", "tip"], positions, parent=parent)
        self.bind_joints = self.joints[:-1]

    def build_rig(self):
        ...  # create controls under self.controls_group, systems under self.systems_group
        self.add_output("tip", tip_control.node, self.joints[-1])
```

## Releasing a new version

1. Update `scripts/jeffy/version.py` (semantic versioning: MAJOR for breaking
   API changes, MINOR for new tools, PATCH for fixes).
2. Move the `[Unreleased]` notes in `CHANGELOG.md` under a new version heading
   (`tests/test_imports.py` checks that the current version is in the changelog).
3. Commit, tag (`git tag v1.1.0`) and push with tags.
4. Users update with `git pull`. The module file points at the repository, so
   there's nothing to reinstall.
