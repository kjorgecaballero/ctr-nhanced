"""Export a Blender object into source_mesh.json.

Run from Blender's Scripting workspace. Edit the two constants below,
then execute the script.

The output goes to <repo>/native_fork/racers/ by default, ready to be
consumed by add_racer.py.
"""
import bpy, json, hashlib
from pathlib import Path

# ===== EDIT THESE 2 LINES =====
OBJECT_NAME = 'ernest'   # object name in Blender (outliner)
OUTPUT_NAME = 'ernest'   # slug, no spaces, matches the target folder name
# ==============================

# <repo>/native_fork/racers/  (this file lives in <repo>/nhanced/tools/custom_racers/)
REPO_ROOT = Path(__file__).resolve().parents[3] if '__file__' in dir() else None
if REPO_ROOT is None or not (REPO_ROOT / 'nhanced').exists():
    # __file__ is not defined when pasted into Blender's console; try bpy
    REPO_ROOT = Path(bpy.data.filepath).resolve().parents[3] if bpy.data.filepath else Path.cwd()
    while REPO_ROOT != REPO_ROOT.parent and not (REPO_ROOT / 'nhanced').exists():
        REPO_ROOT = REPO_ROOT.parent

OUTPUT_DIR = Path(r'C:\Users\Kevin\Desktop\Kevin\CTR\native_fork\ctr_racer_source')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUTPUT_DIR / f'source_mesh_{OUTPUT_NAME}.json'

# ---- fetch + validate ----
o = bpy.data.objects.get(OBJECT_NAME)
if o is None:
    avail = ', '.join(obj.name for obj in bpy.data.objects)
    raise SystemExit(f'Object "{OBJECT_NAME}" not found. Available: {avail}')

m = o.data
m.calc_loop_triangles()

if m.shape_keys is None or 'Basis' not in m.shape_keys.key_blocks:
    raise SystemExit("ERROR: object has no shape key named 'Basis'")
if m.uv_layers.active is None:
    raise SystemExit("ERROR: object has no active UV map")
if 'Color' not in m.color_attributes:
    raise SystemExit("ERROR: object has no color attribute named 'Color'")

# ---- collect materials + images ----
materials = []
images = {}
for mat in m.materials:
    imgs = list({n.image for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image})
    if len(imgs) > 1:
        raise ValueError(f"Material '{mat.name}' has {len(imgs)} images; only 1 allowed per material")
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

src_hash = ''
try:
    bp = bpy.data.filepath
    if bp:
        src_hash = hashlib.sha256(Path(bp).read_bytes()).hexdigest()
except Exception as e:
    print(f"WARNING: could not hash blend file: {e}")

result = {
    'source': bpy.data.filepath,
    'source_sha256': src_hash,
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

print('=' * 64)
print(f'EXPORTED {OBJECT_NAME} -> {OUT_PATH}')
print(f'  vertices:    {len(m.vertices)}')
print(f'  triangles:   {len(m.loop_triangles)}')
print(f'  materials:   {len(materials)}')
print(f'  images:      {len(images)}')
print(f'  shape keys:  {list(result["keys"].keys())}')
print('=' * 64)
print()
print('Next (git-bash, from the repo root):')
print(f'  cd tools/custom_racers')
print(f'  python add_racer.py {OUTPUT_NAME} {OUT_PATH} <page> <slot> <engine> "<Display Name>" --icon <icon.png>')