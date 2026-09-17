# =========================================================================
# MODULE: export — mesh json
# =========================================================================
"""Mesh → source_mesh.json export pipeline.

Owns:
  - _get_blend_mode (Material "blend_mode" custom prop validator)
  - export_mesh_json (builds the JSON dict and writes it)
  - _do_export / _do_export_body (mode-switch wrapper + body)
  - _racer_objects (collects meshes marked as racer)
"""
import bpy
import os
import json
import hashlib
import subprocess
from pathlib import Path

from ..constants import _BLEND_MODE_SET
from ..prefs import _get_prefs


def _get_blend_mode(mat):
    value = mat.get("blend_mode", "half")
    if value not in _BLEND_MODE_SET:
        return "half"
    return value


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