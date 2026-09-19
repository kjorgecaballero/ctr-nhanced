# =========================================================================
# MODULE: dance — state
# =========================================================================
"""Per-scene dance-tab state.

Owns NFR_DanceState (Scene.nfr_dance):
  - slug        : racer folder name the dance belongs to
  - frame_start : first frame of the dance animation
  - frame_end   : last frame of the dance animation
"""
import bpy
from bpy.props import IntProperty, StringProperty
from bpy.types import PropertyGroup


class NFR_DanceState(PropertyGroup):
    slug: StringProperty(
        name="Slug",
        description="Folder name of the racer this dance belongs to",
        default="",
    )
    frame_start: IntProperty(
        name="Start", min=0, default=0,
        description="First frame of the dance animation",
    )
    frame_end: IntProperty(
        name="End", min=0, default=59,
        description="Last frame of the dance animation",
    )


_classes = (NFR_DanceState,)


def register():
    for c in _classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.nfr_dance = bpy.props.PointerProperty(type=NFR_DanceState)


def unregister():
    del bpy.types.Scene.nfr_dance
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)