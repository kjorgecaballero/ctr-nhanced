# =========================================================================
# MODULE: dance — operators
# =========================================================================
"""Dance export operator.

Exports one or both dance variants (win / loose) from the active mesh's
timeline. Win = rank 0, Loose = rank 1-2. Both variants share the same
mesh, materials and Sentinel textures; only the timeline and the output
filename differ.
"""
from pathlib import Path
import subprocess

import bpy
from bpy.props import EnumProperty
from bpy.types import Operator

from ..prefs import _get_prefs
from ..core.helpers import _redraw_view3d
from ..export.mesh_json import export_mesh_json, _bake_timeline_clips


class NFR_OT_DanceExport(Operator):
    bl_idname = "nfr.dance_export"
    bl_label = "Export Dance.ctr"
    bl_description = (
        "Bake the active mesh's timeline as a single 'dance' clip and "
        "export it to <slug>/dance/dance_{win,loose}.ctr. The mesh must "
        "be a separate object, not the racer itself."
    )

    variant: EnumProperty(
        name="Variant",
        items=[
            ('WIN',   "Win",   "Export dance_win.ctr (rank 0)"),
            ('LOOSE', "Loose", "Export dance_loose.ctr (rank 1-2)"),
            ('BOTH',  "Both",  "Export both variants in one go"),
        ],
        default='WIN',
    )

    # ---- helpers --------------------------------------------------------

    def _export_one(self, context, obj, slug_dir, slug, is_win):
        """Bake + export a single variant. Returns the out path or None."""
        st = context.scene.nfr_dance
        prefs = _get_prefs(context)

        if is_win:
            start, end = int(st.win_start), int(st.win_end)
            stem = "dance_win"
        else:
            start, end = int(st.loose_start), int(st.loose_end)
            stem = "dance_loose"

        if end <= start:
            self.report({"ERROR"},
                        f"{stem}: End ({end}) must be > Start ({start})")
            return None

        dance_dir = slug_dir / "dance"
        dance_dir.mkdir(parents=True, exist_ok=True)

        source_dir = slug_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        json_path = source_dir / f"source_mesh_{stem}.json"

        # 1. Bake the timeline for this variant and write the JSON.
        #    override_clips bypasses the racer's own anim_use_timeline
        #    / anim_frame_ranges so the dance does not inherit them.
        try:
            clips = _bake_timeline_clips(obj, {"dance": [start, end]})
            export_mesh_json(obj, json_path, override_clips=clips)
        except Exception as ex:
            self.report({"ERROR"}, f"{stem}: mesh export failed: {ex}")
            return None

        # 2. Build the .ctr. OUT_PATH.parent = <slug>/dance/, so the
        #    sentinel_NN.bin/.png side-cars land there directly.
        build_py = (Path(prefs.repo_path) / "tools" / "custom_racers"
                    / "build_character.py")
        if not build_py.is_file():
            self.report({"ERROR"},
                        f"build_character.py not found: {build_py}")
            return None

        out_ctr = dance_dir / f"{stem}.ctr"
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
                        f"{stem}: build_character failed "
                        f"({res.returncode}):\n{res.stderr[-400:]}")
            return None

        return out_ctr

    # ---- main -----------------------------------------------------------

    def execute(self, context):
        st = context.scene.nfr_dance
        prefs = _get_prefs(context)

        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "Select a mesh first")
            return {"CANCELLED"}

        slug = (st.slug or "").strip()
        if not slug:
            self.report({"ERROR"}, "Set the racer slug first")
            return {"CANCELLED"}

        slug_dir = prefs.racers_dir() / slug
        if not slug_dir.is_dir():
            self.report({"ERROR"}, f"Racer folder not found: {slug_dir}")
            return {"CANCELLED"}

        results = []

        if self.variant in ('WIN', 'BOTH'):
            out = self._export_one(context, obj, slug_dir, slug, is_win=True)
            if out is None:
                return {"CANCELLED"}
            results.append(out)

        if self.variant in ('LOOSE', 'BOTH'):
            out = self._export_one(context, obj, slug_dir, slug, is_win=False)
            if out is None:
                return {"CANCELLED"}
            results.append(out)

        # Report (dance/ has the shared sentinel_*.bin count).
        dance_dir = slug_dir / "dance"
        n_bins = len(list(dance_dir.glob("sentinel_*.bin")))

        parts = []
        for out in results:
            size = out.stat().st_size if out.is_file() else 0
            parts.append(f"{out.name} ({size} B)")

        self.report({"INFO"},
                    "Dance exported: " + ", ".join(parts)
                    + f" — {n_bins} shared textures")
        _redraw_view3d(context)
        return {"FINISHED"}


_classes = (NFR_OT_DanceExport,)


def register():
    for c in _classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)