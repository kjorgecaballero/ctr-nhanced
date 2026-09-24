# =========================================================================
# MODULE: export — operators
# =========================================================================
"""The eight racer-panel operators (validate / export / save-load / build-run)."""
import bpy
import json
import textwrap
from pathlib import Path

from bpy.props import StringProperty
from bpy.types import Operator

from .. import state as ui_state
from ..prefs import _get_prefs
from ..core.helpers import _redraw_view3d
from ..core.icons import _teardown_previews
from ..core.validate import validate_racer, _slugify, _uv_out_of_range
from .mesh_json import _do_export, _racer_objects
from .native_build import _build_exe, _run_game


class NFR_OT_Validate(Operator):
    bl_idname = "nfr.validate"
    bl_label = "Validate"

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "Select a mesh first")
            return {"CANCELLED"}
        ok, warns, errs = validate_racer(obj)
        for _short, long in errs:
            self.report({"ERROR"}, long)
        for _short, long in warns:
            print(f"[Racer Validate] {obj.name}: {long}")

        n_oob, min_u, max_u, min_v, max_v = _uv_out_of_range(obj)
        if n_oob > 0:
            self.report(
                {"WARNING"},
                f"UV out of [0,1]: {n_oob} loops "
                f"(u: {min_u:.3f}..{max_u:.3f}, v: {min_v:.3f}..{max_v:.3f}). "
                f"CTR clamps UVs to the texture edge — the model may look "
                f"different in-game than in Blender."
            )

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
            for short, _long in errs:
                self.report({"ERROR"}, short)
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
                texts = "; ".join(long for _s, long in errs)
                print(f"[Racer Export All] SKIP {obj.name}: {texts}")
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


class NFR_OT_FixSlug(Operator):
    bl_idname = "nfr.fix_slug"
    bl_label = "Fix Slug"
    bl_description = (
        "Rewrite the slug: spaces -> underscores, lowercase, "
        "strip non-alphanumeric characters"
    )

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "Select a mesh first")
            return {"CANCELLED"}
        old = obj.racer.slug
        new = _slugify(old)
        if new == old:
            self.report({"INFO"}, f"Slug already clean: '{old}'")
            return {"FINISHED"}
        obj.racer.slug = new
        _redraw_view3d(context)
        self.report({"INFO"}, f"Slug: '{old}' -> '{new}'")
        return {"FINISHED"}


class NFR_OT_ToggleValidationDetails(Operator):
    bl_idname = "nfr.toggle_validation_details"
    bl_label = "Toggle Validation Details"
    bl_description = (
        "Show/hide the Issues box. When open, the box lists the "
        "errors and warnings from validate_racer plus the "
        "out-of-[0,1] UV check. Does not re-run validation."
    )

    def execute(self, context):
        ui_state._validation_show_details = not ui_state._validation_show_details
        _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_ShowIssue(Operator):
    bl_idname = "nfr.show_issue"
    bl_label = "Issue"
    bl_description = "Click to see the full text"

    issue_text: StringProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=520)

    def draw(self, context):
        col = self.layout.column(align=True)
        for line in textwrap.wrap(self.issue_text, 80):
            col.label(text=line)

    def execute(self, context):
        return {"FINISHED"}


_classes = (
    NFR_OT_Validate,
    NFR_OT_Export,
    NFR_OT_ExportAll,
    NFR_OT_SaveSettings,
    NFR_OT_LoadSettings,
    NFR_OT_BuildExe,
    NFR_OT_RunGame,
    NFR_OT_BuildAndRun,
    NFR_OT_FixSlug,
    NFR_OT_ToggleValidationDetails,
    NFR_OT_ShowIssue,
)


def register():
    for c in _classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)