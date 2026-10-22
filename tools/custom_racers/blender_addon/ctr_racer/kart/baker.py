# =========================================================================
# MODULE: kart — baker
# =========================================================================
"""Fase 2: bake the current material to a 112x107 image, cut it into
9 pieces, and write to the preset folder. Each piece can be saved
as a plain RGB PNG (Sentinel path) or quantized to 16 colors
(legacy paletted path).

Output layout:
    <kart_presets_root>/<variant_dir>/<preset_name>/kart_00.png
                                                  /kart_01.png
                                                  ...
                                                  /kart_08.png

The node graph is untouched: a temporary Image Texture node is added
only for the duration of the bake and removed afterwards.

Coordinate convention:
    The cutter coords in templates.py are in GIMP convention
    (top-left origin), which is the same as PIL's crop system. No
    Y-flip is applied. Blender's image.pixels uses bottom-left origin,
    but we never touch that API here -- we save the bake to a PNG and
    let PIL do the crop.
"""
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
    """Return the mesh object that owns `material`."""
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        for slot in obj.material_slots:
            if slot.material is material:
                return obj
    return None


def _bake_to_image(context, material, width, height):
    """Bake the material into a temp image datablock and return it.

    Adds a target Image Texture node, sets it active, runs the bake
    with the same settings as the original kart_editor.py, then
    removes the node. The image datablock survives.
    """
    # Drop a stale temp image if one is left over.
    old = bpy.data.images.get(_BAKE_TMP_NAME)
    if old is not None:
        bpy.data.images.remove(old)

    baked = bpy.data.images.new(_BAKE_TMP_NAME, width=width, height=height,
                                alpha=True)

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
        # Object mode is required by bpy.ops.object.bake.
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
        # Restore.
        scene.render.engine  = prev_engine
        scene.cycles.device  = prev_device
        scene.cycles.samples = prev_samples
        if prev_active is not None:
            context.view_layer.objects.active = prev_active
        nodes.remove(target_node)

    return baked


def _save_piece(piece, out_path, output_mode):
    """Save one cropped piece.

    SENTINEL: plain RGB, no quantization. The kart preset loader
    decodes the PNG through Blender's standard image path, so no
    palette limit applies and the full baked colors are preserved.

    PALETTED: quantize to 16 colors with dither disabled. Matches the
    behaviour of the original 16_color_reset.py. Only useful when the
    output has to feed a legacy paletted loader.
    """
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
    """
    Save `baked_img` to a temp PNG, calculate UV bounds for each material,
    cut the image dynamically, and write each piece to `out_dir/<name>.png`.
    """
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
        width, height = full.size

        # Obtener la capa de UVs
        uv_layer = obj.data.uv_layers.active.data
        if not uv_layer:
            raise RuntimeError("No active UV map found on the mesh")

        # Mapeo de nombres (ej. "kart_top" -> "hi_kart_00")
        # Asumimos que las zonas en templates.py tienen el nombre del material
        # pero aquí simplemente iteramos los materials del objeto.
        
        applied = 0
        for mat_slot in obj.material_slots:
            mat = mat_slot.material
            if not mat: continue
            
            # Buscar los límites de esta textura en la malla
            min_x, min_y, max_x, max_y = 1.0, 1.0, 0.0, 0.0
            found_faces = False
            
            for poly in obj.data.polygons:
                if poly.material_index == mat_slot.index:
                    found_faces = True
                    for loop_idx in poly.loop_indices:
                        u, v = uv_layer[loop_idx].uv
                        min_x = min(min_x, u)
                        min_y = min(min_y, v)
                        max_x = max(max_x, u)
                        max_y = max(max_y, v)
            
            if not found_faces:
                continue
                
            # Convertir UV a coordenadas de píxeles para PIL (Y invertida)
            px_min_x = int(min_x * width)
            px_max_x = int(max_x * width)
            px_min_y = int((1.0 - max_y) * height)
            px_max_y = int((1.0 - min_y) * height)
            
            # Ajustar límites al tamaño de la imagen (por errores de redondeo)
            px_min_x = max(0, min(px_min_x, width - 1))
            px_max_x = max(1, min(px_max_x, width))
            px_min_y = max(0, min(px_min_y, height - 1))
            px_max_y = max(1, min(px_max_y, height))
            
            # Recortar y guardar
            if px_max_x > px_min_x and px_max_y > px_min_y:
                piece = full.crop((px_min_x, px_min_y, px_max_x, px_max_y))
                
                # El nombre final del archivo se toma del nombre del material
                out_name = mat.name.split('.')[0]
                if out_name.endswith('png'): out_name = out_name[:-4]
                
                _save_piece(piece, out_dir / f"{out_name}.png", output_mode)
                applied += 1

        return applied
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
def _safe_dirname(name):
    keep = "-_. ()"
    return "".join(c if (c.isalnum() or c in keep) else "_" for c in name).strip()


class NFR_OT_KartBakeAndExport(bpy.types.Operator):
    bl_idname = "nfr.kart_bake_and_export"
    bl_label = "Bake & Export"
    bl_description = (
        "Bake the current colors, cut into 9 pieces, save to the "
        "preset folder"
    )

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
            self.report({'ERROR'},
                        "Set 'Kart presets folder' in addon preferences")
            return {'CANCELLED'}
        root = Path(root_str)
        if not root.is_dir():
            self.report({'ERROR'}, f"Preset folder does not exist: {root}")
            return {'CANCELLED'}

        tpl = KART_TEMPLATES.get(state.template_option)
        if tpl is None:
            self.report({'ERROR'}, f"Unknown template: {state.template_option}")
            return {'CANCELLED'}

        variant_dir = tpl["variant_dirs"].get(state.variant)
        if variant_dir is None:
            self.report({'ERROR'}, f"Unknown variant: {state.variant}")
            return {'CANCELLED'}

        mat = bpy.data.materials.get(state.material_name)
        if mat is None or not mat.use_nodes:
            self.report({'ERROR'}, "Material lost -- reimport template")
            return {'CANCELLED'}

        # --- Bake --------------------------------------------------
        try:
            baked = _bake_to_image(context, mat, *tpl["bake_size"])
        except Exception as e:
            self.report({'ERROR'}, f"Bake failed: {e}")
            return {'CANCELLED'}

        # --- Cut + save --------------------------------------------
        out_dir = root / variant_dir / preset_name
        try:
            n = _cut_quantize_save(baked, tpl["cutter"], out_dir,
                                   state.output_mode)
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