# =========================================================================
# MODULE: kart — importer
# =========================================================================
"""Kart template importer."""
import bpy
from pathlib import Path

from ..core.helpers import _redraw_view3d
from .templates import KART_TEMPLATES

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "kart_template"



def _force_closest_interpolation(obj):
    if not obj or obj.type != 'MESH': return
    for slot in obj.material_slots:
        if slot.material and slot.material.use_nodes:
            for node in slot.material.node_tree.nodes:
                if node.type == 'TEX_IMAGE':
                    node.interpolation = 'Closest'

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

    # Merge all mix shaders
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
        if tpl is None: return {'CANCELLED'}

        asset_dir = tpl.get("asset_dir", "")
        
        # =====================================================================
        # HOVERCRAFT (Same FBX for both modes)
        # =====================================================================
        if tpl.get("is_vertex_color"):
            fbx_path = _ASSETS_DIR / asset_dir / tpl["fbx_name"]
            if not fbx_path.is_file():
                self.report({'ERROR'}, f"FBX not found: {fbx_path}")
                return {'CANCELLED'}
                
            _wipe_previous_kart(tpl["material_prefix"])
            bpy.ops.import_scene.fbx(filepath=str(fbx_path))
            _force_closest_interpolation(context.active_object)
            
            obj = context.active_object
            if not obj:
                for o in context.selected_objects:
                    if o.type == 'MESH': obj = o; break
                    
            if obj and obj.type == 'MESH':
                if not obj.data.color_attributes:
                    obj.data.color_attributes.new(name="Color", type='BYTE_COLOR', domain='CORNER')
                obj.data.color_attributes.active_color = obj.data.color_attributes[0]
                
                target_mat_name = "969_208_18_248_4_16"
                slot_idx = -1
                for i, slot in enumerate(obj.material_slots):
                    if slot.material and target_mat_name in slot.material.name:
                        slot_idx = i; break
                        
                if slot_idx != -1:
                    mat = obj.material_slots[slot_idx].material
                    if mat and mat.use_nodes:
                        nodes = mat.node_tree.nodes
                        links = mat.node_tree.links
                        
                        # No nodes. Pure Vertex Colors.

                state.is_imported = True
                state.material_name = obj.material_slots[0].material.name if obj.material_slots else ""
                _redraw_view3d(context)
            return {'FINISHED'}

        # =====================================================================
        # NORMAL LOGIC (Kart, Hi-Kart, Velo)
        # =====================================================================
        mode = state.template_mode
        if mode == "EDIT" and not tpl.get("is_vertex_color"):
            variant = state.variant
            if variant not in tpl["variant_textures"]:
                variant = "DEFAULT"
        else:
            variant = "DEFAULT"
        tex_map = tpl["variant_textures"].get(variant, {})
        if not tex_map and tpl["variant_textures"]: tex_map = list(tpl["variant_textures"].values())[0]

        fbx_name = tpl["fbx_name"] if mode == "EDIT" else tpl["fbx_name"].replace(".fbx", "_user.fbx")
        fbx_path = _ASSETS_DIR / asset_dir / fbx_name
        if not fbx_path.is_file(): return {'CANCELLED'}

        prev_colors = {z.display_name: tuple(z.color) for z in state.zones}
        _wipe_previous_kart(tpl["material_prefix"])
        bpy.ops.import_scene.fbx(filepath=str(fbx_path))
        for o in context.selected_objects:
            _force_closest_interpolation(o)

        if mode == "USER":
            state.is_imported = True
            _redraw_view3d(context)
            return {'FINISHED'}

        material = _find_template_material(tpl["material_prefix"])
        if material:
            material.use_nodes = True
            images_by_slot = {slot: _load_png(png, asset_dir) for slot, png in tex_map.items()}
            rgb_nodes_in_order = _build_graph(material, images_by_slot)
            state.zones.clear()
            for (zone_name, slot_name), (slot, rgb_node) in zip(tpl["zones"], rgb_nodes_in_order):
                z = state.zones.add(); z.display_name = zone_name; z.node_name = rgb_node.name
                z.color = (1.0, 1.0, 1.0); rgb_node.outputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
            state.material_name = material.name
            state.is_imported = True
            _redraw_view3d(context)
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