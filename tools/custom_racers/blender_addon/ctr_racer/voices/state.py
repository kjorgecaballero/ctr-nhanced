# =========================================================================
# MODULE: voices — state
# =========================================================================
"""NFR_VoicesState: per-scene voiceline slug + WAV paths per event.

Also: helpers to check if the voice banks are up to date with the
current roster. The pipeline writes a sidecar (ENG.XNF.voices.json)
with a hash of the roster; we recompute the same hash here and warn
the user if they don't match (VOICELINES-ROSTER-FINGERPRINT).
"""
import hashlib
import json
from pathlib import Path

import bpy
from bpy.props import StringProperty, PointerProperty


VOICE_EVENTS = (
    ("boost_01",     "Boost 1",     "Boost pad / turbo item (variant 1)"),
    ("boost_02",     "Boost 2",     "Boost pad / turbo item (variant 2)"),
    ("hurt_01",      "Hurt 1",      "Hit / squashed / wall crash (variant 1)"),
    ("hurt_02",      "Hurt 2",      "Hit / squashed / wall crash (variant 2)"),
    ("spin_01",      "Spin 1",      "Spin attack (variant 1)"),
    ("spin_02",      "Spin 2",      "Spin attack (variant 2)"),
    ("jump_01",      "Jump 1",      "Big-air meter (variant 1)"),
    ("jump_02",      "Jump 2",      "Big-air meter (variant 2)"),
    ("trap_01",      "Trap 1",      "Potion / TNT / crate (variant 1)"),
    ("trap_02",      "Trap 2",      "Potion / TNT / crate (variant 2)"),
    ("protected_01", "Protected 1", "Blocked hit / shield (variant 1)"),
    ("protected_02", "Protected 2", "Blocked hit / shield (variant 2)"),
    ("overtake_01",  "Overtake 1",  "Passes a human racer (variant 1)"),
    ("overtake_02",  "Overtake 2",  "Passes a human racer (variant 2)"),
    ("attack_01",    "Attack 1",    "Attack item fired (variant 1)"),
    ("attack_02",    "Attack 2",    "Attack item fired (variant 2)"),
    ("menu_yes",     "Menu Yes",    "YES quip in the options menu"),
    ("menu_ouch",    "Menu Ouch",   "OUCH quip in the options menu"),
)

# Slots 0..15 = gameplay, 16..17 = menu. Split index for the UI.
MENU_SPLIT_INDEX = 16

SIDECAR_VERSION = 3

# Legacy fallback map: canonical <group>_01 event -> bare <group>.wav.
# Mirrors LEGACY_FALLBACKS in tools/custom_racers/build_voice_pipeline.py.
# Only *_01 slots have a fallback; *_02 slots are silent if missing.
LEGACY_FALLBACKS = {
    "boost_01":     "boost",
    "hurt_01":      "hurt",
    "spin_01":      "spin",
    "jump_01":      "jump",
    "trap_01":      "trap",
    "protected_01": "protected",
    "overtake_01":  "overtake",
    "attack_01":    "attack",
}


def _auto_detect_wavs(source_dir):
    """Scan source_dir for WAVs matching VOICE_EVENTS.

    Returns a dict {event: Path|None}. Canonical <event>.wav wins;
    for *_01 slots only, fall back to the legacy <group>.wav if the
    canonical file is missing. Mirrors the resolution order in
    build_voice_pipeline.py so the addon and the pipeline agree on
    which WAV is which event.

    The caller is responsible for checking source_dir exists.
    """
    out = {}
    for event, _label, _desc in VOICE_EVENTS:
        cand = source_dir / f"{event}.wav"
        if cand.is_file():
            out[event] = cand
            continue
        legacy = LEGACY_FALLBACKS.get(event)
        if legacy is not None:
            alt = source_dir / f"{legacy}.wav"
            if alt.is_file():
                out[event] = alt
                continue
        out[event] = None
    return out


class NFR_VoicesState(bpy.types.PropertyGroup):
    slug: StringProperty(name="Slug", default="")

    # Where the user's source WAVs live (any folder on disk). The
    # auto-detect operator scans this folder for the 18 canonical
    # event names and fills the per-event pickers.
    source_dir: StringProperty(
        name="Source Folder",
        subtype="DIR_PATH",
        description="Folder containing your source WAVs "
                    "(boost_01.wav, ..., menu_ouch.wav)",
    )

    boost_01:     StringProperty(name="Boost 1",     subtype="FILE_PATH")
    boost_02:     StringProperty(name="Boost 2",     subtype="FILE_PATH")
    hurt_01:      StringProperty(name="Hurt 1",      subtype="FILE_PATH")
    hurt_02:      StringProperty(name="Hurt 2",      subtype="FILE_PATH")
    spin_01:      StringProperty(name="Spin 1",      subtype="FILE_PATH")
    spin_02:      StringProperty(name="Spin 2",      subtype="FILE_PATH")
    jump_01:      StringProperty(name="Jump 1",      subtype="FILE_PATH")
    jump_02:      StringProperty(name="Jump 2",      subtype="FILE_PATH")
    trap_01:      StringProperty(name="Trap 1",      subtype="FILE_PATH")
    trap_02:      StringProperty(name="Trap 2",      subtype="FILE_PATH")
    protected_01: StringProperty(name="Protected 1", subtype="FILE_PATH")
    protected_02: StringProperty(name="Protected 2", subtype="FILE_PATH")
    overtake_01:  StringProperty(name="Overtake 1",  subtype="FILE_PATH")
    overtake_02:  StringProperty(name="Overtake 2",  subtype="FILE_PATH")
    attack_01:    StringProperty(name="Attack 1",    subtype="FILE_PATH")
    attack_02:    StringProperty(name="Attack 2",    subtype="FILE_PATH")
    menu_yes:     StringProperty(name="Menu Yes",    subtype="FILE_PATH")
    menu_ouch:    StringProperty(name="Menu Ouch",   subtype="FILE_PATH")


def _roster_hash(repo_root):
    """SHA256 of the roster, matching build_voice_pipeline.py's
    roster_fingerprint(). Returns None if roster.txt is missing or
    unreadable.

    IMPORTANT: this must stay in sync with read_roster() in the
    pipeline. Both use `line.split()` (not shlex) and skip lines
    with fewer than 3 whitespace-separated tokens.
    """
    roster_path = repo_root / "assets" / "mods" / "racers" / "roster.txt"
    if not roster_path.is_file():
        return None
    try:
        text = roster_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    entries = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            page, slot = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        entries.append(f"{page}|{slot}|{parts[2]}")
    payload = "\n".join(entries)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _read_sidecar(repo_root):
    """Read the pipeline's sidecar. Returns None if missing or corrupt."""
    sidecar = repo_root / "assets" / "XA" / "ENG.XNF.voices.json"
    if not sidecar.is_file():
        return None
    try:
        return json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception:
        return None


def _pipeline_status(repo_root):
    """Return (state, data) where state is one of:
        'no_roster'    - roster.txt not found
        'missing'      - sidecar not found (pipeline never ran)
        'stale'        - sidecar exists but hash doesn't match roster
        'stale_layout' - hash matches but event layout is outdated
                         (sidecar was built with a different event count)
        'fresh'        - sidecar hash matches roster and layout
    data is the sidecar dict (or None).
    """
    current = _roster_hash(repo_root)
    if current is None:
        return ("no_roster", None)
    sidecar = _read_sidecar(repo_root)
    if sidecar is None:
        return ("missing", None)
    if sidecar.get("roster_hash") != current:
        return ("stale", sidecar)
    if sidecar.get("event_count") != len(VOICE_EVENTS):
        return ("stale_layout", sidecar)
    # v3 adds variant_count. Sidecars without it (v2) are stale too.
    if sidecar.get("variant_count") != 2:
        return ("stale_layout", sidecar)
    return ("fresh", sidecar)


_classes = (NFR_VoicesState,)


def register():
    for c in _classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.nfr_voices = PointerProperty(type=NFR_VoicesState)


def unregister():
    del bpy.types.Scene.nfr_voices
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)