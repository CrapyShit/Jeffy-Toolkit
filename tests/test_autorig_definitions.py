"""Static checks of the auto-rig components and templates (no Maya)."""

import pytest

from jeffy.autorig import builder, components, templates

EXPECTED_TYPES = {"root", "spine", "neck", "arm", "leg", "hand", "chain", "eyes", "jaw", "control"}


def test_registry():
    assert EXPECTED_TYPES.issubset(set(components.available()))
    with pytest.raises(KeyError):
        components.get("nope")


@pytest.mark.parametrize("component_type", sorted(EXPECTED_TYPES))
def test_guide_definitions(component_type):
    component_class = components.get(component_type)
    definitions = component_class.guide_definitions(dict(component_class.SETTINGS))
    assert definitions, "component %s has no guides" % component_type
    seen = set()
    for label, position, parent in definitions:
        assert label not in seen, "duplicate guide label %s" % label
        assert len(position) == 3
        assert parent is None or parent in seen, "parent %s of %s must come first" % (parent, label)
        seen.add(label)


@pytest.mark.parametrize("component_type", sorted(EXPECTED_TYPES))
def test_default_positions_mirror(component_type):
    component_class = components.get(component_type)
    left = component_class.default_positions("L")
    right = component_class.default_positions("R")
    for label, position in left.items():
        assert right[label] == pytest.approx((-position[0], position[1], position[2]))


def test_setting_dependent_guides():
    chain = components.get("chain")
    assert len(chain.guide_definitions({"count": 9})) == 9
    hand = components.get("hand")
    labels = [d[0] for d in hand.guide_definitions({"fingers": "thumb,index"})]
    assert labels[0] == "thumb01" and "index05" in labels and not any(lb.startswith("pinky") for lb in labels)


@pytest.mark.parametrize("name", templates.list_templates())
def test_templates(name):
    data = templates.template_data(name)["components"]
    full_names = {"%s_%s" % (c["side"], c["name"]) for c in data}
    assert len(full_names) == len(data), "duplicate component names in template"
    for component in data:
        component_class = components.get(component["type"])
        labels = {d[0] for d in component_class.guide_definitions(component["settings"])}
        assert labels == set(component["positions"]), "%s positions do not match its guides" % component["name"]
        if component["parent"]:
            parent_name = component["parent"].partition(".")[0]
            assert parent_name in full_names, "%s parent %s missing" % (component["name"], parent_name)


def test_sort_components_parents_first():
    def make(component_type, name, side, parent=""):
        return components.get(component_type)(name=name, side=side, parent_output=parent)

    instances = {c.full_name: c for c in [
        make("hand", "hand", "L", "L_arm.hand"),
        make("arm", "arm", "L", "C_spine.chest"),
        make("spine", "spine", "C", "C_root.root"),
        make("root", "root", "C"),
        make("chain", "tail", "C"),
    ]}
    ordered = [c.full_name for c in builder.sort_components(instances)]
    assert ordered[0] == "C_root"
    assert ordered.index("C_spine") < ordered.index("L_arm") < ordered.index("L_hand")
    assert ordered.index("C_root") < ordered.index("C_tail")


def test_sort_components_detects_cycles():
    a = components.get("chain")(name="a", side="C", parent_output="C_b.end")
    b = components.get("chain")(name="b", side="C", parent_output="C_a.end")
    with pytest.raises(ValueError):
        builder.sort_components({"C_a": a, "C_b": b})


def test_mirror_reference():
    from jeffy.autorig import guides

    assert guides.mirror_reference("L_arm.hand") == "R_arm.hand"
    assert guides.mirror_reference("C_spine.chest") == "C_spine.chest"
    assert guides.mirror_reference("") == ""
