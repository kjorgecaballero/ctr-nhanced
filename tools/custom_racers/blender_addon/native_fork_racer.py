# =========================================================================
# MODULE: bl_info
# =========================================================================
bl_info = {
    "name": "CTR NHanced Racer Export",
    "author": "kjorgecaballero",
    "version": (1, 7, 0),
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

DEFAULT_REPO   = r"C:\Users\Kevin\Desktop\Kevin\CTR\native_fork\nhanced"
DEFAULT_PYTHON = r"C:\Users\Kevin\AppData\Local\Programs\Python\Python312\python.exe"
ADDON_ID       = __name__ if __name__ != "__main__" else "native_fork_racer"

MAX_PAGES = 8


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
    """Return the icon_id of an Image datablock's preview thumbnail, or 0."""
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
    # calc_loop_triangles() and mesh data access don't work reliably in
    # Edit Mode; Blender throws "bpy_prop_collection[index]: index out of
    # range" on the first mesh.loops access. Switch to Object Mode for the
    # duration and restore the previous mode afterwards.
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
# MODULE: slot viewer state
# =========================================================================
_slot_view_page = 1
_slot_sel_page = -1
_slot_sel_slot = -1


def _resolve_cells(page, page_entries, active_racer, active_slug):
    """Returns { slot: (kind, data) } where kind is 'entry' | 'pending'
    | 'empty'. 'pending' means the active racer points here but the move
    has not been committed via Export yet."""
    cells = {}
    for slot in range(16):
        e = page_entries.get(slot)
        active_here = (active_racer is not None
                       and active_racer.page == page
                       and active_racer.slot == slot)

        if active_here:
            # Is roster already showing the same folder here? -> committed
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
            # Hide the active racer's stale roster entry so the grid
            # visually reflects the pending move rather than showing the
            # old icon in two places.
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
# MODULE: operators — materials panel
# =========================================================================
class NFR_OT_ToggleDoubleSided(Operator):
    bl_idname = "nfr.toggle_double_sided"
    bl_label = "Toggle double-sided"
    bl_description = ("Toggle Material.use_backface_culling. Off = visible "
                      "from both sides (double-sided) on export.")

    material_name: StringProperty()

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            return {"CANCELLED"}
        mat = obj.data.materials.get(self.material_name)
        if mat is None:
            self.report({"WARNING"}, f"Material '{self.material_name}' not found")
            return {"CANCELLED"}
        mat.use_backface_culling = not mat.use_backface_culling
        _redraw_view3d(context)
        return {"FINISHED"}


# =========================================================================
# MODULE: panels
# =========================================================================
class NFR_PT_Racer(Panel):
    bl_label = "CTR Racer"
    bl_idname = "NFR_PT_racer"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Racer"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            layout.label(text="Select a mesh object", icon="INFO")
            return

        r = obj.racer
        layout.prop(r, "is_racer")

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
        col.label(text="Set position via the Slots grid",
                  icon="RESTRICT_SELECT_OFF")

        col.separator()
        col.prop(r, "engine")
        col.prop(r, "mask")
        col.prop(r, "wheels")

        col.separator()
        col.prop(r, "long_name")
        col.prop(r, "short_name")

        col.separator()
        col.prop(r, "color")
        col.prop(r, "icon_path")

        layout.separator()
        row = layout.row(align=True)
        row.operator("nfr.validate", icon="CHECKMARK")
        row.operator("nfr.export", icon="EXPORT")
        layout.operator("nfr.export_all", icon="FILE_TICK")

        layout.separator()
        layout.label(text="Dev Tools:", icon="TOOL_SETTINGS")
        row = layout.row(align=True)
        row.scale_y = 1.3
        row.operator("nfr.run_game", text="Run", icon="PLAY")
        row.operator("nfr.build_and_run", text="Build & Run",
                     icon="FILE_REFRESH")

        layout.separator()
        if ADDON_ID in context.preferences.addons:
            layout.label(text="Preferences for paths:", icon="PREFERENCES")
            layout.operator("preferences.addon_show",
                            text="Open Preferences").module = ADDON_ID
        else:
            layout.label(text="Script mode — edit DEFAULT_REPO", icon="INFO")
            layout.label(text=f"repo: {DEFAULT_REPO}")


class NFR_PT_Slots(Panel):
    bl_label = "Slots"
    bl_idname = "NFR_PT_slots"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Racer"
    bl_order = 10

    def draw(self, context):
        layout = self.layout
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

        # Both "entry" and "pending" render the same detail block; a
        # pending cell is labelled so the user knows Export is required.
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


class NFR_PT_Materials(Panel):
    bl_label = "Materials"
    bl_idname = "NFR_PT_materials"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Racer"
    bl_order = 20

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == "MESH"
                and hasattr(obj, "racer") and obj.racer.is_racer)

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        m = obj.data

        if not m.materials:
            layout.label(text="No materials on this mesh", icon="INFO")
            return

        for mat in m.materials:
            if mat is None:
                continue

            box = layout.box()
            box.label(text=mat.name, icon="MATERIAL")

            # Find the single texture image (validator already enforces <= 1).
            img = None
            if mat.use_nodes and mat.node_tree:
                for n in mat.node_tree.nodes:
                    if n.type == "TEX_IMAGE" and n.image:
                        img = n.image
                        break

            row = box.row(align=True)
            icon_id = _image_preview_icon_id(img)
            if icon_id:
                row.template_icon(icon_value=icon_id, scale=2.0)
            else:
                row.label(text="", icon="IMAGE_DATA")

            info = row.column()
            info.label(text=img.name if img else "(no image)")

            is_double = not mat.use_backface_culling
            icon_name = "CHECKBOX_HLT" if is_double else "CHECKBOX_DEHLT"
            op = info.operator("nfr.toggle_double_sided",
                               text="Double-sided", icon=icon_name)
            op.material_name = mat.name


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
    NFR_OT_ToggleDoubleSided,
    NFR_PT_Racer,
    NFR_PT_Slots,
    NFR_PT_Materials,
)


def register():
    for c in _classes:
        bpy.utils.register_class(c)
    bpy.types.Object.racer = PointerProperty(type=NFR_RacerProps)


def unregister():
    _teardown_previews()
    if hasattr(bpy.types.Object, "racer"):
        del bpy.types.Object.racer
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()