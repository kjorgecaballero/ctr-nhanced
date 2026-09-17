# =========================================================================
# MODULE: core — icon previews
# =========================================================================
"""bpy.utils.previews management for slot icons and material thumbnails.

Lazily creates a preview collection. The collection is torn down by
the addon's top-level unregister().
"""
import bpy


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