# =========================================================================
# MODULE: dance — operators
# =========================================================================
"""Dance export operator.

Exports one or both dance variants (win / loose) from the active mesh's
timeline. Win = rank 0, Loose = rank 1-2. Both variants share the same
mesh, materials and Sentinel textures; only the timeline and the output
filename differ.
"""
import struct
from pathlib import Path
import subprocess

import bpy
from bpy.props import EnumProperty, IntProperty
from bpy.types import Operator

from ..prefs import _get_prefs
from ..core.helpers import _redraw_view3d
from ..export.mesh_json import export_mesh_json, _bake_timeline_clips


def _resolve_blender_path(p):
    """Resolve a FILE_PATH property to an absolute Path, or None.

    Blender stores relative paths as '//...' (relative to the .blend).
    bpy.path.abspath() resolves them, but ONLY if the .blend has been
    saved: with no filepath it returns a broken '\\..' prefix that
    Path() cannot use. We detect both cases and return None so the
    operator can surface a clear error instead of silently skipping."""
    if not p:
        return None
    if p.startswith("//"):
        if not bpy.data.filepath:
            return None
        return Path(bpy.path.abspath(p))
    if p.startswith("\\"):
        # Blender gave us a corrupted "relative" path because the .blend
        # is unsaved; there is no way to resolve it.
        return None
    return Path(p)


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
            encoding="utf-8", errors="replace",
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


class NFR_OT_DanceBuildMusic(Operator):
    bl_idname = "nfr.dance_build_music"
    bl_label = "Build Music Bank"
    bl_description = (
        "Copy the picked WAV to <slug>/music/podium.wav and run "
        "build_voice_pipeline.py to rebuild ENG.XNF (MUSIC category) "
        "and generate XA/MUSIC/S18.XA"
    )

    def execute(self, context):
        st = context.scene.nfr_dance
        prefs = _get_prefs(context)

        src = (st.podium_music_path or "").strip()
        if not src:
            self.report({"ERROR"}, "Pick a podium music WAV first")
            return {"CANCELLED"}

        slug = (st.slug or "").strip()
        if not slug:
            self.report({"ERROR"}, "Set the racer slug first")
            return {"CANCELLED"}

        slug_dir = prefs.racers_dir() / slug
        if not slug_dir.is_dir():
            self.report({"ERROR"}, f"Racer folder not found: {slug_dir}")
            return {"CANCELLED"}

        music_dir = slug_dir / "music"
        music_dir.mkdir(parents=True, exist_ok=True)
        dst = music_dir / "podium.wav"

        src_path = _resolve_blender_path(src)
        if src_path is None:
            self.report(
                {"ERROR"},
                f"Cannot resolve WAV path {src!r}. Either save the "
                ".blend (File > Save) or uncheck 'Relative Path' in "
                "the file picker and re-pick the WAV.")
            return {"CANCELLED"}
        if not src_path.is_file():
            self.report({"ERROR"}, f"WAV not found: {src_path}")
            return {"CANCELLED"}
        try:
            if src_path.resolve() != dst.resolve():
                import shutil as _sh
                _sh.copy2(src_path, dst)
        except Exception as ex:
            self.report({"ERROR"}, f"Copy failed: {ex}")
            return {"CANCELLED"}

        build_py = (Path(prefs.repo_path) / "tools" / "custom_racers"
                    / "build_voice_pipeline.py")
        res = subprocess.run(
            [prefs.python_exe, str(build_py), "-v"],
            cwd=str(prefs.repo_path),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        if res.returncode != 0:
            self.report({"ERROR"},
                        f"Pipeline failed ({res.returncode}):\n"
                        f"{res.stderr[-400:]}")
            return {"CANCELLED"}

        self.report({"INFO"},
                    f"Podium music built for '{slug}' "
                    f"(<slug>/music/podium.wav)")
        _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_DanceSfxAdd(Operator):
    bl_idname = "nfr.dance_sfx_add"
    bl_label = "Add Dance SFX"
    bl_description = "Add a new per-frame SFX entry to the dance"

    def execute(self, context):
        st = context.scene.nfr_dance
        st.sfx_entries.add()
        _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_DanceSfxRemove(Operator):
    bl_idname = "nfr.dance_sfx_remove"
    bl_label = "Remove Dance SFX"
    bl_description = "Remove this SFX entry"

    index: IntProperty(default=-1)

    def execute(self, context):
        st = context.scene.nfr_dance
        if 0 <= self.index < len(st.sfx_entries):
            st.sfx_entries.remove(self.index)
        _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_DanceBuildSfx(Operator):
    bl_idname = "nfr.dance_build_sfx"
    bl_label = "Build Dance SFX"
    bl_description = (
        "Write <slug>/dance/sfx.bin, copy each WAV to sfx_<i>.wav, "
        "and rebuild ENG.XNF (GAME category, track base 4096)"
    )

    def execute(self, context):
        st = context.scene.nfr_dance
        prefs = _get_prefs(context)

        # bpy.path.abspath() below resolves Blender-relative paths
        # ("//.." = relative to the .blend file's directory) so a WAV
        # picked with Relative Path enabled still resolves correctly.
        slug = (st.slug or "").strip()
        if not slug:
            self.report({"ERROR"}, "Set the racer slug first")
            return {"CANCELLED"}

        slug_dir = prefs.racers_dir() / slug
        if not slug_dir.is_dir():
            self.report({"ERROR"}, f"Racer folder not found: {slug_dir}")
            return {"CANCELLED"}

        if len(st.sfx_entries) == 0:
            self.report({"ERROR"}, "No SFX entries. Add at least one.")
            return {"CANCELLED"}

        # Sort by frame, dedup, drop entries without a WAV.
        entries = []
        seen = set()
        skipped_empty = 0
        skipped_dup = 0
        skipped_missing = 0
        for e in st.sfx_entries:
            if not e.wav_path:
                skipped_empty += 1
                continue
            f = int(e.frame)
            if f in seen:
                skipped_dup += 1
                continue
            src = _resolve_blender_path(e.wav_path)
            if src is None:
                self.report(
                    {"ERROR"},
                    f"Cannot resolve WAV path {e.wav_path!r}. Either "
                    "save the .blend (File > Save) or uncheck "
                    "'Relative Path' in the file picker and re-pick "
                    "the WAV.")
                return {"CANCELLED"}
            if not src.is_file():
                skipped_missing += 1
                continue
            seen.add(f)
            entries.append((f, src))

        entries.sort(key=lambda x: x[0])

        if not entries:
            self.report({"ERROR"},
                        "No valid entries (missing WAV, empty, or all dup)")
            return {"CANCELLED"}

        dance_dir = slug_dir / "dance"
        dance_dir.mkdir(parents=True, exist_ok=True)

        # Copy WAVs to sfx_<i>.wav, index-aligned with sfx.bin.
        import shutil as _sh
        copied = 0
        for i, (_frame, src) in enumerate(entries):
            dst = dance_dir / f"sfx_{i}.wav"
            try:
                if src.resolve() != dst.resolve():
                    _sh.copy2(src, dst)
                    copied += 1
            except Exception as ex:
                self.report({"ERROR"}, f"Copy failed for {src}: {ex}")
                return {"CANCELLED"}

        # Write sfx.bin (magic SFX1 + u32 count + u32 frames[]).
        frames = [f for f, _ in entries]
        sfx_bin = dance_dir / "sfx.bin"
        sfx_bin.write_bytes(
            b"SFX1"
            + struct.pack("<I", len(frames))
            + struct.pack(f"<{len(frames)}I", *frames)
        )

        # Run the pipeline (writes XNF + banks + sidecar).
        build_py = (Path(prefs.repo_path) / "tools" / "custom_racers"
                    / "build_voice_pipeline.py")
        if not build_py.is_file():
            self.report({"ERROR"},
                        f"build_voice_pipeline.py not found: {build_py}")
            return {"CANCELLED"}
        res = subprocess.run(
            [prefs.python_exe, str(build_py), "-v"],
            cwd=str(prefs.repo_path),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        if res.returncode != 0:
            self.report({"ERROR"},
                        f"Pipeline failed ({res.returncode}):\n"
                        f"{res.stderr[-400:]}")
            return {"CANCELLED"}

        msg = (f"Dance SFX built for '{slug}': "
               f"{len(entries)} trigger(s), {copied} WAV(s) copied")
        if skipped_dup:
            msg += f", {skipped_dup} dup dropped"
        if skipped_empty:
            msg += f", {skipped_empty} empty dropped"
        if skipped_missing:
            msg += f", {skipped_missing} missing dropped"
        self.report({"INFO"}, msg)
        _redraw_view3d(context)
        return {"FINISHED"}


_classes = (NFR_OT_DanceExport, NFR_OT_DanceBuildMusic,
            NFR_OT_DanceSfxAdd, NFR_OT_DanceSfxRemove,
            NFR_OT_DanceBuildSfx)


def register():
    for c in _classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)