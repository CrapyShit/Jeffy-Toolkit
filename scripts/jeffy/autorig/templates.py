"""Built-in guide templates.

A template is a list of component descriptions; positions come from each
component's defaults (authored for a ~180 cm tall Y-up character facing +Z)
unless overridden. ``scale`` resizes the whole template.
"""

from jeffy.autorig import components, guides
from jeffy.core import mathlib, naming


def _component(component_type, name, side, parent="", settings=None, positions=None):
    return {"type": component_type, "name": name, "side": side, "parent": parent, "settings": settings or {},
            "positions": positions or {}}


TEMPLATES = {
    "biped": [
        _component("root", "root", "C"),
        _component("spine", "spine", "C", "C_root.root"),
        _component("neck", "neck", "C", "C_spine.chest"),
        _component("jaw", "jaw", "C", "C_neck.head"),
        _component("eyes", "eyes", "C", "C_neck.head"),
        _component("arm", "arm", "L", "C_spine.chest"),
        _component("arm", "arm", "R", "C_spine.chest"),
        _component("hand", "hand", "L", "L_arm.hand"),
        _component("hand", "hand", "R", "R_arm.hand"),
        _component("leg", "leg", "L", "C_spine.hips"),
        _component("leg", "leg", "R", "C_spine.hips"),
    ],
    "simple_biped": [
        _component("root", "root", "C"),
        _component("spine", "spine", "C", "C_root.root", {"joint_count": 4, "fk_controls": 2}),
        _component("neck", "neck", "C", "C_spine.chest", {"neck_joints": 1}),
        _component("arm", "arm", "L", "C_spine.chest", {"twist_joints": 0}),
        _component("arm", "arm", "R", "C_spine.chest", {"twist_joints": 0}),
        _component("hand", "hand", "L", "L_arm.hand", {"fingers": "thumb,index,middle", "metacarpals": False}),
        _component("hand", "hand", "R", "R_arm.hand", {"fingers": "thumb,index,middle", "metacarpals": False}),
        _component("leg", "leg", "L", "C_spine.hips", {"twist_joints": 0}),
        _component("leg", "leg", "R", "C_spine.hips", {"twist_joints": 0}),
    ],
    "prop": [
        _component("root", "root", "C"),
        _component("control", "prop", "C", "C_root.root", {"shape": "cube", "control_size": 10.0},
                   {"control": (0.0, 10.0, 0.0)}),
    ],
}
TEMPLATES["biped_with_tail"] = TEMPLATES["biped"] + [
    _component("chain", "tail", "C", "C_spine.hips", {"count": 8, "mode": "spline", "spline_controls": 4},
               {"c%02d" % (i + 1): (0.0, 95.0 - i * 2.0, -10.0 - 9.0 * i) for i in range(8)}),
]


def list_templates():
    return sorted(TEMPLATES)


def template_data(name):
    """Full template data (positions resolved) for :func:`guides.load_template`."""
    result = []
    for entry in TEMPLATES[name]:
        component_class = components.get(entry["type"])
        settings = dict(component_class.SETTINGS)
        settings.update(entry["settings"])
        positions = component_class.default_positions(entry["side"], settings)
        for label, position in entry["positions"].items():
            positions[label] = mathlib.reflect(position, "x") if entry["side"] == naming.SIDE_RIGHT else position
        result.append({
            "type": entry["type"],
            "name": entry["name"],
            "side": entry["side"],
            "parent": entry["parent"],
            "settings": settings,
            "positions": positions,
            "size": 2.0,
        })
    return {"components": result}


def create(name="biped", scale=1.0, replace=True):
    """Create the guides of a built-in template."""
    if name not in TEMPLATES:
        raise KeyError("Unknown template %r (available: %s)" % (name, ", ".join(list_templates())))
    return guides.load_template(template_data(name), replace=replace, scale=scale)
