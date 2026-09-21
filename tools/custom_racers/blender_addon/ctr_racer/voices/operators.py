# =========================================================================
# MODULE: voices — operators
# =========================================================================
"""NFR_OT_VoicesBuild: copy WAVs and run build_voice_pipeline.py."""
import bpy
import shutil
import subprocess
import sys
from pathlib import Path
from bpy.types import Operator

from ..constants import DEFAULT_REPO
from ..prefs import _get_prefs
from .state import VOICE_EVENTS


class NFR_OT_VoicesBuild(Operator):
    bl_idname = "nfr.voices_build"
    bl_label = "Build Voice Banks"
    bl_description = (
        "Copy the selected WAVs to <slug>/voices/<event>.wav and "
        "run tools/custom_racers/build_voice_pipeline.py to "
        "regenerate ENG.XNF and the S18.XA+ sidecar banks"
    )

    def execute(self, context):
        st = context.scene.nfr_voices
        prefs = _get_prefs(context)

        slug = (st.slug or "").strip()
        if not slug:
            self.report({'ERROR'}, "Set the racer slug first")
            return {'CANCELLED'}

        slug_dir = prefs.racers_dir() / slug
        if not slug_dir.is_dir():
            self.report({'ERROR'}, f"Racer folder not found: {slug_dir}")
            return {'CANCELLED'}

        voices_dir = slug_dir / "voices"
        voices_dir.mkdir(exist_ok=True)

        copied, skipped = [], []
        for event, _label, _desc in VOICE_EVENTS:
            src = (getattr(st, event, "") or "").strip()
            if not src:
                skipped.append(event)
                continue
            src_path = Path(bpy.path.abspath(src))
            if not src_path.is_file():
                self.report({'WARNING'},
                            f"{event}: source file not found, skipping")
                skipped.append(event)
                continue
            dst = voices_dir / f"{event}.wav"
            try:
                # If the picker already points to the destination, skip.
                if src_path.resolve() == dst.resolve():
                    skipped.append(event)
                    continue
            except OSError:
                pass
            try:
                shutil.copy2(src_path, dst)
                copied.append(event)
            except Exception as e:
                self.report({'ERROR'}, f"{event}: copy failed: {e}")
                return {'CANCELLED'}

        if not copied:
            self.report({'ERROR'},
                        "No WAVs to copy. Pick at least one file.")
            return {'CANCELLED'}

        repo = Path(DEFAULT_REPO)
        pipeline = (repo / "tools" / "custom_racers"
                    / "build_voice_pipeline.py")
        if not pipeline.is_file():
            self.report({'ERROR'}, f"Pipeline not found: {pipeline}")
            return {'CANCELLED'}

        python_exe = sys.executable or "python"
        try:
            result = subprocess.run(
                [python_exe, str(pipeline), "-v"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            self.report({'ERROR'}, "Pipeline timed out (>5 min)")
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Pipeline subprocess failed: {e}")
            return {'CANCELLED'}

        print("=== build_voice_pipeline.py stdout ===")
        print(result.stdout or "(empty)")
        if result.stderr:
            print("=== build_voice_pipeline.py stderr ===")
            print(result.stderr)

        if result.returncode != 0:
            self.report(
                {'ERROR'},
                f"Pipeline failed (exit {result.returncode}). "
                f"See the Blender console for details."
            )
            return {'CANCELLED'}

        msg = f"Built {len(copied)} voice track(s)"
        if skipped:
            msg += f" ({len(skipped)} event(s) skipped)"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


_classes = (NFR_OT_VoicesBuild,)


def register():
    for c in _classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)