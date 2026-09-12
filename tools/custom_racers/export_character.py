"""Export a Blender object into source_mesh.json.

Run from Blender's Scripting workspace. Edit the three constants below,
then execute the script.
"""
import bpy, json, hashlib
from pathlib import Path

# ===== EDIT THESE 3 LINES =====
OBJECT_NAME = 'Rusty'                          # object name in Blender
OUTPUT_DIR  = Path(r'')
OUTPUT_NAME = 'rusty'                          # slug, no spaces
# ==============================

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUTPUT_DIR / f'source_mesh_{OUTPUT_NAME}.json'

o = bpy.data.objects.get(OBJECT_NAME)
if o is None:
    available = ', '.join(obj.name for obj in bpy.data.objects)
    raise SystemExit(f'Object "{OBJECT_NAME}" not found. Available objects: {available}')

m = o.data
m.calc_loop_triangles()

materials = []; images = {}
for mat in m.materials:
    imgs = [n.image for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image]
    imgs = list(set(imgs))
    if len(imgs) > 1:
        raise ValueError(f"Material {mat.name} has multiple images")
    im = imgs[0] if imgs else None
    materials.append({'name': mat.name, 'image': im.name if im else None})
    if im and im.name not in images:
        images[im.name] = {'size': list(im.size), 'pixels_rgba': list(im.pixels)}

def corners(tri):
    return [{'vertex': m.loops[li].vertex_index,
             'uv': list(m.uv_layers.active.data[li].uv),
             'color_linear': list(m.color_attributes['Color'].data[li].color),
             'color_srgb': list(m.color_attributes['Color'].data[li].color_srgb)}
            for li in tri.loops]

result = {
    'source': bpy.data.filepath,
    'source_sha256': hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest(),
    'matrix_world': [list(r) for r in o.matrix_world],
    'vertices': [list(v.co) for v in m.vertices],
    'triangles': [{'polygon': t.polygon_index, 'material': t.material_index,
                   'corners': corners(t)} for t in m.loop_triangles],
    'materials': materials,
    'images': images,
    'keys': {k.name: [list(v.co) for v in k.data] for k in m.shape_keys.key_blocks},
    'groups': {g.name: {str(v.index): next((a.weight for a in v.groups if a.group == g.index), 0)
                        for v in m.vertices} for g in o.vertex_groups},
}

OUT_PATH.write_text(json.dumps(result, separators=(',', ':')), encoding='utf-8')
print('EXPORTED', OBJECT_NAME, '->', OUT_PATH)
print(json.dumps({
    'vertices': len(m.vertices),
    'triangles': len(m.loop_triangles),
    'images': list(images.keys()),
    'keys': list(result['keys'])[:5],
}))