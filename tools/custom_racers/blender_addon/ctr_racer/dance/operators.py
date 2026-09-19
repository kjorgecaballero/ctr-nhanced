# =========================================================================
# MODULE: dance — operators
# =========================================================================
"""Dance export operator."""
from pathlib import Path
import subprocess

import bpy
from bpy.types import Operator

from ..prefs import _get_prefs
from ..core.helpers import _redraw_view3d
from ..export.mesh_json import export_mesh_json, _bake_timeline_clips


class NFR_OT_DanceExport(Operator):
    bl_idname = "nfr.dance_export"
    bl_label = "Export Dance.ctr"
    bl_description = (
        "Bake the active mesh's timeline as a single 'dance' clip and "
        "export it to <slug>/dance/dance.ctr. The mesh must be a "
        "separate object, not the racer itself."
    )

    def execute(self, context):
        scene = context.scene
        st = scene.nfr_dance
        prefs = _get_prefs(context)

        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "Select a mesh first")
            return {"CANCELLED"}

        slug = (st.slug or "").strip()
        if not slug:
            self.report({"ERROR"}, "Set the racer slug first")
            return {"CANCELLED"}

        racers_dir = prefs.racers_dir()
        slug_dir = racers_dir / slug
        if not slug_dir.is_dir():
            self.report({"ERROR"}, f"Racer folder not found: {slug_dir}")
            return {"CANCELLED"}

        dance_dir = slug_dir / "dance"
        dance_dir.mkdir(parents=True, exist_ok=True)

        start = int(st.frame_start)
        end = int(st.frame_end)
        if end <= start:
            self.report({"ERROR"},
                        f"End ({end}) must be > start ({start})")
            return {"CANCELLED"}

        # 1. Build source_mesh.json with the dance clip baked in.
        #    We call export_mesh_json with override_clips so the racer's
        #    own anim_use_timeline / anim_frame_ranges settings do not
        #    leak into this export.
        source_dir = slug_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        json_path = source_dir / "source_mesh_dance.json"

        try:
            clips = _bake_timeline_clips(obj, {"dance": [start, end]})
            export_mesh_json(obj, json_path, override_clips=clips)
        except Exception as ex:
            self.report({"ERROR"}, f"Mesh export failed: {ex}")
            return {"CANCELLED"}

        # 2. Build the .ctr in dance/. OUT_PATH.parent is <slug>/dance/,
        #    so the sentinel_NN.bin/.png side-cars land there directly.
        build_py = (Path(prefs.repo_path) / "tools" / "custom_racers"
                    / "build_character.py")
        if not build_py.is_file():
            self.report({"ERROR"}, f"build_character.py not found: {build_py}")
            return {"CANCELLED"}

        out_ctr = dance_dir / "dance.ctr"
        cmd = [
            prefs.python_exe, str(build_py),
            str(json_path), slug, str(out_ctr),
            "--sentinel", "--dance",
        ]

        res = subprocess.run(
            cmd, cwd=str(prefs.repo_path),
            capture_output=True, text=True,
        )
        if res.returncode != 0:
            self.report({"ERROR"},
                        f"build_character failed ({res.returncode}):\n"
                        f"{res.stderr[-400:]}")
            return {"CANCELLED"}

        # 3. Report.
        n_bins = len(list(dance_dir.glob("sentinel_*.bin")))
        size = out_ctr.stat().st_size if out_ctr.is_file() else 0
        self.report({"INFO"},
                    f"Dance exported: {out_ctr.name} ({size} bytes, "
                    f"{n_bins} textures)")
        _redraw_view3d(context)
        return {"FINISHED"}


_classes = (NFR_OT_DanceExport,)


def register():
    for c in _classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)