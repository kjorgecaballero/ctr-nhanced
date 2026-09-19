# =========================================================================
# MODULE: anim — state
# =========================================================================
"""Per-scene animation-tab state.

Owns NFR_AnimState (Scene.nfr_anim):
  - selected_clip : the currently selected clip in the segmented bar
  - <clip>_start / <clip>_end : editable frame ranges, mirrored to
    prefs.anim_frame_ranges (JSON) so the bake pipeline keeps working

Bidirectional sync between state and prefs JSON:
  - Edit a spinner  -> update callback writes prefs.anim_frame_ranges
  - Edit the JSON   -> panel draw calls request_sync_from_prefs() which
    schedules a deferred sync (panel.draw cannot write to ID datablocks;
    a timer callback can).
"""
import bpy
import json
from bpy.props import (
    BoolProperty, EnumProperty, IntProperty, StringProperty,
)
from bpy.types import PropertyGroup

from ..constants import ADDON_ID
from .helpers import CLIP_ORDER


def _get_prefs_obj():
    """Fetch addon prefs without needing a full context."""
    try:
        return bpy.context.preferences.addons[ADDON_ID].preferences
    except Exception:
        return None


def _write_ranges_to_prefs(self, context):
    """Update callback: state -> prefs.anim_frame_ranges JSON.

    Suppressed while a deferred sync is writing."""
    if getattr(self, "nfr_anim_syncing", False):
        return
    prefs = _get_prefs_obj()
    if prefs is None:
        return

    data = {
        clip: [getattr(self, f"{clip}_start"), getattr(self, f"{clip}_end")]
        for clip in CLIP_ORDER
    }
    try:
        prefs.anim_frame_ranges = json.dumps(data)
        self.nfr_anim_last_synced_json = prefs.anim_frame_ranges
    except Exception:
        pass


class NFR_AnimState(PropertyGroup):
    selected_clip: EnumProperty(
        name="Clip",
        items=[("turn", "Turn", ""),
               ("reverse", "Reverse", ""),
               ("bump", "Bump", ""),
               ("jump", "Jump", "")],
        default="turn",
    )

    # --- frame ranges (mirrored to prefs JSON) ---
    turn_start:    IntProperty(name="Start", min=0, default=0,
                               update=_write_ranges_to_prefs)
    turn_end:      IntProperty(name="End",   min=0, default=22,
                               update=_write_ranges_to_prefs)
    reverse_start: IntProperty(name="Start", min=0, default=23,
                               update=_write_ranges_to_prefs)
    reverse_end:   IntProperty(name="End",   min=0, default=35,
                               update=_write_ranges_to_prefs)
    bump_start:    IntProperty(name="Start", min=0, default=36,
                               update=_write_ranges_to_prefs)
    bump_end:      IntProperty(name="End",   min=0, default=53,
                               update=_write_ranges_to_prefs)
    jump_start:    IntProperty(name="Start", min=0, default=54,
                               update=_write_ranges_to_prefs)
    jump_end:      IntProperty(name="End",   min=0, default=59,
                               update=_write_ranges_to_prefs)

    # --- internal sync bookkeeping (hidden; no leading underscore,
    #     Blender rejects those). ---
    nfr_anim_syncing: BoolProperty(default=False)
    nfr_anim_last_synced_json: StringProperty(default="")


def _apply_sync_to_scene(scene):
    """Do the actual write. Safe from update callbacks, operators, and
    timer callbacks. NOT safe from panel.draw."""
    if scene is None:
        return
    prefs = _get_prefs_obj()
    if prefs is None:
        return
    try:
        st = scene.nfr_anim
    except Exception:
        return

    current = getattr(prefs, "anim_frame_ranges", "") or "{}"
    if st.nfr_anim_last_synced_json == current:
        return

    try:
        data = json.loads(current)
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}

    st.nfr_anim_syncing = True
    try:
        for clip in CLIP_ORDER:
            if clip not in data:
                continue
            rng = data[clip]
            if not (isinstance(rng, (list, tuple)) and len(rng) == 2):
                continue
            try:
                s = int(rng[0])
                e = int(rng[1])
            except (TypeError, ValueError):
                continue
            setattr(st, f"{clip}_start", s)
            setattr(st, f"{clip}_end", e)
    finally:
        st.nfr_anim_syncing = False
    st.nfr_anim_last_synced_json = current


def sync_state_from_prefs(scene):
    """Synchronous sync. Call from update callbacks / operators / timers.
    NOT from panel.draw — use request_sync_from_prefs instead."""
    _apply_sync_to_scene(scene)


# ----------------------------------------------------------------------
# Deferred sync (safe from panel.draw)
# ----------------------------------------------------------------------

_pending_sync_scenes = set()
_sync_timer_pending = False


def _sync_timer():
    global _sync_timer_pending
    _sync_timer_pending = False
    scenes = list(_pending_sync_scenes)
    _pending_sync_scenes.clear()
    for scene in scenes:
        try:
            _apply_sync_to_scene(scene)
        except Exception as ex:
            print(f"[anim] deferred sync failed: {ex}")
    return None  # one-shot


def request_sync_from_prefs(scene):
    """Schedule a deferred sync. Safe to call from panel.draw."""
    global _sync_timer_pending
    if scene is None:
        return

    prefs = _get_prefs_obj()
    if prefs is None:
        return
    try:
        st = scene.nfr_anim
    except Exception:
        return
    current = getattr(prefs, "anim_frame_ranges", "") or "{}"
    if st.nfr_anim_last_synced_json == current:
        return

    _pending_sync_scenes.add(scene)
    if _sync_timer_pending:
        return
    _sync_timer_pending = True
    bpy.app.timers.register(_sync_timer, first_interval=0.0)


_classes = (NFR_AnimState,)


def register():
    for c in _classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.nfr_anim = bpy.props.PointerProperty(type=NFR_AnimState)


def unregister():
    del bpy.types.Scene.nfr_anim
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)