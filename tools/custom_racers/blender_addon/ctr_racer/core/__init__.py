# =========================================================================
# MODULE: core subpackage
# =========================================================================
"""Core racer logic.

Owns: racer properties, roster I/O, icon previews, validate, and the
small helpers shared across the addon.

register()/unregister() wire up the submodules that own Blender
classes (currently only racer_props).
"""
from . import racer_props


def register():
    racer_props.register()


def unregister():
    racer_props.unregister()