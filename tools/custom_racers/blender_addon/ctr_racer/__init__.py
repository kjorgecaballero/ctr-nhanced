# =========================================================================
# MODULE: bl_info
# =========================================================================
bl_info = {
    "name": "CTR Racer",
    "author": "kjorgecaballero",
    "version": (2, 0, 0),
    "blender": (3, 2, 0),
    "location": "View3D > N > Racer",
    "description": "Configure and export custom CTR racers",
    "category": "Import-Export",
}

# =========================================================================
# MODULE: imports
# =========================================================================
from . import prefs
from . import core
from . import render
from . import slots
from . import export
from . import ui
from .core.icons import _teardown_previews

# =========================================================================
# MODULE: registration
# =========================================================================

def register():
    prefs.register()
    core.register()
    render.register()
    slots.register()
    export.register()
    ui.register()

def unregister():
    _teardown_previews()
    ui.unregister()
    export.unregister()
    slots.unregister()
    render.unregister()
    core.unregister()
    prefs.unregister()

