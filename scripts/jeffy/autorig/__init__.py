"""Guide based modular auto-rigger.

Workflow::

    from jeffy.autorig import templates, guides, builder
    templates.create("biped")              # 1. create guides
    # 2. move the guide markers to fit your character (left side + centre)
    guides.mirror_all("L")                 # 3. mirror left guides to the right
    builder.build("hero")                  # 4. build
    builder.rebuild("hero")                # tweak guides -> rebuild any time

Components: root, spine, neck, arm, leg, hand, chain, eyes, jaw, control.
Write your own by subclassing
:class:`jeffy.autorig.components.base.Component`.
"""
