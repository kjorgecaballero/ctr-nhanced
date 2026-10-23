# =========================================================================
# MODULE: kart — package init
# =========================================================================
"""Kart template editor.

Phase 1: import + color pickers.
Phase 2: bake + cut + quantize + save to preset folder.
Phase 3: preset browser + apply to racer.
"""
from . import state, importer, baker, presets


def register():
    state.register()
    importer.register()
    baker.register()
    presets.register()


def unregister():
    presets.unregister()
    baker.unregister()
    importer.unregister()
    state.unregister()