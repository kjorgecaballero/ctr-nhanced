# =========================================================================
# MODULE: render — color attribute helpers
# =========================================================================
"""Color attribute ("Color") creation and normalization.

Ensures every mesh has a BYTE_COLOR CORNER attribute called "Color",
matching what the C exporter reads (see export_character.py).

Pure helpers. No registration.
"""
import bpy
import bmesh


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