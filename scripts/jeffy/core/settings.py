"""Persistent user settings stored as JSON in the user data folder."""

import os

from jeffy.core import fileio

DEFAULTS = {
    "control_size": 1.0,
    "rig_scale": 1.0,
    "control_shape": "circle",
    "control_axis": "x",
    "control_line_width": 2.0,
    "offset_groups": ["ZRO"],
    "orient_aim_axis": "x",
    "orient_up_axis": "y",
    "orient_world_up": [0.0, 1.0, 0.0],
    "joint_radius": 0.5,
    "skin_max_influences": 4,
    "skin_prune_threshold": 0.01,
    "mirror_axis": "x",
    "last_export_dir": "",
    "ui_last_tab": 0,
}

_cache = {}


def _path():
    return os.path.join(fileio.user_dir(), "settings.json")


def load():
    global _cache
    data = dict(DEFAULTS)
    path = _path()
    if os.path.isfile(path):
        try:
            data.update(fileio.read_json(path))
        except (ValueError, OSError):
            pass
    _cache = data
    return data


def get(key, default=None):
    if not _cache:
        load()
    if key in _cache:
        return _cache[key]
    return DEFAULTS.get(key, default)


def set(key, value, save_now=True):  # noqa: A001 - mirrors dict API on purpose
    if not _cache:
        load()
    _cache[key] = value
    if save_now:
        save()


def save():
    try:
        fileio.write_json(_path(), _cache, precision=None)
    except OSError:
        pass


def reset():
    global _cache
    _cache = dict(DEFAULTS)
    save()


def rig_scale():
    """Global multiplier for every control shape the toolkit creates.

    Set it to fit the size of the character in the scene (for example 0.1 when
    the default shapes come out ten times too big). Always a positive float.
    """
    try:
        value = float(get("rig_scale", 1.0))
    except (TypeError, ValueError):
        return 1.0
    return value if value > 0.0 else 1.0


def set_rig_scale(value):
    value = float(value)
    if value <= 0.0:
        raise ValueError("The rig scale must be greater than 0")
    set("rig_scale", value)
    return value
