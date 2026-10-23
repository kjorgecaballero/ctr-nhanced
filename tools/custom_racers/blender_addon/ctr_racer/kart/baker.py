# =========================================================================
# MODULE: kart — baker
# =========================================================================
import os
import tempfile
from pathlib import Path

import bpy

try:
    from PIL import Image as PIL_Image
except ImportError:
    PIL_Image = None

from ..prefs import _get_prefs
from ..core.helpers import _redraw_view3d
from .templates import KART_TEMPLATES


_BAKE_TMP_NAME = "__nfr_kart_bake_tmp__"


def _find_kart_object(material):
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        for slot in obj.material_slots:
            if slot.material is material:
                return obj
    return None


def _bake_to_image(context, material, width, height):
    old = bpy.data.images.get(_BAKE_TMP_NAME)
    if old is not None:
        bpy.data.images.remove(old)

    baked = bpy.data.images.new(_BAKE_TMP_NAME, width=width, height=height, alpha=True)

    nodes = material.node_tree.nodes
    target_node = nodes.new('ShaderNodeTexImage')
    target_node.image = baked
    target_node.location = (-400, -800)
    nodes.active = target_node
    target_node.select = True

    kart_obj = _find_kart_object(material)
    if kart_obj is None:
        nodes.remove(target_node)
        bpy.data.images.remove(baked)
        raise RuntimeError("kart mesh object not found for material")

    scene = context.scene
    prev_engine   = scene.render.engine
    prev_device   = scene.cycles.device
    prev_samples  = scene.cycles.samples
    prev_active   = context.view_layer.objects.active

    try:
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        scene.render.engine = 'CYCLES'
        scene.cycles.device = 'GPU'
        scene.cycles.samples = 1
        scene.render.bake.use_pass_direct = False
        scene.render.bake.use_pass_indirect = False
        scene.render.bake.use_clear = True

        bpy.ops.object.select_all(action='DESELECT')
        kart_obj.select_set(True)
        context.view_layer.objects.active = kart_obj

        bpy.ops.object.bake(type='COMBINED')
    finally:
        scene.render.engine  = prev_engine
        scene.cycles.device  = prev_device
        scene.cycles.samples = prev_samples
        if prev_active is not None:
            context.view_layer.objects.active = prev_active
        nodes.remove(target_node)

    return baked


def _save_piece(piece, out_path, output_mode):
    if output_mode == "SENTINEL":
        piece.save(out_path)
        return

    quantized = piece.convert(
        "P",
        palette=PIL_Image.ADAPTIVE,
        colors=16,
        dither=PIL_Image.NONE,
    )
    quantized.save(out_path)


def _cut_quantize_save(baked_img, tpl, obj, out_dir, output_mode="SENTINEL"):
    if PIL_Image is None:
        raise RuntimeError("Pillow (PIL) is required for the kart baker")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="nfr_kart_bake_")
    os.close(tmp_fd)
    try:
        baked_img.filepath_raw = tmp_path
        baked_img.file_format = 'PNG'
        baked_img.save()
        full = PIL_Image.open(tmp_path).convert("RGB")
        cutter = tpl.get("cutter", [])
        if not cutter:
            raise RuntimeError("No cutter coordinates found in template.")
        for out_name, (xmin, ymin, xmax, ymax) in cutter:
            piece = full.crop((xmin, ymin, xmax, ymax))
            _save_piece(piece, out_dir / f"{out_name}.png", output_mode)
        return len(cutter)
    finally:
        try: os.remove(tmp_path)
        except OSError: pass


def _safe_dirname(name):
    keep = "-_. ()"
    return "".join(c if (c.isalnum() or c in keep) else "_" for c in name).strip()


class NFR_OT_KartBakeAndExport(bpy.types.Operator):
    bl_idname = "nfr.kart_bake_and_export"
    bl_label = "Bake & Export"
    bl_description = "Bake the current colors, cut into pieces, save to the preset folder"

    def execute(self, context):
        state = context.scene.kart_state
        prefs = _get_prefs(context)

        if not state.is_imported:
            self.report({'ERROR'}, "Import a template first")
            return {'CANCELLED'}

        preset_name = _safe_dirname(state.preset_name)
        if not preset_name:
            self.report({'ERROR'}, "Give your preset a name first")
            return {'CANCELLED'}

        root_str = getattr(prefs, "kart_presets_root", "") or ""
        if not root_str:
            self.report({'ERROR'}, "Set 'Kart presets folder' in addon preferences")
            return {'CANCELLED'}
        root = Path(root_str)
        if not root.is_dir():
            self.report({'ERROR'}, f"Preset folder does not exist: {root}")
            return {'CANCELLED'}

        tpl = KART_TEMPLATES.get(state.template_option)
        if tpl is None:
            self.report({'ERROR'}, f"Unknown template: {state.template_option}")
            return {'CANCELLED'}

        # --- 1. HOVERCRAFT ---
        if tpl.get("is_vertex_color"):
            import json
            from PIL import Image as PIL_Image
            
            variant_dir = tpl.get("variant_dirs", {}).get("DEFAULT", "hovercraft/default")
            out_dir = root / variant_dir / preset_name
            out_dir.mkdir(parents=True, exist_ok=True)
            
            json_data = {
                "hue": state.hover_hue,
                "saturation": state.hover_saturation,
                "value": state.hover_value
            }
            with open(out_dir / "preset.json", "w", encoding="utf-8") as fh:
                json.dump(json_data, fh, indent=2)
                
            if PIL_Image:
                import colorsys
                r, g, b = colorsys.hsv_to_rgb(state.hover_hue, state.hover_saturation, state.hover_value)
                rgb = (int(r*255), int(g*255), int(b*255))
                PIL_Image.new("RGB", (32, 32), rgb).save(out_dir / "preview.png")
                
            self.report({'INFO'}, f"Preset saved to {out_dir}")
            return {'FINISHED'}

        # --- 2. KARTS NORMALES ---
        variant_dir = tpl.get("variant_dirs", {}).get(state.variant)
        if variant_dir is None:
            self.report({'ERROR'}, f"Unknown variant: {state.variant}")
            return {'CANCELLED'}

        mat = bpy.data.materials.get(state.material_name)
        if mat is None or not mat.use_nodes:
            self.report({'ERROR'}, "Material lost -- reimport template")
            return {'CANCELLED'}
            
        kart_obj = _find_kart_object(mat)
        if not kart_obj:
            self.report({'ERROR'}, "Kart object not found for baking")
            return {'CANCELLED'}

        # --- Bake ---
        try:
            baked = _bake_to_image(context, mat, *tpl["bake_size"])
        except Exception as e:
            self.report({'ERROR'}, f"Bake failed: {e}")
            return {'CANCELLED'}

        # --- Cut + save ---
        out_dir = root / variant_dir / preset_name
        try:
            n = _cut_quantize_save(baked, tpl, kart_obj, out_dir, state.output_mode)
        except Exception as e:
            self.report({'ERROR'}, f"Save failed: {e}")
            bpy.data.images.remove(baked)
            return {'CANCELLED'}

        bpy.data.images.remove(baked)
        _redraw_view3d(context)
        self.report({'INFO'}, f"Wrote {n} PNGs to {out_dir}")
        return {'FINISHED'}


_classes = (NFR_OT_KartBakeAndExport,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)