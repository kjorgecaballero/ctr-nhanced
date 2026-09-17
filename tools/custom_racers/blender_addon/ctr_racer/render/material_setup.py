# =========================================================================
# MODULE: render — PS1 material setup
# =========================================================================
"""PS1 material node setups.

NFR_PS1MaterialSetup is the base class. Four subclasses select one of
the four PS1 blend modes. NFR_PS1MaterialFactory picks the right one.

The node graph data lives in render/node_setups.py.

Reads Material props (nfr_ps1_blend_method_override,
nfr_ps1_transparency_overlap_mode, nfr_ps1_transparency_overlap_manual,
nfr_ps1_show_backface) that are registered elsewhere; all accesses are
guarded with getattr so this module works regardless of registration
order.
"""
import numpy as np

from .node_setups import NFR_PS1_NODE_SETUPS


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