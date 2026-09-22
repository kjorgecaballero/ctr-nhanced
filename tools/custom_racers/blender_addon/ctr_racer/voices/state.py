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
    ("boost",     "Boost",     "Boost pad / turbo item"),
    ("hurt",      "Hurt",      "Hit / squashed"),
    ("spin",      "Spin",      "Spin attack"),
    ("jump",      "Jump",      "Big-air meter"),
    ("trap",      "Trap",      "Potion / TNT / crate"),
    ("protected", "Protected", "Blocked hit / shield"),
    ("overtake",  "Overtake",  "Passes a human racer"),
    ("attack",    "Attack",    "Attack item fired"),
)

SIDECAR_VERSION = 1


class NFR_VoicesState(bpy.types.PropertyGroup):
    slug: StringProperty(name="Slug", default="")

    boost:     StringProperty(name="Boost",     subtype="FILE_PATH")
    hurt:      StringProperty(name="Hurt",      subtype="FILE_PATH")
    spin:      StringProperty(name="Spin",      subtype="FILE_PATH")
    jump:      StringProperty(name="Jump",      subtype="FILE_PATH")
    trap:      StringProperty(name="Trap",      subtype="FILE_PATH")
    protected: StringProperty(name="Protected", subtype="FILE_PATH")
    overtake:  StringProperty(name="Overtake",  subtype="FILE_PATH")
    attack:    StringProperty(name="Attack",    subtype="FILE_PATH")


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
        'no_roster'   - roster.txt not found
        'missing'     - sidecar not found (pipeline never ran)
        'stale'       - sidecar exists but hash doesn't match roster
        'fresh'       - sidecar hash matches roster
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