# =========================================================================
# MODULE: sfx — state
# =========================================================================
"""Per-scene SFX-tab state.

Owns NFR_SfxState (Scene.nfr_sfx):
  - slug: racer folder name the SFX belong to
  - 11 StringProperty FILE_PATH, one per NATIVE_KART_SFX_* event

Same UX as voicelines: each custom ships WAVs in <slug>/sfx/<event>.wav.
The pipeline (build_voice_pipeline.py) encodes them to .vag at 11025 Hz
and the C-side loads them into SPU at race start.
"""
import bpy
from bpy.props import StringProperty
from bpy.types import PropertyGroup


# Slot names must match NATIVE_KART_SFX_* in
# include/platform/native_custom_racer.h and KART_SFX_EVENTS in
# tools/custom_racers/build_voice_pipeline.py.
SFX_EVENTS = [
    ("boost",           "Boost / Turbo fire"),
    ("warp",            "Warp pad"),
    ("overrev",         "Engine over-rev"),
    ("mask_grab",       "Mask grab whistle"),
    ("missile_launch",  "Missile launch"),
    ("bomb_launch",     "Bomb launch"),
    ("mine_drop",       "TNT / Nitro drop"),
    ("shield",          "Shield pickup"),
    ("clock",           "Clock pickup"),
    ("warpball",        "Warpball launch"),
    ("invisibility",    "Invisibility pickup"),
    ("engine",          "Engine loop (continuous, 8000 Hz, --loop)"),
]


class NFR_SfxState(PropertyGroup):
    slug: StringProperty(
        name="Slug",
        description="Folder name of the racer these SFX belong to",
        default="",
    )

    wav_boost: StringProperty(
        name="Boost",
        description="Custom boost fire SFX (replaces retail SOUND 0x0d)",
        subtype="FILE_PATH", default="")
    wav_warp: StringProperty(
        name="Warp",
        description="Custom warp pad SFX (replaces retail SOUND 0x97)",
        subtype="FILE_PATH", default="")
    wav_overrev: StringProperty(
        name="Over-rev",
        description="Custom engine over-rev SFX (replaces retail SOUND 0x0f)",
        subtype="FILE_PATH", default="")
    wav_mask_grab: StringProperty(
        name="Mask grab",
        description="Custom mask grab whistle (replaces retail SOUND 0x55)",
        subtype="FILE_PATH", default="")
    wav_missile_launch: StringProperty(
        name="Missile launch",
        description="Custom missile launch SFX (replaces retail SOUND 0x4a)",
        subtype="FILE_PATH", default="")
    wav_bomb_launch: StringProperty(
        name="Bomb launch",
        description="Custom bomb launch SFX (replaces retail SOUND 0x47)",
        subtype="FILE_PATH", default="")
    wav_mine_drop: StringProperty(
        name="Mine drop",
        description="Custom TNT/Nitro drop SFX (replaces retail SOUND 0x52)",
        subtype="FILE_PATH", default="")
    wav_shield: StringProperty(
        name="Shield",
        description="Custom shield pickup SFX (replaces retail SOUND 0x57)",
        subtype="FILE_PATH", default="")
    wav_clock: StringProperty(
        name="Clock",
        description="Custom clock pickup SFX (replaces retail SOUND 0x44)",
        subtype="FILE_PATH", default="")
    wav_warpball: StringProperty(
        name="Warpball",
        description="Custom warpball launch SFX (replaces retail SOUND 0x4d)",
        subtype="FILE_PATH", default="")
    wav_invisibility: StringProperty(
        name="Invisibility",
        description="Custom invisibility SFX (replaces retail SOUND 0x61)",
        subtype="FILE_PATH", default="")
    wav_engine: StringProperty(
        name="Engine loop",
        description=("Continuous engine hum, pitch-modulated by speed. "
                     "Encoded to VAG @ 8000 Hz with --loop."),
        subtype="FILE_PATH", default="")


_classes = (NFR_SfxState,)


def register():
    for c in _classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.nfr_sfx = bpy.props.PointerProperty(type=NFR_SfxState)


def unregister():
    del bpy.types.Scene.nfr_sfx
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)