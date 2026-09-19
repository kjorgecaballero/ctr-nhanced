# =========================================================================
# MODULE: anim subpackage
# =========================================================================
"""Animation-clip UX: state + operators for the Anim tab."""
from . import helpers
from . import state
from . import operators


def register():
    state.register()
    operators.register()


def unregister():
    operators.unregister()
    state.unregister()