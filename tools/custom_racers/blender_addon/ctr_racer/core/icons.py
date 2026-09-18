# =========================================================================
# MODULE: core — icon previews
# =========================================================================
"""bpy.utils.previews management for slot icons and material thumbnails.

Lazily creates a preview collection. The collection is torn down by
the addon's top-level unregister().
"""
import bpy
from pathlib import Path


# Bundled original-racer icons live in ctr_racer/icons/. From
# core/icons.py, that's two levels up.
_ADDON_ICONS_DIR = Path(__file__).resolve().parent.parent / "icons"

_preview_collection = None
_icon_cache = {}
_icon_mtimes = {}


def _ensure_previews():
    global _preview_collection
    if _preview_collection is None:
        _preview_collection = bpy.utils.previews.new()
    return _preview_collection


def _teardown_previews():
    global _preview_collection
    if _preview_collection is not None:
        try:
            bpy.utils.previews.remove(_preview_collection)
        except Exception:
            pass
        _preview_collection = None
    _icon_cache.clear()
    _icon_mtimes.clear()


def _get_icon(slug, png_path):
    pc = _ensure_previews()
    try:
        mtime = png_path.stat().st_mtime
    except OSError:
        return None
    if slug in _icon_cache and _icon_mtimes.get(slug) == mtime:
        return _icon_cache[slug]
    if slug in _icon_cache:
        try:
            pc.remove(slug)
        except Exception:
            pass
        del _icon_cache[slug]
    try:
        icon = pc.load(slug, str(png_path), "IMAGE")
    except Exception:
        _icon_mtimes.pop(slug, None)
        return None
    _icon_cache[slug] = icon
    _icon_mtimes[slug] = mtime
    return icon


def _get_original_icon(icon_file):
    """Load a bundled original-racer icon (crash.png, cortex.png, ...).

    The cache key is prefixed with '__orig__' so it can't collide with a
    user-named racer slug (e.g. a custom folder literally called 'crash'
    would otherwise overwrite the cache entry)."""
    png = _ADDON_ICONS_DIR / icon_file
    return _get_icon(f"__orig__{icon_file}", png)


def _image_preview_icon_id(img):
    if img is None:
        return 0
    try:
        img.preview_ensure()
    except Exception:
        return 0
    pv = getattr(img, "preview", None)
    if pv is None:
        return 0
    try:
        return pv.icon_id or 0
    except Exception:
        return 0