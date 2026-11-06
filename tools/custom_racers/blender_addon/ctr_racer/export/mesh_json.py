
def _linear_to_srgb(c):
    if c <= 0.0031308:
        return 12.92 * c
    return 1.055 * (c ** (1.0 / 2.4)) - 0.055

# =========================================================================
# MODULE: export — mesh json
# =========================================================================
"""Mesh → source_mesh.json export pipeline."""

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


def export_mesh_json(obj, out_path, override_clips=None):
    """Serialize `obj` to source_mesh.json."""
    r = obj.racer
    is_custom = (r.kart_rot == 'custom')
    
    # Save rotation delta (Live Preview) and center object for export
    prev_delta = list(obj.delta_rotation_euler)
    if is_custom:
        obj.delta_rotation_euler = (0.0, 0.0, 0.0)
        bpy.context.view_layer.update()
        
    m = obj.data
    m.calc_loop_triangles()

    materials = []
    images = {}
    for slot_idx, mat in enumerate(m.materials):
        # Empty slot: m.materials can contain None when the user
        # deleted a material but left the slot. Polygon
        # material_index still points here, so we append a
        # placeholder -- a `continue` would shift every later
        # material one slot left and remap every face.
        if mat is None:
            materials.append({
                "name": f"__empty_slot_{slot_idx}__",
                "image": None,
                "double_sided": False,
                "blend_mode": "half",
            })
            continue
        # Material with use_nodes off or purged node_tree: keep the
        # real name but no image. The polygon material_index stays
        # valid.
        if not mat.use_nodes or mat.node_tree is None:
            materials.append({
                "name": mat.name,
                "image": None,
                "double_sided": not mat.use_backface_culling,
                "blend_mode": "half",
            })
            continue

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

    if m.shape_keys:
        keys_dict = {k.name: [list(v.co) for v in k.data]
                     for k in m.shape_keys.key_blocks}
    else:
        keys_dict = {"Basis": [list(v.co) for v in m.vertices]}

    result = {
        "jump_rot_enable": is_custom,
        "jump_rot_pitch": getattr(r, "jump_rot_pitch", 0.0),
        "jump_rot_roll": getattr(r, "jump_rot_roll", 0.0),
        "jump_rot_yaw": getattr(r, "jump_rot_yaw", 0.0),
        "jump_rot_pivot_z": getattr(r, "jump_rot_pivot_z", 0.35),
        "jump_rot_frames": getattr(r, "jump_rot_frames", 4),
        "source": bpy.data.filepath,
        "source_sha256": src_hash,
        "matrix_world": [list(row) for row in obj.matrix_world],
        "vertices": [list(v.co) for v in m.vertices],
        "triangles": [{"polygon": t.polygon_index, "material": t.material_index,
                       "corners": corners(t)} for t in m.loop_triangles],
        "materials": materials,
        "images": images,
        "keys": keys_dict,
        "groups": {g.name: {str(v.index): next((a.weight for a in v.groups
                                                if a.group == g.index), 0)
                            for v in m.vertices} for g in obj.vertex_groups},
    }

    # Optional: bake per-frame vertex positions from the timeline.
    if override_clips is not None:
        result["clips"] = override_clips
    else:
        # Guarded so a broken JSON in prefs doesn't kill the export.
        try:
            prefs = _get_prefs(bpy.context)
            if getattr(prefs, "anim_use_timeline", False):
                ranges = json.loads(getattr(prefs, "anim_frame_ranges", "{}"))
                if ranges:
                    result["clips"] = _bake_timeline_clips(obj, ranges)
        except Exception as ex:
            print(f"[mesh_json] timeline bake skipped: {ex}")

    # Restore visual rotation after export
    if getattr(r, "jump_rot_enable", False):
        obj.delta_rotation_euler = prev_delta
        bpy.context.view_layer.update()

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
    cmd += ["--rot", r.kart_rot]

    if prefs.sentinel_models:
        cmd.append("--sentinel")

    if tuple(r.color[:3]) != (1.0, 1.0, 1.0):
        hexcol = "#{:02X}{:02X}{:02X}".format(
            int(_linear_to_srgb(r.color[0]) * 255), 
            int(_linear_to_srgb(r.color[1]) * 255), 
            int(_linear_to_srgb(r.color[2]) * 255))
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


def _bake_timeline_clips(obj, frame_ranges):
    """Bake per-frame vertex positions from the Blender timeline."""
    scene = bpy.context.scene
    original_frame = scene.frame_current
    depsgraph = bpy.context.evaluated_depsgraph_get()
    result = {}
    try:
        for clip_name, (fmin, fmax) in frame_ranges.items():
            frames = []
            for f in range(int(fmin), int(fmax) + 1):
                scene.frame_set(f)
                depsgraph.update()
                obj_eval = obj.evaluated_get(depsgraph)
                mesh_eval = obj_eval.to_mesh()
                frames.append([[v.co.x, v.co.y, v.co.z]
                               for v in mesh_eval.vertices])
                obj_eval.to_mesh_clear()
            result[clip_name] = frames
    finally:
        scene.frame_set(original_frame)
    return result