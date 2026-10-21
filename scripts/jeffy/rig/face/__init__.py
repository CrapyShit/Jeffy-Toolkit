"""Face rigging tools.

Built in this order (antCGi style joint / ribbon face, plus blendshapes):

* :mod:`ribbon` - face ribbons for lips, brows, cheek lines: one skin joint
  per vertex on a ribbon shaped by a few controls.
* :mod:`curve_rig` - curve rigs from an edge loop; eyelids aimed from the
  eye centre, lips that need a seal.
* :mod:`blink` - eyelid blink (``blink`` / ``blinkHeight``) and lip seal
  (``seal`` / ``sealHeight``) on two curve rigs.
* :mod:`jaw` - jaw control; the lips and corners follow it by percentages.
* :mod:`follow` - partial follow (cheeks after lip corners, nose after the
  upper lip...) and fleshy eyes (lids rotating with the eye).
* :mod:`surface_controls` - controls riding on the face mesh driving joints,
  without double transforms.
* :mod:`sliders` - slider controls and face boards driving blendshapes.
"""
