# =========================================================================
# MODULE: kart — baker
# =========================================================================
"""Fase 2: bake the current material to a 112x107 image, cut it into
9 pieces, quantize each to 16 colors, and write to the preset folder.

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


def _cut_quantize_save(baked_img, cutter, out_dir):
    """Save `baked_img` to a temp PNG, cut it, quantize, write each
    piece to `out_dir/<name>.png`. Returns the number of pieces.

    Coordinate convention: PIL and GIMP both use top-left origin, so
    the cutter coords are used as-is (no Y-flip).

    Quantization: convert to RGB first (drop alpha) so PIL doesn't
    reserve a palette slot for transparency, and use dither=NONE so
    the palette stays strictly at 16 entries. Matches the behaviour
    of the original 16_color_reset.py.
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

        # Force RGB (drop alpha channel entirely). The kart has no
        # transparency, and keeping RGBA would make PIL reserve one
        # of the 16 palette slots for the alpha marker.
        full = PIL_Image.open(tmp_path).convert("RGB")

        for out_name, (xmin, ymin, xmax, ymax) in cutter:
            piece = full.crop((xmin, ymin, xmax, ymax))
            piece = piece.convert(
                "P",
                palette=PIL_Image.ADAPTIVE,
                colors=16,
                dither=PIL_Image.NONE,
            )
            piece.save(out_dir / f"{out_name}.png")

        return len(cutter)
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
        "Bake the current colors, cut into 9 pieces, quantize to 16 "
        "colors, save to the preset folder"
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

        # --- Cut + quantize + save ---------------------------------
        out_dir = root / variant_dir / preset_name
        try:
            n = _cut_quantize_save(baked, tpl["cutter"], out_dir)
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