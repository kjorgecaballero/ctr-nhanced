# =========================================================================
# MODULE: bl_info
# =========================================================================
bl_info = {
    "name": "CTR Racer",
    "author": "kjorgecaballero",
    "version": (2, 0, 0),
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
# MODULE: submodule imports
# =========================================================================
from .constants import (
    ENGINES, _ENGINE_SET, BLEND_MODES, _BLEND_MODE_SET,
    DEFAULT_REPO, DEFAULT_PYTHON, ADDON_ID,
    MAX_PAGES, MAX_MATS_PER_PAGE,
)
from . import prefs
from .prefs import _get_prefs
from . import state
from .core.helpers import _redraw_view3d, _find_object_by_slug, _active_racer
from .core.roster import (
    _parse_roster_line, _read_roster, _group_by_page, _remove_roster_entry,
)
from .core.icons import (
    _ensure_previews, _teardown_previews, _get_icon, _image_preview_icon_id,
)
from .core.validate import validate_racer
from . import core
from . import render

# =========================================================================
# MODULE: material helpers
# =========================================================================
def _get_blend_mode(mat):
    value = mat.get("blend_mode", "half")
    if value not in _BLEND_MODE_SET:
        return "half"
    return value

# =========================================================================
# MODULE: mesh export
# =========================================================================

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
        prefs = _get_prefs(context)
        entries = _read_roster(prefs)
        entry = next((x for x in entries
                      if x["page"] == self.page and x["slot"] == self.slot),
                     None)

        state._slot_sel_page = self.page
        state._slot_sel_slot = self.slot

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
        if state._slot_sel_page < 0 or state._slot_sel_slot < 0:
            self.report({"ERROR"}, "Click a slot in the grid first")
            return {"CANCELLED"}
        obj = context.active_object
        if obj is None or obj.type != "MESH" or not obj.racer.is_racer:
            self.report({"ERROR"}, "Select a racer mesh first")
            return {"CANCELLED"}

        prefs = _get_prefs(context)
        entries = _read_roster(prefs)
        existing = next((x for x in entries
                         if x["page"] == state._slot_sel_page
                         and x["slot"] == state._slot_sel_slot), None)

        obj.racer.page = state._slot_sel_page
        obj.racer.slot = state._slot_sel_slot

        if existing is not None and existing["folder"] != obj.racer.slug:
            self.report({"WARNING"},
                f"Slot {state._slot_sel_slot} is already taken by "
                f"'{existing['folder']}'. Export will leave two entries "
                f"at this position.")
        else:
            self.report({"INFO"},
                f"Assigned {obj.name} to page {state._slot_sel_page} "
                f"slot {state._slot_sel_slot}. Press Export to commit.")
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
        prefs = _get_prefs(context)
        ok, result = _remove_roster_entry(prefs, self.page, self.slot)
        if not ok:
            self.report({"ERROR"}, result)
            return {"CANCELLED"}

        if state._slot_sel_page == self.page and state._slot_sel_slot == self.slot:
            state._slot_sel_page = -1
            state._slot_sel_slot = -1

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
        if state._slot_view_page > 1:
            state._slot_view_page -= 1
            _redraw_view3d(context)
        return {"FINISHED"}

class NFR_OT_SlotNextPage(Operator):
    bl_idname = "nfr.slot_next_page"
    bl_label = "Next page"

    def execute(self, context):
        if state._slot_view_page < MAX_PAGES:
            state._slot_view_page += 1
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
        row.label(text=f"Page {state._slot_view_page} / {MAX_PAGES}")
        row.operator("nfr.slot_next_page", text="", icon="TRIA_RIGHT")

        row = layout.row(align=True)
        row.scale_y = 1.2
        row.operator("nfr.slot_refresh", text="Refresh", icon="FILE_REFRESH")
        assign_row = row.row(align=True)
        assign_row.enabled = (state._slot_sel_page == state._slot_view_page
                              and state._slot_sel_slot >= 0
                              and active_racer is not None)
        assign_row.operator("nfr.slot_assign_here",
                            text="Assign Here", icon="ADD")

        entries = _read_roster(prefs)
        pages = _group_by_page(entries)
        page_entries = pages.get(state._slot_view_page, {})
        cells = _resolve_cells(state._slot_view_page, page_entries,
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
            op.page = state._slot_view_page
            op.slot = slot

        if state._slot_sel_page != state._slot_view_page or state._slot_sel_slot < 0:
            layout.separator()
            layout.label(text="Click a slot to inspect", icon="INFO")
            return

        kind, data = cells.get(state._slot_sel_slot, ("empty", None))

        layout.separator()
        box = layout.box()

        if kind == "empty":
            box.label(text=f"Slot {state._slot_sel_slot} — empty", icon="INFO")
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
        header = f"Slot {state._slot_sel_slot} — {data['folder']}"
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
            op.page = state._slot_sel_page
            op.slot = state._slot_sel_slot

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

        if state._mat_view_page < 1:
            state._mat_view_page = 1
        if state._mat_view_page > total_pages:
            state._mat_view_page = total_pages

        # -------- Pagination (only if more than one page) --------
        if total_pages > 1:
            row = layout.row(align=True)
            sub_left = row.row(align=True)
            sub_left.enabled = state._mat_view_page > 1
            sub_left.operator("nfr.mat_prev_page", text="", icon="TRIA_LEFT")
            row.label(
                text=f"Materials  {state._mat_view_page} / {total_pages}  ({total} total)"
            )
            sub_right = row.row(align=True)
            sub_right.enabled = state._mat_view_page < total_pages
            sub_right.operator("nfr.mat_next_page", text="", icon="TRIA_RIGHT")
            layout.separator()

        start = (state._mat_view_page - 1) * MAX_MATS_PER_PAGE
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
    # panel (single)
    NFR_PT_Racer,
)

def register():
    prefs.register()
    core.register()
    for c in _classes:
        bpy.utils.register_class(c)
    render.register()

def unregister():
    _teardown_previews()
    render.unregister()
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
    core.unregister()
    prefs.unregister()

