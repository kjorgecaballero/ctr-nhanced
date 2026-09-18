# =========================================================================
# MODULE: kart — package init
# =========================================================================
"""Kart template editor.

Fase 1: import + color pickers.
Fase 2: bake + cut + quantize + save to preset folder.
Fase 3 (planned): preset browser.
"""
from . import state, importer, baker


def register():
    state.register()
    importer.register()
    baker.register()


def unregister():
    baker.unregister()
    importer.unregister()
    state.unregister()