# =========================================================================
# MODULE: ui — panel
# =========================================================================
"""NFR_PT_Racer: the single unified panel with sub-tabs.

Dispatches to one of three draw methods based on scene.nfr_ui_tab.
Pure UI: no persistent state, no operators owned here.
"""
import bpy
from bpy.types import Panel

from .. import state
from ..constants import (
    ADDON_ID, DEFAULT_REPO,
    MAX_PAGES, MAX_MATS_PER_PAGE, _BLEND_MODE_SET,
)
from ..prefs import _get_prefs
from ..core.helpers import _find_object_by_slug, _active_racer
from ..core.roster import _read_roster, _group_by_page
from ..core.icons import _get_icon, _get_original_icon, _image_preview_icon_id
from ..core.validate import validate_racer
from ..slots.state import _resolve_cells


class NFR_PT_Racer(Panel):
    bl_label = "CTR Racer"
    bl_idname = "NFR_PT_racer"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Racer"

    # ---------------------------------------------------------------------
    # Dispatch based on scene.nfr_ui_tab
    # ---------------------------------------------------------------------
    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Sub-tab selector — full-width segmented buttons
        row = layout.row(align=True)
        row.scale_y = 1.4
        row.prop(scene, "nfr_ui_tab", expand=True)

        layout.separator()

        tab = scene.nfr_ui_tab
        if tab == 'SETTINGS':
            self._draw_settings(context, layout)
        elif tab == 'SLOTS':
            self._draw_slots(context, layout)
        elif tab == 'MATERIALS':
            self._draw_materials(context, layout)

    # ---------------------------------------------------------------------
    # SETTINGS tab
    # ---------------------------------------------------------------------
    def _draw_settings(self, context, layout):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            layout.label(text="Select a mesh object", icon="INFO")
            return

        r = obj.racer

        # -------- Row: Is Racer checkbox + Validate icon --------
        row = layout.row(align=True)
        row.prop(r, "is_racer")

        if r.is_racer:
            # Small inline validate button (icon only). Turns red if invalid.
            try:
                ok, _warns, _errs = validate_racer(obj)
            except Exception:
                ok = False

            sub = row.row(align=True)
            sub.alert = not ok
            sub.operator(
                "nfr.validate",
                text="",
                icon='CHECKMARK' if ok else 'ERROR',
            )

        if not r.is_racer:
            layout.label(text="Check 'Is Racer' to configure", icon="INFO")
            return

        col = layout.column(align=True)
        col.prop(r, "slug")

        info = col.row(align=True)
        info.alignment = "EXPAND"
        info.label(text=f"Page {r.page}", icon="INFO")
        info.label(text=f"Slot {r.slot}")
        info.label(text=f"ID {r.custom_id()}")
        col.label(text="Set position via the Slots tab",
                  icon="RESTRICT_SELECT_OFF")

        col.separator()
        col.prop(r, "engine")
        col.prop(r, "mask")
        col.prop(r, "wheels")

        col.separator()
        col.prop(r, "long_name")
        col.prop(r, "short_name")

        col.separator()
        color_row = col.row(align=True)
        color_row.label(text="Minimap Color:")
        color_row.prop(r, "color", text="")
        col.prop(r, "icon_path")

        # -------- Dev Tools --------
        layout.separator()
        layout.label(text="Dev Tools:", icon="TOOL_SETTINGS")

        row = layout.row(align=True)
        row.scale_y = 1.3
        row.operator("nfr.export", text="Export", icon="EXPORT")
        row.operator("nfr.export_all", text="Export All", icon="FILE_TICK")

        row = layout.row(align=True)
        row.scale_y = 1.3
        row.operator("nfr.run_game", text="Run", icon="PLAY")
        row.operator("nfr.build_and_run", text="Build & Run", icon="FILE_REFRESH")

        layout.separator()
        if ADDON_ID in context.preferences.addons:
            layout.operator(
                "preferences.addon_show",
                text="Open Preferences",
                icon="PREFERENCES",
            ).module = ADDON_ID
        else:
            layout.label(text="Script mode — edit DEFAULT_REPO", icon="INFO")
            layout.label(text=f"repo: {DEFAULT_REPO}")

    # ---------------------------------------------------------------------
    # SLOTS tab
    # ---------------------------------------------------------------------
    def _draw_slots(self, context, layout):
        prefs = _get_prefs(context)
        active_racer = _active_racer(context)
        active_slug = active_racer.slug if active_racer else None

        row = layout.row(align=True)
        row.operator("nfr.slot_prev_page", text="", icon="TRIA_LEFT")
        row.label(text=f"Page {state._slot_view_page} / {MAX_PAGES}")
        row.operator("nfr.slot_next_page", text="", icon="TRIA_RIGHT")

        row = layout.row(align=True)
        row.scale_y = 1.2
        row.operator("nfr.slot_refresh", text="Refresh", icon="FILE_REFRESH")
        assign_row = row.row(align=True)
        # Disable "Assign Here" if the selected slot is a page-0 original
        # (slots 0-15 are reserved by the engine and cannot be reassigned).
        is_original_sel = (state._slot_sel_page == 0
                           and 0 <= state._slot_sel_slot < 16)
        assign_row.enabled = (state._slot_sel_page == state._slot_view_page
                              and state._slot_sel_slot >= 0
                              and active_racer is not None
                              and not is_original_sel)
        assign_row.operator("nfr.slot_assign_here",
                            text="Assign Here", icon="ADD")

        entries = _read_roster(prefs)
        pages = _group_by_page(entries)
        page_entries = pages.get(state._slot_view_page, {})
        cells = _resolve_cells(state._slot_view_page, page_entries,
                               active_racer, active_slug)

        n = 18
        occupied = sum(1 for k, _ in cells.values() if k != "empty")
        layout.label(text=f"{occupied}/{n} slots occupied")

        grid = layout.grid_flow(
            row_major=True, columns=6,
            even_columns=True, even_rows=True, align=True)

        # Mirror the in-game page-0 grid: slot 16 is the leftmost cell of
        # row 3 and slot 17 the rightmost, with slots 12-15 in between.
        # Rows 1-2 keep their natural order. This is a DISPLAY order — the
        # click handler still reports the real slot number.
        DISPLAY_ORDER = [
            0, 1, 2, 3, 4, 5,
            6, 7, 8, 9, 10, 11,
            16, 12, 13, 14, 15, 17,
        ]

        for slot in DISPLAY_ORDER:
            kind, data = cells[slot]

            # Engine originals on page 0, slots 0-15: draw like a normal
            # cell with the bundled icon. The cell is still clickable (to
            # inspect it), but "Assign Here" is gated off above.
            if kind == "original":
                icon = _get_original_icon(data["icon_file"])
                if icon is not None:
                    op = grid.operator("nfr.slot_click", text="",
                                       icon_value=icon.icon_id)
                else:
                    op = grid.operator("nfr.slot_click", text=str(slot))
                op.page = state._slot_view_page
                op.slot = slot
                continue

            if kind in ("entry", "pending"):
                folder = data["folder"]
                png = prefs.racers_dir() / folder / "icon.png"
                icon = _get_icon(folder, png) if png.is_file() else None
                if icon is not None:
                    op = grid.operator("nfr.slot_click", text="",
                                       icon_value=icon.icon_id)
                else:
                    op = grid.operator("nfr.slot_click",
                                       text=folder[:6])
            else:
                op = grid.operator("nfr.slot_click", text=str(slot))
            op.page = state._slot_view_page
            op.slot = slot

        if state._slot_sel_page != state._slot_view_page or state._slot_sel_slot < 0:
            layout.separator()
            layout.label(text="Click a slot to inspect", icon="INFO")
            return

        kind, data = cells.get(state._slot_sel_slot, ("empty", None))

        layout.separator()
        box = layout.box()

        if kind == "original":
            box.label(
                text=f"Slot {state._slot_sel_slot} — {data['name']}",
                icon="LOCKED")
            box.label(text="Engine original. Cannot be reassigned.",
                      icon="INFO")
            return

        if kind == "empty":
            box.label(text=f"Slot {state._slot_sel_slot} — empty", icon="INFO")
            if active_racer is not None:
                box.label(text=f"Press 'Assign Here' to place {active_slug}")
            else:
                box.label(text="Select a racer mesh, then Assign Here")
            return

        row = box.row(align=True)
        preview_col = row.column()
        preview_col.scale_x = 1.0
        png = prefs.racers_dir() / data["folder"] / "icon.png"
        icon = _get_icon(data["folder"], png) if png.is_file() else None
        if icon is not None:
            preview_col.template_icon(icon_value=icon.icon_id, scale=5.0)

        info_col = row.column()
        info_col.scale_x = 1.0
        header = f"Slot {state._slot_sel_slot} — {data['folder']}"
        if kind == "pending":
            header += "  (pending export)"
        info_col.label(text=header)
        info_col.label(text=data["name"])
        info_col.label(text=f"Engine: {data['engine']}")
        info_col.label(text=f"Mask: {data['mask']}")
        info_col.label(text=f"Wheels: {data['wheels']}")
        if data.get("color"):
            info_col.label(text=f"Color: {data['color']}")

        obj = _find_object_by_slug(data["folder"])
        if obj is not None:
            info_col.label(text=f"In blend: {obj.name}", icon="CHECKMARK")
        else:
            info_col.label(text="Not in this .blend", icon="INFO")

        row = box.row(align=True)
        if obj is not None:
            op = row.operator("nfr.slot_load_to_panel",
                              text="Focus", icon="RESTRICT_SELECT_OFF")
            op.slug = data["folder"]
        if kind == "entry":
            op = row.operator("nfr.slot_delete",
                              text="Delete from roster", icon="TRASH")
            op.page = state._slot_sel_page
            op.slot = state._slot_sel_slot

    # ---------------------------------------------------------------------
    # MATERIALS tab
    # ---------------------------------------------------------------------
    def _draw_materials(self, context, layout):
        scene = context.scene
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            layout.label(text="Select a mesh object", icon="INFO")
            return

        m = obj.data

        # -------- Render ON/OFF (top of tab) --------
        top = layout.row(align=True)
        top.scale_y = 1.4
        toggle_icon = 'RADIOBUT_ON' if scene.nfr_ps1_render_state else 'RADIOBUT_OFF'
        top.operator(
            "nfr.ps1_toggle_render",
            text="Render: ON" if scene.nfr_ps1_render_state else "Render: OFF",
            icon=toggle_icon,
        )
        layout.separator()

        if not m.materials:
            layout.label(text="No materials on this mesh", icon="INFO")
            return

        mats = [mat for mat in m.materials if mat is not None]
        total = len(mats)
        if total == 0:
            layout.label(text="No materials on this mesh", icon="INFO")
            return

        total_pages = max(1, (total + MAX_MATS_PER_PAGE - 1) // MAX_MATS_PER_PAGE)

        if state._mat_view_page < 1:
            state._mat_view_page = 1
        if state._mat_view_page > total_pages:
            state._mat_view_page = total_pages

        # -------- Pagination (only if more than one page) --------
        if total_pages > 1:
            row = layout.row(align=True)
            sub_left = row.row(align=True)
            sub_left.enabled = state._mat_view_page > 1
            sub_left.operator("nfr.mat_prev_page", text="", icon="TRIA_LEFT")
            row.label(
                text=f"Materials  {state._mat_view_page} / {total_pages}  ({total} total)"
            )
            sub_right = row.row(align=True)
            sub_right.enabled = state._mat_view_page < total_pages
            sub_right.operator("nfr.mat_next_page", text="", icon="TRIA_RIGHT")
            layout.separator()

        start = (state._mat_view_page - 1) * MAX_MATS_PER_PAGE
        end = min(start + MAX_MATS_PER_PAGE, total)
        page_mats = mats[start:end]

        # -------- Per material --------
        for mat in page_mats:
            stored = mat.get("blend_mode", "half")
            if stored not in _BLEND_MODE_SET:
                stored = "half"
            if getattr(mat, "nfr_racer_blend_mode", "half") != stored:
                mat.nfr_racer_blend_mode = stored

            box = layout.box()

            img = None
            if mat.use_nodes and mat.node_tree:
                for n in mat.node_tree.nodes:
                    if n.type == "TEX_IMAGE" and n.image:
                        img = n.image
                        break

            # Row 1: thumb | info | eye | apply
            row = box.row(align=True)

            icon_id = _image_preview_icon_id(img)
            if icon_id:
                row.template_icon(icon_value=icon_id, scale=2.0)
            else:
                row.label(text="", icon="IMAGE_DATA")

            info = row.column(align=True)
            info.label(text=mat.name, icon="MATERIAL")
            if img:
                info.label(text=img.name, icon="IMAGE_DATA")
            else:
                info.label(text="(no image)", icon="ERROR")

            is_showing = getattr(mat, 'nfr_ps1_show_backface', False)
            toggle_op = row.operator(
                "nfr.toggle_double_sided",
                text="",
                icon='HIDE_OFF' if is_showing else 'HIDE_ON',
                depress=is_showing,
            )
            toggle_op.material_name = mat.name

            apply_op = row.operator(
                "nfr.racer_apply_blend_mode",
                text="",
                icon='CHECKMARK',
            )
            apply_op.material_name = mat.name

            # Row 2: blend mode dropdown
            drop = box.row(align=True)
            drop.prop(mat, "nfr_racer_blend_mode", text="")


_classes = (NFR_PT_Racer,)


def register():
    for c in _classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)