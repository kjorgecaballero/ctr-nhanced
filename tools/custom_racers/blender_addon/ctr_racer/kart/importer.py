# =========================================================================
# MODULE: kart — importer
# =========================================================================
"""Kart template importer.

Reproduces the exact node graph of the original standalone script
(tools/custom_racers/blender_addon/kart_editor.py), but:
  - paths come from the bundled assets, not from C:\\Users\\...
  - the 4 RGB nodes are tagged so the panel can edit them
  - reimporting is idempotent (wipes the previous kart first)

The graph is:
    image[atlas]  -> overlay[atlas]  <- rgb[atlas]   -> mix[atlas]   (Fac=0.0)
    image[pipes]  -> overlay[pipes]  <- rgb[pipes]   -> mix[pipes]   (Fac=0.0)
    image[extra1] -> overlay[extra1] <- rgb[extra1]  -> mix[extra1]  (Fac=0.3)
    image[extra2] -> overlay[extra2] <- rgb[extra2]  -> mix[extra2]  (Fac=0.3)

    add1 = mix[atlas]  + mix[pipes]
    add3 = mix[extra1] + mix[extra2]
    out  = add1 + add3 -> Material Output
"""
import bpy
from pathlib import Path

from ..core.helpers import _redraw_view3d
from .templates import KART_TEMPLATES


_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "kart_template"


def _load_png(png_name):
    return bpy.data.images.load(str(_ASSETS_DIR / png_name), check_existing=True)


def _wipe_previous_kart(material_prefix):
    """Remove any mesh object that owns a material matching the
    template prefix, then purge orphaned materials and images that
    carry the same prefix. Keeps the scene idempotent across
    reimports and avoids `.001` suffixes on the FBX import."""
    to_remove = []
    for obj in list(bpy.context.scene.objects):
        if obj.type != 'MESH':
            continue
        for slot in obj.material_slots:
            m = slot.material
            if m and m.name.startswith(material_prefix):
                to_remove.append(obj)
                break
    for obj in to_remove:
        bpy.data.objects.remove(obj, do_unlink=True)

    # Purge orphaned materials matching the prefix.
    for mat in list(bpy.data.materials):
        if mat.name.startswith(material_prefix) and mat.users == 0:
            bpy.data.materials.remove(mat, do_unlink=True)


def _find_template_material(material_prefix):
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        for slot in obj.material_slots:
            m = slot.material
            if m and m.use_nodes and m.name.startswith(material_prefix):
                return m
    return None


def _build_graph(material, images_by_slot):
    """Rebuild the kart node graph verbatim.

    Returns a list of (slot_name, rgb_node) in graph order, so the
    caller can tag/restore colors on the correct nodes.
    """
    nodes = material.node_tree.nodes
    links = material.node_tree.links

    for n in list(nodes):
        nodes.remove(n)

    slot_order = ["atlas", "pipes", "extra1", "extra2"]
    # MixShader Fac per slot: 0.0 for the two solid zones, 0.3 for the
    # two tint zones (verbatim from kart_editor.py).
    mix_fac = {"atlas": 0.0, "pipes": 0.0, "extra1": 0.3, "extra2": 0.3}

    tex_nodes, rgb_nodes, overlay_nodes, mix_nodes = {}, {}, {}, {}

    for i, slot in enumerate(slot_order):
        y = 200 - 200 * i

        tex = nodes.new('ShaderNodeTexImage')
        tex.location = (-800, y)
        tex.image = images_by_slot[slot]
        tex_nodes[slot] = tex

        rgb = nodes.new('ShaderNodeRGB')
        rgb.location = (-400, y)
        rgb.outputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
        rgb_nodes[slot] = rgb

        ov = nodes.new('ShaderNodeMixRGB')
        ov.location = (-200, y)
        ov.blend_type = 'OVERLAY'
        ov.inputs[0].default_value = 1.0
        links.new(tex.outputs['Color'], ov.inputs[1])
        links.new(rgb.outputs['Color'], ov.inputs[2])
        overlay_nodes[slot] = ov

        mix = nodes.new('ShaderNodeMixShader')
        mix.location = (0, y)
        mix.inputs[0].default_value = mix_fac[slot]
        links.new(ov.outputs['Color'], mix.inputs[1])
        mix_nodes[slot] = mix

    # Add shader tree (verbatim).
    add1 = nodes.new('ShaderNodeAddShader')
    add1.location = (400, 200)
    links.new(mix_nodes["atlas"].outputs['Shader'], add1.inputs[0])
    links.new(mix_nodes["pipes"].outputs['Shader'], add1.inputs[1])

    add3 = nodes.new('ShaderNodeAddShader')
    add3.location = (400, -200)
    links.new(mix_nodes["extra1"].outputs['Shader'], add3.inputs[0])
    links.new(mix_nodes["extra2"].outputs['Shader'], add3.inputs[1])

    add2 = nodes.new('ShaderNodeAddShader')
    add2.location = (800, 0)
    links.new(add1.outputs['Shader'], add2.inputs[0])
    links.new(add3.outputs['Shader'], add2.inputs[1])

    out = nodes.new('ShaderNodeOutputMaterial')
    out.location = (1000, 0)
    links.new(add2.outputs['Shader'], out.inputs[0])

    return [(slot, rgb_nodes[slot]) for slot in slot_order]


class NFR_OT_KartImportTemplate(bpy.types.Operator):
    bl_idname = "nfr.kart_import_template"
    bl_label = "Import Template"
    bl_description = "Import the kart template and wire the color pickers"

    def execute(self, context):
        scene = context.scene
        state = scene.kart_state

        tpl = KART_TEMPLATES.get(state.template_option)
        if tpl is None:
            self.report({'ERROR'}, f"Unknown template: {state.template_option}")
            return {'CANCELLED'}

        fbx_path = _ASSETS_DIR / tpl["fbx_name"]
        if not fbx_path.is_file():
            self.report({'ERROR'}, f"FBX not found: {fbx_path}")
            return {'CANCELLED'}

        variant = state.variant
        tex_map = tpl["variant_textures"].get(variant)
        if tex_map is None:
            self.report({'ERROR'}, f"Unknown variant: {variant}")
            return {'CANCELLED'}

        # Preserve existing colors across reimports.
        prev_colors = {z.display_name: tuple(z.color) for z in state.zones}

        # --- 1. Idempotent import ----------------------------------
        _wipe_previous_kart(tpl["material_prefix"])
        bpy.ops.import_scene.fbx(filepath=str(fbx_path))

        material = _find_template_material(tpl["material_prefix"])
        if material is None:
            self.report({'ERROR'},
                        f"No material with prefix '{tpl['material_prefix']}' "
                        f"found after import")
            return {'CANCELLED'}

        # --- 2. Rebuild the node graph -----------------------------
        material.use_nodes = True
        images_by_slot = {slot: _load_png(png) for slot, png in tex_map.items()}
        rgb_nodes_in_order = _build_graph(material, images_by_slot)

        # --- 3. Rebuild the zone list, restoring colors ------------
        state.zones.clear()
        for (zone_name, slot_name), (slot, rgb_node) in zip(
                tpl["zones"], rgb_nodes_in_order):
            assert slot_name == slot, (
                f"zone/slot order mismatch: {zone_name}/{slot_name} vs {slot}"
            )
            z = state.zones.add()
            z.display_name = zone_name
            z.node_name    = rgb_node.name
            z.color        = prev_colors.get(zone_name, (1.0, 1.0, 1.0, 1.0))
            # Apply manually -- update callbacks don't fire reliably
            # during initial assignment.
            rgb_node.outputs[0].default_value = tuple(z.color)

        state.material_name = material.name
        state.is_imported   = True

        _redraw_view3d(context)
        self.report({'INFO'},
                    f"Template '{tpl['display_name']}' imported ({variant})")
        return {'FINISHED'}


_classes = (NFR_OT_KartImportTemplate,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)