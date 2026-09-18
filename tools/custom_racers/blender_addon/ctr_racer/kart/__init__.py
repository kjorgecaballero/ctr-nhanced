# =========================================================================
# MODULE: kart — package init
# =========================================================================
"""Kart template editor.

Fase 1: import the bundled FBX template, wire the node graph, expose
the 4 editable RGB nodes as color pickers in the panel.

No bake, no presets yet (those are Fase 2 / Fase 3).
"""
from . import state, importer


def register():
    state.register()
    importer.register()


def unregister():
    importer.unregister()
    state.unregister()