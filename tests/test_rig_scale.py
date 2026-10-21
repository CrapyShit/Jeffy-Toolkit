# ruff: noqa: F811 - pytest fixtures imported from test_rig_builds
"""Global rig scale: every action multiplies its control sizes by it."""

import pytest

from test_rig_builds import cmds, geometry, make_arm, run  # noqa: F401


@pytest.fixture
def rig_scale():
    from jeffy.core import settings

    settings.reset()
    yield settings
    settings.reset()


@pytest.fixture
def shape_sizes(monkeypatch):
    """Record the size every control shape is built at."""
    from jeffy.controls import library

    sizes = []
    original = library.transform_shape

    def spy(curves, size=1.0, *args, **kwargs):
        sizes.append(size)
        return original(curves, size, *args, **kwargs)

    monkeypatch.setattr(library, "transform_shape", spy)
    return sizes


def test_setting_round_trip(rig_scale):
    import jeffy

    assert jeffy.get_rig_scale() == 1.0
    jeffy.set_rig_scale(0.25)
    assert jeffy.get_rig_scale() == 0.25
    rig_scale.load()  # read back from disk
    assert jeffy.get_rig_scale() == 0.25
    with pytest.raises(ValueError):
        jeffy.set_rig_scale(0)
    rig_scale.set("rig_scale", "nonsense")
    assert rig_scale.rig_scale() == 1.0


def test_create_controls_scaled(cmds, rig_scale, shape_sizes):
    from jeffy.ui import actions

    cmds.select(clear=True)
    run(actions.create_controls, shape="circle", size=2.0)
    rig_scale.set_rig_scale(0.1)
    cmds.select(clear=True)
    run(actions.create_controls, shape="circle", size=2.0)
    assert shape_sizes == pytest.approx([2.0, 0.2])


@pytest.mark.parametrize("action", ["build_flexible_ribbon", "build_flexible_limb", "build_ikfk"])
def test_setups_scaled(geometry, rig_scale, shape_sizes, action):
    cmds = geometry
    from jeffy.ui import actions

    builds = []
    for scale, prefix in ((1.0, "A"), (0.1, "B")):
        rig_scale.set_rig_scale(scale)
        del shape_sizes[:]
        arm = make_arm(cmds, names=(prefix + "_upArm_JNT", prefix + "_foreArm_JNT", prefix + "_hand_JNT"))
        cmds.select(arm)
        run(getattr(actions, action))
        builds.append(list(shape_sizes))
    full, scaled = builds
    assert full and len(full) == len(scaled)
    assert scaled == pytest.approx([size * 0.1 for size in full])
