# =========================================================================
# MODULE: core — racer properties
# =========================================================================
"""Racer Object properties and the Object.racer pointer.

Owns NFR_RacerProps and the PointerProperty registration on
bpy.types.Object. Registers/unregisters its own class.
"""
import bpy
from bpy.props import (
    StringProperty, IntProperty, BoolProperty,
    EnumProperty, FloatVectorProperty, PointerProperty,
)
from bpy.types import PropertyGroup

from ..constants import ENGINES


class NFR_RacerProps(PropertyGroup):
    is_racer:   BoolProperty(name="Is Racer", default=False)
    slug:       StringProperty(name="Slug", description="Folder name and internal .ctr name")
    page:       IntProperty(name="Page", default=1, min=0, max=8)
    slot:       IntProperty(name="Slot", default=0, min=0, max=17)
    engine:     EnumProperty(name="Engine", items=ENGINES, default="BALANCED")
    mask:       EnumProperty(
        name="Mask",
        description="Which mask this racer receives from item boxes",
        items=[("good",        "Good (Aku Aku)",   ""),
               ("bad",         "Bad (Uka Uka)",    ""),
               ("custom_good", "Custom (Aku Aku)", ""),
               ("custom_bad",  "Custom (Uka Uka)", "")],
        default="good")
    wheels:     EnumProperty(
        name="Wheels",
        description="Tire sprite visibility (Oxide-style hidden tires)",
        items=[("yes", "Visible",             ""),
               ("no",  "Hidden (Oxide-style)", "")],
        default="yes")
    long_name:  StringProperty(name="Long Name")
    short_name: StringProperty(name="Short Name")
    color:      FloatVectorProperty(name="Minimap Color", subtype="COLOR",
                                    default=(1.0, 1.0, 1.0), min=0.0, max=1.0)
    icon_path:  StringProperty(name="Icon PNG", subtype="FILE_PATH")

    def custom_id(self):
        # Page 0,     slots 16-17 -> 144 + (slot - 16)
        # Pages 1-8,  slots 0-15  -> 16  + (page-1)*16 + slot
        # Pages 1-8,  slots 16-17 -> 146 + (page-1)*2  + (slot - 16)
        if self.page == 0:
            return 144 + (self.slot - 16)
        if self.slot >= 16:
            return 146 + (self.page - 1) * 2 + (self.slot - 16)
        return 16 + (self.page - 1) * 16 + self.slot


_classes = (NFR_RacerProps,)


def register():
    for c in _classes:
        bpy.utils.register_class(c)
    if hasattr(bpy.types.Object, "racer"):
        del bpy.types.Object.racer
    bpy.types.Object.racer = PointerProperty(type=NFR_RacerProps)


def unregister():
    if hasattr(bpy.types.Object, "racer"):
        del bpy.types.Object.racer
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)