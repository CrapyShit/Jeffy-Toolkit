"""Logging helpers.

All toolkit loggers live under the ``jeffy`` namespace so their verbosity can
be changed in one place::

    from jeffy.core import logger
    logger.set_level("DEBUG")
"""

import logging

ROOT_NAME = "jeffy"
_FORMAT = "[%(name)s] %(levelname)s: %(message)s"


def get_logger(name=None):
    """Return a logger in the ``jeffy`` hierarchy."""
    if not name:
        full = ROOT_NAME
    elif name == ROOT_NAME or name.startswith(ROOT_NAME + "."):
        full = name
    else:
        full = "%s.%s" % (ROOT_NAME, name)
    log = logging.getLogger(full)
    root = logging.getLogger(ROOT_NAME)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        root.propagate = False
    return log


def set_level(level):
    """Set the verbosity of every toolkit logger (``"DEBUG"``, ``"INFO"``...)."""
    if isinstance(level, str):
        level = getattr(logging, level.upper())
    get_logger().setLevel(level)
