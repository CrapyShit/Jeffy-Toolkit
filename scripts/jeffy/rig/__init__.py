"""Rig building blocks.

=====================  ======================================================
module                 contents
=====================  ======================================================
``structure``          standard rig hierarchy, global scale, display switches
``fk``                 FK chains
``ik``                 IK with stretch, soft IK, pinning, pole vectors
``ikfk``               IK/FK limbs, blending and seamless matching
``space_switch``       dynamic parenting with seamless switching
``twist``              no-flip twist extraction and twist joints
``spline``             spline IK with stretch, volume and advanced twist
``ribbon``             ribbon (surface + follicles) setups, bendy limbs
``foot``               reverse foot (roll, bank, twists, toe tap)
``fingers``            finger controls with curl/fist/spread/relax
``aim``                eye / look-at rigs
``attach``             follicles, uvPin, rivets
``matrix_constraints`` matrix based constraints (offsetParentMatrix)
``pose_reader``        cone/twist pose readers for correctives
``dynamics``           nHair driven overlap chains
=====================  ======================================================
"""
