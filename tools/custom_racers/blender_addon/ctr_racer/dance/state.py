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
from bpy.props import CollectionProperty, IntProperty, StringProperty
from bpy.types import PropertyGroup


class NFR_DanceSfxEntry(PropertyGroup):
    """One per-frame SFX trigger for a custom podium dance.

    Mirrors the sfx.bin layout written by NFR_OT_DanceBuildSfx:
    entries are sorted by frame at build time, and the slot index in
    sfx.bin matches the file name sfx_<slot>.wav. The C-side
    (NativeCustomRacer_TickDanceSfx) fires CDSYS_XAPlay on the first
    frame transition that matches a target."""

    frame: IntProperty(
        name="Frame",
        min=0,
        default=0,
        description="Frame index within the dance clip (0-based, "
                    "same as the Blender timeline when Start=0)",
    )
    wav_path: StringProperty(
        name="WAV",
        subtype="FILE_PATH",
        default="",
        description="WAV played when the dance reaches this frame",
    )


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

    # Per-frame SFX list (up to NATIVE_DANCE_SFX_MAX = 16). The build
    # operator sorts by frame, dedups, writes sfx.bin + sfx_<i>.wav,
    # then runs the pipeline. Win and loose share this list.
    sfx_entries: CollectionProperty(type=NFR_DanceSfxEntry)


_classes = (NFR_DanceSfxEntry, NFR_DanceState)


def register():
    for c in _classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.nfr_dance = bpy.props.PointerProperty(type=NFR_DanceState)


def unregister():
    del bpy.types.Scene.nfr_dance
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)