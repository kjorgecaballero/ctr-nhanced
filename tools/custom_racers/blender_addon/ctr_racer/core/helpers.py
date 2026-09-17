# =========================================================================
# MODULE: core — helpers
# =========================================================================
"""Small helpers shared across the addon.

No classes, no registration. Pure functions.
"""
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