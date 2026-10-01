import pytest

from jeffy.core import naming


def test_compose_default():
    assert naming.compose("arm", "L", "control") == "L_arm_CTL"
    assert naming.compose("arm", None, "joint") == "arm_JNT"
    assert naming.compose("arm") == "arm"
    assert naming.compose("finger", "R", "joint", index=3) == "R_finger_JNT"


def test_custom_convention():
    convention = naming.NamingConvention("{name}{index}_{side}_{type}", index_padding=3)
    assert convention.compose("spine", "C", "joint", 2) == "spine002_C_JNT"
    assert convention.compose("spine", None, None) == "spine"


def test_parse():
    assert naming.parse("L_arm_CTL") == {"side": "L", "name": "arm", "type": "CTL"}
    assert naming.parse("|grp|ns:R_upper_arm_JNT") == {"side": "R", "name": "upper_arm", "type": "JNT"}
    assert naming.parse("thing") == {"side": None, "name": "thing", "type": None}


@pytest.mark.parametrize("name,expected", [
    ("L_arm_CTL", "R_arm_CTL"),
    ("R_arm_CTL", "L_arm_CTL"),
    ("arm_L_CTL", "arm_R_CTL"),
    ("L_arm_to_R_hand", "R_arm_to_L_hand"),
    ("Leg_CTL", "Leg_CTL"),
    ("left_eye", "right_eye"),
    ("Left_eye", "Right_eye"),
    ("armLeft_CTL", "armRight_CTL"),
    ("ns:L_arm_CTL", "ns:R_arm_CTL"),
    ("C_spine_CTL", "C_spine_CTL"),
    ("lf_hand", "rt_hand"),
])
def test_mirror_name(name, expected):
    assert naming.mirror_name(name) == expected


def test_short_names():
    assert naming.short_name("|a|b|ns:c") == "ns:c"
    assert naming.strip_namespace("|a|b|ns:c") == "c"
    assert naming.get_namespace("|a|ns:sub:c") == "ns:sub"
    assert naming.get_namespace("c") == ""


def test_side_from_name():
    assert naming.side_from_name("L_arm_CTL") == "L"
    assert naming.side_from_name("arm_R_CTL") == "R"
    assert naming.side_from_name("C_spine") == "C"
    assert naming.side_from_name("left_hand") == "L"
    assert naming.side_from_name("spine") is None


def test_increment_and_patterns():
    assert naming.increment_name("arm") == "arm1"
    assert naming.increment_name("arm1") == "arm2"
    assert naming.increment_name("arm_09") == "arm_10"
    assert naming.expand_pattern("finger_##_JNT", 3) == "finger_03_JNT"
    assert naming.expand_pattern("finger", 3) == "finger3"


def test_legalize():
    assert naming.legalize("my node!") == "my_node_"
    assert naming.legalize("1abc") == "_1abc"
    assert naming.legalize("   ") == "node"


def test_camel_case():
    assert naming.camel_case("upper", "arm", "twist") == "upperArmTwist"
    assert naming.camel_case() == ""


def test_mirror_side():
    assert naming.mirror_side("L") == "R"
    assert naming.mirror_side("C") == "C"
