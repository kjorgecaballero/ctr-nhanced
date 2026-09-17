# =========================================================================
# MODULE: slots subpackage
# =========================================================================
"""Slot viewer: cell resolution and the seven slot-grid operators."""
from . import state
from . import operators


def register():
    operators.register()


def unregister():
    operators.unregister()