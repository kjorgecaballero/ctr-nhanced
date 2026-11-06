# =========================================================================
# MODULE: core — helpers
# =========================================================================
"""Small helpers shared across the addon.

No classes, no registration. Pure functions.
"""
from pathlib import Path

import bpy


def _redraw_view3d(context):
    try:
        screen = context.screen
        if screen is None:
            return
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()
    except Exception:
        pass


def _find_object_by_slug(slug):
    return next((o for o in bpy.data.objects
                 if o.type == "MESH"
                 and hasattr(o, "racer")
                 and o.racer.slug == slug), None)


def _active_racer(context):
    obj = context.active_object
    if (obj is None or obj.type != "MESH"
            or not hasattr(obj, "racer") or not obj.racer.is_racer):
        return None
    return obj.racer


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

def get_python_exe():
    """Find the internal Python executable shipped with Blender."""
    import bpy
    from pathlib import Path
    
    # 1. Check if the user configured it
    try:
        prefs = bpy.context.preferences.addons["ctr_racer"].preferences
        if getattr(prefs, "python_exe", ""):
            return prefs.python_exe
    except Exception:
        pass

    # 2. Find Blender's internal Python
    blender_dir = Path(bpy.app.binary_path).parent
    ver = ".".join(bpy.app.version_string.split(".")[:2])
    
    for c in [
        blender_dir / ver / "python" / "bin" / "python.exe",
        blender_dir / "python" / "bin" / "python.exe",
        blender_dir / ver / "python" / "bin" / "python3",
        blender_dir / "python" / "bin" / "python3"
    ]:
        if c.exists():
            return str(c)
            
    return "python"
