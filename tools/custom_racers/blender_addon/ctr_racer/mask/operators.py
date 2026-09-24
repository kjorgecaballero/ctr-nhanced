# =========================================================================
# MODULE: mask — operators
# =========================================================================
"""Mask export operator.

Exports the active mesh as <slug>/mask/mask.ctr (the shield that
rotates around the kart) and/or <slug>/mask/beam.ctr (the light beam
above the mask). Both are static: rotation is applied per-tick by
RB_MaskWeapon_ThTick, so a 1-frame clip is all the runtime reads.

The roster entry must have mask=custom_good | mask=custom_bad for the
runtime to load them; the addon does not touch roster.txt.
"""
from pathlib import Path
import subprocess

import bpy
from bpy.props import EnumProperty
from bpy.types import Operator

from ..prefs import _get_prefs
from ..core.helpers import _redraw_view3d
from ..export.mesh_json import export_mesh_json, _bake_timeline_clips


class NFR_OT_MaskExport(Operator):
    bl_idname = "nfr.mask_export"
    bl_label = "Export Mask.ctr"
    bl_description = (
        "Export the active mesh as <slug>/mask/mask.ctr (the shield) "
        "and/or <slug>/mask/beam.ctr (the beam above the mask). Both "
        "are static: the runtime rotates them per-tick. Roster entry "
        "must say mask=custom_good | mask=custom_bad."
    )

    variant: EnumProperty(
        name="Variant",
        items=[
            ('MASK', "Mask", "Export mask.ctr (the shield that rotates around the kart)"),
            ('BEAM', "Beam", "Export beam.ctr (the light beam above the mask)"),
            ('BOTH', "Both", "Export both in one go"),
        ],
        default='MASK',
    )

    # ---- helpers --------------------------------------------------------

    def _export_one(self, context, obj, slug_dir, slug, is_mask):
        """Bake + export a single variant. Returns the out path or None."""
        prefs = _get_prefs(context)

        if is_mask:
            stem = "mask"
            extra_flag = "--mask"
        else:
            stem = "beam"
            extra_flag = "--mask-beam"

        mask_dir = slug_dir / "mask"
        mask_dir.mkdir(parents=True, exist_ok=True)

        source_dir = slug_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        json_path = source_dir / f"source_mesh_{stem}.json"

        # Mask and beam are static (rotation is per-tick in
        # RB_MaskWeapon_ThTick), so bake a single frame. override_clips
        # bypasses the racer's own anim_use_timeline / anim_frame_ranges.
        frame = int(context.scene.frame_current)
        try:
            clips = _bake_timeline_clips(obj, {stem: [frame, frame]})
            export_mesh_json(obj, json_path, override_clips=clips)
        except Exception as ex:
            self.report({"ERROR"}, f"{stem}: mesh export failed: {ex}")
            return None

        build_py = (Path(prefs.repo_path) / "tools" / "custom_racers"
                    / "build_character.py")
        if not build_py.is_file():
            self.report({"ERROR"},
                        f"build_character.py not found: {build_py}")
            return None

        out_ctr = mask_dir / f"{stem}.ctr"
        cmd = [
            prefs.python_exe, str(build_py),
            str(json_path), slug, str(out_ctr),
            "--sentinel", extra_flag,
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
        st = context.scene.nfr_mask
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

        if self.variant in ('MASK', 'BOTH'):
            out = self._export_one(context, obj, slug_dir, slug, is_mask=True)
            if out is None:
                return {"CANCELLED"}
            results.append(out)

        if self.variant in ('BEAM', 'BOTH'):
            out = self._export_one(context, obj, slug_dir, slug, is_mask=False)
            if out is None:
                return {"CANCELLED"}
            results.append(out)

        # Report (mask/ has both sets of sentinels).
        mask_dir = slug_dir / "mask"
        n_mask_bins = len([p for p in mask_dir.glob("sentinel_*.bin")
                           if not p.name.startswith("beam_")])
        n_beam_bins = len(list(mask_dir.glob("beam_sentinel_*.bin")))

        parts = []
        for out in results:
            size = out.stat().st_size if out.is_file() else 0
            parts.append(f"{out.name} ({size} B)")

        msg = ("Mask exported: " + ", ".join(parts)
               + f" — {n_mask_bins} mask textures")
        if n_beam_bins:
            msg += f", {n_beam_bins} beam textures"
        self.report({"INFO"}, msg)
        _redraw_view3d(context)
        return {"FINISHED"}


_classes = (NFR_OT_MaskExport,)


def register():
    for c in _classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
