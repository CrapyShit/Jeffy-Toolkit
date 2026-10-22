"""Setup Belt: stackable setup tools that rig the skeleton you built yourself.

Build the bind skeleton first (no controls). Then each tool turns the joints
you give it into one clean setup, and layer tools stack on top of setups that
already exist. Everything is matrix based (no constraint nodes) and every
setup can be deleted (the skeleton goes back to its rest pose) or rebuilt
with new options.

Window::

    import jeffy.setups
    jeffy.setups.show()

Python::

    from jeffy.setups.tools.rig_base import RigBase
    from jeffy.setups.tools.fk_chain import FkChain
    from jeffy.setups.tools.ikfk_limb import IkFkLimb
    from jeffy.setups.tools.spaces import Spaces

    RigBase.build(root_joint="C_root_JNT", name="hero")
    FkChain.build(start="L_clavicle_JNT")                       # mirror=True by default
    arm = IkFkLimb.build(start="L_shoulder_JNT", mid="L_elbow_JNT", end="L_wrist_JNT", name="arm")
    Spaces.build(control="L_armIK_CTL", targets=["C_root_CTL", "C_global_CTL"])
    arm.rebuild(options={"knee": "no-flip"})
    arm.delete()

See ``docs/setup_belt.md``.
"""


def show(*args, **kwargs):
    """Open the Setup Belt window."""
    from jeffy.ui.setup_belt import window

    return window.show(*args, **kwargs)


def tools():
    """``{type: tool class}`` of every registered tool, in belt order."""
    from jeffy.setups.core import scene

    return scene.load_tools()


def find(node):
    """The setup a node belongs to (control, output, group, tag or driven joint)."""
    from jeffy.setups.core import scene

    return scene.find_setup(node)


def all_setups():
    from jeffy.setups.core import scene

    return scene.all_setups()
