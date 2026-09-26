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

    # Optional mask music loop. WAV that the pipeline encodes to
    # <slug>/mask/mask_song.vag with --rate 11025 --loop. When the
    # custom with mask=custom_good|custom_bad grabs the mask, CSEQ is
    # stopped and this VAG plays on SPU voice 29 (range
    # 0x180000-0x1A0000). Fallback to the retail Aku/Uka jingle if
    # missing.
    mask_music_path: StringProperty(
        name="Mask Music",
        description="WAV loop that plays while the mask is active. "
                    "Encoded to VAG @ 11025 Hz with --loop.",
        subtype="FILE_PATH",
        default="",
    )

    # Optional HUD icon. PNG that build_icon_bin.py converts to
    # <slug>/mask/icon.bin (RGBA8 + <II w h>). When present, the HUD
    # draws this instead of the retail Aku/Uka icon while the mask is
    # held. ~32x32 or 44x26 recommended; the C-side accepts any size
    # up to 4096x4096.
    icon_path: StringProperty(
        name="HUD Icon",
        description="Optional PNG for the mask item-slot icon",
        subtype="FILE_PATH",
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
