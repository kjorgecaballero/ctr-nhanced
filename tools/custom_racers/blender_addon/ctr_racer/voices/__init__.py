# =========================================================================
# MODULE: voices — subpackage
# =========================================================================
"""Custom voiceline UI: pick WAVs per event, run build_voice_pipeline.py."""
from . import state, operators


def register():
    state.register()
    operators.register()


def unregister():
    operators.unregister()
    state.unregister()