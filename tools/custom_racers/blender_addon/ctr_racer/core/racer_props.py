# =========================================================================
# MODULE: core — racer properties
# =========================================================================
"""Racer Object properties and the Object.racer pointer.

Owns NFR_RacerProps and the PointerProperty registration on
bpy.types.Object. Registers/unregisters its own class.
"""
import bpy
from bpy.props import (
    StringProperty, IntProperty, BoolProperty, FloatProperty,
    EnumProperty, FloatVectorProperty, PointerProperty,
)
from bpy.types import PropertyGroup

from ..constants import ENGINES



def update_rot_preview(self, context):
    obj = context.active_object
    if obj and obj.type == 'MESH' and obj.racer.is_racer:
        import math
        if obj.racer.kart_rot == 'custom' and getattr(obj.racer, 'jump_rot_preview', True):
            obj.delta_rotation_euler[0] = math.radians(obj.racer.jump_rot_pitch)
            obj.delta_rotation_euler[1] = math.radians(obj.racer.jump_rot_yaw)
            obj.delta_rotation_euler[2] = math.radians(obj.racer.jump_rot_roll)
        else:
            obj.delta_rotation_euler = (0, 0, 0)

class NFR_RacerProps(PropertyGroup):
    is_racer:   BoolProperty(name="Is Racer", default=False)
    slug:       StringProperty(name="Slug", description="Folder name and internal .ctr name")
    page:       IntProperty(name="Page", default=1, min=0, max=8)
    slot:       IntProperty(name="Slot", default=0, min=0, max=23)
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
    kart_rot:   EnumProperty(
        name="Kart Rotation",
        description="Airborne rotation matrices style",
        items=[
            ("auto", "Auto (By clip length)", ""),
            ("none", "None (No baked rotation)", ""),
            ("crash", "Crash", ""),
            ("cortex", "Cortex", ""),
            ("tiny", "Tiny", ""),
            ("coco", "Coco", ""),
            ("ngin", "N. Gin", ""),
            ("dingodile", "Dingodile", ""),
            ("polar", "Polar", ""),
            ("pura", "Pura", ""),
            ("tropy", "N. Tropy", ""),
            ("pinstripe", "Pinstripe", ""),
            ("ripper", "Ripper Roo", ""),
            ("papu", "Papu Papu", ""),
            ("joe", "Komodo Joe", ""),
            ("custom", "Custom", "")
        ],
        default="auto", update=update_rot_preview)
    long_name:  StringProperty(name="Long Name")
    short_name: StringProperty(name="Short Name")
    color:      FloatVectorProperty(name="Minimap Color", subtype="COLOR",
                                    default=(1.0, 1.0, 1.0), min=0.0, max=1.0)

    jump_rot_preview: BoolProperty(name="Preview in Viewport", default=True, update=update_rot_preview)
    jump_rot_pitch: FloatProperty(name="Pitch (Up/Down)", default=45.0, min=-90.0, max=90.0, subtype='FACTOR', update=update_rot_preview)
    jump_rot_roll: FloatProperty(name="Roll (Sideways)", default=0.0, min=-90.0, max=90.0, subtype='FACTOR', update=update_rot_preview)
    jump_rot_yaw: FloatProperty(name="Yaw (Spin)", default=0.0, min=-90.0, max=90.0, subtype='FACTOR', update=update_rot_preview)
    jump_rot_pivot_z: FloatProperty(name="Pivot Height (Z)", default=0.35, min=0.0, max=2.0)
    jump_rot_frames: IntProperty(name="Rotation Frames", default=4, min=2, max=10)

    icon_path:  StringProperty(name="Icon PNG", subtype="FILE_PATH")

    def custom_id(self):
        # Page 0,     slots 16-23 -> 144 + (slot - 16)
        # Pages 1-8,  slots 0-15  -> 16  + (page-1)*16 + slot
        # Pages 1-8,  slots 16-23 -> 152 + (page-1)*8 + (slot - 16)
        if self.page == 0:
            return 144 + (self.slot - 16)
        if self.slot >= 16:
            return 152 + (self.page - 1) * 8 + (self.slot - 16)
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