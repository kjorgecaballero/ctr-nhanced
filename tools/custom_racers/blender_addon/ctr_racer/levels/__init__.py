"""Levels tab: import/export custom CTR level content."""

from . import state, operators


def register():
    state.register()
    operators.register()


def unregister():
    operators.unregister()
    state.unregister()
