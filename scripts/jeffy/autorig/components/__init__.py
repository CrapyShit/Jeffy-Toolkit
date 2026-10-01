"""Auto-rig components and their registry.

Built-in components are registered on import. Third party / studio
components can be added with :func:`register`::

    from jeffy.autorig import components
    from jeffy.autorig.components.base import Component

    @components.register
    class Wing(Component):
        TYPE = "wing"
        ...
"""

_REGISTRY = {}


def register(component_class):
    _REGISTRY[component_class.TYPE] = component_class
    return component_class


def get(component_type):
    _load_builtins()
    if component_type not in _REGISTRY:
        raise KeyError("Unknown component type %r (known: %s)" % (component_type, ", ".join(sorted(_REGISTRY))))
    return _REGISTRY[component_type]


def available():
    _load_builtins()
    return dict(_REGISTRY)


_loaded = {"value": False}


def _load_builtins():
    if _loaded["value"]:
        return
    _loaded["value"] = True
    from jeffy.autorig.components import (  # noqa: F401 - imported for registration
        arm,
        chain,
        eyes,
        hand,
        jaw,
        leg,
        neck,
        root,
        single,
        spine,
    )
