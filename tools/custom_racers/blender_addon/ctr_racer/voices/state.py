# =========================================================================
# MODULE: voices — state
# =========================================================================
"""NFR_VoicesState: per-scene voiceline slug + WAV paths per event."""
import bpy
from bpy.props import StringProperty, PointerProperty


VOICE_EVENTS = (
    ("boost",     "Boost",     "Boost pad / turbo item"),
    ("hurt",      "Hurt",      "Hit / squashed"),
    ("spin",      "Spin",      "Spin attack"),
    ("jump",      "Jump",      "Big-air meter"),
    ("trap",      "Trap",      "Potion / TNT / crate"),
    ("protected", "Protected", "Blocked hit / shield"),
    ("overtake",  "Overtake",  "Passes a human racer"),
    ("attack",    "Attack",    "Attack item fired"),
)


class NFR_VoicesState(bpy.types.PropertyGroup):
    slug: StringProperty(name="Slug", default="")

    boost:     StringProperty(name="Boost",     subtype="FILE_PATH")
    hurt:      StringProperty(name="Hurt",      subtype="FILE_PATH")
    spin:      StringProperty(name="Spin",      subtype="FILE_PATH")
    jump:      StringProperty(name="Jump",      subtype="FILE_PATH")
    trap:      StringProperty(name="Trap",      subtype="FILE_PATH")
    protected: StringProperty(name="Protected", subtype="FILE_PATH")
    overtake:  StringProperty(name="Overtake",  subtype="FILE_PATH")
    attack:    StringProperty(name="Attack",    subtype="FILE_PATH")


_classes = (NFR_VoicesState,)


def register():
    for c in _classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.nfr_voices = PointerProperty(type=NFR_VoicesState)


def unregister():
    del bpy.types.Scene.nfr_voices
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)