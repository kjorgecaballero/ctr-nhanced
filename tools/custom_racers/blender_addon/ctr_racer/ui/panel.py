# =========================================================================
# MODULE: ui — panel
# =========================================================================
"""NFR_PT_Racer: the single unified panel with sub-tabs."""
import bpy
from pathlib import Path
from bpy.types import Panel

from .. import state
from ..constants import (
    ADDON_ID, DEFAULT_REPO,
    MAX_PAGES, MAX_MATS_PER_PAGE, MAX_PRESETS_PER_PAGE, _BLEND_MODE_SET,
    UI_MODES, UI_TABS_BY_MODE, UI_MODE_OF_TAB,
)
from ..prefs import _get_prefs
from ..core.helpers import _find_object_by_slug, _active_racer
from ..core.roster import _read_roster, _group_by_page
from ..core.icons import _get_icon, _get_original_icon, _image_preview_icon_id
from ..core.validate import validate_racer, _uv_out_of_range

from ..slots.state import _resolve_cells
from ..kart.templates import KART_TEMPLATES
from ..kart.presets import scan_presets
from ..anim.state import request_sync_from_prefs
from ..voices.state import VOICE_EVENTS, MENU_SPLIT_INDEX, _pipeline_status


class NFR_PT_Racer(Panel):
    bl_label = "CTR Racer"
    bl_idname = "NFR_PT_racer"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Racer"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Auto-sync mode from tab (handles old .blend files)
        # NFR_UI_SINGLE_BAR_V1
        try:
            current = UI_MODE_OF_TAB.get(scene.nfr_ui_tab, 'SETUP')
            if scene.nfr_ui_mode != current:
                scene.nfr_ui_mode = current
        except Exception:
            pass

        try:
            self._draw_nav_bar(context, layout)
        except Exception as e:
            print(f"[NFR] nav bar failed: {e}")
            print(f"[NFR] falling back to legacy 11-tab layout")
            self._draw_legacy_tabs(context, layout)

        layout.separator()

        tab = scene.nfr_ui_tab
        if tab == 'SETTINGS':
            self._draw_settings(context, layout)
        elif tab == 'SLOTS':
            self._draw_slots(context, layout)
        elif tab == 'MATERIALS':
            self._draw_materials(context, layout)
        elif tab == 'KART':
            self._draw_kart(context, layout)
        elif tab == 'PRESETS':
            self._draw_presets(context, layout)
        elif tab == 'ANIM':
            self._draw_anim(context, layout)
        elif tab == 'DANCE':
            self._draw_dance(context, layout)
        elif tab == 'ITEMS':
            self._draw_items(context, layout)
        elif tab == 'SFX':
            self._draw_sfx(context, layout)
        elif tab == 'ADVENTURE':
            _draw_adventure(layout, context)
        elif tab == 'LEVELS':
            self._draw_levels(context, layout)
        elif tab == 'VOICES':
            self._draw_voices(context, layout)

    def _draw_nav_bar(self, context, layout):
        """Single dropdown bar: all tabs grouped by mode."""
        # NFR_UI_SINGLE_DROPDOWN_V1
        scene = context.scene

        # Find the label of the current tab
        label = 'Select Tab'
        for mode_id, _mlabel, _mdesc in UI_MODES:
            for tid, lb, _d in UI_TABS_BY_MODE.get(mode_id, []):
                if tid == scene.nfr_ui_tab:
                    label = lb
                    break

        row = layout.row(align=True)
        row.scale_y = 1.3
        row.menu("NFR_MT_ui_tab", text=label, icon='TRIA_DOWN')

    def _draw_legacy_tabs(self, context, layout):
        """Fallback: old 11-tab layout."""
        scene = context.scene
        row_items = [
            [('SETTINGS', 'Settings'), ('SLOTS', 'Slots'), ('MATERIALS', 'Materials')],
            [('KART', 'Kart'), ('PRESETS', 'Presets'), ('ANIM', 'Anim')],
            [('DANCE', 'Dance'), ('ITEMS', 'Items'), ('SFX', 'SFX')],
            [('VOICES', 'Voices')],
            [('LEVELS', 'Levels')],
        ]
        for row_data in row_items:
            row = layout.row(align=True)
            row.scale_y = 1.3
            for tab_id, label in row_data:
                row.prop_enum(scene, "nfr_ui_tab", tab_id, text=label)

    def _draw_settings(self, context, layout):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            layout.label(text="Select a mesh object", icon="INFO")
            return

        r = obj.racer

        row = layout.row(align=True)
        row.prop(r, "is_racer")

        if r.is_racer:
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

            # Separate toggle: shows/hides the Issues box below.
            # Does NOT re-run validation — that is what the [check]
            # button above is for.
            det = row.row(align=True)
            det.operator(
                "nfr.toggle_validation_details",
                text="",
                icon='TRIA_DOWN' if state._validation_show_details else 'TRIA_RIGHT',
            )

        if not r.is_racer:
            layout.label(text="Check 'Is Racer' to configure", icon="INFO")
            return

        # Issues box (opt-in). Recomputes on draw only when expanded;
        # the UV check is the expensive part, so it is gated here too.
        # Each item is (level, short, long): the row shows `short`,
        # the click popup shows `long`.
        if state._validation_show_details:
            try:
                _ok, warns, errs = validate_racer(obj)
            except Exception:
                warns, errs = [], []

            items = []
            for short, long in errs:
                items.append(("ERROR", short, long))
            for short, long in warns:
                items.append(("WARNING", short, long))

            n_oob, min_u, max_u, min_v, max_v = _uv_out_of_range(obj)
            if n_oob > 0:
                items.append((
                    "WARNING",
                    "UV out of range",
                    f"UV out of [0,1]: {n_oob} loops "
                    f"(u: {min_u:.3f}..{max_u:.3f}, "
                    f"v: {min_v:.3f}..{max_v:.3f}). "
                    f"CTR clamps UVs to the texture edge before "
                    f"quantizing to u8. If you used tiling or mirroring, "
                    f"the in-game render will not match the Blender "
                    f"preview."
                ))

            box = layout.box()
            if not items:
                box.label(text="All checks passed", icon='CHECKMARK')
            else:
                for level, short, long in items:
                    r2 = box.row(align=True)
                    if level == "ERROR":
                        r2.alert = True
                    op = r2.operator(
                        "nfr.show_issue",
                        text=short,
                        icon='CANCEL' if level == "ERROR" else 'ERROR',
                    )
                    op.issue_text = long
                    # Vertex-color overflow has an automatic fix: run
                    # the k-means reduction down to the builder's limit
                    # (128 unique colors, build_character.py:670).
                    if short == "Vertex colors: too many":
                        r2.operator(
                            "nfr.fix_vertex_colors",
                            text="", icon="FILE_REFRESH",
                        )

        col = layout.column(align=True)
        slug_row = col.row(align=True)
        slug_row.prop(r, "slug")
        if " " in (r.slug or ""):
            slug_row.alert = True
            slug_row.operator("nfr.fix_slug", text="Fix", icon="FILE_REFRESH")

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
        col.prop(r, "kart_rot")
        
        # Box de rotacion custom (aparece solo si se elige Custom)
        if r.kart_rot == 'custom':
            box = col.box()
            box.label(text="Custom Parameters", icon="FILE_3D")
            box.prop(r, "jump_rot_preview")
            box.separator()
            box.prop(r, "jump_rot_pitch", slider=True)
            box.prop(r, "jump_rot_roll", slider=True)
            box.prop(r, "jump_rot_yaw", slider=True)
            box.prop(r, "jump_rot_pivot_z")
            box.prop(r, "jump_rot_frames")
            
            box.separator()
            box.operator("nfr.reset_jump_rot", text="Reset Defaults", icon="LOOP_BACK")

        col.separator()
        col.prop(r, "long_name")
        col.prop(r, "short_name")

        col.separator()
        color_row = col.row(align=True)
        color_row.label(text="Minimap Color:")
        color_row.prop(r, "color", text="")
        icon_row = col.row(align=True)
        icon_row.prop(r, "icon_path", text="Icon PNG")
        if r.icon_image:
            icon_row.label(text="", icon="PACKAGE")

        layout.separator()
        layout.label(text="Tools:", icon="TOOL_SETTINGS")

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

        n = 24
        occupied = sum(1 for k, _ in cells.values() if k != "empty")
        layout.label(text=f"{occupied}/{n} slots occupied")

        grid = layout.grid_flow(
            row_major=True, columns=8,
            even_columns=True, even_rows=True, align=True)

        DISPLAY_ORDER = [
            18, 8, 0, 1, 2, 3, 9, 19,
            20, 10, 4, 5, 6, 7, 11, 21,
            22, 16, 12, 13, 14, 15, 17, 23,
        ]

        for slot in DISPLAY_ORDER:
            kind, data = cells[slot]

            icon = None
            if kind == "original":
                icon = _get_original_icon(data["icon_file"])
            elif kind in ("entry", "pending"):
                folder = data["folder"]
                png = prefs.racers_dir() / folder / "icon.png"
                icon = _get_icon(folder, png) if png.is_file() else None

            if icon is not None:
                op = grid.operator("nfr.slot_click", text="",
                                   icon_value=icon.icon_id)
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

    def _draw_materials(self, context, layout):
        scene = context.scene
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            layout.label(text="Select a mesh object", icon="INFO")
            return

        m = obj.data

        top = layout.row(align=True)
        top.scale_y = 1.4
        toggle_icon = 'RADIOBUT_ON' if scene.nfr_ps1_render_state else 'RADIOBUT_OFF'
        top.operator(
            "nfr.ps1_toggle_render",
            text="Render: ON" if scene.nfr_ps1_render_state else "Render: OFF",
            icon=toggle_icon,
        )
        
        row = layout.row()
        row.prop(scene, "nfr_mat_search", icon="VIEWZOOM", text="Search Material")
        layout.separator()

        if not m.materials:
            layout.label(text="No materials on this mesh", icon="INFO")
            return

        search_term = scene.nfr_mat_search.lower().strip()
        mats = [mat for mat in m.materials if mat is not None and (not search_term or search_term in mat.name.lower())]
        total = len(mats)
        if total == 0:
            layout.label(text="No materials matched search", icon="INFO")
            return

        total_pages = max(1, (total + MAX_MATS_PER_PAGE - 1) // MAX_MATS_PER_PAGE)

        if state._mat_view_page < 1:
            state._mat_view_page = 1
        if state._mat_view_page > total_pages:
            state._mat_view_page = total_pages

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

            drop = box.row(align=True)
            drop.prop(mat, "nfr_racer_blend_mode", text="")

    def _draw_kart(self, context, layout):
        st = context.scene.kart_state
        scene = context.scene
        obj = context.active_object

        # 1. EDITOR SECTION
        box = layout.box()
        row = box.row()
        row.prop(scene, "nfr_kart_show_editor", text="", icon='TRIA_DOWN' if scene.nfr_kart_show_editor else 'TRIA_RIGHT', emboss=False)
        row.label(text="Kart Editor", icon="MESH_DATA")

        if scene.nfr_kart_show_editor:
            col = box.column(align=True)
            col.prop(st, "template_mode", text="Mode")
            col.prop(st, "template_option", text="Template")
            if st.template_mode == 'EDIT' and st.template_option in ('KART', 'KART_HI'):
                col.prop(st, "variant", text="Variant")

            col.separator()
            col.operator("nfr.kart_import_template", icon="IMPORT", text="Import Template")

        # If USER mode, end drawing here (just import)
        if st.template_mode == 'USER':
            return

        # 2. COLORS SECTION (The rest is only for EDIT mode)
        if st.is_imported:
            layout.separator()
            
            # Header
            hdr = layout.row()
            hdr.prop(scene, "nfr_kart_show_colors", text="", icon='TRIA_DOWN' if scene.nfr_kart_show_colors else 'TRIA_RIGHT', emboss=False)
            
            if st.template_option == 'HOVERCRAFT':
                hdr.label(text="Hovercraft Color (HSV)", icon="COLOR")
                if scene.nfr_kart_show_colors:
                    col = layout.column(align=True)
                    col.prop(st, "hover_hue", slider=True)
                    col.prop(st, "hover_saturation", slider=True)
                    col.prop(st, "hover_value", slider=True)
            else:
                hdr.label(text="Color Zones", icon="COLOR")
                if scene.nfr_kart_show_colors:
                    col = layout.column(align=True)
                    for z in st.zones:
                        col.prop(z, "color", text=z.display_name)

            if scene.nfr_kart_show_colors:
                layout.separator()
                layout.operator("nfr.kart_reset_colors", icon="LOOP_BACK")

            # 3. PRESET SECTION
            layout.separator()
            box = layout.box()
            row = box.row()
            row.prop(scene, "nfr_kart_show_preset", text="", icon='TRIA_DOWN' if scene.nfr_kart_show_preset else 'TRIA_RIGHT', emboss=False)
            row.label(text="Export Preset", icon="FILE_TICK")
            
            if scene.nfr_kart_show_preset:
                col = box.column(align=True)
                col.prop(st, "preset_name", text="Name")
                col.prop(st, "output_mode", text="Format")
                col.operator("nfr.kart_bake_and_export", icon="EXPORT")

    def _draw_presets(self, context, layout):
        prefs = _get_prefs(context)
        st = context.scene.kart_state

        root_str = getattr(prefs, "kart_presets_root", "") or ""
        if not root_str:
            warn = layout.box()
            warn.label(text="Set 'Kart presets folder' in", icon="ERROR")
            warn.label(text="addon preferences first")
            return

        root = Path(root_str)
        if not root.is_dir():
            warn = layout.box()
            warn.label(text="Folder not found:", icon="ERROR")    
            warn.label(text=root_str)
            return

        row = layout.row(align=True)
        row.label(text="Preset Browser", icon="FILE_FOLDER")      

        obj = context.active_object
        can_apply = (obj is not None and obj.type == 'MESH' and obj.racer.is_racer)
        if can_apply:
            layout.label(text=f"Target: {obj.name}", icon="OBJECT_DATA")
            layout.label(text=f"slug: {obj.racer.slug}")
        else:
            layout.label(text="Select a racer mesh to enable Apply", icon="INFO")

        layout.separator()
        box = layout.box()
        box.label(text="Filter Presets:", icon="FILTER")
        box.prop(st, "template_filter", text="Template")
        if st.template_filter in ('KART', 'KART_HI'):
            box.prop(st, "variant_filter", text="Variant")        
        layout.separator()

        from ..kart.templates import KART_TEMPLATES
        tpl_obj = KART_TEMPLATES.get(st.template_filter)

        if tpl_obj:
            var_key = st.variant_filter
            if var_key == 'GOLD': var_key = 'GOLD_PIPES'
            elif var_key == 'SILVER': var_key = 'SILVER_PIPES'    
            elif var_key == 'DEFAULT': var_key = 'DEFAULT'        

            variant_dir = tpl_obj["variant_dirs"].get(var_key, "")
        else:
            variant_dir = ""

        all_presets = scan_presets(root)
        items = all_presets.get(variant_dir, [])

        if not items:
            layout.label(text=f"No presets in '{variant_dir}/' yet.", icon="INFO")
            return

        total = len(items)
        total_pages = max(1, (total + MAX_PRESETS_PER_PAGE - 1) // MAX_PRESETS_PER_PAGE)
        current_page = max(1, min(st.preset_page, total_pages))   

        if total_pages > 1:
            prow = layout.row(align=True)
            left = prow.row(align=True)
            left.enabled = current_page > 1
            left.operator("nfr.kart_preset_prev_page", text="", icon="TRIA_LEFT")
            prow.label(text=f"Page {current_page} / {total_pages}  ({total} total)")
            right = prow.row(align=True)
            right.enabled = current_page < total_pages
            right.operator("nfr.kart_preset_next_page", text="", icon="TRIA_RIGHT")

        start = (current_page - 1) * MAX_PRESETS_PER_PAGE
        end = min(start + MAX_PRESETS_PER_PAGE, total)
        page_items = items[start:end]

        for name, path in page_items:
            row = layout.row(align=True)

            icon_key = f"__preset__{variant_dir}__{name}"
            png_files = list(path.glob("*.png"))
            icon = _get_icon(icon_key, png_files[0]) if png_files else None

            if icon is not None:
                row.template_icon(icon_value=icon.icon_id, scale=1.4)
            else:
                row.label(text="", icon="IMAGE_DATA")

            row.label(text=name)

            sub = row.row(align=True)
            sub.enabled = can_apply
            op = sub.operator("nfr.kart_apply_preset", text="Apply", icon="CHECKMARK")
            op.preset_dir = str(path)


    def _draw_anim(self, context, layout):
        # Trata de obtener el estado, sea anim_state o nfr_anim
        st = getattr(context.scene, "anim_state", None) or getattr(context.scene, "nfr_anim", None)
        
        if st is None:
            layout.label(text="Animation state not found", icon="ERROR")
            return
            
        box = layout.box()
        box.label(text="Animation clips", icon="ACTION")
        
        row = box.row(align=True)
        row.prop(st, "selected_clip", text="")
        row.operator("nfr.anim_jump_to_clip", text="", icon="PLAY")
        row.operator("nfr.anim_toggle_markers", text="", icon="MARKER")
        
        clip = st.selected_clip.lower()
        if clip:
            row = box.row(align=True)
            row.prop(st, f"{clip}_start", text="Start:")
            row.prop(st, f"{clip}_end", text="End:")
        
        layout.separator()
        
        box2 = layout.box()
        box2.label(text="Tools", icon="TOOL_SETTINGS")
        
        row = box2.row(align=True)
        row.operator("nfr.anim_mark_kart", text="Mark Kart", icon="OUTLINER_DATA_MESH")
        row.operator("nfr.anim_generate_test_shape_keys", text="Generate ShapeKeys", icon="SHAPEKEY_DATA")

    def _draw_dance(self, context, layout):
        scene = context.scene
        st = scene.nfr_dance
        obj = context.active_object

        layout.label(text="Custom Podium Dance", icon="ARMATURE_DATA")
        
        if obj and obj.type == 'MESH':
            layout.label(text=f"Mesh: {obj.name} ({len(obj.data.vertices)} verts)", icon="MESH_DATA")
        else:
            layout.label(text="Select the dance mesh first", icon="ERROR")
            return

        col = layout.column(align=True)
        col.prop(st, "slug", text="Slug")

        # --- TIMELINES ---
        layout.separator()
        row = layout.row()
        row.prop(scene, "nfr_dance_show_timelines", text="", icon='TRIA_DOWN' if scene.nfr_dance_show_timelines else 'TRIA_RIGHT', emboss=False)
        row.label(text="Timelines", icon="ARMATURE_DATA")
        
        if scene.nfr_dance_show_timelines:
            win_box = layout.box()
            win_box.label(text="Win (rank 0)", icon="TRIA_RIGHT")
            row = win_box.row()
            row.prop(st, "win_start", text="Start")
            row.prop(st, "win_end",   text="End")

            loose_box = layout.box()
            loose_box.label(text="Loose (rank 1-2)", icon="TRIA_RIGHT")
            row = loose_box.row()
            row.prop(st, "loose_start", text="Start")
            row.prop(st, "loose_end",   text="End")

        # --- PODIUM MUSIC ---
        layout.separator()
        row = layout.row()
        row.prop(scene, "nfr_dance_show_music", text="", icon='TRIA_DOWN' if scene.nfr_dance_show_music else 'TRIA_RIGHT', emboss=False)
        row.label(text="Podium Music", icon="SOUND")
        
        if scene.nfr_dance_show_music:
            music_box = layout.box()
            music_box.prop(st, "podium_music_path", text="WAV")
            row = music_box.row()
            row.operator("nfr.dance_build_music", text="Build Music Bank", icon="PLAY")

        # --- DANCE SFX ---
        layout.separator()
        row = layout.row()
        row.prop(scene, "nfr_dance_show_sfx", text="", icon='TRIA_DOWN' if scene.nfr_dance_show_sfx else 'TRIA_RIGHT', emboss=False)
        row.label(text="Dance SFX", icon="SPEAKER")
        
        if scene.nfr_dance_show_sfx:
            sfx_box = layout.box()
            sfx_box.label(text="Fires a WAV when the dance hits a frame.", icon="INFO")
            if not st.sfx_entries:
                sfx_box.label(text="(none — click Add SFX to create one)", icon="INFO")
            
            # FIX: Usar enumerate para el index, no find()
            for i, e in enumerate(st.sfx_entries):
                row = sfx_box.row()
                row.prop(e, "frame", text="")
                row.prop(e, "wav_path", text="")
                op = row.operator("nfr.dance_sfx_remove", text="", icon="X")
                op.index = i
            
            row = sfx_box.row()
            row.operator("nfr.dance_sfx_add", text="Add SFX", icon="ADD")
            row.operator("nfr.dance_build_sfx", text="Build Dance SFX", icon="PLAY")

        # --- EXPORTS ---
        layout.separator()
        row = layout.row(align=True)
        op = row.operator("nfr.dance_export", text="Export Win", icon="EXPORT")
        op.variant = 'WIN'
        op = row.operator("nfr.dance_export", text="Export Loose", icon="EXPORT")
        op.variant = 'LOOSE'
        
    def _draw_items(self, context, layout):
        scene = context.scene
        st = scene.nfr_mask
        obj = context.active_object

        layout.label(text="Custom Item Model", icon="MESH_DATA")
        layout.prop(st, "item_type", text="Item Type")
        
        if st.item_type == 'MASK':
            layout.label(text="Roster must say mask=custom_good | custom_bad.", icon="ERROR")

        is_icon_only = st.item_type in ('CLOCK', 'INVISIBILITY')

        if not is_icon_only:
            if obj and obj.type == 'MESH':
                layout.label(text=f"Mesh: {obj.name} ({len(obj.data.vertices)} verts)", icon="MESH_DATA")
            else:
                layout.label(text="Select the mesh first", icon="ERROR")
                return

        col = layout.column(align=True)
        col.prop(st, "slug", text="Slug")

        # --- HUD ICON ---
        layout.separator()
        row = layout.row()
        row.prop(scene, "nfr_items_show_icon", text="", icon='TRIA_DOWN' if scene.nfr_items_show_icon else 'TRIA_RIGHT', emboss=False)
        row.label(text="HUD Icon", icon="IMAGE_DATA")
        
        if scene.nfr_items_show_icon:
            icon_box = layout.box()
            if st.item_type == 'MASK':
                icon_box.label(text="Replaces the Aku/Uka face.", icon="INFO")
            elif is_icon_only:
                icon_box.label(text="Replaces the HUD icon.", icon="INFO")
            else:
                icon_box.label(text="Replaces the item's HUD icon.", icon="INFO")
            
            icon_box.prop(st, "icon_path", text="PNG")
            icon_box.operator("nfr.mask_export_icon", text="Export Icon", icon="PLAY")

        # --- MASK MUSIC ---
        if st.item_type == 'MASK':
            layout.separator()
            row = layout.row()
            row.prop(scene, "nfr_items_show_music", text="", icon='TRIA_DOWN' if scene.nfr_items_show_music else 'TRIA_RIGHT', emboss=False)
            row.label(text="Music", icon="SOUND")
            
            if scene.nfr_items_show_music:
                music_box = layout.box()
                music_box.label(text="WAV loop that plays while the mask is active.", icon="INFO")
                music_box.prop(st, "mask_music_path", text="WAV")
                music_box.operator("nfr.mask_build_music", text="Build Mask Music", icon="PLAY")

        # --- OBJECT ---
        layout.separator()
        row = layout.row()
        row.prop(scene, "nfr_items_show_object", text="", icon='TRIA_DOWN' if scene.nfr_items_show_object else 'TRIA_RIGHT', emboss=False)
        row.label(text="Object", icon="OBJECT_DATA")
        
        if scene.nfr_items_show_object:
            box = layout.box()
            if st.item_type == 'MASK':
                row = box.row(align=True)
                row.operator("nfr.mask_export", text="Export Mask", icon="FILE_TICK")
                row.operator("nfr.mask_export", text="Export Beam", icon="FILE_TICK")
            else:
                box.operator("nfr.mask_export", text="Export Item", icon="FILE_TICK")
                
    def _draw_sfx(self, context, layout):
        st = context.scene.nfr_sfx

        box = layout.box()
        box.label(text="Custom Kart SFX", icon="SPEAKER")
        box.label(text="Per-character SFX for kart events.")
        box.label(text="Encoded to VAG @ 11025 Hz, played on SPU.")
        box.label(text="Missing slots fall back to retail.")

        col = box.column(align=True)
        col.prop(st, "slug", text="Slug")

        from ..sfx.state import SFX_EVENTS
        events_box = box.box()
        events_box.label(text="Event SFX:")
        for event, label in SFX_EVENTS:
            row = events_box.row(align=True)
            row.label(text=f"{label}:")
            row.prop(st, f"wav_{event}", text="")

        row = box.row(align=True)
        row.scale_y = 1.4
        row.operator("nfr.sfx_build", icon="SOUND")
        row.operator("nfr.sfx_clear",
                     text="Clear SFX", icon="TRASH")

    def _draw_voices(self, context, layout):
        scene = context.scene
        st = scene.nfr_voices
        obj = context.active_object

        layout.label(text="Custom Voicelines", icon="SPEAKER")
        
        col = layout.column(align=True)
        col.prop(st, "slug", text="Slug")
        
        if st.slug:
            slug_dir = _get_prefs(context).racers_dir() / st.slug
            if slug_dir.is_dir():
                layout.label(text=f"Racer folder exists: {st.slug}", icon="CHECKMARK")
            else:
                layout.label(text=f"Racer folder not found: {st.slug}", icon="ERROR")

        # --- SOURCE FOLDER ---
        layout.separator()
        row = layout.row()
        row.prop(scene, "nfr_voices_show_source", text="", icon='TRIA_DOWN' if scene.nfr_voices_show_source else 'TRIA_RIGHT', emboss=False)
        row.label(text="Source Folder (Auto-detect)", icon="FILE_FOLDER")
        
        if scene.nfr_voices_show_source:
            src_box = layout.box()
            src_box.prop(st, "source_dir", text="")
            src_box.operator("nfr.voices_auto_detect", text="Auto-detect from folder", icon="FILE_REFRESH")

        # --- GAMEPLAY EVENTS ---
        layout.separator()
        row = layout.row()
        row.prop(scene, "nfr_voices_show_gameplay", text="", icon='TRIA_DOWN' if scene.nfr_voices_show_gameplay else 'TRIA_RIGHT', emboss=False)
        row.label(text="Gameplay Events", icon="SOUND")
        
        if scene.nfr_voices_show_gameplay:
            box = layout.box()
            # Robust loop that doesn't break if VOICE_EVENTS changes format
            for i, item in enumerate(VOICE_EVENTS):
                if i >= MENU_SPLIT_INDEX: break
                event = item[0] if isinstance(item, tuple) else item
                box.prop(st, event, text="")

        # --- MENU EVENTS ---
        layout.separator()
        row = layout.row()
        row.prop(scene, "nfr_voices_show_menu", text="", icon='TRIA_DOWN' if scene.nfr_voices_show_menu else 'TRIA_RIGHT', emboss=False)
        row.label(text="Menu Events", icon="SOUND")
        
        if scene.nfr_voices_show_menu:
            box = layout.box()
            # Robust loop
            for i, item in enumerate(VOICE_EVENTS):
                if i < MENU_SPLIT_INDEX: continue
                event = item[0] if isinstance(item, tuple) else item
                box.prop(st, event, text="")

        # --- BUILD BUTTON ---
        layout.separator()
        layout.operator("nfr.voices_build", text="Build Voice Banks", icon="PLAY")

    def _draw_levels(self, context, layout):
        st = context.scene.nfr_levels
        
        box = layout.box()
        box.label(text="Track Builder", icon="WORLD")
        col = box.column(align=True)
        col.prop(st, "lev_file", text=".LEV File")
        col.prop(st, "vrm_file", text=".VRM File")
        col.prop(st, "level_name", text="Name")
        col.prop(st, "music_file", text="Music WAV")
        
        col.separator()
        col.prop(st, "action_type", text="Mode")
        col.prop(st, "replace_target", text="Base / Target Track")
        
        layout.separator()
        box = layout.box()
        box.label(text="Manage", icon="FILE_FOLDER")
        
        row = box.row(align=True)
        row.operator("nfr.levels_build", icon="PLAY", text="Build Track")
        
        row = box.row(align=True)
        row.operator("nfr.levels_list", icon="FILE_REFRESH", text="List Tracks")
        row.operator("nfr.levels_delete", icon="TRASH", text="Delete")
        
        # COLLAPSIBLE LIST
        row = layout.row()
        icon = 'TRIA_DOWN' if st.show_tracks else 'TRIA_RIGHT'
        row.prop(st, "show_tracks", text="Installed Tracks", icon=icon, emboss=False)
        
        if st.show_tracks:
            box = layout.box()
            if st.list_output:
                col = box.column(align=True)
                for line in st.list_output.split("\n"):
                    col.label(text=line)
            else:
                box.label(text="Click 'List Tracks' to refresh.", icon="INFO")
                
        if st.last_status:
            layout.separator()
            icon = "ERROR" if "FAILED" in st.last_status else "CHECKMARK"
            layout.label(text=f"Status: {st.last_status}", icon=icon)


_CLASSES = (
    NFR_PT_Racer,
)

def register():
    for c in _CLASSES:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(_CLASSES):
        bpy.utils.unregister_class(c)

def _draw_adventure(layout, context):
    st = context.scene.nfr_adventure

    # ─── PACK SETUP ─────────────────────────────────
    box = layout.box()
    box.label(text="Garage Pack", icon='WORLD')
    row = box.row(align=True)
    row.prop(st, "pack_name", text="Name")
    row.prop(st, "slug", text="Slug")
    row = box.row(align=True)
    row.prop(st, "lev_file", text="LEV")
    row.prop(st, "vrm_file", text="VRM")

    # ─── CAMERA ─────────────────────────────────────
    box = layout.box()
    box.label(text="Camera (one per garage)", icon='CAMERA_DATA')
    row = box.row(align=True)
    row.operator("nfr.adventure_add_cam", text="Add Camera...", icon='ADD')
    row.operator("nfr.adventure_assign_cam", text="Get from Active Cam", icon='EYEDROPPER')
    if st.cam_captured:
        box.label(text=f"✓ Captured: X:{st.cam_x} Y:{st.cam_y} Z:{st.cam_z}", icon='CHECKMARK')
    else:
        box.label(text="⚠ Not captured — place a camera, then Get", icon='ERROR')

    # ─── SLOT EDITOR ────────────────────────────────
    box = layout.box()
    box.label(text="Slot Editor", icon='OUTLINER_OB_GROUP_INSTANCE')
    box.prop(st, "active_slot_idx", text="Active Slot")

    if st.active_slot_idx >= len(st.slots):
        box.label(text="Initializing slots...", icon='INFO')
        layout.separator()
        row = layout.row(); row.scale_y = 1.5
        row.operator("nfr.adventure_build", icon='EXPORT', text="BUILD GARAGE PACK")
        return

    slot = st.slots[st.active_slot_idx]
    sub = box.box()

    sub.prop(slot, "char_slug", text="Character Slug")
    sub.prop(slot, "idle_object", text="Idle/Character Object")
    sub.prop(slot, "kart_object", text="Kart Object (optional)")

    sub.separator()
    sub.label(text="Animations", icon='PLAY')
    row = sub.row(align=True)
    row.label(text="Idle:")
    row.prop(slot, "idle_anim", text="Anim")
    row.prop(slot, "idle_start", text="Start")
    row.prop(slot, "idle_end", text="End")
    row.prop(slot, "idle_loop", text="Loop")

    row = sub.row(align=True)
    row.label(text="Select:")
    row.prop(slot, "select_anim", text="Anim")
    row.prop(slot, "select_start", text="Start")
    row.prop(slot, "select_end", text="End")
    row.prop(slot, "select_loop", text="Loop")

    # Position (read-only, auto-captured)
    sub.separator()
    row = sub.row(align=True)
    row.label(text=f"Position: X:{slot.pos_x} Y:{slot.pos_y} Z:{slot.pos_z} Rot:{slot.pos_rot}", icon='INFO')

    # Export
    row = sub.row()
    row.scale_y = 1.2
    row.operator("nfr.adventure_export_assets", text=f"📤 Export Garage Model for S{st.active_slot_idx}", icon='EXPORT')

    # ─── AUDIO (per slot) ───────────────────────────
    box = layout.box()
    box.label(text=f"Audio for S{st.active_slot_idx} ({slot.char_slug or 'unset'})", icon='SOUND')
    box.prop(slot, "ambient_wav", text="Ambient WAV (loop)")

    sub = box.box()
    sub.label(text="Per-frame SFX:")
    if len(slot.sfx_entries) == 0:
        sub.label(text="(none — click Add SFX)", icon='INFO')
    for e_idx, e in enumerate(slot.sfx_entries):
        row = sub.row(align=True)
        row.prop(e, "frame", text="F")
        row.prop(e, "wav_path", text="")
        op = row.operator("nfr.adventure_sfx_remove", text="", icon='X')
        op.index = e_idx
    row = sub.row(align=True)
    row.operator("nfr.adventure_sfx_add", text="Add SFX", icon='ADD')
    row.operator("nfr.adventure_build_audio", text=f"🔊 Build Audio for S{st.active_slot_idx}", icon='SOUND')

    # ─── BUILD ──────────────────────────────────────
    layout.separator()
    row = layout.row()
    row.scale_y = 1.5
    row.operator("nfr.adventure_build", icon='EXPORT', text="BUILD GARAGE PACK")
