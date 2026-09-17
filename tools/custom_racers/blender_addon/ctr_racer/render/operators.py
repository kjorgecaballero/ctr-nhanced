# =========================================================================
# MODULE: render — operators
# =========================================================================
"""Render operators and materials pagination operators.

Owns:
  - six _nfr_* mode/interpolation helpers
  - NFR_OT_TogglePS1Render, NFR_OT_SetBackface, NFR_OT_ApplyBlendMode
  - NFR_OT_MatPrevPage, NFR_OT_MatNextPage
  - NFR_OT_ToggleDoubleSided, NFR_OT_ApplyRacerBlendMode

bmesh is imported locally inside the two operators that need it, as
in the original code.
"""
import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator

from .. import state
from ..constants import _BLEND_MODE_SET
from ..core.helpers import _redraw_view3d
from .color_attrs import (
    _nfr_ensure_attribute_exists,
    _nfr_ensure_all_objects_have_color_attributes,
)
from .material_setup import NFR_PS1MaterialFactory


# ---------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------
def _nfr_detect_mode_from_suffix(name):
    if name.endswith("_0"):
        return 'HALF_TRANSPARENT'
    elif name.endswith("_1"):
        return 'ADDITIVE'
    elif name.endswith("_2"):
        return 'SUBTRACTIVE'
    return 'ADDITIVE_TRANSLUCENT'


def _nfr_save_current_modes():
    count = 0
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        if hasattr(mat, 'nfr_ps1_blend_mode') and mat.nfr_ps1_blend_mode != 'NONE':
            mat.nfr_ps1_last_active_mode = mat.nfr_ps1_blend_mode
            count += 1
    return count


def _nfr_restore_last_modes():
    count = 0
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        if hasattr(mat, 'nfr_ps1_last_active_mode') and mat.nfr_ps1_last_active_mode != 'NONE':
            mat.nfr_ps1_blend_mode = mat.nfr_ps1_last_active_mode
            count += 1
    return count


def _nfr_setup_ps1_materials(context):
    _nfr_ensure_all_objects_have_color_attributes("Color")
    processed = set()
    count = 0
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        for slot in obj.material_slots:
            mat = slot.material
            if not mat or not mat.use_nodes or not mat.node_tree:
                continue
            if mat in processed:
                continue
            processed.add(mat)
            if hasattr(mat, 'nfr_ps1_blend_mode') and mat.nfr_ps1_blend_mode != 'NONE':
                mode = mat.nfr_ps1_blend_mode
            else:
                mode = 'ADDITIVE_TRANSLUCENT'
                mat.nfr_ps1_blend_mode = mode
            try:
                setup = NFR_PS1MaterialFactory.get_material_setup(mat, mode)
                if setup.apply_setup():
                    count += 1
            except Exception as e:
                print(f"[NFR] material setup error on '{mat.name}': {e}")
    context.view_layer.update()
    return count


def _nfr_restore_standard_materials(context):
    processed = set()
    count = 0
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        for slot in obj.material_slots:
            mat = slot.material
            if not mat or not mat.use_nodes or not mat.node_tree:
                continue
            if mat in processed:
                continue
            processed.add(mat)

            nodes = mat.node_tree.nodes
            links = mat.node_tree.links

            img_node = next((n for n in nodes if n.type == 'TEX_IMAGE'), None)
            out_node = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
            if not out_node:
                continue

            for n in list(nodes):
                if n not in [img_node, out_node]:
                    nodes.remove(n)

            if img_node:
                principled = nodes.new(type='ShaderNodeBsdfPrincipled')
                principled.location = (0, 0)
                try:
                    if 'Specular' in principled.inputs:
                        principled.inputs['Specular'].default_value = 0.0
                except Exception:
                    pass
                try:
                    links.new(img_node.outputs['Color'], principled.inputs['Base Color'])
                    links.new(principled.outputs['BSDF'], out_node.inputs['Surface'])
                except Exception as e:
                    print(f"[NFR] restore link warning '{mat.name}': {e}")

            try:
                mat.blend_method = 'OPAQUE'
            except Exception:
                pass
            mat.use_backface_culling = False
            count += 1

    context.view_layer.update()
    return count


def _nfr_set_interpolation(mode):
    count = 0
    for mat in bpy.data.materials:
        if mat.use_nodes and mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE':
                    if node.interpolation != mode:
                        node.interpolation = mode
                        count += 1
    return count


# ---------------------------------------------------------------------
# render operators
# ---------------------------------------------------------------------
class NFR_OT_TogglePS1Render(Operator):
    bl_idname = "nfr.ps1_toggle_render"
    bl_label = "Toggle Render"
    bl_description = ("Activate/deactivate PS1-style material override, "
                      "vertex color attributes, closest interpolation and "
                      "color management")

    def execute(self, context):
        scene = context.scene
        if scene.nfr_ps1_render_active:
            # ---- OFF ----
            _nfr_save_current_modes()
            processed = _nfr_restore_standard_materials(context)
            _nfr_set_interpolation('Linear')
            if hasattr(scene, 'eevee') and hasattr(scene.eevee, 'use_shadows'):
                scene.eevee.use_shadows = scene.nfr_ps1_prev_shadow_state
            scene.nfr_ps1_render_active = False
            scene.nfr_ps1_render_state = False
            scene.view_settings.view_transform = 'Standard'
            scene.view_settings.look = 'None'

            for obj in bpy.data.objects:
                if obj.type == 'MESH':
                    obj.data.update_tag()
            for mat in bpy.data.materials:
                if mat.use_nodes and mat.node_tree:
                    mat.node_tree.update_tag()
            bpy.context.view_layer.update()
            try:
                bpy.context.evaluated_depsgraph_get().update()
            except Exception:
                pass
            _redraw_view3d(context)

            self.report({'INFO'},
                        f"Render OFF. {processed} materials restored.")
        else:
            # ---- ON ----
            detected = 0
            for mat in bpy.data.materials:
                if hasattr(mat, 'nfr_ps1_blend_mode') and mat.nfr_ps1_blend_mode == 'NONE':
                    suffix_mode = _nfr_detect_mode_from_suffix(mat.name)
                    if suffix_mode != 'ADDITIVE_TRANSLUCENT':
                        mat.nfr_ps1_blend_mode = suffix_mode
                        detected += 1
            restored = _nfr_restore_last_modes()
            processed = _nfr_setup_ps1_materials(context)
            _nfr_set_interpolation('Closest')

            scene.view_settings.view_transform = 'Standard'
            scene.view_settings.look = 'None'

            if hasattr(scene, 'eevee') and hasattr(scene.eevee, 'use_shadows'):
                scene.nfr_ps1_prev_shadow_state = scene.eevee.use_shadows
                scene.eevee.use_shadows = False

            if context.area and context.area.type == 'VIEW_3D':
                for space in context.area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type = 'RENDERED'
                        space.overlay.show_overlays = False

            scene.nfr_ps1_render_active = True
            scene.nfr_ps1_render_state = True

            for obj in bpy.data.objects:
                if obj.type == 'MESH':
                    obj.data.update_tag()
            for mat in bpy.data.materials:
                if mat.use_nodes and mat.node_tree:
                    mat.node_tree.update_tag()
            bpy.context.view_layer.update()
            try:
                bpy.context.evaluated_depsgraph_get().update()
            except Exception:
                pass
            _redraw_view3d(context)

            self.report({'INFO'},
                        f"Render ON. {detected} detected, {restored} restored, {processed} processed.")
        return {'FINISHED'}


class NFR_OT_SetBackface(Operator):
    bl_idname = "nfr.ps1_set_backface"
    bl_label = "Set Backface Visibility"
    bl_description = "Show or hide backfaces on selected materials"
    bl_options = {'REGISTER', 'UNDO'}

    show: BoolProperty(name="Show Backfaces", default=True)

    def execute(self, context):
        import bmesh
        processed = set()

        if context.mode == 'EDIT_MESH' and context.tool_settings.mesh_select_mode[2]:
            has_sel = False
            for edit_obj in context.objects_in_mode:
                if edit_obj.type != 'MESH':
                    continue
                bm = bmesh.from_edit_mesh(edit_obj.data)
                sel_faces = [f for f in bm.faces if f.select]
                if sel_faces:
                    has_sel = True
                    mat_idxs = set(f.material_index for f in sel_faces)
                    for idx in mat_idxs:
                        if idx < len(edit_obj.material_slots):
                            mat = edit_obj.material_slots[idx].material
                            if mat and mat not in processed:
                                mat.nfr_ps1_show_backface = self.show
                                mat.use_backface_culling = not self.show
                                processed.add(mat)
            if not has_sel:
                self.report({'INFO'}, "No faces selected in edit mode")
                return {'CANCELLED'}
        else:
            for sel_obj in context.selected_objects:
                if sel_obj.type != 'MESH':
                    continue
                for slot in sel_obj.material_slots:
                    mat = slot.material
                    if mat and mat not in processed:
                        mat.nfr_ps1_show_backface = self.show
                        mat.use_backface_culling = not self.show
                        processed.add(mat)

        context.view_layer.update()
        self.report({'INFO'},
                    f"Backfaces {'visible' if self.show else 'hidden'} on "
                    f"{len(processed)} material(s)")
        return {'FINISHED'}


class NFR_OT_ApplyBlendMode(Operator):
    bl_idname = "nfr.ps1_apply_blend_mode"
    bl_label = "Apply Blend Mode"
    bl_description = "Apply selected blend mode to selected materials"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import bmesh
        scene = context.scene
        mode = scene.nfr_ps1_blend_mode
        obj = context.active_object

        selected_names = set()

        if context.mode == 'EDIT_MESH' and obj and obj.type == 'MESH':
            bm = bmesh.from_edit_mesh(obj.data)
            sel_faces = [f for f in bm.faces if f.select]
            if not sel_faces:
                self.report({'WARNING'}, "No faces selected.")
                return {'CANCELLED'}
            mat_idxs = set(f.material_index for f in sel_faces)
            for idx in mat_idxs:
                if idx < len(obj.material_slots):
                    mat = obj.material_slots[idx].material
                    if mat:
                        selected_names.add(mat.name)
            if not selected_names:
                self.report({'WARNING'}, "Selected faces have no materials.")
                return {'CANCELLED'}
        else:
            for mat in bpy.data.materials:
                if hasattr(mat, 'select_get') and mat.select_get():
                    selected_names.add(mat.name)
            if not selected_names:
                for obj_sel in context.selected_objects:
                    if obj_sel.type == 'MESH' and obj_sel.active_material:
                        selected_names.add(obj_sel.active_material.name)
            if not selected_names and context.active_object and context.active_object.active_material:
                selected_names.add(context.active_object.active_material.name)
            if not selected_names:
                self.report({'WARNING'}, "No materials selected.")
                return {'CANCELLED'}

        applied = 0
        for mat_name in selected_names:
            material = bpy.data.materials.get(mat_name)
            if not material or not material.use_nodes:
                continue
            cur_bf = getattr(material, 'nfr_ps1_show_backface', False)
            material.nfr_ps1_blend_mode = mode
            material.nfr_ps1_show_backface = cur_bf
            if scene.nfr_ps1_render_active:
                try:
                    setup = NFR_PS1MaterialFactory.get_material_setup(material, mode)
                    setup.apply_setup()
                except Exception as e:
                    self.report({'WARNING'}, f"Material '{material.name}': {e}")
                    continue
            applied += 1

        if context.active_object and context.active_object.type == 'MESH':
            _nfr_ensure_attribute_exists(context.active_object, "Color")

        context.view_layer.update()
        self.report({'INFO'}, f"Applied '{mode}' to {applied} material(s).")
        return {'FINISHED'}


# ---------------------------------------------------------------------
# materials pagination operators
# ---------------------------------------------------------------------
class NFR_OT_MatPrevPage(Operator):
    bl_idname = "nfr.mat_prev_page"
    bl_label = "Previous materials page"
    bl_description = "Show the previous page of materials"

    def execute(self, context):
        if state._mat_view_page > 1:
            state._mat_view_page -= 1
            _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_MatNextPage(Operator):
    bl_idname = "nfr.mat_next_page"
    bl_label = "Next materials page"
    bl_description = "Show the next page of materials"

    def execute(self, context):
        state._mat_view_page += 1
        _redraw_view3d(context)
        return {"FINISHED"}


# ---------------------------------------------------------------------
# materials panel operators
# ---------------------------------------------------------------------
class NFR_OT_ToggleDoubleSided(Operator):
    bl_idname = "nfr.toggle_double_sided"
    bl_label = "Show/Hide Backface"
    bl_description = ("Toggle backface visibility for this material only. "
                      "Hidden = cull backfaces; Shown = double-sided.")

    material_name: StringProperty()

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            return {"CANCELLED"}
        mat = obj.data.materials.get(self.material_name)
        if mat is None:
            self.report({"WARNING"}, f"Material '{self.material_name}' not found")
            return {"CANCELLED"}

        new_show = not getattr(mat, 'nfr_ps1_show_backface', False)
        mat.nfr_ps1_show_backface = new_show
        mat.use_backface_culling = not new_show

        _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_ApplyRacerBlendMode(Operator):
    bl_idname = "nfr.racer_apply_blend_mode"
    bl_label = "Apply"
    bl_description = ("Apply the selected racer blend mode to this material. "
                      "If Render is active, also rebuild the PS1 shader.")

    material_name: StringProperty()

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            return {"CANCELLED"}
        mat = obj.data.materials.get(self.material_name)
        if mat is None:
            self.report({"WARNING"}, f"Material '{self.material_name}' not found")
            return {"CANCELLED"}

        mode = getattr(mat, "nfr_racer_blend_mode", "half")
        if mode not in _BLEND_MODE_SET:
            mode = "half"
        if mat.get("blend_mode") != mode:
            mat["blend_mode"] = mode

        scene = context.scene
        if scene.nfr_ps1_render_active:
            mode_map = {
                'half':     'HALF_TRANSPARENT',
                'add':      'ADDITIVE',
                'subtract': 'SUBTRACTIVE',
                'add_25':   'ADDITIVE_TRANSLUCENT',
            }
            ps1_mode = mode_map.get(mode, 'ADDITIVE_TRANSLUCENT')
            cur_bf = getattr(mat, 'nfr_ps1_show_backface', False)
            mat.nfr_ps1_blend_mode = ps1_mode
            mat.nfr_ps1_show_backface = cur_bf
            try:
                setup = NFR_PS1MaterialFactory.get_material_setup(mat, ps1_mode)
                setup.apply_setup()
            except Exception as e:
                self.report({"WARNING"}, f"Material '{mat.name}': {e}")
                return {"CANCELLED"}

        _redraw_view3d(context)
        self.report({"INFO"}, f"Applied '{mode}' to '{mat.name}'")
        return {"FINISHED"}


# ---------------------------------------------------------------------
# registration
# ---------------------------------------------------------------------
_classes = (
    NFR_OT_TogglePS1Render,
    NFR_OT_SetBackface,
    NFR_OT_ApplyBlendMode,
    NFR_OT_MatPrevPage,
    NFR_OT_MatNextPage,
    NFR_OT_ToggleDoubleSided,
    NFR_OT_ApplyRacerBlendMode,
)


def register():
    for c in _classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)