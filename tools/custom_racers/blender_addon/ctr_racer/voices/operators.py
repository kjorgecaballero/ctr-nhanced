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
from .state import VOICE_EVENTS, _auto_detect_wavs


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

        copied, already_in_place, skipped = [], [], []
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
                # If the picker already points to the destination, no copy
                # is needed. This is the normal case for auto-detected
                # entries, so we must not treat it as "nothing to do".
                if src_path.resolve() == dst.resolve():
                    already_in_place.append(event)
                    continue
            except OSError:
                pass
            try:
                shutil.copy2(src_path, dst)
                copied.append(event)
            except Exception as e:
                self.report({'ERROR'}, f"{event}: copy failed: {e}")
                return {'CANCELLED'}

        if not copied and not already_in_place:
            self.report({'ERROR'},
                        "No WAVs to copy. Pick at least one file "
                        "(or run Auto-detect from folder).")
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

        n_used = len(copied) + len(already_in_place)
        msg = f"Built {n_used} voice track(s)"
        if copied and already_in_place:
            msg += f" ({len(copied)} copied, {len(already_in_place)} in place)"
        elif copied:
            msg += f" ({len(copied)} copied)"
        elif already_in_place:
            msg += f" ({len(already_in_place)} already in place)"
        if skipped:
            msg += f", {len(skipped)} event(s) skipped"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class NFR_OT_VoicesAutoDetect(Operator):
    bl_idname = "nfr.voices_auto_detect"
    bl_label = "Auto-detect from folder"
    bl_description = (
        "Scan the Source Folder for WAVs matching the 18 canonical "
        "event names (boost_01.wav, ..., menu_ouch.wav) and the "
        "legacy <group>.wav fallback for *_01 slots. Fills the "
        "pickers; missing events are cleared"
    )

    def execute(self, context):
        st = context.scene.nfr_voices

        source_str = (st.source_dir or "").strip()
        if not source_str:
            self.report({'ERROR'},
                        "Set the Source Folder first "
                        "(where your WAVs live)")
            return {'CANCELLED'}

        source_dir = Path(bpy.path.abspath(source_str))
        if not source_dir.is_dir():
            self.report({'ERROR'},
                        f"Source folder not found: {source_dir}")
            return {'CANCELLED'}

        found = _auto_detect_wavs(source_dir)

        # Overwrite every picker: the source folder is the source of
        # truth. Events without a matching WAV are cleared (silent,
        # same as the pipeline's null entries).
        hit, miss = 0, 0
        for event, _label, _desc in VOICE_EVENTS:
            path = found.get(event)
            if path is not None:
                setattr(st, event, str(path))
                hit += 1
            else:
                setattr(st, event, "")
                miss += 1

        if hit == 0:
            self.report(
                {'WARNING'},
                f"No matching WAVs in {source_dir.name}/. Expected "
                f"names like boost_01.wav, ..., menu_ouch.wav "
                f"(or legacy boost.wav for *_01 slots)"
            )
            return {'CANCELLED'}

        self.report({'INFO'},
                    f"Auto-detected {hit}/{len(VOICE_EVENTS)} events "
                    f"({miss} empty)")
        return {'FINISHED'}


_classes = (NFR_OT_VoicesBuild, NFR_OT_VoicesAutoDetect)


def register():
    for c in _classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)