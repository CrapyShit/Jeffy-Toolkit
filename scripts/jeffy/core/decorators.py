"""Context managers and decorators used by every tool.

* :func:`undo_chunk` / :func:`undoable` - one undo step per tool.
* :func:`keep_selection` - restore the user's selection afterwards.
* :func:`no_refresh` - suspend viewport refresh for speed.
* :func:`tool` - the decorator used by UI/menu actions: undo chunk, error
  reporting in the viewport and the script editor.
"""

import contextlib
import functools
import traceback

from maya import cmds

from jeffy.core import logger

LOG = logger.get_logger("tools")


@contextlib.contextmanager
def undo_chunk(name="jeffy"):
    """Group every command executed inside the block into a single undo."""
    cmds.undoInfo(openChunk=True, chunkName=name)
    try:
        yield
    finally:
        cmds.undoInfo(closeChunk=True)


def undoable(func):
    """Decorator version of :func:`undo_chunk`."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with undo_chunk(func.__name__):
            return func(*args, **kwargs)

    return wrapper


@contextlib.contextmanager
def keep_selection():
    selection = cmds.ls(selection=True, long=True) or []
    try:
        yield selection
    finally:
        existing = [node for node in selection if cmds.objExists(node)]
        if existing:
            cmds.select(existing, replace=True)
        else:
            cmds.select(clear=True)


@contextlib.contextmanager
def no_refresh():
    """Suspend viewport refresh (big speed up for heavy operations)."""
    cmds.refresh(suspend=True)
    try:
        yield
    finally:
        cmds.refresh(suspend=False)


@contextlib.contextmanager
def autokey_off():
    state = cmds.autoKeyframe(query=True, state=True)
    cmds.autoKeyframe(state=False)
    try:
        yield
    finally:
        cmds.autoKeyframe(state=state)


@contextlib.contextmanager
def at_time(frame):
    """Temporarily go to ``frame`` (restores the current time afterwards)."""
    current = cmds.currentTime(query=True)
    cmds.currentTime(frame, edit=True)
    try:
        yield
    finally:
        cmds.currentTime(current, edit=True)


@contextlib.contextmanager
def unlocked(plugs):
    """Temporarily unlock attributes (``['node.tx', ...]``)."""
    locked = [plug for plug in plugs if cmds.getAttr(plug, lock=True)]
    for plug in locked:
        cmds.setAttr(plug, lock=False)
    try:
        yield
    finally:
        for plug in locked:
            if cmds.objExists(plug):
                cmds.setAttr(plug, lock=True)


@contextlib.contextmanager
def wait_cursor():
    cmds.waitCursor(state=True)
    try:
        yield
    finally:
        cmds.waitCursor(state=False)


def message(text, position="topCenter", fade=True):
    """Show a short message in the viewport (silently ignored in batch)."""
    try:
        cmds.inViewMessage(assistMessage=text, position=position, fade=fade)
    except Exception:  # batch mode / no UI
        pass


class ToolError(RuntimeError):
    """Raise this for user errors (bad selection...). Shown without traceback."""


def tool(label=None, undo=True, keep_sel=False):
    """Decorator for user facing entry points (menus, buttons, shelf).

    * wraps the call in an undo chunk,
    * reports :class:`ToolError` as a friendly warning,
    * logs unexpected exceptions with a full traceback,
    * never lets an exception escape into Qt (which would be swallowed).
    """

    def decorator(func):
        name = label or func.__name__.replace("_", " ").title()

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                if undo:
                    with undo_chunk(name):
                        if keep_sel:
                            with keep_selection():
                                return func(*args, **kwargs)
                        return func(*args, **kwargs)
                return func(*args, **kwargs)
            except ToolError as error:
                cmds.warning("[Jeffy] %s: %s" % (name, error))
                message("<hl>%s</hl>: %s" % (name, error))
            except Exception as error:  # pragma: no cover - interactive only
                LOG.error("%s failed: %s\n%s", name, error, traceback.format_exc())
                cmds.warning("[Jeffy] %s failed: %s (see Script Editor)" % (name, error))
            return None

        wrapper.tool_label = name
        return wrapper

    return decorator


def require_selection(minimum=1, maximum=None, node_type=None, flatten=False):
    """Return the selection or raise :class:`ToolError` if it is invalid."""
    kwargs = {"selection": True, "long": False, "flatten": flatten}
    if node_type:
        kwargs["type"] = node_type
    selection = cmds.ls(**kwargs) or []
    if len(selection) < minimum:
        what = node_type or "object"
        raise ToolError("Select at least %d %s(s)" % (minimum, what))
    if maximum is not None and len(selection) > maximum:
        raise ToolError("Select at most %d object(s)" % maximum)
    return selection
