# =========================================================================
# MODULE: render subpackage
# =========================================================================
"""Render-related modules.

Owns: PS1 node setups, material setup, color attribute helpers,
property registration and render operators.
"""
from . import props
from . import operators


def register():
    props.register()
    operators.register()


def unregister():
    operators.unregister()
    props.unregister()