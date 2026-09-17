# =========================================================================
# MODULE: bl_info
# =========================================================================
bl_info = {
    "name": "CTR NHanced Racer Export",
    "author": "kjorgecaballero",
    "version": (1, 8, 0),
    "blender": (3, 2, 0),
    "location": "View3D > N > Racer",
    "description": "Configure and export custom CTR racers",
    "category": "Import-Export",
}

# =========================================================================
# MODULE: imports
# =========================================================================
import bpy
import os
import json
import time
import shlex
import hashlib
import subprocess
import numpy as np
from pathlib import Path
from bpy.props import (
    StringProperty, IntProperty, BoolProperty, EnumProperty,
    FloatVectorProperty, PointerProperty,
)
from bpy.types import Panel, Operator, AddonPreferences, PropertyGroup


# =========================================================================
# MODULE: constants
# =========================================================================
ENGINES = [
    ("SPEED",    "Speed",    ""),
    ("BALANCED", "Balanced", ""),
    ("ACCEL",    "Accel",    ""),
    ("TURN",     "Turn",     ""),
]
_ENGINE_SET = {"SPEED", "BALANCED", "ACCEL", "TURN"}

BLEND_MODES = [
    ("half",     "Half Transparent",     "50% transparency (default)"),
    ("add",      "Additive",             "Additive blending"),
    ("subtract", "Subtractive",          "Subtractive blending"),
    ("add_25",   "Additive Translucent", "Additive at 25%"),
]
_BLEND_MODE_SET = {m[0] for m in BLEND_MODES}

DEFAULT_REPO   = r"C:\Users\Kevin\Desktop\Kevin\CTR\native_fork\nhanced"
DEFAULT_PYTHON = r"C:\Users\Kevin\AppData\Local\Programs\Python\Python312\python.exe"
ADDON_ID       = __name__ if __name__ != "__main__" else "native_fork_racer"

MAX_PAGES = 8
MAX_MATS_PER_PAGE = 10


# =========================================================================
# MODULE: render — compat helpers
# =========================================================================
def _nfr_ge_3_5():
    return bpy.app.version >= (3, 5, 0)

def _nfr_ge_4_0():
    return bpy.app.version >= (4, 0, 0)

def _nfr_ge_5_0():
    return bpy.app.version >= (5, 0, 0)


# =========================================================================
# MODULE: render — node setups
# =========================================================================
NFR_PS1_NODE_SETUPS = {
    'ADDITIVE': {
        'nodes': [
            ('ShaderNodeOutputMaterial', 'Material Output', (210, 125), 140.0, {'is_active_output': True}),
            ('ShaderNodeAttribute', 'Attribute', (-800, -150), 140.0, {'attribute_name': 'Color'}),
            ('ShaderNodeMath', 'Compare Alpha', (-470, 215), 140.0, {'operation': 'LESS_THAN', 'inputs[1].default_value': 0.999}),
            ('ShaderNodeMixRGB', 'Solid Mix', (-600, -90), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0}),
            ('ShaderNodeMixRGB', 'Solid Multiply 4x', (-470, -110), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0, 'inputs[2].default_value': (4.0, 4.0, 4.0, 1.0)}),
            ('ShaderNodeInvert', 'Solid Invert', (-470, -45), 140.0, {'inputs[0].default_value': 1.0}),
            ('ShaderNodeBsdfTransparent', 'Solid Transparent BSDF', (-470, -215), 140.0, {}),
            ('ShaderNodeMixShader', 'Solid Mix Shader', (-200, -65), 140.0, {}),
            ('ShaderNodeMixRGB', 'Transp Mix', (-575, 95), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0}),
            ('ShaderNodeMixRGB', 'Transp Multiply 4x', (-470, 125), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0, 'inputs[2].default_value': (4.0, 4.0, 4.0, 1.0)}),
            ('ShaderNodeInvert', 'Transp Invert', (-470, 20), 140.0, {'inputs[0].default_value': 0.5}),
            ('ShaderNodeMixShader', 'Transp Mix Shader', (-205, 60), 140.0, {}),
            ('ShaderNodeBsdfTransparent', 'Transp Transparent 2', (-200, -20), 140.0, {}),
            ('ShaderNodeAddShader', 'Transp Add Shader', (-85, 65), 140.0, {}),
            ('ShaderNodeMixShader', 'Final Mix Shader', (100, 115), 140.0, {}),
            ('ShaderNodeMixRGB', 'Transp Multiply 4x.001', (-325, 125), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0, 'inputs[2].default_value': (4.0, 4.0, 4.0, 1.0)}),
            ('ShaderNodeGamma', 'Transp Gamma', (-400, 15), 140.0, {'inputs[1].default_value': 20.0}),
            ('ShaderNodeBsdfTransparent', 'Transparent BSDF', (-325, 15), 140.0, {})
        ],
        'connections': [
            ('Final Mix Shader', 0, 'Material Output', 0),
            ('Image Texture', 1, 'Compare Alpha', 0),
            ('Image Texture', 0, 'Solid Mix', 1),
            ('Attribute', 0, 'Solid Mix', 2),
            ('Solid Mix', 0, 'Solid Multiply 4x', 1),
            ('Image Texture', 1, 'Solid Invert', 1),
            ('Solid Invert', 0, 'Solid Mix Shader', 0),
            ('Solid Multiply 4x', 0, 'Solid Mix Shader', 1),
            ('Solid Transparent BSDF', 0, 'Solid Mix Shader', 2),
            ('Image Texture', 0, 'Transp Mix', 1),
            ('Attribute', 0, 'Transp Mix', 2),
            ('Transp Mix', 0, 'Transp Multiply 4x', 1),
            ('Image Texture', 1, 'Transp Invert', 1),
            ('Transp Multiply 4x.001', 0, 'Transp Mix Shader', 1),
            ('Transparent BSDF', 0, 'Transp Mix Shader', 2),
            ('Transp Mix Shader', 0, 'Transp Add Shader', 0),
            ('Transp Transparent 2', 0, 'Transp Add Shader', 1),
            ('Compare Alpha', 0, 'Final Mix Shader', 0),
            ('Solid Mix Shader', 0, 'Final Mix Shader', 1),
            ('Transp Add Shader', 0, 'Final Mix Shader', 2),
            ('Transp Multiply 4x', 0, 'Transp Multiply 4x.001', 1),
            ('Transp Invert', 0, 'Transp Gamma', 0),
            ('Transp Gamma', 0, 'Transparent BSDF', 0)
        ]
    },
    'SUBTRACTIVE': {
        'nodes': [
            ('ShaderNodeAttribute', 'Attribute', (-800, -50), 140.0, {'attribute_name': 'Color'}),
            ('ShaderNodeOutputMaterial', 'Material Output', (230, 30), 140.0, {'is_active_output': True}),
            ('ShaderNodeMath', 'Compare Alpha', (-650, 100), 140.0, {'operation': 'LESS_THAN', 'inputs[1].default_value': 0.999}),
            ('ShaderNodeMixShader', 'Final Mix Shader', (-5, 25), 140.0, {}),
            ('ShaderNodeMixRGB', 'Solid Mix', (-650, -65), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0}),
            ('ShaderNodeMixRGB', 'Solid Multiply 4x', (-450, -65), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0, 'inputs[2].default_value': (4.0, 4.0, 4.0, 1.0)}),
            ('ShaderNodeInvert', 'Solid Invert', (-450, 55), 140.0, {'inputs[0].default_value': 1.0}),
            ('ShaderNodeBsdfTransparent', 'Transparent BSDF', (-275, -100), 140.0, {}),
            ('ShaderNodeMixShader', 'Solid Mix Shader', (-150, -65), 140.0, {}),
            ('ShaderNodeMixRGB', 'Transp Mix', (-650, 15), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0}),
            ('ShaderNodeMixRGB', 'Transp Multiply 4x', (-450, 15), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0, 'inputs[2].default_value': (4.0, 4.0, 4.0, 1.0)}),
            ('ShaderNodeBsdfTransparent', 'Transp Transparent', (-150, -30), 140.0, {}),
            ('ShaderNodeInvert', 'Transp Invert 2', (-350, 15), 140.0, {'inputs[0].default_value': 1.0}),
            ('ShaderNodeGamma', 'Gamma', (-275, 15), 140.0, {'inputs[1].default_value': 10.0})
        ],
        'connections': [
            ('Final Mix Shader', 0, 'Material Output', 0),
            ('Image Texture', 1, 'Compare Alpha', 0),
            ('Compare Alpha', 0, 'Final Mix Shader', 0),
            ('Image Texture', 0, 'Solid Mix', 1),
            ('Attribute', 0, 'Solid Mix', 2),
            ('Solid Mix', 0, 'Solid Multiply 4x', 1),
            ('Image Texture', 1, 'Solid Invert', 1),
            ('Solid Invert', 0, 'Solid Mix Shader', 0),
            ('Solid Multiply 4x', 0, 'Solid Mix Shader', 1),
            ('Transparent BSDF', 0, 'Solid Mix Shader', 2),
            ('Solid Mix Shader', 0, 'Final Mix Shader', 1),
            ('Image Texture', 0, 'Transp Mix', 1),
            ('Attribute', 0, 'Transp Mix', 2),
            ('Transp Mix', 0, 'Transp Multiply 4x', 1),
            ('Transp Multiply 4x', 0, 'Transp Invert 2', 1),
            ('Transp Invert 2', 0, 'Gamma', 0),
            ('Gamma', 0, 'Transp Transparent', 0),
            ('Transp Transparent', 0, 'Final Mix Shader', 2)
        ]
    },
    'HALF_TRANSPARENT': {
        'nodes': [
            ('ShaderNodeAttribute', 'Attribute', (-800, -90), 140.0, {'attribute_name': 'Color'}),
            ('ShaderNodeOutputMaterial', 'Material Output', (170, 105), 140.0, {'is_active_output': True}),
            ('ShaderNodeMath', 'Compare Alpha', (-465, 120), 140.0, {'operation': 'LESS_THAN', 'inputs[1].default_value': 0.999}),
            ('ShaderNodeMixShader', 'Final Mix Shader', (40, 110), 140.0, {'inputs[0].default_value': 0.5}),
            ('ShaderNodeMixRGB', 'Solid Mix', (-615, -95), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0}),
            ('ShaderNodeMixRGB', 'Solid Multiply 4x', (-465, -95), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0, 'inputs[2].default_value': (4.0, 4.0, 4.0, 1.0)}),
            ('ShaderNodeBsdfTransparent', 'Transparent BSDF', (-320, -80), 140.0, {}),
            ('ShaderNodeMixShader', 'Solid Mix Shader', (-115, 55), 140.0, {}),
            ('ShaderNodeMixRGB', 'Transp Mix', (-615, -25), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0}),
            ('ShaderNodeMixRGB', 'Transp Multiply 4x', (-465, -25), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0, 'inputs[2].default_value': (4.0, 4.0, 4.0, 1.0), 'use_clamp': True}),
            ('ShaderNodeInvert', 'Transp Invert', (-470, 20), 140.0, {'inputs[0].default_value': 1.0}),
            ('ShaderNodeBsdfTransparent', 'Transp Transparent', (-320, -120), 140.0, {}),
            ('ShaderNodeMixShader', 'Transp Mix Shader', (-120, -15), 140.0, {})
        ],
        'connections': [
            ('Final Mix Shader', 0, 'Material Output', 0),
            ('Image Texture', 1, 'Compare Alpha', 0),
            ('Image Texture', 0, 'Solid Mix', 1),
            ('Attribute', 0, 'Solid Mix', 2),
            ('Solid Mix', 0, 'Solid Multiply 4x', 1),
            ('Compare Alpha', 0, 'Solid Mix Shader', 0),
            ('Solid Multiply 4x', 0, 'Solid Mix Shader', 1),
            ('Transparent BSDF', 0, 'Solid Mix Shader', 2),
            ('Solid Mix Shader', 0, 'Final Mix Shader', 1),
            ('Image Texture', 0, 'Transp Mix', 1),
            ('Attribute', 0, 'Transp Mix', 2),
            ('Transp Mix', 0, 'Transp Multiply 4x', 1),
            ('Image Texture', 1, 'Transp Invert', 1),
            ('Transp Invert', 0, 'Transp Mix Shader', 0),
            ('Transp Multiply 4x', 0, 'Transp Mix Shader', 1),
            ('Transp Transparent', 0, 'Transp Mix Shader', 2),
            ('Transp Mix Shader', 0, 'Final Mix Shader', 2)
        ]
    },
    'ADDITIVE_TRANSLUCENT': {
        'nodes': [
            ('ShaderNodeAttribute', 'Attribute', (-600, 0), 140.0, {'attribute_name': 'Color'}),
            ('ShaderNodeOutputMaterial', 'Material Output', (500, 0), 140.0, {'is_active_output': True}),
            ('ShaderNodeMixRGB', 'Mix Texture Vertex', (-400, 0), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0}),
            ('ShaderNodeMixRGB', 'Multiply 4x', (-200, 0), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0, 'inputs[2].default_value': (4.0, 4.0, 4.0, 1.0)}),
            ('ShaderNodeBsdfTransparent', 'Transparent BSDF', (0, -120), 140.0, {}),
            ('ShaderNodeInvert', 'Invert Alpha', (-200, 120), 140.0, {'inputs[0].default_value': 1.0}),
            ('ShaderNodeMixShader', 'Mix Shader', (200, 0), 140.0, {}),
            ('ShaderNodeGamma', 'Gamma', (0, 120), 140.0, {'inputs[1].default_value': 10.0})
        ],
        'connections': [
            ('Image Texture', 0, 'Mix Texture Vertex', 1),
            ('Attribute', 0, 'Mix Texture Vertex', 2),
            ('Mix Texture Vertex', 0, 'Multiply 4x', 1),
            ('Multiply 4x', 0, 'Mix Shader', 1),
            ('Transparent BSDF', 0, 'Mix Shader', 2),
            ('Mix Shader', 0, 'Material Output', 0),
            ('Image Texture', 1, 'Invert Alpha', 1),
            ('Invert Alpha', 0, 'Gamma', 0),
            ('Gamma', 0, 'Mix Shader', 0)
        ]
    }
}


# =========================================================================
# MODULE: render — color attribute helpers
# =========================================================================
def _nfr_create_color_attr(obj, target_name="Color"):
    mesh = obj.data
    if not hasattr(mesh, "color_attributes"):
        return False
    try:
        mesh.color_attributes.new(name=target_name, type='BYTE_COLOR', domain='CORNER')
        _nfr_apply_white_color(obj, target_name)
        mesh.update()
        return True
    except Exception as e:
        print(f"[NFR] Error creating color attribute for '{obj.name}': {e}")
        return False


def _nfr_apply_white_color(obj, attribute_name="Color"):
    mesh = obj.data
    try:
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(mesh)
        layer = bm.loops.layers.color.get(attribute_name) or bm.loops.layers.color.new(attribute_name)
        white = (1.0, 1.0, 1.0, 1.0)
        for face in bm.faces:
            for loop in face.loops:
                loop[layer] = white
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        return True
    except Exception as e:
        print(f"[NFR] Error applying white color to '{obj.name}': {e}")
        return False


def _nfr_list_color_attrs(obj):
    mesh = obj.data
    if not hasattr(mesh, "color_attributes") or not mesh.color_attributes:
        return []
    return [a.name for a in mesh.color_attributes]


def _nfr_rename_color_attr(obj, old_name, new_name):
    mesh = obj.data
    if not hasattr(mesh, "color_attributes"):
        return False
    for a in mesh.color_attributes:
        if a.name == old_name:
            a.name = new_name
            return True
    return False


def _nfr_ensure_attribute_exists(obj, target_name="Color"):
    mesh = obj.data
    if not hasattr(mesh, "color_attributes"):
        return False
    if not mesh.color_attributes:
        return _nfr_create_color_attr(obj, target_name)
    names = [a.name for a in mesh.color_attributes]
    if target_name in names:
        idx = names.index(target_name)
        mesh.color_attributes.active_color_index = idx
        mesh.update()
        return True
    first = mesh.color_attributes[0]
    first.name = target_name
    mesh.color_attributes.active_color_index = 0
    _nfr_apply_white_color(obj, target_name)
    mesh.update()
    return True


def _nfr_ensure_all_objects_have_color_attributes(target_name="Color"):
    created = 0
    renamed = 0
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        cur = _nfr_list_color_attrs(obj)
        if not cur:
            if _nfr_create_color_attr(obj, target_name):
                created += 1
        elif target_name not in cur:
            if _nfr_rename_color_attr(obj, cur[0], target_name):
                renamed += 1
        else:
            _nfr_ensure_attribute_exists(obj, target_name)
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    return created + renamed


# =========================================================================
# MODULE: render — PS1 material setup
# =========================================================================
class NFR_PS1MaterialSetup:
    def __init__(self, material):
        self.mat = material
        self.mat.use_nodes = True
        self.nodes = {}

    def clear_existing_nodes(self):
        self.nodes.clear()
        for node in self.mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                self.nodes['Image Texture'] = node
                break
        to_remove = [n for n in self.mat.node_tree.nodes if n.type != 'TEX_IMAGE']
        for n in to_remove:
            self.mat.node_tree.nodes.remove(n)
        if 'Image Texture' not in self.nodes:
            it = self.mat.node_tree.nodes.new('ShaderNodeTexImage')
            it.name = "Image Texture"
            self.nodes['Image Texture'] = it
        self.nodes['Image Texture'].location = (-1000, 0)

    def build_setup(self, mode):
        cfg = NFR_PS1_NODE_SETUPS[mode]
        for node_type, name, location, width, props in cfg['nodes']:
            node = self.mat.node_tree.nodes.new(node_type)
            node.name = name
            node.location = location
            node.width = width
            for prop_path, value in props.items():
                if '.' in prop_path:
                    parts = prop_path.split('.')
                    obj = node
                    for part in parts[:-1]:
                        if '[' in part and ']' in part:
                            attr_name = part.split('[')[0]
                            index = int(part.split('[')[1].split(']')[0])
                            obj = getattr(obj, attr_name)[index]
                        else:
                            obj = getattr(obj, part)
                    setattr(obj, parts[-1], value)
                else:
                    setattr(node, prop_path, value)
            self.nodes[name] = node
        for from_name, from_sock, to_name, to_sock in cfg['connections']:
            try:
                self.mat.node_tree.links.new(
                    self.nodes[from_name].outputs[from_sock],
                    self.nodes[to_name].inputs[to_sock])
            except Exception as e:
                print(f"[NFR] connect error {from_name}.{from_sock} -> {to_name}.{to_sock}: {e}")

    def analyze_image_texture(self):
        img_node = self.nodes.get('Image Texture')
        if not img_node or not img_node.image:
            return "NO_IMAGE"
        try:
            image = img_node.image
            if image.size[0] == 0 or image.size[1] == 0 or not image.pixels:
                return "NO_IMAGE"
            w, h = image.size
            pixels = np.array(image.pixels).reshape(h, w, 4)
            solid = transparent = semi = 0
            for y in range(h):
                for x in range(w):
                    a = pixels[y, x, 3]
                    if a >= 1.0:
                        solid += 1
                    elif a <= 0.01:
                        transparent += 1
                    else:
                        semi += 1
            total = w * h
            if semi > 0:
                return "HAS_SEMI_TRANSPARENT"
            elif solid == total:
                return "ALL_SOLID"
            elif transparent == total:
                return "ALL_TRANSPARENT"
            elif solid > 0 and transparent > 0:
                return "SOLID_AND_TRANSPARENT"
            return "UNKNOWN"
        except Exception as e:
            print(f"[NFR] analyze error: {e}")
            return "UNKNOWN"

    def apply_blend_mode(self, mode, pixel_type, used_additive_translucent_setup):
        blend_override = getattr(self.mat, 'nfr_ps1_blend_method_override', 'AUTO')
        if blend_override != 'AUTO':
            try:
                self.mat.blend_method = blend_override
            except Exception:
                pass
        else:
            if mode == 'ADDITIVE_TRANSLUCENT' and pixel_type == "HAS_SEMI_TRANSPARENT":
                try:
                    self.mat.blend_method = 'HASHED'
                except Exception:
                    pass
            else:
                try:
                    if pixel_type == "HAS_SEMI_TRANSPARENT":
                        self.mat.blend_method = 'BLEND'
                    else:
                        self.mat.blend_method = 'HASHED'
                except Exception:
                    pass

        default_overlap = not used_additive_translucent_setup
        mode_choice = getattr(self.mat, 'nfr_ps1_transparency_overlap_mode', 'DEFAULT')
        if mode_choice == 'DEFAULT':
            final_overlap = default_overlap
        else:
            final_overlap = getattr(self.mat, 'nfr_ps1_transparency_overlap_manual', True)

        if hasattr(self.mat, 'use_transparency_overlap'):
            self.mat.use_transparency_overlap = final_overlap
        elif hasattr(self.mat, 'show_transparent_back'):
            self.mat.show_transparent_back = final_overlap

        if hasattr(self.mat, 'nfr_ps1_show_backface'):
            self.mat.use_backface_culling = not self.mat.nfr_ps1_show_backface
        else:
            self.mat.use_backface_culling = True
        self.mat.update_tag()


class NFR_AdditiveMaterialSetup(NFR_PS1MaterialSetup):
    def apply_setup(self):
        self.clear_existing_nodes()
        px = self.analyze_image_texture()
        used_at = False
        if px != "HAS_SEMI_TRANSPARENT":
            self.build_setup('ADDITIVE_TRANSLUCENT')
            used_at = True
        else:
            self.build_setup('ADDITIVE')
        self.apply_blend_mode('ADDITIVE', px, used_at)
        return True


class NFR_SubtractiveMaterialSetup(NFR_PS1MaterialSetup):
    def apply_setup(self):
        self.clear_existing_nodes()
        px = self.analyze_image_texture()
        used_at = False
        if px != "HAS_SEMI_TRANSPARENT":
            self.build_setup('ADDITIVE_TRANSLUCENT')
            used_at = True
        else:
            self.build_setup('SUBTRACTIVE')
        self.apply_blend_mode('SUBTRACTIVE', px, used_at)
        return True


class NFR_HalfTransparentMaterialSetup(NFR_PS1MaterialSetup):
    def apply_setup(self):
        self.clear_existing_nodes()
        px = self.analyze_image_texture()
        used_at = False
        if px != "HAS_SEMI_TRANSPARENT":
            self.build_setup('ADDITIVE_TRANSLUCENT')
            used_at = True
        else:
            self.build_setup('HALF_TRANSPARENT')
        self.apply_blend_mode('HALF_TRANSPARENT', px, used_at)
        return True


class NFR_AdditiveTranslucentMaterialSetup(NFR_PS1MaterialSetup):
    def apply_setup(self):
        self.clear_existing_nodes()
        px = self.analyze_image_texture()
        self.build_setup('ADDITIVE_TRANSLUCENT')
        self.apply_blend_mode('ADDITIVE_TRANSLUCENT', px, True)
        return True


class NFR_PS1MaterialFactory:
    @staticmethod
    def get_material_setup(material, mode):
        if mode == 'ADDITIVE':
            return NFR_AdditiveMaterialSetup(material)
        elif mode == 'SUBTRACTIVE':
            return NFR_SubtractiveMaterialSetup(material)
        elif mode == 'HALF_TRANSPARENT':
            return NFR_HalfTransparentMaterialSetup(material)
        elif mode == 'ADDITIVE_TRANSLUCENT':
            return NFR_AdditiveTranslucentMaterialSetup(material)
        return NFR_AdditiveMaterialSetup(material)


# =========================================================================
# MODULE: render — property callbacks
# =========================================================================
def _nfr_update_ps1_blend_mode(self, context):
    if getattr(self, 'nfr_ps1_blend_mode', 'NONE') == 'NONE':
        return
    cur_bf = getattr(self, 'nfr_ps1_show_backface', False)
    if context.scene.nfr_ps1_render_active:
        try:
            setup = NFR_PS1MaterialFactory.get_material_setup(self, self.nfr_ps1_blend_mode)
            setup.apply_setup()
            self.nfr_ps1_show_backface = cur_bf
        except Exception as e:
            print(f"[NFR] update blend mode error on '{self.name}': {e}")
    else:
        self.nfr_ps1_last_active_mode = self.nfr_ps1_blend_mode
        self.nfr_ps1_show_backface = cur_bf


def _nfr_mat_blend_mode_update(self, context):
    v = getattr(self, "nfr_racer_blend_mode", "half")
    if v not in _BLEND_MODE_SET:
        return
    current = self.get("blend_mode", "half")
    if current != v:
        self["blend_mode"] = v


# =========================================================================
# MODULE: preferences
# =========================================================================
class NFR_Preferences(AddonPreferences):
    bl_idname = ADDON_ID

    repo_path:  StringProperty(name="Repo Path", default=DEFAULT_REPO, subtype="DIR_PATH")
    python_exe: StringProperty(name="Python Exe", default=DEFAULT_PYTHON, subtype="FILE_PATH")
    build_dir:  StringProperty(
        name="Build Dir",
        description="Relative to Repo Path (MSVC out-of-source build folder)",
        default="build-msvc-x86")
    exe_name:   StringProperty(name="Exe Name", default="ctr_native.exe")

    def racers_dir(self):
        return Path(self.repo_path) / "assets" / "mods" / "racers"

    def build_path(self):
        return Path(self.repo_path) / self.build_dir

    def exe_path(self):
        return Path(self.repo_path) / self.exe_name

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "repo_path")
        layout.prop(self, "python_exe")
        layout.separator()
        layout.label(text="Build / Run:")
        layout.prop(self, "build_dir")
        layout.prop(self, "exe_name")
        layout.separator()
        layout.label(text="Export target (derived from Repo Path):", icon="INFO")
        layout.label(text=str(self.racers_dir()))
        layout.separator()
        row = layout.row(align=True)
        row.operator("nfr.save_settings", text="Save Settings JSON")
        row.operator("nfr.load_settings", text="Load Settings JSON")


class _FallbackPrefs:
    def __init__(self):
        self.repo_path = DEFAULT_REPO
        self.python_exe = DEFAULT_PYTHON
        self.build_dir = "build-msvc-x86"
        self.exe_name = "ctr_native.exe"

    def racers_dir(self):
        return Path(self.repo_path) / "assets" / "mods" / "racers"

    def build_path(self):
        return Path(self.repo_path) / self.build_dir

    def exe_path(self):
        return Path(self.repo_path) / self.exe_name


_fallback_prefs_instance = None


def _get_prefs(context):
    global _fallback_prefs_instance
    entry = context.preferences.addons.get(ADDON_ID)
    if entry is not None:
        return entry.preferences
    if _fallback_prefs_instance is None:
        _fallback_prefs_instance = _FallbackPrefs()
    return _fallback_prefs_instance


# =========================================================================
# MODULE: material helpers
# =========================================================================
def _get_blend_mode(mat):
    value = mat.get("blend_mode", "half")
    if value not in _BLEND_MODE_SET:
        return "half"
    return value


# =========================================================================
# MODULE: racer properties
# =========================================================================
class NFR_RacerProps(PropertyGroup):
    is_racer:   BoolProperty(name="Is Racer", default=False)
    slug:       StringProperty(name="Slug", description="Folder name and internal .ctr name")
    page:       IntProperty(name="Page", default=1, min=1, max=8)
    slot:       IntProperty(name="Slot", default=0, min=0, max=15)
    engine:     EnumProperty(name="Engine", items=ENGINES, default="BALANCED")
    mask:       EnumProperty(
        name="Mask",
        description="Which mask this racer receives from item boxes",
        items=[("good", "Good (Aku Aku)", ""),
               ("bad",  "Bad (Uka Uka)",  "")],
        default="good")
    wheels:     EnumProperty(
        name="Wheels",
        description="Tire sprite visibility (Oxide-style hidden tires)",
        items=[("yes", "Visible",             ""),
               ("no",  "Hidden (Oxide-style)", "")],
        default="yes")
    long_name:  StringProperty(name="Long Name")
    short_name: StringProperty(name="Short Name")
    color:      FloatVectorProperty(name="Minimap Color", subtype="COLOR",
                                    default=(1.0, 1.0, 1.0), min=0.0, max=1.0)
    icon_path:  StringProperty(name="Icon PNG", subtype="FILE_PATH")

    def custom_id(self):
        return 16 + (self.page - 1) * 16 + self.slot


# =========================================================================
# MODULE: roster I/O
# =========================================================================
def _parse_roster_line(line):
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    try:
        toks = shlex.split(s)
    except ValueError:
        return None
    if len(toks) < 3:
        return None
    try:
        page = int(toks[0])
        slot = int(toks[1])
    except ValueError:
        return None
    folder = toks[2]
    rest = toks[3:]

    engine = "BALANCED"
    if rest and rest[0] in _ENGINE_SET:
        engine = rest[0]
        rest = rest[1:]

    name = ""
    color = None
    mask = "good"
    wheels = "yes"
    for tok in rest:
        if tok.startswith("mask="):
            v = tok[5:]
            if v in ("good", "bad"):
                mask = v
        elif tok.startswith("wheels="):
            v = tok[7:]
            if v in ("yes", "no"):
                wheels = v
        elif tok.startswith("#"):
            color = tok
        elif len(tok) == 6 and all(c in "0123456789abcdefABCDEF" for c in tok):
            color = "#" + tok
        elif not name:
            name = tok

    return {
        "page": page, "slot": slot, "folder": folder,
        "engine": engine, "name": name or folder, "color": color,
        "mask": mask, "wheels": wheels,
    }


def _read_roster(prefs):
    path = prefs.racers_dir() / "roster.txt"
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    entries = []
    for line in text.splitlines():
        e = _parse_roster_line(line)
        if e is not None:
            entries.append(e)
    return entries


def _group_by_page(entries):
    pages = {}
    for e in entries:
        pages.setdefault(e["page"], {})[e["slot"]] = e
    return pages


def _remove_roster_entry(prefs, page, slot):
    path = prefs.racers_dir() / "roster.txt"
    if not path.is_file():
        return (False, "roster.txt not found")
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as ex:
        return (False, f"Read failed: {ex}")

    new_lines = []
    removed_slug = None
    for line in text.splitlines():
        e = _parse_roster_line(line)
        if e is not None and e["page"] == page and e["slot"] == slot:
            removed_slug = e["folder"]
            continue
        new_lines.append(line)

    if removed_slug is None:
        return (False, "No entry at that slot")

    try:
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except Exception as ex:
        return (False, f"Write failed: {ex}")

    return (True, removed_slug)


# =========================================================================
# MODULE: icon previews
# =========================================================================
_preview_collection = None
_icon_cache = {}
_icon_mtimes = {}


def _ensure_previews():
    global _preview_collection
    if _preview_collection is None:
        _preview_collection = bpy.utils.previews.new()
    return _preview_collection


def _teardown_previews():
    global _preview_collection
    if _preview_collection is not None:
        try:
            bpy.utils.previews.remove(_preview_collection)
        except Exception:
            pass
        _preview_collection = None
    _icon_cache.clear()
    _icon_mtimes.clear()


def _get_icon(slug, png_path):
    pc = _ensure_previews()
    try:
        mtime = png_path.stat().st_mtime
    except OSError:
        return None
    if slug in _icon_cache and _icon_mtimes.get(slug) == mtime:
        return _icon_cache[slug]
    if slug in _icon_cache:
        try:
            pc.remove(slug)
        except Exception:
            pass
        del _icon_cache[slug]
    try:
        icon = pc.load(slug, str(png_path), "IMAGE")
    except Exception:
        _icon_mtimes.pop(slug, None)
        return None
    _icon_cache[slug] = icon
    _icon_mtimes[slug] = mtime
    return icon


def _image_preview_icon_id(img):
    if img is None:
        return 0
    try:
        img.preview_ensure()
    except Exception:
        return 0
    pv = getattr(img, "preview", None)
    if pv is None:
        return 0
    try:
        return pv.icon_id or 0
    except Exception:
        return 0


# =========================================================================
# MODULE: mesh export
# =========================================================================
def validate_racer(obj):
    errors = []
    warnings = []
    props = obj.racer

    if not props.slug:
        errors.append("Slug is empty")
    if not props.long_name:
        warnings.append("Long Name is empty (will fall back to slug)")

    m = obj.data
    if m.shape_keys is None or "Basis" not in m.shape_keys.key_blocks:
        errors.append("No 'Basis' shape key")
    if m.uv_layers.active is None:
        errors.append("No active UV layer")
    if "Color" not in m.color_attributes:
        errors.append("No 'Color' color attribute")

    for mat in m.materials:
        if mat is None:
            continue
        if not mat.use_nodes:
            warnings.append(f"Material '{mat.name}' has no nodes")
            continue
        imgs = [n.image for n in mat.node_tree.nodes
                if n.type == "TEX_IMAGE" and n.image]
        if len(imgs) > 1:
            errors.append(f"Material '{mat.name}' has {len(imgs)} images (max 1)")
        for im in imgs:
            if im.packed_file is None:
                errors.append(f"Image '{im.name}' is NOT packed into the .blend")
            else:
                warnings.append(f"Image '{im.name}': {im.size[0]}x{im.size[1]} packed")

    if props.icon_path:
        resolved = bpy.path.abspath(props.icon_path)
        if not os.path.isfile(resolved):
            errors.append(
                f"Icon file not found: {props.icon_path} "
                f"(resolved to: {resolved})")
    else:
        warnings.append("No icon PNG selected")

    return (len(errors) == 0, warnings, errors)


def export_mesh_json(obj, out_path):
    m = obj.data
    m.calc_loop_triangles()

    materials = []
    images = {}
    for mat in m.materials:
        imgs = list({n.image for n in mat.node_tree.nodes
                     if n.type == "TEX_IMAGE" and n.image})
        im = imgs[0] if imgs else None
        materials.append({
            "name": mat.name,
            "image": im.name if im else None,
            "double_sided": not mat.use_backface_culling,
            "blend_mode": _get_blend_mode(mat),
        })
        if im and im.name not in images:
            images[im.name] = {"size": list(im.size),
                               "pixels_rgba": list(im.pixels)}

    def corners(tri):
        return [{"vertex": m.loops[li].vertex_index,
                 "uv": list(m.uv_layers.active.data[li].uv),
                 "color_linear": list(m.color_attributes["Color"].data[li].color),
                 "color_srgb": list(m.color_attributes["Color"].data[li].color_srgb)}
                for li in tri.loops]

    src_hash = ""
    try:
        bp = bpy.data.filepath
        if bp:
            src_hash = hashlib.sha256(Path(bp).read_bytes()).hexdigest()
    except Exception:
        pass

    result = {
        "source": bpy.data.filepath,
        "source_sha256": src_hash,
        "matrix_world": [list(r) for r in obj.matrix_world],
        "vertices": [list(v.co) for v in m.vertices],
        "triangles": [{"polygon": t.polygon_index, "material": t.material_index,
                       "corners": corners(t)} for t in m.loop_triangles],
        "materials": materials,
        "images": images,
        "keys": {k.name: [list(v.co) for v in k.data]
                 for k in m.shape_keys.key_blocks},
        "groups": {g.name: {str(v.index): next((a.weight for a in v.groups
                                                if a.group == g.index), 0)
                            for v in m.vertices} for g in obj.vertex_groups},
    }

    Path(out_path).write_text(json.dumps(result, separators=(",", ":")),
                              encoding="utf-8")


def _do_export(context, obj):
    prev_mode = context.mode
    switched = False
    if prev_mode != 'OBJECT':
        if context.active_object is None:
            raise RuntimeError(
                f"Export requires Object Mode (currently {prev_mode}) "
                f"and no active object is available to switch")
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
            switched = True
        except Exception as ex:
            raise RuntimeError(
                f"Export requires Object Mode (currently {prev_mode}); "
                f"could not switch: {ex}")

    try:
        _do_export_body(context, obj)
    finally:
        if switched:
            try:
                bpy.ops.object.mode_set(mode=prev_mode)
            except Exception:
                pass


def _do_export_body(context, obj):
    prefs = _get_prefs(context)
    r = obj.racer

    racers_dir = prefs.racers_dir()
    slug_dir   = racers_dir / r.slug
    source_dir = slug_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    json_path = source_dir / "source_mesh.json"
    export_mesh_json(obj, json_path)

    add_racer = Path(prefs.repo_path) / "tools" / "custom_racers" / "add_racer.py"
    if not add_racer.is_file():
        raise RuntimeError(f"add_racer.py not found at {add_racer}")

    cmd = [
        prefs.python_exe, str(add_racer),
        r.slug, str(json_path),
        str(r.page), str(r.slot), r.engine, r.long_name,
    ]

    if r.icon_path:
        icon_abs = bpy.path.abspath(r.icon_path)
        if not os.path.isfile(icon_abs):
            raise RuntimeError(f"Icon not found: {r.icon_path} -> {icon_abs}")
        cmd += ["--icon", icon_abs]

    cmd += ["--mask", r.mask, "--wheels", r.wheels]

    if tuple(r.color[:3]) != (1.0, 1.0, 1.0):
        hexcol = "#{:02X}{:02X}{:02X}".format(
            int(r.color[0] * 255), int(r.color[1] * 255), int(r.color[2] * 255))
        cmd += ["--color", hexcol]

    res = subprocess.run(cmd, cwd=str(prefs.repo_path),
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(
            f"add_racer failed ({res.returncode}):\n{res.stderr[-400:]}")


def _racer_objects(context):
    sel = [o for o in context.selected_objects
           if o.type == "MESH" and o.racer.is_racer]
    if sel:
        return sel
    return [o for o in bpy.data.objects
            if o.type == "MESH" and o.racer.is_racer]


# =========================================================================
# MODULE: build & run
# =========================================================================
def _kill_running_exe(prefs):
    try:
        res = subprocess.run(
            ["taskkill", "/F", "/IM", prefs.exe_name],
            capture_output=True, text=True, timeout=5)
        return res.returncode == 0
    except Exception:
        return False


def _build_exe(context):
    prefs = _get_prefs(context)
    repo = Path(prefs.repo_path)
    build_dir = prefs.build_path()

    if not repo.is_dir():
        return (False, f"Repo not found: {repo}")
    if not build_dir.is_dir():
        return (False, f"Build dir not found: {build_dir}")

    if _kill_running_exe(prefs):
        time.sleep(2)

    log_path = repo / "build_addon.log"
    try:
        with open(log_path, "w", encoding="utf-8") as log:
            res = subprocess.run(
                ["cmake", "--build", str(build_dir), "--config", "Release"],
                cwd=str(repo), stdout=log, stderr=subprocess.STDOUT,
                timeout=900)
    except FileNotFoundError:
        return (False, "cmake not found in PATH")
    except subprocess.TimeoutExpired:
        return (False, "Build timed out (>15 min)")

    if res.returncode != 0:
        return (False, f"Build failed (rc={res.returncode}); see {log_path.name}")
    return (True, "Build OK")


def _run_game(context):
    prefs = _get_prefs(context)
    repo = Path(prefs.repo_path)
    exe = prefs.exe_path()

    if not exe.is_file():
        return (False, f"Exe not found: {exe} (build first?)")

    _kill_running_exe(prefs)
    time.sleep(0.5)

    try:
        subprocess.Popen([str(exe)], cwd=str(repo))
    except Exception as ex:
        return (False, f"Launch failed: {ex}")
    return (True, f"Launched {exe.name}")


# =========================================================================
# MODULE: helpers
# =========================================================================
def _redraw_view3d(context):
    try:
        screen = context.screen
        if screen is None:
            return
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()
    except Exception:
        pass


def _find_object_by_slug(slug):
    return next((o for o in bpy.data.objects
                 if o.type == "MESH"
                 and hasattr(o, "racer")
                 and o.racer.slug == slug), None)


def _active_racer(context):
    obj = context.active_object
    if (obj is None or obj.type != "MESH"
            or not hasattr(obj, "racer") or not obj.racer.is_racer):
        return None
    return obj.racer


# =========================================================================
# MODULE: state (slot + material pagination)
# =========================================================================
_slot_view_page = 1
_slot_sel_page = -1
_slot_sel_slot = -1
_mat_view_page = 1


def _resolve_cells(page, page_entries, active_racer, active_slug):
    cells = {}
    for slot in range(16):
        e = page_entries.get(slot)
        active_here = (active_racer is not None
                       and active_racer.page == page
                       and active_racer.slot == slot)

        if active_here:
            if e is not None and e["folder"] == active_slug:
                cells[slot] = ("entry", e)
            else:
                cells[slot] = ("pending", {
                    "folder": active_slug or "?",
                    "name": active_racer.long_name or active_slug or "?",
                    "engine": active_racer.engine,
                    "mask": active_racer.mask,
                    "wheels": active_racer.wheels,
                    "color": None,
                    "is_pending": True,
                })
            continue

        if e is not None:
            if (active_slug is not None and e["folder"] == active_slug
                    and active_racer is not None
                    and (active_racer.page != page or active_racer.slot != slot)):
                cells[slot] = ("empty", None)
                continue
            cells[slot] = ("entry", e)
            continue

        cells[slot] = ("empty", None)
    return cells


# =========================================================================
# MODULE: operators — racer panel
# =========================================================================
class NFR_OT_Validate(Operator):
    bl_idname = "nfr.validate"
    bl_label = "Validate"

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "Select a mesh first")
            return {"CANCELLED"}
        ok, warns, errs = validate_racer(obj)
        for e in errs:
            self.report({"ERROR"}, e)
        for w in warns:
            print(f"[Racer Validate] {obj.name}: {w}")
        if ok:
            self.report({"INFO"}, f"{obj.name}: OK")
        return {"FINISHED"}


class NFR_OT_Export(Operator):
    bl_idname = "nfr.export"
    bl_label = "Export"

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "Select a mesh first")
            return {"CANCELLED"}
        if not obj.racer.is_racer:
            self.report({"ERROR"}, "Object is not marked as racer")
            return {"CANCELLED"}

        ok, _warns, errs = validate_racer(obj)
        if not ok:
            for e in errs:
                self.report({"ERROR"}, e)
            return {"CANCELLED"}

        try:
            _do_export(context, obj)
        except Exception as ex:
            self.report({"ERROR"}, str(ex)[:300])
            return {"CANCELLED"}

        _teardown_previews()
        self.report({"INFO"},
            f"Exported {obj.racer.slug} -> page {obj.racer.page} slot {obj.racer.slot}")
        _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_ExportAll(Operator):
    bl_idname = "nfr.export_all"
    bl_label = "Export All"

    def execute(self, context):
        objs = _racer_objects(context)
        if not objs:
            self.report({"ERROR"}, "No objects with Is Racer checked")
            return {"CANCELLED"}

        ok_count = 0
        fail_count = 0
        for obj in objs:
            ok, _w, errs = validate_racer(obj)
            if not ok:
                fail_count += 1
                print(f"[Racer Export All] SKIP {obj.name}: {'; '.join(errs)}")
                continue
            try:
                _do_export(context, obj)
                ok_count += 1
                print(f"[Racer Export All] OK {obj.name}")
            except Exception as ex:
                fail_count += 1
                print(f"[Racer Export All] FAIL {obj.name}: {ex}")

        _teardown_previews()
        self.report({"INFO"}, f"{ok_count} exported, {fail_count} failed")
        _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_SaveSettings(Operator):
    bl_idname = "nfr.save_settings"
    bl_label = "Save Settings JSON"
    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.json")

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = str(Path(_get_prefs(context).repo_path) / "racer_settings.json")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        data = {}
        for obj in bpy.data.objects:
            if obj.type != "MESH" or not obj.racer.is_racer:
                continue
            r = obj.racer
            data[obj.name] = {
                "slug": r.slug, "page": r.page, "slot": r.slot, "engine": r.engine,
                "long_name": r.long_name, "short_name": r.short_name,
                "color": list(r.color), "icon_path": r.icon_path,
                "mask": r.mask, "wheels": r.wheels,
            }
        Path(self.filepath).write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.report({"INFO"}, f"Saved {len(data)} racers to {self.filepath}")
        return {"FINISHED"}


class NFR_OT_LoadSettings(Operator):
    bl_idname = "nfr.load_settings"
    bl_label = "Load Settings JSON"
    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.json")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        data = json.loads(Path(self.filepath).read_text(encoding="utf-8"))
        loaded = 0
        for name, d in data.items():
            obj = bpy.data.objects.get(name)
            if obj is None or obj.type != "MESH":
                continue
            r = obj.racer
            r.is_racer = True
            r.slug = d.get("slug", "")
            r.page = int(d.get("page", 1))
            r.slot = int(d.get("slot", 0))
            r.engine = d.get("engine", "BALANCED")
            r.long_name = d.get("long_name", "")
            r.short_name = d.get("short_name", "")
            c = d.get("color", [1.0, 1.0, 1.0, 1.0])
            r.color = tuple(c[:4]) if len(c) >= 3 else (1.0, 1.0, 1.0, 1.0)
            r.icon_path = d.get("icon_path", "")
            r.mask      = d.get("mask",   "good")
            r.wheels    = d.get("wheels", "yes")
            loaded += 1
        self.report({"INFO"}, f"Loaded {loaded} racers from {self.filepath}")
        return {"FINISHED"}


class NFR_OT_BuildExe(Operator):
    bl_idname = "nfr.build_exe"
    bl_label = "Build Exe (only, no launch)"
    bl_description = "Kill running exe, then cmake --build --config Release"

    def execute(self, context):
        ok, msg = _build_exe(context)
        self.report({"INFO"} if ok else {"ERROR"}, msg)
        return {"FINISHED"} if ok else {"CANCELLED"}


class NFR_OT_RunGame(Operator):
    bl_idname = "nfr.run_game"
    bl_label = "Run"
    bl_description = "Kill any running instance, then launch ctr_native.exe (no rebuild)"

    def execute(self, context):
        ok, msg = _run_game(context)
        self.report({"INFO"} if ok else {"ERROR"}, msg)
        return {"FINISHED"} if ok else {"CANCELLED"}


class NFR_OT_BuildAndRun(Operator):
    bl_idname = "nfr.build_and_run"
    bl_label = "Build & Run"
    bl_description = "Rebuild the exe, then launch it"

    def execute(self, context):
        ok, msg = _build_exe(context)
        if not ok:
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}
        ok, msg = _run_game(context)
        self.report({"INFO"} if ok else {"ERROR"}, msg)
        return {"FINISHED"} if ok else {"CANCELLED"}


# =========================================================================
# MODULE: render — operators
# =========================================================================
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


# =========================================================================
# MODULE: operators — slot viewer
# =========================================================================
class NFR_OT_SlotClick(Operator):
    bl_idname = "nfr.slot_click"
    bl_label = "Slot"
    bl_description = ("Select a cell. If occupied, also focus the matching "
                      "Blender object for editing.")

    page: IntProperty()
    slot: IntProperty()

    def execute(self, context):
        global _slot_sel_page, _slot_sel_slot
        prefs = _get_prefs(context)
        entries = _read_roster(prefs)
        entry = next((x for x in entries
                      if x["page"] == self.page and x["slot"] == self.slot),
                     None)

        _slot_sel_page = self.page
        _slot_sel_slot = self.slot

        if entry is not None:
            obj = _find_object_by_slug(entry["folder"])
            if obj is not None:
                for o in bpy.data.objects:
                    o.select_set(False)
                obj.select_set(True)
                context.view_layer.objects.active = obj
                self.report({"INFO"}, f"Selected {obj.name}")
            else:
                self.report({"INFO"},
                    f"'{entry['folder']}' not in this .blend (roster-only)")

        _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_SlotAssignHere(Operator):
    bl_idname = "nfr.slot_assign_here"
    bl_label = "Assign Here"
    bl_description = ("Set the active racer mesh's page/slot to the selected "
                      "cell. roster.txt is not touched until you press Export.")

    def execute(self, context):
        if _slot_sel_page < 0 or _slot_sel_slot < 0:
            self.report({"ERROR"}, "Click a slot in the grid first")
            return {"CANCELLED"}
        obj = context.active_object
        if obj is None or obj.type != "MESH" or not obj.racer.is_racer:
            self.report({"ERROR"}, "Select a racer mesh first")
            return {"CANCELLED"}

        prefs = _get_prefs(context)
        entries = _read_roster(prefs)
        existing = next((x for x in entries
                         if x["page"] == _slot_sel_page
                         and x["slot"] == _slot_sel_slot), None)

        obj.racer.page = _slot_sel_page
        obj.racer.slot = _slot_sel_slot

        if existing is not None and existing["folder"] != obj.racer.slug:
            self.report({"WARNING"},
                f"Slot {_slot_sel_slot} is already taken by "
                f"'{existing['folder']}'. Export will leave two entries "
                f"at this position.")
        else:
            self.report({"INFO"},
                f"Assigned {obj.name} to page {_slot_sel_page} "
                f"slot {_slot_sel_slot}. Press Export to commit.")
        _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_SlotDelete(Operator):
    bl_idname = "nfr.slot_delete"
    bl_label = "Delete from roster"
    bl_description = "Remove this slot's roster.txt line (files kept on disk)"

    page: IntProperty()
    slot: IntProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        global _slot_sel_page, _slot_sel_slot
        prefs = _get_prefs(context)
        ok, result = _remove_roster_entry(prefs, self.page, self.slot)
        if not ok:
            self.report({"ERROR"}, result)
            return {"CANCELLED"}

        if _slot_sel_page == self.page and _slot_sel_slot == self.slot:
            _slot_sel_page = -1
            _slot_sel_slot = -1

        self.report({"INFO"},
            f"Removed '{result}' from roster.txt (files kept)")
        _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_SlotRefresh(Operator):
    bl_idname = "nfr.slot_refresh"
    bl_label = "Refresh"
    bl_description = "Reload roster.txt and icon previews from disk"

    def execute(self, context):
        _teardown_previews()
        _redraw_view3d(context)
        self.report({"INFO"}, "Reloaded roster.txt and icons")
        return {"FINISHED"}


class NFR_OT_SlotPrevPage(Operator):
    bl_idname = "nfr.slot_prev_page"
    bl_label = "Previous page"

    def execute(self, context):
        global _slot_view_page
        if _slot_view_page > 1:
            _slot_view_page -= 1
            _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_SlotNextPage(Operator):
    bl_idname = "nfr.slot_next_page"
    bl_label = "Next page"

    def execute(self, context):
        global _slot_view_page
        if _slot_view_page < MAX_PAGES:
            _slot_view_page += 1
            _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_SlotLoadToPanel(Operator):
    bl_idname = "nfr.slot_load_to_panel"
    bl_label = "Focus in panel"
    bl_description = "Select the Blender object whose slug matches this entry"

    slug: StringProperty()

    def execute(self, context):
        obj = _find_object_by_slug(self.slug)
        if obj is None:
            self.report({"WARNING"},
                f"No Blender object with slug '{self.slug}'")
            return {"CANCELLED"}

        for o in bpy.data.objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj

        self.report({"INFO"}, f"Selected {obj.name}")
        _redraw_view3d(context)
        return {"FINISHED"}


# =========================================================================
# MODULE: operators — materials pagination
# =========================================================================
class NFR_OT_MatPrevPage(Operator):
    bl_idname = "nfr.mat_prev_page"
    bl_label = "Previous materials page"
    bl_description = "Show the previous page of materials"

    def execute(self, context):
        global _mat_view_page
        if _mat_view_page > 1:
            _mat_view_page -= 1
            _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_MatNextPage(Operator):
    bl_idname = "nfr.mat_next_page"
    bl_label = "Next materials page"
    bl_description = "Show the next page of materials"

    def execute(self, context):
        global _mat_view_page
        _mat_view_page += 1
        _redraw_view3d(context)
        return {"FINISHED"}


# =========================================================================
# MODULE: operators — materials panel
# =========================================================================
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


# =========================================================================
# MODULE: panels — single unified panel with sub-tabs
# =========================================================================
class NFR_PT_Racer(Panel):
    bl_label = "CTR Racer"
    bl_idname = "NFR_PT_racer"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Racer"

    # ---------------------------------------------------------------------
    # Dispatch based on scene.nfr_ui_tab
    # ---------------------------------------------------------------------
    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Sub-tab selector — full-width segmented buttons
        row = layout.row(align=True)
        row.scale_y = 1.4
        row.prop(scene, "nfr_ui_tab", expand=True)

        layout.separator()

        tab = scene.nfr_ui_tab
        if tab == 'SETTINGS':
            self._draw_settings(context, layout)
        elif tab == 'SLOTS':
            self._draw_slots(context, layout)
        elif tab == 'MATERIALS':
            self._draw_materials(context, layout)

    # ---------------------------------------------------------------------
    # SETTINGS tab
    # ---------------------------------------------------------------------
    def _draw_settings(self, context, layout):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            layout.label(text="Select a mesh object", icon="INFO")
            return

        r = obj.racer

        # -------- Row: Is Racer checkbox + Validate icon --------
        row = layout.row(align=True)
        row.prop(r, "is_racer")

        if r.is_racer:
            # Small inline validate button (icon only). Turns red if invalid.
            try:
                ok, _warns, _errs = validate_racer(obj)
            except Exception:
                ok = False

            sub = row.row(align=True)
            sub.alert = not ok
            sub.operator(
                "nfr.validate",
                text="",
                icon='CHECKMARK' if ok else 'ERROR',
            )

        if not r.is_racer:
            layout.label(text="Check 'Is Racer' to configure", icon="INFO")
            return

        col = layout.column(align=True)
        col.prop(r, "slug")

        info = col.row(align=True)
        info.alignment = "EXPAND"
        info.label(text=f"Page {r.page}", icon="INFO")
        info.label(text=f"Slot {r.slot}")
        info.label(text=f"ID {r.custom_id()}")
        col.label(text="Set position via the Slots tab",
                  icon="RESTRICT_SELECT_OFF")

        col.separator()
        col.prop(r, "engine")
        col.prop(r, "mask")
        col.prop(r, "wheels")

        col.separator()
        col.prop(r, "long_name")
        col.prop(r, "short_name")

        col.separator()
        color_row = col.row(align=True)
        color_row.label(text="Minimap Color:")
        color_row.prop(r, "color", text="")
        col.prop(r, "icon_path")

        # -------- Dev Tools --------
        layout.separator()
        layout.label(text="Dev Tools:", icon="TOOL_SETTINGS")

        row = layout.row(align=True)
        row.scale_y = 1.3
        row.operator("nfr.export", text="Export", icon="EXPORT")
        row.operator("nfr.export_all", text="Export All", icon="FILE_TICK")

        row = layout.row(align=True)
        row.scale_y = 1.3
        row.operator("nfr.run_game", text="Run", icon="PLAY")
        row.operator("nfr.build_and_run", text="Build & Run", icon="FILE_REFRESH")

        layout.separator()
        if ADDON_ID in context.preferences.addons:
            layout.operator(
                "preferences.addon_show",
                text="Open Preferences",
                icon="PREFERENCES",
            ).module = ADDON_ID
        else:
            layout.label(text="Script mode — edit DEFAULT_REPO", icon="INFO")
            layout.label(text=f"repo: {DEFAULT_REPO}")

    # ---------------------------------------------------------------------
    # SLOTS tab
    # ---------------------------------------------------------------------
    def _draw_slots(self, context, layout):
        prefs = _get_prefs(context)
        active_racer = _active_racer(context)
        active_slug = active_racer.slug if active_racer else None

        row = layout.row(align=True)
        row.operator("nfr.slot_prev_page", text="", icon="TRIA_LEFT")
        row.label(text=f"Page {_slot_view_page} / {MAX_PAGES}")
        row.operator("nfr.slot_next_page", text="", icon="TRIA_RIGHT")

        row = layout.row(align=True)
        row.scale_y = 1.2
        row.operator("nfr.slot_refresh", text="Refresh", icon="FILE_REFRESH")
        assign_row = row.row(align=True)
        assign_row.enabled = (_slot_sel_page == _slot_view_page
                              and _slot_sel_slot >= 0
                              and active_racer is not None)
        assign_row.operator("nfr.slot_assign_here",
                            text="Assign Here", icon="ADD")

        entries = _read_roster(prefs)
        pages = _group_by_page(entries)
        page_entries = pages.get(_slot_view_page, {})
        cells = _resolve_cells(_slot_view_page, page_entries,
                               active_racer, active_slug)

        occupied = sum(1 for k, _ in cells.values() if k != "empty")
        layout.label(text=f"{occupied}/16 slots occupied")

        grid = layout.grid_flow(
            row_major=True, columns=4,
            even_columns=True, even_rows=True, align=True)

        for slot in range(16):
            kind, data = cells[slot]
            if kind in ("entry", "pending"):
                folder = data["folder"]
                png = prefs.racers_dir() / folder / "icon.png"
                icon = _get_icon(folder, png) if png.is_file() else None
                if icon is not None:
                    op = grid.operator("nfr.slot_click", text="",
                                       icon_value=icon.icon_id)
                else:
                    op = grid.operator("nfr.slot_click",
                                       text=folder[:6])
            else:
                op = grid.operator("nfr.slot_click", text=str(slot))
            op.page = _slot_view_page
            op.slot = slot

        if _slot_sel_page != _slot_view_page or _slot_sel_slot < 0:
            layout.separator()
            layout.label(text="Click a slot to inspect", icon="INFO")
            return

        kind, data = cells.get(_slot_sel_slot, ("empty", None))

        layout.separator()
        box = layout.box()

        if kind == "empty":
            box.label(text=f"Slot {_slot_sel_slot} — empty", icon="INFO")
            if active_racer is not None:
                box.label(text=f"Press 'Assign Here' to place {active_slug}")
            else:
                box.label(text="Select a racer mesh, then Assign Here")
            return

        row = box.row(align=True)
        preview_col = row.column()
        preview_col.scale_x = 1.0
        png = prefs.racers_dir() / data["folder"] / "icon.png"
        icon = _get_icon(data["folder"], png) if png.is_file() else None
        if icon is not None:
            preview_col.template_icon(icon_value=icon.icon_id, scale=5.0)

        info_col = row.column()
        info_col.scale_x = 1.0
        header = f"Slot {_slot_sel_slot} — {data['folder']}"
        if kind == "pending":
            header += "  (pending export)"
        info_col.label(text=header)
        info_col.label(text=data["name"])
        info_col.label(text=f"Engine: {data['engine']}")
        info_col.label(text=f"Mask: {data['mask']}")
        info_col.label(text=f"Wheels: {data['wheels']}")
        if data.get("color"):
            info_col.label(text=f"Color: {data['color']}")

        obj = _find_object_by_slug(data["folder"])
        if obj is not None:
            info_col.label(text=f"In blend: {obj.name}", icon="CHECKMARK")
        else:
            info_col.label(text="Not in this .blend", icon="INFO")

        row = box.row(align=True)
        if obj is not None:
            op = row.operator("nfr.slot_load_to_panel",
                              text="Focus", icon="RESTRICT_SELECT_OFF")
            op.slug = data["folder"]
        if kind == "entry":
            op = row.operator("nfr.slot_delete",
                              text="Delete from roster", icon="TRASH")
            op.page = _slot_sel_page
            op.slot = _slot_sel_slot

    # ---------------------------------------------------------------------
    # MATERIALS tab
    # ---------------------------------------------------------------------
    def _draw_materials(self, context, layout):
        scene = context.scene
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            layout.label(text="Select a mesh object", icon="INFO")
            return

        m = obj.data

        # -------- Render ON/OFF (top of tab) --------
        top = layout.row(align=True)
        top.scale_y = 1.4
        toggle_icon = 'RADIOBUT_ON' if scene.nfr_ps1_render_state else 'RADIOBUT_OFF'
        top.operator(
            "nfr.ps1_toggle_render",
            text="Render: ON" if scene.nfr_ps1_render_state else "Render: OFF",
            icon=toggle_icon,
        )
        layout.separator()

        if not m.materials:
            layout.label(text="No materials on this mesh", icon="INFO")
            return

        mats = [mat for mat in m.materials if mat is not None]
        total = len(mats)
        if total == 0:
            layout.label(text="No materials on this mesh", icon="INFO")
            return

        total_pages = max(1, (total + MAX_MATS_PER_PAGE - 1) // MAX_MATS_PER_PAGE)

        global _mat_view_page
        if _mat_view_page < 1:
            _mat_view_page = 1
        if _mat_view_page > total_pages:
            _mat_view_page = total_pages

        # -------- Pagination (only if more than one page) --------
        if total_pages > 1:
            row = layout.row(align=True)
            sub_left = row.row(align=True)
            sub_left.enabled = _mat_view_page > 1
            sub_left.operator("nfr.mat_prev_page", text="", icon="TRIA_LEFT")
            row.label(
                text=f"Materials  {_mat_view_page} / {total_pages}  ({total} total)"
            )
            sub_right = row.row(align=True)
            sub_right.enabled = _mat_view_page < total_pages
            sub_right.operator("nfr.mat_next_page", text="", icon="TRIA_RIGHT")
            layout.separator()

        start = (_mat_view_page - 1) * MAX_MATS_PER_PAGE
        end = min(start + MAX_MATS_PER_PAGE, total)
        page_mats = mats[start:end]

        # -------- Per material --------
        for mat in page_mats:
            stored = mat.get("blend_mode", "half")
            if stored not in _BLEND_MODE_SET:
                stored = "half"
            if getattr(mat, "nfr_racer_blend_mode", "half") != stored:
                mat.nfr_racer_blend_mode = stored

            box = layout.box()

            img = None
            if mat.use_nodes and mat.node_tree:
                for n in mat.node_tree.nodes:
                    if n.type == "TEX_IMAGE" and n.image:
                        img = n.image
                        break

            # Row 1: thumb | info | eye | apply
            row = box.row(align=True)

            icon_id = _image_preview_icon_id(img)
            if icon_id:
                row.template_icon(icon_value=icon_id, scale=2.0)
            else:
                row.label(text="", icon="IMAGE_DATA")

            info = row.column(align=True)
            info.label(text=mat.name, icon="MATERIAL")
            if img:
                info.label(text=img.name, icon="IMAGE_DATA")
            else:
                info.label(text="(no image)", icon="ERROR")

            is_showing = getattr(mat, 'nfr_ps1_show_backface', False)
            toggle_op = row.operator(
                "nfr.toggle_double_sided",
                text="",
                icon='HIDE_OFF' if is_showing else 'HIDE_ON',
                depress=is_showing,
            )
            toggle_op.material_name = mat.name

            apply_op = row.operator(
                "nfr.racer_apply_blend_mode",
                text="",
                icon='CHECKMARK',
            )
            apply_op.material_name = mat.name

            # Row 2: blend mode dropdown
            drop = box.row(align=True)
            drop.prop(mat, "nfr_racer_blend_mode", text="")


# =========================================================================
# MODULE: registration
# =========================================================================
_classes = (
    NFR_RacerProps,
    NFR_Preferences,
    NFR_OT_Validate,
    NFR_OT_Export,
    NFR_OT_ExportAll,
    NFR_OT_SaveSettings,
    NFR_OT_LoadSettings,
    NFR_OT_BuildExe,
    NFR_OT_RunGame,
    NFR_OT_BuildAndRun,
    NFR_OT_SlotClick,
    NFR_OT_SlotAssignHere,
    NFR_OT_SlotDelete,
    NFR_OT_SlotRefresh,
    NFR_OT_SlotPrevPage,
    NFR_OT_SlotNextPage,
    NFR_OT_SlotLoadToPanel,
    NFR_OT_MatPrevPage,
    NFR_OT_MatNextPage,
    NFR_OT_ToggleDoubleSided,
    NFR_OT_ApplyRacerBlendMode,
    # render
    NFR_OT_TogglePS1Render,
    NFR_OT_SetBackface,
    NFR_OT_ApplyBlendMode,
    # panel (single)
    NFR_PT_Racer,
)


def _register_render_props():
    # UI sub-tab
    bpy.types.Scene.nfr_ui_tab = EnumProperty(
        name="Tab",
        description="Section to display in the CTR Racer panel",
        items=[
            ('SETTINGS',  "Settings",  "Racer settings and dev tools"),
            ('SLOTS',     "Slots",     "Page/slot grid and roster"),
            ('MATERIALS', "Materials", "Per-material render settings"),
        ],
        default='SETTINGS',
    )

    # Scene
    bpy.types.Scene.nfr_ps1_render_state = BoolProperty(default=False)
    bpy.types.Scene.nfr_ps1_render_active = BoolProperty(default=False)
    bpy.types.Scene.nfr_ps1_prev_shadow_state = BoolProperty(default=True)
    bpy.types.Scene.nfr_ps1_blend_mode = EnumProperty(
        items=[
            ('HALF_TRANSPARENT', "Half Transparent", ""),
            ('ADDITIVE', "Additive", ""),
            ('SUBTRACTIVE', "Subtractive", ""),
            ('ADDITIVE_TRANSLUCENT', "Additive Translucent", ""),
        ],
        default='HALF_TRANSPARENT',
    )

    # Material — PS1 render
    bpy.types.Material.nfr_ps1_blend_mode = EnumProperty(
        items=[
            ('NONE', "None", ""),
            ('ADDITIVE', "Additive", ""),
            ('SUBTRACTIVE', "Subtractive", ""),
            ('HALF_TRANSPARENT', "Half Transparent", ""),
            ('ADDITIVE_TRANSLUCENT', "Additive Translucent", ""),
        ],
        default='NONE',
        update=_nfr_update_ps1_blend_mode,
    )
    bpy.types.Material.nfr_ps1_last_active_mode = EnumProperty(
        items=[
            ('NONE', "None", ""),
            ('ADDITIVE', "Additive", ""),
            ('SUBTRACTIVE', "Subtractive", ""),
            ('HALF_TRANSPARENT', "Half Transparent", ""),
            ('ADDITIVE_TRANSLUCENT', "Additive Translucent", ""),
        ],
        default='NONE',
    )
    bpy.types.Material.nfr_ps1_show_backface = BoolProperty(default=False)
    bpy.types.Material.nfr_ps1_blend_method_override = EnumProperty(
        items=[
            ('AUTO', "Auto", ""),
            ('OPAQUE', "Opaque", ""),
            ('CLIP', "Clip", ""),
            ('HASHED', "Hashed", ""),
            ('BLEND', "Blend", ""),
        ],
        default='AUTO',
    )
    bpy.types.Material.nfr_ps1_transparency_overlap_mode = EnumProperty(
        items=[
            ('DEFAULT', "Default", ""),
            ('MANUAL', "Manual", ""),
        ],
        default='DEFAULT',
    )
    bpy.types.Material.nfr_ps1_transparency_overlap_manual = BoolProperty(
        default=True,
    )

    # Material — racer blend mode
    bpy.types.Material.nfr_racer_blend_mode = EnumProperty(
        name="Blend Mode",
        description="Per-material blend mode forwarded to source_mesh.json",
        items=BLEND_MODES,
        default="half",
        update=_nfr_mat_blend_mode_update,
    )


def _unregister_render_props():
    del bpy.types.Scene.nfr_ui_tab
    del bpy.types.Scene.nfr_ps1_render_state
    del bpy.types.Scene.nfr_ps1_render_active
    del bpy.types.Scene.nfr_ps1_prev_shadow_state
    del bpy.types.Scene.nfr_ps1_blend_mode
    del bpy.types.Material.nfr_ps1_blend_mode
    del bpy.types.Material.nfr_ps1_last_active_mode
    del bpy.types.Material.nfr_ps1_show_backface
    del bpy.types.Material.nfr_ps1_blend_method_override
    del bpy.types.Material.nfr_ps1_transparency_overlap_mode
    del bpy.types.Material.nfr_ps1_transparency_overlap_manual
    del bpy.types.Material.nfr_racer_blend_mode


def register():
    for c in _classes:
        bpy.utils.register_class(c)
    bpy.types.Object.racer = PointerProperty(type=NFR_RacerProps)
    _register_render_props()


def unregister():
    _teardown_previews()
    _unregister_render_props()
    if hasattr(bpy.types.Object, "racer"):
        del bpy.types.Object.racer
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()