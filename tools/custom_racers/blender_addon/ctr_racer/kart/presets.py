# =========================================================================
# MODULE: kart — presets
# =========================================================================
"""Fase 3: preset browser + apply.

Scans <kart_presets_root>/<variant_dir>/<preset_name>/ and lets the
user apply a preset's kart_NN.png textures to the active racer mesh.

Replacement is by image name: for each material in the racer we look
at every TEX_IMAGE node, read the image datablock's name (with .png
and Blender's .001 duplicate suffix stripped), and if it matches
"kart_NN" where the preset has a kart_NN.png, we replace the image's
in-memory pixel buffer.

Destructive in Blender's session (the image datablock is modified).
The original PNG on disk is NOT touched.
"""
import os
import sys
import subprocess
from pathlib import Path

import bpy

from ..prefs import _get_prefs
from ..core.helpers import _redraw_view3d
from .templates import KART_TEMPLATES


_VARIANT_DIRS = tuple(set(v for tpl in KART_TEMPLATES.values() for v in tpl.get("variant_dirs", {}).values()))
_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tga", ".bmp")


def _stem(name):
    """Normalize a datablock name to its canonical stem.

    Strips extension and Blender's .NNN duplicate suffix in a loop
    (order does not matter), so 'kart_00.png.001', 'kart_00.001.png',
    'kart_00.png', and 'kart_00' all reduce to 'kart_00'.
    """
    base = name.lower()
    changed = True
    while changed:
        changed = False
        for ext in _EXTENSIONS:
            if base.endswith(ext):
                base = base[: -len(ext)]
                changed = True
                break
        head, dot, tail = base.rpartition(".")
        if dot and tail.isdigit() and len(tail) == 3:
            base = head
            changed = True
    return base


def scan_presets(root):
    """Return {variant_dir: [(name, path), ...]} for all presets."""
    root = Path(root)
    out = {}
    for variant_dir in _VARIANT_DIRS:
        vp = root / variant_dir
        if not vp.is_dir():
            continue
        items = []
        for p in sorted(vp.iterdir()):
            if p.is_dir():
                items.append((p.name, p))
        if items:
            out[variant_dir] = items
    return out


def _find_target_images(obj):
    """Return {stem: image_datablock} for every TEX_IMAGE node in
    the object's materials."""
    targets = {}
    for mat in obj.data.materials:
        if not mat or not mat.use_nodes or mat.node_tree is None:
            continue
        for node in mat.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image is not None:
                stem = _stem(node.image.name)
                if stem not in targets:
                    targets[stem] = node.image
    return targets


def _replace_image_pixels(target_img, preset_path):
    """Replace the pixel buffer of `target_img` with the preset PNG.
    If sizes mismatch slightly, auto-scale the image to fit."""
    src = bpy.data.images.load(str(preset_path), check_existing=False)
    try:
        if tuple(src.size) != tuple(target_img.size):
            # Auto-scale the image to fit (avoids size mismatch)
            print(f"Auto-resizing {preset_path.name} from {tuple(src.size)} to {tuple(target_img.size)}")
            src.scale(target_img.size[0], target_img.size[1])
            
        target_img.pixels = list(src.pixels)
        target_img.update()
    finally:
        bpy.data.images.remove(src)


class NFR_OT_KartApplyPreset(bpy.types.Operator):
    bl_idname = "nfr.kart_apply_preset"
    bl_label = "Apply Preset"
    bl_description = (
        "Replace the kart_NN textures of the active racer with the "
        "PNGs from this preset. Modifies the image datablocks in this "
        "session. The original PNGs on disk are left untouched"
    )

    preset_dir: bpy.props.StringProperty()

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH' or not obj.racer.is_racer:
            self.report({'ERROR'}, "Select a racer mesh first")
            return {'CANCELLED'}

        preset_path = Path(self.preset_dir)
        if not preset_path.is_dir():
            self.report({'ERROR'}, f"Preset not found: {preset_path}")
            return {'CANCELLED'}

        # First, check if it is a Hovercraft preset (JSON)
        json_path = preset_path / "preset.json"
        if json_path.is_file():
            try:
                import json
                import colorsys
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                h = data.get("hue", 0.5)
                s = data.get("saturation", 1.0)
                v = data.get("value", 1.0)
                
                context.scene.kart_state.hover_hue = h
                context.scene.kart_state.hover_saturation = s
                context.scene.kart_state.hover_value = v

                if not obj.data.color_attributes.active_color:
                    obj.data.color_attributes.new(name="Color", type='BYTE_COLOR', domain='CORNER')
                color_layer = obj.data.color_attributes.active_color
                
                if "orig_vcols" not in obj:
                    obj["orig_vcols"] = [list(c.color) for c in color_layer.data]
                orig_colors = obj["orig_vcols"]

                target_mat_prefix = "969_208_18_248_4_16"
                target_slot_idx = -1
                for i, slot in enumerate(obj.material_slots):
                    if slot.material and target_mat_prefix in slot.material.name:
                        target_slot_idx = i; break
                if target_slot_idx == -1: target_slot_idx = 0

                for poly in obj.data.polygons:
                    if poly.material_index == target_slot_idx:
                        for loop_idx in poly.loop_indices:
                            if loop_idx < len(orig_colors):
                                r, g, b = orig_colors[loop_idx][:3]
                                ch, cs, cv = colorsys.rgb_to_hsv(r, g, b)
                                nh = (ch + (h - 0.5)) % 1.0
                                ns = min(1.0, max(0.0, cs * s))
                                nv = min(1.0, max(0.0, cv * v))
                                nr, ng, nb = colorsys.hsv_to_rgb(nh, ns, nv)
                                color_layer.data[loop_idx].color = (nr, ng, nb, 1.0)
                
                obj.data.update()
                _redraw_view3d(context)
                self.report({'INFO'}, "Hovercraft HSV applied from JSON")
                return {'FINISHED'}
            except Exception as e:
                self.report({'ERROR'}, f"Failed to read preset.json: {e}")
                return {'CANCELLED'}

        # If not JSON, continue with PNG textures logic
        preset_files = {}
        for png in preset_path.glob("*.png"):
            preset_files[png.stem.lower()] = png

        if not preset_files:
            self.report({'ERROR'}, "Preset has no files")
            return {'CANCELLED'}

        targets = _find_target_images(obj)
        if not targets:
            self.report({'ERROR'},
                        "No TEX_IMAGE nodes in this racer's materials")
            return {'CANCELLED'}

        applied = 0
        missing = []
        errors = []
        for stem in sorted(preset_files):
            preset_png = preset_files[stem]
            target = targets.get(stem)
            if target is None:
                missing.append(stem)
                continue
            try:
                _replace_image_pixels(target, preset_png)
                applied += 1
            except Exception as e:
                errors.append(f"{stem}: {e}")

        _redraw_view3d(context)

        if errors:
            self.report({'ERROR'},
                        f"Applied {applied}, errors: {'; '.join(errors[:3])}")
            return {'FINISHED'}

        if missing:
            self.report({'WARNING'},
                        f"Applied {applied}. Missing target image(s): "
                        + ", ".join(missing))
        else:
            self.report({'INFO'}, f"Applied {applied} texture(s)")
        return {'FINISHED'}


class NFR_OT_KartOpenPresetsFolder(bpy.types.Operator):
    bl_idname = "nfr.kart_open_presets_folder"
    bl_label = "Open Presets Folder"

    def execute(self, context):
        prefs = _get_prefs(context)
        root = getattr(prefs, "kart_presets_root", "") or ""
        if not root or not os.path.isdir(root):
            self.report({'ERROR'}, "Presets folder not set or not found")
            return {'CANCELLED'}
        try:
            if sys.platform.startswith("win"):
                os.startfile(root)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", root])
            else:
                subprocess.Popen(["xdg-open", root])
        except Exception as e:
            self.report({'ERROR'}, f"Could not open folder: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}


class NFR_OT_KartPresetPrevPage(bpy.types.Operator):
    bl_idname = "nfr.kart_preset_prev_page"
    bl_label = "Previous Preset Page"

    def execute(self, context):
        st = context.scene.kart_state
        st.preset_page = max(1, st.preset_page - 1)
        _redraw_view3d(context)
        return {'FINISHED'}


class NFR_OT_KartPresetNextPage(bpy.types.Operator):
    bl_idname = "nfr.kart_preset_next_page"
    bl_label = "Next Preset Page"

    def execute(self, context):
        st = context.scene.kart_state
        st.preset_page = st.preset_page + 1   # clamped in _draw_presets
        _redraw_view3d(context)
        return {'FINISHED'}


_classes = (
    NFR_OT_KartApplyPreset,
    NFR_OT_KartOpenPresetsFolder,
    NFR_OT_KartPresetPrevPage,
    NFR_OT_KartPresetNextPage,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)