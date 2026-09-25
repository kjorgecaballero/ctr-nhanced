# =========================================================================
# MODULE: ctr_racer — package init
# =========================================================================
"""CTR Racer Blender addon.

Top-level orchestrator. Pure wiring: no functional code lives here.
Each subpackage owns its own register()/unregister().
"""
bl_info = {
    "name": "CTR Racer",
    "author": "kjorgecaballero",
    "version": (2, 0, 0),
    "blender": (3, 2, 0),
    "location": "View3D > Sidebar > Racer",
    "description": "Custom racer export + kart template editor for CTR nhanced",
    "category": "Import-Export",
}

from . import prefs, core, render, slots, export, kart, anim, dance, mask, sfx, voices, ui
from .core.icons import _teardown_previews


def register():
    prefs.register()
    core.register()      # Object.racer PointerProperty + NFR_RacerProps
    render.register()    # Scene/Material props + render operators
    slots.register()     # slot operators
    export.register()    # export operators
    kart.register()      # kart template importer + Scene.kart_state
    anim.register()      # animation-clip UX (Create Actions, Jump to clip)
    dance.register()     # custom podium dance export
    mask.register()      # custom mask model + beam export (Scene.nfr_mask)
    sfx.register()       # custom kart SFX export (Scene.nfr_sfx)
    voices.register()    # custom voiceline WAV export (Scene.nfr_voices)
    ui.register()        # panel


def unregister():
    _teardown_previews()
    ui.unregister()
    voices.unregister()
    sfx.unregister()
    mask.unregister()
    dance.unregister()
    anim.unregister()
    kart.unregister()
    export.unregister()
    slots.unregister()
    render.unregister()
    core.unregister()
    prefs.unregister()