"""Jeffy Toolkit startup - builds the "Jeffy" menu once Maya's UI is ready.

Maya runs every ``userSetup.py`` found on its Python path, so this file is
picked up automatically when the toolkit is installed as a Maya module.
"""


def _jeffy_toolkit_startup():
    try:
        import jeffy

        jeffy.install_menu()
    except Exception as error:  # never break Maya's startup
        print("[Jeffy] Could not create the menu: %s" % error)


try:
    from maya import cmds, utils

    if not cmds.about(batch=True):
        utils.executeDeferred(_jeffy_toolkit_startup)
except ImportError:
    pass
