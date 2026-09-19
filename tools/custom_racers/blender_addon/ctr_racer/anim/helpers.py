# =========================================================================
# MODULE: anim — helpers
# =========================================================================
"""Frame-range parsing. Pure module: only stdlib json, no bpy."""
import json


# Recognized clip names, in the order the panel shows them.
# Anything else in the JSON is ignored (but preserved on disk).
CLIP_ORDER = ("turn", "reverse", "bump", "jump")


def parse_frame_ranges(prefs):
    """Parse prefs.anim_frame_ranges.

    Returns:
        dict[clip_name] = (start, end)  on success (only recognized clips,
                                        in CLIP_ORDER, ints, end >= start)
        None                            if the JSON is malformed
        {}                              if the JSON is valid but has no
                                        recognized clips
    """
    raw = getattr(prefs, "anim_frame_ranges", "") or "{}"
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    out = {}
    for name in CLIP_ORDER:
        if name not in data:
            continue
        rng = data[name]
        if not isinstance(rng, (list, tuple)) or len(rng) != 2:
            continue
        try:
            fmin = int(rng[0])
            fmax = int(rng[1])
        except (TypeError, ValueError):
            continue
        if fmax < fmin:
            continue
        out[name] = (fmin, fmax)
    return out