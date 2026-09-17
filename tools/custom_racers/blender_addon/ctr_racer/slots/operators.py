# =========================================================================
# MODULE: slots — operators
# =========================================================================
"""Slot viewer operators.

Owns the seven slot-grid operators. The view/selection page state lives
in ctr_racer.state (top-level); these operators read/write it via
state._slot_*.
"""
import bpy
from bpy.props import IntProperty, StringProperty
from bpy.types import Operator

from .. import state
from ..constants import MAX_PAGES
from ..prefs import _get_prefs
from ..core.helpers import _redraw_view3d, _find_object_by_slug
from ..core.roster import _read_roster, _remove_roster_entry
from ..core.icons import _teardown_previews


class NFR_OT_SlotClick(Operator):
    bl_idname = "nfr.slot_click"
    bl_label = "Slot"
    bl_description = ("Select a cell. If occupied, also focus the matching "
                      "Blender object for editing.")

    page: IntProperty()
    slot: IntProperty()

    def execute(self, context):
        prefs = _get_prefs(context)
        entries = _read_roster(prefs)
        entry = next((x for x in entries
                      if x["page"] == self.page and x["slot"] == self.slot),
                     None)

        state._slot_sel_page = self.page
        state._slot_sel_slot = self.slot

        if entry is not None:
            obj = _find_object_by_slug(entry["folder"])
            if obj is not None:
                for o in bpy.data.objects:
                    o.select_set(False)
                obj.select_set(True)
                context.view_layer.objects.active = obj
                self.report({"INFO"}, f"Selected {obj.name}")
            else:
                self.report({"INFO"},
                    f"'{entry['folder']}' not in this .blend (roster-only)")

        _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_SlotAssignHere(Operator):
    bl_idname = "nfr.slot_assign_here"
    bl_label = "Assign Here"
    bl_description = ("Set the active racer mesh's page/slot to the selected "
                      "cell. roster.txt is not touched until you press Export.")

    def execute(self, context):
        if state._slot_sel_page < 0 or state._slot_sel_slot < 0:
            self.report({"ERROR"}, "Click a slot in the grid first")
            return {"CANCELLED"}
        obj = context.active_object
        if obj is None or obj.type != "MESH" or not obj.racer.is_racer:
            self.report({"ERROR"}, "Select a racer mesh first")
            return {"CANCELLED"}

        prefs = _get_prefs(context)
        entries = _read_roster(prefs)
        existing = next((x for x in entries
                         if x["page"] == state._slot_sel_page
                         and x["slot"] == state._slot_sel_slot), None)

        obj.racer.page = state._slot_sel_page
        obj.racer.slot = state._slot_sel_slot

        if existing is not None and existing["folder"] != obj.racer.slug:
            self.report({"WARNING"},
                f"Slot {state._slot_sel_slot} is already taken by "
                f"'{existing['folder']}'. Export will leave two entries "
                f"at this position.")
        else:
            self.report({"INFO"},
                f"Assigned {obj.name} to page {state._slot_sel_page} "
                f"slot {state._slot_sel_slot}. Press Export to commit.")
        _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_SlotDelete(Operator):
    bl_idname = "nfr.slot_delete"
    bl_label = "Delete from roster"
    bl_description = "Remove this slot's roster.txt line (files kept on disk)"

    page: IntProperty()
    slot: IntProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        prefs = _get_prefs(context)
        ok, result = _remove_roster_entry(prefs, self.page, self.slot)
        if not ok:
            self.report({"ERROR"}, result)
            return {"CANCELLED"}

        if state._slot_sel_page == self.page and state._slot_sel_slot == self.slot:
            state._slot_sel_page = -1
            state._slot_sel_slot = -1

        self.report({"INFO"},
            f"Removed '{result}' from roster.txt (files kept)")
        _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_SlotRefresh(Operator):
    bl_idname = "nfr.slot_refresh"
    bl_label = "Refresh"
    bl_description = "Reload roster.txt and icon previews from disk"

    def execute(self, context):
        _teardown_previews()
        _redraw_view3d(context)
        self.report({"INFO"}, "Reloaded roster.txt and icons")
        return {"FINISHED"}


class NFR_OT_SlotPrevPage(Operator):
    bl_idname = "nfr.slot_prev_page"
    bl_label = "Previous page"

    def execute(self, context):
        if state._slot_view_page > 0:
            state._slot_view_page -= 1
            _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_SlotNextPage(Operator):
    bl_idname = "nfr.slot_next_page"
    bl_label = "Next page"

    def execute(self, context):
        if state._slot_view_page < MAX_PAGES:
            state._slot_view_page += 1
            _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_SlotLoadToPanel(Operator):
    bl_idname = "nfr.slot_load_to_panel"
    bl_label = "Focus in panel"
    bl_description = "Select the Blender object whose slug matches this entry"

    slug: StringProperty()

    def execute(self, context):
        obj = _find_object_by_slug(self.slug)
        if obj is None:
            self.report({"WARNING"},
                f"No Blender object with slug '{self.slug}'")
            return {"CANCELLED"}

        for o in bpy.data.objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj

        self.report({"INFO"}, f"Selected {obj.name}")
        _redraw_view3d(context)
        return {"FINISHED"}


_classes = (
    NFR_OT_SlotClick,
    NFR_OT_SlotAssignHere,
    NFR_OT_SlotDelete,
    NFR_OT_SlotRefresh,
    NFR_OT_SlotPrevPage,
    NFR_OT_SlotNextPage,
    NFR_OT_SlotLoadToPanel,
)


def register():
    for c in _classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)