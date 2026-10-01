"""JSON file helpers and default data locations."""

import io
import json
import os

FORMAT_VERSION = 1


def _round(value, precision):
    if isinstance(value, float):
        return round(value, precision)
    if isinstance(value, dict):
        return {k: _round(v, precision) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_round(v, precision) for v in value]
    return value


def write_json(path, data, precision=6, indent=2):
    """Write data as JSON (floats rounded to keep files small)."""
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    if precision is not None:
        data = _round(data, precision)
    with io.open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(data, indent=indent, sort_keys=False))
    return path


def read_json(path):
    with io.open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def user_dir(*parts):
    """Folder for user data (``<maya app dir>/jeffy_toolkit``)."""
    base = None
    try:
        from maya import cmds

        base = cmds.internalVar(userAppDir=True)
    except Exception:
        base = None
    if not base or not isinstance(base, str):
        base = os.path.join(os.path.expanduser("~"), "maya")
    path = os.path.join(base, "jeffy_toolkit", *parts)
    if not os.path.isdir(path):
        try:
            os.makedirs(path)
        except OSError:
            pass
    return path


def scene_dir():
    """Folder of the current scene, or the user data folder if unsaved."""
    try:
        from maya import cmds

        scene = cmds.file(query=True, sceneName=True)
        if scene:
            return os.path.dirname(scene)
    except Exception:
        pass
    return user_dir()


def scene_basename():
    try:
        from maya import cmds

        scene = cmds.file(query=True, sceneName=True, shortName=True)
        if scene:
            return os.path.splitext(scene)[0]
    except Exception:
        pass
    return "untitled"
