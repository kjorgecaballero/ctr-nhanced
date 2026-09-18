# =========================================================================
# MODULE: prefs
# =========================================================================
"""Addon preferences.

Owns NFR_Preferences and the _get_prefs accessor. Registers/unregisters
its own classes.
"""
import bpy
from pathlib import Path
from bpy.props import StringProperty, BoolProperty
from bpy.types import AddonPreferences

from .constants import ADDON_ID, DEFAULT_REPO, DEFAULT_PYTHON


class NFR_Preferences(AddonPreferences):
    bl_idname = ADDON_ID

    repo_path:  StringProperty(name="Repo Path", default=DEFAULT_REPO, subtype="DIR_PATH")
    python_exe: StringProperty(name="Python Exe", default=DEFAULT_PYTHON, subtype="FILE_PATH")
    build_dir:  StringProperty(
        name="Build Dir",
        description="Relative to Repo Path (MSVC out-of-source build folder)",
        default="build-msvc-x86")
    exe_name:   StringProperty(name="Exe Name", default="ctr_native.exe")
    clean_stale_on_export: BoolProperty(
        name="Clean stale entries on export",
        description="Remove same-slug entries on other slots of the same page "
                    "when exporting a racer, so moving a racer to a new slot "
                    "doesn't leave the old entry orphaned. A slug can still "
                    "live on multiple pages (page 0 + page 1)",
        default=True)
    sentinel_models: BoolProperty(
        name="Use Sentinel model textures",
        description="Export customs with Sentinel CLUT textures instead of "
                    "the VRAM atlas + textures.vrm. Textures are full-res "
                    "up to 256x256 (u8 UV limit). Requires the C-side "
                    "runtime to support sentinel_00.bin (commit 95cf1cf70+)",
        default=False)
    kart_presets_root: StringProperty(
        name="Kart presets folder",
        description="Where baked kart presets are written. The addon creates "
                    "subfolders per variant (kart/ gold/ silver/) and per "
                    "preset name inside this folder",
        subtype="DIR_PATH",
        default="")

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
        layout.label(text="Export behavior:")
        layout.prop(self, "clean_stale_on_export")
        layout.prop(self, "sentinel_models")
        layout.separator()
        layout.label(text="Kart Editor:")
        layout.prop(self, "kart_presets_root")
        layout.separator()
        layout.label(text="Export target (derived from Repo Path):", icon="INFO")
        layout.label(text=str(self.racers_dir()))
        layout.separator()
        row = layout.row(align=True)
        row.operator("nfr.save_settings", text="Save Settings JSON")
        row.operator("nfr.load_settings", text="Load Settings JSON")


def _get_prefs(context):
    return context.preferences.addons[ADDON_ID].preferences


_classes = (NFR_Preferences,)


def register():
    for c in _classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)