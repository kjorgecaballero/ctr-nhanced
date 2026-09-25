# =========================================================================
# MODULE: sfx — operators
# =========================================================================
"""Custom kart SFX export.

Copies the picked WAVs to <slug>/sfx/<event>.wav and runs
build_voice_pipeline.py -v, which encodes each WAV to .vag at
11025 Hz. The C-side loads the VAGs into SPU at race start.
"""
import shutil
from pathlib import Path
import subprocess

import bpy
from bpy.types import Operator

from ..prefs import _get_prefs
from ..core.helpers import _redraw_view3d
from ..dance.operators import _resolve_blender_path
from .state import SFX_EVENTS


class NFR_OT_SfxBuild(Operator):
    bl_idname = "nfr.sfx_build"
    bl_label = "Build SFX"
    bl_description = (
        "Copy the picked WAVs to <slug>/sfx/<event>.wav and run the "
        "pipeline, which encodes each to .vag at 11025 Hz. The runtime "
        "loads the VAGs into SPU at race start."
    )

    def execute(self, context):
        st = context.scene.nfr_sfx
        prefs = _get_prefs(context)

        slug = (st.slug or "").strip()
        if not slug:
            self.report({"ERROR"}, "Set the racer slug first")
            return {"CANCELLED"}

        slug_dir = prefs.racers_dir() / slug
        if not slug_dir.is_dir():
            self.report({"ERROR"}, f"Racer folder not found: {slug_dir}")
            return {"CANCELLED"}

        sfx_dir = slug_dir / "sfx"
        sfx_dir.mkdir(parents=True, exist_ok=True)

        copied = 0
        for event, _ in SFX_EVENTS:
            src_str = (getattr(st, f"wav_{event}", "") or "").strip()
            if not src_str:
                continue
            src = _resolve_blender_path(src_str)
            if src is None or not src.is_file():
                self.report(
                    {"WARNING"},
                    f"{event}: cannot resolve WAV {src_str!r}, skipped")
                continue
            dst = sfx_dir / f"{event}.wav"
            try:
                if src.resolve() != dst.resolve():
                    shutil.copy2(src, dst)
            except Exception as ex:
                self.report({"WARNING"}, f"{event}: copy failed: {ex}")
                continue
            copied += 1

        if copied == 0:
            self.report({"ERROR"}, "No WAVs were copied. Pick at least one.")
            return {"CANCELLED"}

        pipeline = (Path(prefs.repo_path) / "tools" / "custom_racers"
                    / "build_voice_pipeline.py")
        if not pipeline.is_file():
            self.report({"ERROR"},
                        f"build_voice_pipeline.py not found: {pipeline}")
            return {"CANCELLED"}

        res = subprocess.run(
            [prefs.python_exe, str(pipeline), "-v"],
            cwd=str(prefs.repo_path),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        if res.returncode != 0:
            self.report({"ERROR"},
                        f"pipeline failed ({res.returncode}):\n"
                        f"{res.stderr[-400:]}")
            return {"CANCELLED"}

        n_vags = len(list(sfx_dir.glob("*.vag")))
        self.report({"INFO"},
                    f"SFX built: {copied} WAV(s) copied, "
                    f"{n_vags} VAG(s) in {sfx_dir.name}/")
        _redraw_view3d(context)
        return {"FINISHED"}


_classes = (NFR_OT_SfxBuild,)


def register():
    for c in _classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)