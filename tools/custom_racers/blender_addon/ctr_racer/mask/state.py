# =========================================================================
# MODULE: mask — state
# =========================================================================
"""Per-scene mask-tab state.

Owns NFR_MaskState (Scene.nfr_mask):
  - slug: racer folder name the mask belongs to

Mask and beam are static (rotation is applied per-tick by
RB_MaskWeapon_ThTick), so there are no frame ranges here — the
exporter bakes a single frame from the active mesh's timeline. The
roster entry needs mask=custom_good | mask=custom_bad for the runtime
to load the .ctr files at all.
"""
import bpy
from bpy.props import StringProperty
from bpy.types import PropertyGroup


class NFR_MaskState(PropertyGroup):
    slug: StringProperty(
        name="Slug",
        description="Folder name of the racer this mask belongs to",
        default="",
    )


_classes = (NFR_MaskState,)


def register():
    for c in _classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.nfr_mask = bpy.props.PointerProperty(type=NFR_MaskState)


def unregister():
    del bpy.types.Scene.nfr_mask
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
