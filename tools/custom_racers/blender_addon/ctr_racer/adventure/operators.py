import bpy
import os
import json
import tempfile
import subprocess
import math
from bpy.props import IntProperty, StringProperty
from bpy.types import Operator


# ─────────────────────────────────────────────────────────────────────
# Blender (Z-up, metros)  ->  motor CTR (Y-up, ANG 0x1000 = 360 grados)
#
# Mismo cambio de ejes que usa build_character.py para el mesh:
#     motor = (bx, bz, -by)
# Un personaje que mira a -Y en Blender (vista frontal) mira a +Z en el
# motor con yaw 0, asi que yaw_motor = rotacion Z de Blender.
# ─────────────────────────────────────────────────────────────────────
# Unidades de motor por unidad de Blender. Debe coincidir con K=64 en build_character.py.
NFR_ENGINE_SCALE = 64.0
# Si el personaje sale girado en el garaje, sumar 0x800 (180 grados) aqui.
NFR_SLOT_YAW_OFFSET = 0


def _s16(v):
    """Redondea y satura a s16 (el motor guarda posiciones en s16)."""
    return max(-32768, min(32767, int(round(v))))


def _ang(rad):
    """Radianes -> unidades ANG del motor (0x1000 = 360 grados)."""
    return int(round(rad * 4096.0 / (2.0 * math.pi)))


def _pos_to_engine(v):
    k = NFR_ENGINE_SCALE
    return _s16(v.x * k), _s16(v.z * k), _s16(-v.y * k)


def _slot_from_object(slot, obj):
    """Captura posicion/yaw en espacio mundo y en coordenadas del motor."""
    mw = obj.matrix_world
    slot.pos_x, slot.pos_y, slot.pos_z = _pos_to_engine(mw.translation)
    slot.pos_rot = (_ang(mw.to_euler().z) + NFR_SLOT_YAW_OFFSET) & 0xFFF


def _camera_to_engine(cam):
    """Posicion + (pitch, yaw) de la camara en espacio motor.

    La camara de Blender mira hacia su -Z local. Se saca ese vector en mundo,
    se pasa al motor y se calcula yaw/pitch con la misma convencion que usa
    CS_Garage.c para su look-at: yaw = atan2(dx, dz), pitch positivo = mira
    hacia arriba. El roll no se exporta (el garaje lo fija a 180 grados).
    """
    from mathutils import Vector
    mw = cam.matrix_world
    px, py, pz = _pos_to_engine(mw.translation)
    f = mw.to_quaternion() @ Vector((0.0, 0.0, -1.0))
    fx, fy, fz = f.x, f.z, -f.y
    yaw = math.atan2(fx, fz)
    pitch = math.atan2(fy, math.hypot(fx, fz))
    return px, py, pz, _ang(pitch), _ang(yaw) & 0xFFF


def _root(context):
    """Get the repo root (folder that contains tools/custom_racers/)."""
    try:
        from ..prefs import _get_prefs
        from ..constants import DEFAULT_REPO
    except Exception as e:
        raise RuntimeError(f"NFR: cannot import prefs/constants: {e}")

    prefs = _get_prefs(context)

    # 1. Try preferences (several possible attribute names)
    for attr in ("repo_root", "repo", "repo_path"):
        v = getattr(prefs, attr, "") if prefs is not None else ""
        if v:
            p = os.path.abspath(bpy.path.abspath(v))
            if os.path.isdir(os.path.join(p, "tools", "custom_racers")):
                return p

    # 2. Try DEFAULT_REPO
    if DEFAULT_REPO:
        p = os.path.abspath(bpy.path.abspath(DEFAULT_REPO))
        if os.path.isdir(os.path.join(p, "tools", "custom_racers")):
            return p

    # 3. Walk up from __file__ (works only when running from source)
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(10):
        here = os.path.dirname(here)
        if os.path.isdir(os.path.join(here, "tools", "custom_racers")):
            return here

    # 4. Nothing found: clear error
    raise RuntimeError(
        "NFR: Cannot find the repo root. "
        "Configure 'Repo root' in Edit -> Preferences -> Add-ons -> CTR Racer. "
        "It must point to a folder containing 'tools/custom_racers/'. "
        f"DEFAULT_REPO={DEFAULT_REPO!r}"
    )


def _clean_path(path):
    if not path:
        return ""
    path = path.strip().strip('"').strip("'")
    # Resolve Blender's // (relative to .blend) to absolute
    if path.startswith("//"):
        try:
            path = bpy.path.abspath(path)
        except Exception:
            pass
    # Normalize separators (Blender uses / even on Windows)
    path = os.path.normpath(path)
    return path


def get_python_exe():
    """Get Blender's internal Python (portable, no system Python needed)."""
    if hasattr(bpy.app, "binary_path_python") and bpy.app.binary_path_python:
        return bpy.app.binary_path_python
    import sys
    return sys.executable


# ─────────────────────────────────────────────────────────────────────
# CAMERA
# ─────────────────────────────────────────────────────────────────────
class NFR_OT_AdventureAddCam(Operator):
    bl_idname = "nfr.adventure_add_cam"
    bl_label = "Add Camera"
    ar: StringProperty(default="4:3")

    def execute(self, context):
        self.report({'INFO'}, f"Camera preset {self.ar} (use Get from Active Cam)")
        return {'FINISHED'}


class NFR_OT_AdventureAssignCam(Operator):
    bl_idname = "nfr.adventure_assign_cam"
    bl_label = "Get from Active Camera"

    def execute(self, context):
        st = context.scene.nfr_adventure
        cam = context.scene.camera
        if cam is None:
            self.report({'ERROR'}, "No active camera in scene")
            return {'CANCELLED'}
        (st.cam_x, st.cam_y, st.cam_z,
         st.cam_rot_x, st.cam_rot_y) = _camera_to_engine(cam)
        # cam_rot_x = pitch (positivo = mira arriba), cam_rot_y = yaw; ANG 0x1000 = 360
        st.cam_captured = True
        self.report({'INFO'},
                    f"Camera captured (engine): X:{st.cam_x} Y:{st.cam_y} Z:{st.cam_z} "
                    f"pitch:{st.cam_rot_x} yaw:{st.cam_rot_y}")
        return {'FINISHED'}


class NFR_OT_AdventureAimCam(Operator):
    bl_idname = "nfr.adventure_aim_cam"
    bl_label = "Aim Camera at Slot 0"

    def execute(self, context):
        st = context.scene.nfr_adventure
        cam = context.scene.camera
        if cam is None or len(st.slots) == 0:
            return {'CANCELLED'}
        slot0 = st.slots[0]
        # Point the camera at slot 0
        # (simple: align -Z axis of camera to slot0 position)
        self.report({'INFO'}, f"Aim at S0 ({slot0.char_slug})")
        return {'FINISHED'}


# ─────────────────────────────────────────────────────────────────────
# SLOT ASSIGN (used by panel "Get" button if it exists)
# ─────────────────────────────────────────────────────────────────────
class NFR_OT_AdventureAssignSingle(Operator):
    bl_idname = "nfr.adventure_assign_single"
    bl_label = "Get Slot"
    slot_index: IntProperty(default=0)

    def execute(self, context):
        st = context.scene.nfr_adventure
        if self.slot_index >= len(st.slots):
            self.report({'ERROR'}, "Invalid slot index")
            return {'CANCELLED'}
        slot = st.slots[self.slot_index]
        obj = context.active_object
        if obj is None:
            self.report({'ERROR'}, "No active object")
            return {'CANCELLED'}
        slot.idle_object = obj
        if not slot.char_slug:
            slot.char_slug = obj.name.lower().replace(" ", "_")
        _slot_from_object(slot, obj)
        self.report({'INFO'}, f"Slot {self.slot_index} = {slot.char_slug} @ ({slot.pos_x},{slot.pos_y},{slot.pos_z})")
        return {'FINISHED'}


# ─────────────────────────────────────────────────────────────────────
# EXPORT ASSETS (per-slot .ctr export)
# ─────────────────────────────────────────────────────────────────────
class NFR_OT_AdventureExportAssets(Operator):
    bl_idname = "nfr.adventure_export_assets"
    bl_label = "Export Garage Model"
    bl_description = "Export ONLY the character (idle_object) to <slug>/garage/model.ctr + sentinel_*.bin"

    def execute(self, context):
        from pathlib import Path
        from ..export.mesh_json import export_mesh_json
        import subprocess

        st = context.scene.nfr_adventure
        idx = st.active_slot_idx
        if idx >= len(st.slots): return {'CANCELLED'}
        slot = st.slots[idx]
        if slot.idle_object is None:
            self.report({'ERROR'}, "Set the Idle/Character Object first")
            return {'CANCELLED'}
        if not slot.char_slug:
            slot.char_slug = slot.idle_object.name.lower().replace(" ", "_")

        root = _root(context)
        slug_dir = Path(root) / "assets" / "mods" / "racers" / slot.char_slug
        garage_dir = slug_dir / "garage"
        garage_dir.mkdir(parents=True, exist_ok=True)
        source_dir = slug_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)

        build_py = Path(root) / "tools" / "custom_racers" / "build_character.py"
        py_exe = get_python_exe()

        obj = slot.idle_object
        _slot_from_object(slot, obj)

        json_path = source_dir / "source_mesh_garage.json"
        export_mesh_json(obj, json_path)
        out_ctr = garage_dir / "model.ctr"
        cmd = [py_exe, str(build_py), str(json_path), slot.char_slug, str(out_ctr), "--sentinel", "--garage"]
        r = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
        if r.returncode != 0:
            self.report({'ERROR'}, "Character garage build failed. Check console.")
            return {'CANCELLED'}

        self.report({'INFO'}, f"S{idx} ({slot.char_slug}): garage model exported.")
        return {'FINISHED'}


class NFR_OT_AdventureExportKart(Operator):
    bl_idname = "nfr.adventure_export_kart"
    bl_label = "Export Kart"
    bl_description = "Export ONLY the kart to <slug>/garage/kart/kart.ctr"

    def execute(self, context):
        from pathlib import Path
        from ..export.mesh_json import export_mesh_json
        import subprocess
        import shutil

        st = context.scene.nfr_adventure
        idx = st.active_slot_idx
        if idx >= len(st.slots): return {'CANCELLED'}
        slot = st.slots[idx]
        if slot.kart_object is None:
            self.report({'ERROR'}, "Set the Kart Object first")
            return {'CANCELLED'}
        if not slot.char_slug:
            if slot.idle_object:
                slot.char_slug = slot.idle_object.name.lower().replace(" ", "_")
            else:
                return {'CANCELLED'}

        root = _root(context)
        slug_dir = Path(root) / "assets" / "mods" / "racers" / slot.char_slug
        kart_dir = slug_dir / "garage" / "kart"
        kart_dir.mkdir(parents=True, exist_ok=True)
        source_dir = slug_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)

        build_py = Path(root) / "tools" / "custom_racers" / "build_character.py"
        py_exe = get_python_exe()

        json_path = source_dir / "source_mesh_kart.json"
        export_mesh_json(slot.kart_object, json_path)
        out_ctr = kart_dir / "kart.ctr"
        cmd = [py_exe, str(build_py), str(json_path), slot.char_slug, str(out_ctr), "--sentinel"]
        r = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
        
        if r.returncode != 0:
            self.report({'ERROR'}, "Kart build failed.")
            return {'CANCELLED'}

        shutil.copy2(out_ctr, slug_dir / "kart.ctr")
        self.report({'INFO'}, f"S{idx}: kart exported safely to garage/kart/.")
        return {'FINISHED'}

class NFR_OT_AdventureSfxAdd(Operator):
    bl_idname = "nfr.adventure_sfx_add"
    bl_label = "Add SFX"

    def execute(self, context):
        st = context.scene.nfr_adventure
        if st.active_slot_idx >= len(st.slots):
            return {'CANCELLED'}
        slot = st.slots[st.active_slot_idx]
        slot.sfx_entries.add()
        self.report({'INFO'}, "SFX entry added")
        return {'FINISHED'}


class NFR_OT_AdventureSfxRemove(Operator):
    bl_idname = "nfr.adventure_sfx_remove"
    bl_label = "Remove SFX"
    index: IntProperty(default=0)

    def execute(self, context):
        st = context.scene.nfr_adventure
        if st.active_slot_idx >= len(st.slots):
            return {'CANCELLED'}
        slot = st.slots[st.active_slot_idx]
        if 0 <= self.index < len(slot.sfx_entries):
            slot.sfx_entries.remove(self.index)
        return {'FINISHED'}


class NFR_OT_AdventureBuildAudio(Operator):
    bl_idname = "nfr.adventure_build_audio"
    bl_label = "Build Audio for Slot"

    def execute(self, context):
        self.report({'INFO'},
                    "Audio pipeline for garage slots is a separate feature "
                    "(see docs/CUSTOM_GARAGE_CONTEXT.md §8). "
                    "For now, no audio is generated.")
        return {'FINISHED'}


# ─────────────────────────────────────────────────────────────────────
# BUILD GARAGE PACK (the main operator)
# ─────────────────────────────────────────────────────────────────────
class NFR_OT_AdventureBuild(Operator):
    bl_idname = "nfr.adventure_build"
    bl_label = "BUILD GARAGE PACK"

    def execute(self, context):
        st = context.scene.nfr_adventure
        try:
            root = _root(context)
        except Exception as e:
            self.report({'ERROR'}, str(e))
            print(f"[NFR] BUILD: _root failed: {e}")
            return {'CANCELLED'}
        script = os.path.join(root, "tools", "custom_racers", "add_adventure_pack.py")
        print(f"[NFR] BUILD: root={root}")
        print(f"[NFR] BUILD: script={script} exists={os.path.isfile(script)}")

        lev_path = _clean_path(st.lev_file)
        vrm_path = _clean_path(st.vrm_file)

        print(f"\n--- GARAGE BUILD START ---")
        print(f"Root: {root}")
        print(f"Script: {script}")
        print(f"LEV: {lev_path}")
        print(f"VRM: {vrm_path}")
        print(f"Slots: {len(st.slots)}")

        if not lev_path or not vrm_path or not os.path.isfile(lev_path) or not os.path.isfile(vrm_path):
            msg = (f"Archivos no encontrados.\n"
                   f"  LEV: {lev_path}\n"
                   f"       (raw: {st.lev_file})\n"
                   f"  VRM: {vrm_path}\n"
                   f"       (raw: {st.vrm_file})\n"
                   f"Tip: en el file picker, desactivá 'Relative Paths' "
                   f"si tus archivos no están en la carpeta del .blend.")
            self.report({'ERROR'}, msg)
            print(f"[NFR] BUILD CANCELLED: {msg}")
            return {'CANCELLED'}
        if not os.path.isfile(script):
            self.report({'ERROR'}, f"No se encuentra el script en: {script}")
            return {'CANCELLED'}

        # Ensure 8 slots
        while len(st.slots) < 8:
            st.slots.add()

        # Build the data JSON (slots + camera)
        slots_json = []
        for i in range(8):
            s = st.slots[i]
            # Auto-derive kart slug from kart_object if set
            kart_slug = ""
            if s.kart_object is not None:
                racers_dir = os.path.join(root, "assets", "mods", "racers")
                cands = [s.kart_object.name.lower().replace(" ", "_"),
                         s.kart_object.name, s.char_slug]
                for c in cands:
                    if c and os.path.isfile(os.path.join(racers_dir, c, "kart.ctr")):
                        kart_slug = c
                        break
                if not kart_slug:
                    self.report({'WARNING'},
                                f"Slot {i}: no encontre kart.ctr para {cands} en {racers_dir}")
            # --- KART POS ---
            kx = ky = kz = kr = 0
            if s.kart_object is not None:
                kmw = s.kart_object.matrix_world
                kx, ky, kz = _pos_to_engine(kmw.translation)
                kr = (_ang(kmw.to_euler().z) + NFR_SLOT_YAW_OFFSET) & 0xFFF

            if s.idle_object is not None:
                _slot_from_object(s, s.idle_object)

            slots_json.append({
                "char": s.char_slug,
                "kx": kx, "ky": ky, "kz": kz, "krot": kr,
                "kart": kart_slug,
                "x": s.pos_x,
                "y": s.pos_y,
                "z": s.pos_z,
                "rot": s.pos_rot,
                "idle_anim": s.idle_anim,
                "idle_start": s.idle_start,
                "idle_end": s.idle_end,
                "idle_loop": 1 if s.idle_loop else 0,
                "select_anim": s.select_anim,
                "select_start": s.select_start,
                "select_end": s.select_end,
                "select_loop": 1 if s.select_loop else 0,
                "ambient_wav": _clean_path(s.ambient_wav) if s.ambient_wav else "",
                "sfx": [
                    {"frame": e.frame, "wav": _clean_path(e.wav_path)}
                    for e in s.sfx_entries
                ],
            })

        data = {
            "slots": slots_json,
            "camera": {
                "x": st.cam_x, "y": st.cam_y, "z": st.cam_z,
                "rot_x": st.cam_rot_x, "rot_y": st.cam_rot_y,
                "captured": 1 if st.cam_captured else 0,
            },
        }

        # Write to temp file
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8')
        json.dump(data, tmp, indent=2)
        tmp.close()

        py_exe = _clean_path(get_python_exe())
        cmd = [
            py_exe, script,
            "--name", st.pack_name,
            "--slug", st.slug,
            "--lev", lev_path,
            "--vrm", vrm_path,
            "--data-json", tmp.name,
        ]

        print(f"Executing: {cmd}")
        try:
            p = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
            if p.stdout: print(f"STDOUT:\n{p.stdout}")
            if p.stderr: print(f"STDERR:\n{p.stderr}")

            if p.returncode != 0:
                self.report({'ERROR'}, f"Fallo el script (rc={p.returncode}). Revisa la consola.")
                return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Excepcion: {e}")
            return {'CANCELLED'}
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

        self.report({'INFO'}, "Garage Pack built successfully")
        return {'FINISHED'}



_classes = (
    NFR_OT_AdventureAddCam,
    NFR_OT_AdventureAssignCam,
    NFR_OT_AdventureAimCam,
    NFR_OT_AdventureAssignSingle,
    NFR_OT_AdventureExportAssets,
    NFR_OT_AdventureExportKart,
    NFR_OT_AdventureSfxAdd,
    NFR_OT_AdventureSfxRemove,
    NFR_OT_AdventureBuildAudio,
    NFR_OT_AdventureBuild,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)