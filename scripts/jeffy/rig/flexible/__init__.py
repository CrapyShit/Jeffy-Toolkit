"""Flexible rig tools (after antCGi's "Create a Flexible Rig" course).

Each builder recreates one setup of the course exactly as it is built in the
course's own scenes:

* :mod:`~jeffy.rig.flexible.limb` - IK/FK limb, ``IK_FK_Switch`` + reverse node,
  distance/condition stretch on ``scaleX``, non-rotating bind helper joints.
* :mod:`~jeffy.rig.flexible.spine` - direct spine (COG, hips, one control per joint).
* :mod:`~jeffy.rig.flexible.fingers` - plain FK fingers following the wrist.
* :mod:`~jeffy.rig.flexible.ribbon` - ribbon limb (9 follicles, 5 control joints
  with aim setup, sine/twist blendshape layer, toon controls) and the elbow/knee
  crease fix.
* :mod:`~jeffy.rig.flexible.foot` - node based reverse foot (roll with break /
  straight / end angles, bank, twists, toe tap).
* :mod:`~jeffy.rig.flexible.structure` - master control and VIZ switches.

These differ from the toolkit's own builders (``jeffy.rig.ikfk``,
``jeffy.rig.ribbon``...) in how they are made and how they behave; both are
available in the UI (the flexible ones in the *Advanced* tabs).
"""
