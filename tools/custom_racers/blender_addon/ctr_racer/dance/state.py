# =========================================================================
# MODULE: dance — state
# =========================================================================
"""Per-scene dance-tab state.

Owns NFR_DanceState (Scene.nfr_dance):
  - slug        : racer folder name the dance belongs to
  - win_start   : first frame of the win (rank 0) dance animation
  - win_end     : last  frame of the win dance animation
  - loose_start : first frame of the loose (rank 1-2) dance animation
  - loose_end   : last  frame of the loose dance animation

Both variants share the same mesh, materials and Sentinel textures.
Only the timeline (frame range) and the output filename change.
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

    # Rank 0 / 1st place
    win_start: IntProperty(
        name="Win Start", min=0, default=0,
        description="First frame of the win (rank 0) dance animation",
    )
    win_end: IntProperty(
        name="Win End", min=0, default=45,
        description="Last frame of the win (rank 0) dance animation",
    )

    # Ranks 1-2 / 2nd-3rd place
    loose_start: IntProperty(
        name="Loose Start", min=0, default=46,
        description="First frame of the loose (rank 1-2) dance animation",
    )
    loose_end: IntProperty(
        name="Loose End", min=0, default=90,
        description="Last frame of the loose (rank 1-2) dance animation",
    )

    # Podium music (optional). One WAV per custom, played at rank 0.
    # Copied to <slug>/music/podium.wav by NFR_OT_DanceBuildMusic.
    podium_music_path: StringProperty(
        name="Podium Music",
        description="Optional WAV for the podium music (rank 0). "
                    "Exported to <slug>/music/podium.wav",
        subtype="FILE_PATH",
        default="",
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