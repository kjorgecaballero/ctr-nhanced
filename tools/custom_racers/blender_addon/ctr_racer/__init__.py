# =========================================================================
# MODULE: ctr_racer — package init
# =========================================================================
"""CTR Racer Blender addon.

Top-level orchestrator. Pure wiring: no functional code lives here.
Each subpackage owns its own register()/unregister().
"""
bl_info = {
    "name": "CTR Racer",
    "author": "kjorgecaballero",
    "version": (2, 0, 0),
    "blender": (3, 2, 0),
    "location": "View3D > Sidebar > Racer",
    "description": "Custom racer export + kart template editor for CTR nhanced",
    "category": "Import-Export",
}

from . import prefs, core, render, slots, export, kart, anim, dance, items, sfx, voices, levels, ui, adventure
from .core.icons import _teardown_previews


def register():
    register_empty_slots_props()
    bpy.utils.register_class(CTR_OT_SaveEmptyIcon)
    prefs.register()
    core.register()      # Object.racer PointerProperty + NFR_RacerProps
    render.register()
    adventure.register()    # Scene/Material props + render operators
    slots.register()     # slot operators
    export.register()    # export operators
    kart.register()      # kart template importer + Scene.kart_state
    anim.register()      # animation-clip UX (Create Actions, Jump to clip)
    dance.register()     # custom podium dance export
    items.register()      # custom mask model + beam export (Scene.nfr_mask)
    sfx.register()       # custom kart SFX export (Scene.nfr_sfx)
    voices.register()    # custom voiceline WAV export (Scene.nfr_voices)
    levels.register()
    ui.register()        # panel


def unregister():
    bpy.utils.unregister_class(CTR_OT_SaveEmptyIcon)
    unregister_empty_slots_props()
    _teardown_previews()
    ui.unregister()
    levels.unregister()
    voices.unregister()
    sfx.unregister()
    items.unregister()
    dance.unregister()
    anim.unregister()
    kart.unregister()
    export.unregister()
    slots.unregister()
    adventure.unregister()
    render.unregister()
    core.unregister()
    prefs.unregister()



# ==========================================
# EMPTY SLOT FALLBACK (UI + CONVERTER)
# ==========================================
import bpy
import os
import shutil
from pathlib import Path
from .constants import ADDON_ID
import struct

def register_empty_slots_props():
    bpy.types.Scene.empty_slot_mode = bpy.props.EnumProperty(
        name="Empty Slots",
        items=[
            ('0', "Retail", "Show retail character"),
            ('1', "Blank", "Show empty box"),
            ('2', "Custom", "Show custom icon")
        ],
        default='0'
    )
    bpy.types.Scene.empty_slot_icon_path = bpy.props.StringProperty(
        name="Icon Path",
        subtype='FILE_PATH'
    )

def unregister_empty_slots_props():
    if hasattr(bpy.types.Scene, "empty_slot_mode"):
        del bpy.types.Scene.empty_slot_mode
    if hasattr(bpy.types.Scene, "empty_slot_icon_path"):
        del bpy.types.Scene.empty_slot_icon_path

class CTR_OT_SaveEmptyIcon(bpy.types.Operator):
    bl_idname = "ctr.save_empty_icon"
    bl_label = "Save Config"
    
    def execute(self, context):
        scene = context.scene
        prefs = context.preferences.addons[ADDON_ID].preferences
        repo_path = Path(prefs.repo_path)
        
        # 1. ALWAYS write the mode to ctr_native.cfg
        cfg_path = repo_path / "assets" / "ctr_native.cfg"
        mode = scene.empty_slot_mode
        
        try:
            lines = []
            if cfg_path.exists():
                with open(cfg_path, "r", newline="") as f:
                    lines = [l for l in f.readlines() if not l.startswith("empty_slot_mode=")]
            lines.append(f"empty_slot_mode={mode}\n")
            with open(cfg_path, "w", newline="\n") as f:
                f.writelines(lines)
            self.report({'INFO'}, f"Mode {mode} saved to {cfg_path.name}")
        except Exception as e:
            self.report({'ERROR'}, f"CFG error: {e}")
            return {'CANCELLED'}

        # 2. If Mode 2 (Custom), convert and save icon.bin
        if mode == '2':
            if not scene.empty_slot_icon_path:
                self.report({'WARNING'}, "Custom mode selected, but no image provided.")
                return {'FINISHED'}
                
            src = Path(bpy.path.abspath(scene.empty_slot_icon_path))
            if not src.exists():
                self.report({'ERROR'}, f"File not found: {src}")
                return {'CANCELLED'}

            try:
                img = bpy.data.images.load(str(src))
                img.scale(44, 26)
                w, h = img.size
                pixels = img.pixels[:]

                data = bytearray()
                data.extend(struct.pack("<I", w))
                data.extend(struct.pack("<I", h))

                # Vertical flip (Blender goes bottom-to-top)
                for row in range(h - 1, -1, -1):
                    for col in range(w):
                        i = (row * w + col) * 4
                        r = int(pixels[i] * 255)
                        g = int(pixels[i+1] * 255)
                        b = int(pixels[i+2] * 255)
                        a = int(pixels[i+3] * 255)
                        data.extend([r, g, b, a])

                dest_dir = repo_path / "assets" / "mods" / "racers" / "empty_slot"
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_file = dest_dir / "icon.bin"

                with open(dest_file, "wb") as f:
                    f.write(data)

                bpy.data.images.remove(img)
                self.report({'INFO'}, f"Icon saved to {dest_file}")
            except Exception as e:
                self.report({'ERROR'}, f"Image conversion failed: {e}")
                return {'CANCELLED'}
        
        return {'FINISHED'}
