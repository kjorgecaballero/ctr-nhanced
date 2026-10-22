# =========================================================================
# MODULE: kart — importer
# =========================================================================
"""Kart template importer."""
import bpy
from pathlib import Path

from ..core.helpers import _redraw_view3d
from .templates import KART_TEMPLATES

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "kart_template"


def _load_png(png_name, subdir):
    return bpy.data.images.load(str(_ASSETS_DIR / subdir / png_name), check_existing=False)


def _wipe_previous_kart(material_prefix):
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
    nodes = material.node_tree.nodes
    links = material.node_tree.links

    for n in list(nodes):
        nodes.remove(n)

    rgb_nodes = {}
    mix_shaders = []

    for i, (slot, img) in enumerate(images_by_slot.items()):
        y = 200 - 200 * i

        tex = nodes.new('ShaderNodeTexImage')
        tex.location = (-800, y)
        tex.image = img
        tex.interpolation = 'Closest'

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

        mix = nodes.new('ShaderNodeMixShader')
        mix.location = (0, y)
        mix.inputs[0].default_value = 0.0 if i < 2 else 0.3
        links.new(ov.outputs['Color'], mix.inputs[1])
        mix_shaders.append(mix)

    # Unir todos los mix shaders
    current_shader = mix_shaders[0].outputs['Shader']
    for i, mix in enumerate(mix_shaders[1:], start=1):
        add_node = nodes.new('ShaderNodeAddShader')
        add_node.location = (400, 200 - 200 * i)
        links.new(current_shader, add_node.inputs[0])
        links.new(mix.outputs['Shader'], add_node.inputs[1])
        current_shader = add_node.outputs['Shader']

    out = nodes.new('ShaderNodeOutputMaterial')
    out.location = (800, 0)
    links.new(current_shader, out.inputs[0])

    return [(slot, rgb_nodes[slot]) for slot in images_by_slot.keys()]


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

        asset_dir = tpl.get("asset_dir", "")
        mode = state.template_mode
        
        # Forzar DEFAULT en modo USER para evitar errores de variante
        variant = state.variant if mode == "EDIT" else "DEFAULT"
        
        tex_map = tpl["variant_textures"].get(variant)
        if not tex_map:
            tex_map = list(tpl["variant_textures"].values())[0]

        fbx_name = tpl["fbx_name"] if mode == "EDIT" else tpl["fbx_name"].replace(".fbx", "_user.fbx")
        fbx_path = _ASSETS_DIR / asset_dir / fbx_name
        
        if not fbx_path.is_file():
            self.report({'ERROR'}, f"FBX not found: {fbx_path}")
            return {'CANCELLED'}

        prev_colors = {z.display_name: tuple(z.color) for z in state.zones}
        _wipe_previous_kart(tpl["material_prefix"])
        bpy.ops.import_scene.fbx(filepath=str(fbx_path))

        if mode == "USER":
            # The FBX already has embedded textures. Solo marcamos como importado y salimos.
            state.is_imported = True
            state.material_name = ""
            _redraw_view3d(context)
            self.report({'INFO'}, f"User Template '{tpl['display_name']}' imported (Textures Embedded)")
            return {'FINISHED'}

        # Modo EDIT
        material = _find_template_material(tpl["material_prefix"])
        if material is None:
            self.report({'ERROR'}, "No material found after import")
            return {'CANCELLED'}

        material.use_nodes = True
        images_by_slot = {slot: _load_png(png, asset_dir) for slot, png in tex_map.items()}
        rgb_nodes_in_order = _build_graph(material, images_by_slot)

        state.zones.clear()
        for (zone_name, slot_name), (slot, rgb_node) in zip(tpl["zones"], rgb_nodes_in_order):
            z = state.zones.add()
            z.display_name = zone_name
            z.node_name    = rgb_node.name
            z.color        = (1.0, 1.0, 1.0)
            rgb_node.outputs[0].default_value = (1.0, 1.0, 1.0, 1.0)

        state.material_name = material.name
        state.is_imported   = True

        _redraw_view3d(context)
        self.report({'INFO'}, f"Template '{tpl['display_name']}' imported ({variant})")
        return {'FINISHED'}


class NFR_OT_KartResetColors(bpy.types.Operator):
    bl_idname = "nfr.kart_reset_colors"
    bl_label = "Reset Colors"
    bl_description = "Reset all zone color pickers to white"

    def execute(self, context):
        state = context.scene.kart_state
        if not state.is_imported:
            return {'CANCELLED'}
        for z in state.zones:
            z.color = (1.0, 1.0, 1.0)
        _redraw_view3d(context)
        self.report({'INFO'}, "All kart colors reset to white")
        return {'FINISHED'}


_classes = (NFR_OT_KartImportTemplate, NFR_OT_KartResetColors)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
