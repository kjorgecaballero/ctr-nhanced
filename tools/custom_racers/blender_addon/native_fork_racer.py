bl_info = {
    "name": "CTR NHanced Racer Export",
    "author": "kjorgecaballero",
    "version": (1, 0, 0),
    "blender": (3, 2, 0),
    "location": "View3D > N > Racer",
    "description": "Configure and export custom CTR racers",
    "category": "Import-Export",
}

import bpy
import os
import json
import hashlib
import subprocess
from pathlib import Path
from bpy.props import StringProperty, IntProperty, BoolProperty, EnumProperty, FloatVectorProperty, PointerProperty
from bpy.types import Panel, Operator, AddonPreferences, PropertyGroup

ENGINES = [
    ("SPEED",    "Speed",    ""),
    ("BALANCED", "Balanced", ""),
    ("ACCEL",    "Accel",    ""),
    ("TURN",     "Turn",     ""),
]

DEFAULT_REPO       = r"C:\Users\Kevin\Desktop\Kevin\CTR\native_fork\nhanced"
DEFAULT_SOURCE_DIR = r"C:\Users\Kevin\Desktop\Kevin\CTR\native_fork\ctr_racer_source"
DEFAULT_PYTHON     = r"C:\Users\Kevin\AppData\Local\Programs\Python\Python312\python.exe"
ADDON_ID           = __name__ if __name__ != "__main__" else "native_fork_racer"


# =============================================================
# PropertyGroup attached to every Object
# =============================================================
class NFR_RacerProps(PropertyGroup):
    is_racer:   BoolProperty(name="Is Racer", default=False)
    slug:       StringProperty(name="Slug", description="Folder name and internal .ctr name")
    page:       IntProperty(name="Page", default=1, min=1, max=8)
    slot:       IntProperty(name="Slot", default=0, min=0, max=15)
    engine:     EnumProperty(name="Engine", items=ENGINES, default="BALANCED")
    long_name:  StringProperty(name="Long Name", description="Shown under the 3D preview")
    short_name: StringProperty(name="Short Name", description="Used by TT fallback etc.")
    color:      FloatVectorProperty(name="Minimap Color", subtype="COLOR",
                                    default=(1.0, 1.0, 1.0), min=0.0, max=1.0)
    icon_path:  StringProperty(name="Icon PNG", subtype="FILE_PATH")

    def custom_id(self):
        return 16 + (self.page - 1) * 16 + self.slot


# =============================================================
# Preferences (global, persists across restarts)
# =============================================================
class NFR_Preferences(AddonPreferences):
    bl_idname = ADDON_ID

    repo_path:       StringProperty(name="Repo Path", default=DEFAULT_REPO, subtype="DIR_PATH")
    source_mesh_dir: StringProperty(name="Source Mesh Dir", default=DEFAULT_SOURCE_DIR, subtype="DIR_PATH")
    python_exe:      StringProperty(name="Python Exe", default=DEFAULT_PYTHON, subtype="FILE_PATH")

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "repo_path")
        layout.prop(self, "source_mesh_dir")
        layout.prop(self, "python_exe")
        layout.separator()
        row = layout.row(align=True)
        row.operator("nfr.save_settings", text="Save Settings JSON")
        row.operator("nfr.load_settings", text="Load Settings JSON")


# =============================================================
# Validation
# =============================================================
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
        imgs = [n.image for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]
        if len(imgs) > 1:
            errors.append(f"Material '{mat.name}' has {len(imgs)} images (max 1)")
        for im in imgs:
            if im.packed_file is None:
                errors.append(f"Image '{im.name}' is NOT packed into the .blend")
            else:
                warnings.append(f"Image '{im.name}': {im.size[0]}x{im.size[1]} packed")

    if props.icon_path:
        if not os.path.isfile(props.icon_path):
            errors.append(f"Icon file not found: {props.icon_path}")
    else:
        warnings.append("No icon PNG selected")

    return (len(errors) == 0, warnings, errors)


# =============================================================
# Mesh JSON export (mirrors tools/custom_racers/export_character.py)
# =============================================================
def export_mesh_json(obj, out_path):
    m = obj.data
    m.calc_loop_triangles()

    materials = []
    images = {}
    for mat in m.materials:
        imgs = list({n.image for n in mat.node_tree.nodes
                     if n.type == "TEX_IMAGE" and n.image})
        im = imgs[0] if imgs else None
        materials.append({"name": mat.name, "image": im.name if im else None})
        if im and im.name not in images:
            images[im.name] = {"size": list(im.size), "pixels_rgba": list(im.pixels)}

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
        "keys": {k.name: [list(v.co) for v in k.data] for k in m.shape_keys.key_blocks},
        "groups": {g.name: {str(v.index): next((a.weight for a in v.groups
                                                if a.group == g.index), 0)
                            for v in m.vertices} for g in obj.vertex_groups},
    }

    Path(out_path).write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")


# =============================================================
# Helpers
# =============================================================
def _get_prefs(context):
    return context.preferences.addons[ADDON_ID].preferences


def _do_export(context, obj):
    prefs = _get_prefs(context)
    r = obj.racer

    source_dir = Path(prefs.source_mesh_dir)
    source_dir.mkdir(parents=True, exist_ok=True)
    json_path = source_dir / f"source_mesh_{r.slug}.json"
    export_mesh_json(obj, json_path)

    add_racer = Path(prefs.repo_path) / "tools" / "custom_racers" / "add_racer.py"
    if not add_racer.is_file():
        raise RuntimeError(f"add_racer.py not found at {add_racer}")

    cmd = [
        prefs.python_exe, str(add_racer),
        r.slug, str(json_path),
        str(r.page), str(r.slot), r.engine, r.long_name,
        "--icon", r.icon_path,
    ]

    # Only pass --color if it differs from default white
    if tuple(r.color[:3]) != (1.0, 1.0, 1.0):
        hexcol = "#{:02X}{:02X}{:02X}".format(
            int(r.color[0] * 255), int(r.color[1] * 255), int(r.color[2] * 255))
        cmd += ["--color", hexcol]

    res = subprocess.run(cmd, cwd=str(prefs.repo_path),
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"add_racer failed ({res.returncode}):\n{res.stderr[-400:]}")


def _racer_objects(context):
    sel = [o for o in context.selected_objects if o.type == "MESH" and o.racer.is_racer]
    if sel:
        return sel
    return [o for o in bpy.data.objects if o.type == "MESH" and o.racer.is_racer]


# =============================================================
# Operators
# =============================================================
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

        self.report({"INFO"}, f"Exported {obj.racer.slug} -> page {obj.racer.page} slot {obj.racer.slot}")
        return {"FINISHED"}


class NFR_OT_ExportAll(Operator):
    bl_idname = "nfr.export_all"
    bl_label = "Export All Racers"

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

        self.report({"INFO"}, f"{ok_count} exported, {fail_count} failed")
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
            loaded += 1
        self.report({"INFO"}, f"Loaded {loaded} racers from {self.filepath}")
        return {"FINISHED"}


# =============================================================
# Panel (View3D > N sidebar > "Racer")
# =============================================================
class NFR_PT_Racer(Panel):
    bl_label = "CTR Racer"
    bl_idname = "NFR_PT_racer"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Racer"

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
        row = col.row(align=True)
        row.prop(r, "page")
        row.prop(r, "slot")
        col.label(text=f"Custom ID: {r.custom_id()}", icon="INFO")
        col.prop(r, "engine")
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

        layout.separator()
        layout.operator("nfr.export_all", icon="FILE_TICK")

        layout.separator()
        layout.label(text="Preferences for paths:", icon="PREFERENCES")
        layout.operator("preferences.addon_show", text="Open Preferences").module = ADDON_ID


# =============================================================
# Registration
# =============================================================
_classes = (
    NFR_RacerProps,
    NFR_Preferences,
    NFR_OT_Validate,
    NFR_OT_Export,
    NFR_OT_ExportAll,
    NFR_OT_SaveSettings,
    NFR_OT_LoadSettings,
    NFR_PT_Racer,
)


def register():
    for c in _classes:
        bpy.utils.register_class(c)
    bpy.types.Object.racer = PointerProperty(type=NFR_RacerProps)


def unregister():
    if hasattr(bpy.types.Object, "racer"):
        del bpy.types.Object.racer
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
