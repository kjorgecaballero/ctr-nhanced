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

        for row_items in (
            (('SETTINGS', 'Settings'), ('SLOTS', 'Slots'),
             ('MATERIALS', 'Materials')),
            (('KART', 'Kart'), ('PRESETS', 'Presets'), ('ANIM', 'Anim')),
            (('DANCE', 'Dance'), ('VOICES', 'Voices')),
        ):
            row = layout.row(align=True)
            row.scale_y = 1.3
            for tab_id, label in row_items:
                row.prop_enum(scene, "nfr_ui_tab", tab_id, text=label)

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
        elif tab == 'VOICES':
            self._draw_voices(context, layout)

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
                    r2 = box.row()
                    if level == "ERROR":
                        r2.alert = True
                    op = r2.operator(
                        "nfr.show_issue",
                        text=short,
                        icon='CANCEL' if level == "ERROR" else 'ERROR',
                    )
                    op.issue_text = long

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

        col.separator()
        col.prop(r, "long_name")
        col.prop(r, "short_name")

        col.separator()
        color_row = col.row(align=True)
        color_row.label(text="Minimap Color:")
        color_row.prop(r, "color", text="")
        col.prop(r, "icon_path")

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

        n = 18
        occupied = sum(1 for k, _ in cells.values() if k != "empty")
        layout.label(text=f"{occupied}/{n} slots occupied")

        grid = layout.grid_flow(
            row_major=True, columns=6,
            even_columns=True, even_rows=True, align=True)

        DISPLAY_ORDER = [
            0, 1, 2, 3, 4, 5,
            6, 7, 8, 9, 10, 11,
            16, 12, 13, 14, 15, 17,
        ]

        for slot in DISPLAY_ORDER:
            kind, data = cells[slot]

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
        prefs = _get_prefs(context)

        layout.label(text="Kart Editor", icon="MESH_DATA")

        col = layout.column(align=True)
        col.prop(st, "template_option")
        col.prop(st, "variant")

        row = col.row(align=True)
        row.scale_y = 1.3
        row.operator("nfr.kart_import_template", icon="IMPORT")

        if not st.is_imported:
            layout.separator()
            layout.label(text="Press 'Import Template' to spawn the kart",
                         icon="INFO")
            return

        layout.separator()

        reset_row = layout.row(align=True)
        reset_row.scale_y = 1.2
        reset_row.operator("nfr.kart_reset_colors", icon="LOOP_BACK")

        box = layout.box()
        box.label(text="Colors", icon="COLOR")
        for z in st.zones:
            r = box.row()
            split = r.split(factor=0.4)
            split.label(text=z.display_name)
            split.prop(z, "color", text="")

        layout.separator()
        layout.label(text="Save Preset:", icon="FILE_TICK")
        layout.prop(st, "preset_name", text="")

        root_str = getattr(prefs, "kart_presets_root", "") or ""
        if not root_str:
            warn = layout.box()
            warn.label(text="Set 'Kart presets folder' in",
                       icon="ERROR")
            warn.label(text="addon preferences first")
        else:
            layout.label(text=f"→ {root_str}", icon="FILE_FOLDER")

        bake_row = layout.row(align=True)
        bake_row.scale_y = 1.4
        bake_row.enabled = bool(root_str) and bool(st.preset_name.strip())
        bake_row.operator("nfr.kart_bake_and_export",
                          text="Bake & Export", icon="RENDER_STILL")

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
        row.operator("nfr.kart_open_presets_folder", text="", icon="FILEBROWSER")

        obj = context.active_object
        can_apply = (obj is not None and obj.type == 'MESH'
                     and obj.racer.is_racer)
        if can_apply:
            layout.label(text=f"Target: {obj.name}", icon="OBJECT_DATA")
            layout.label(text=f"slug: {obj.racer.slug}")
        else:
            layout.label(text="Select a racer mesh to enable Apply",
                         icon="INFO")

        layout.separator()
        filter_row = layout.row(align=True)
        filter_row.scale_y = 1.3
        filter_row.prop(st, "preset_filter", expand=True)
        layout.separator()

        filter_to_dir = {'KART': 'kart', 'GOLD': 'gold', 'SILVER': 'silver'}
        variant_dir = filter_to_dir.get(st.preset_filter, 'kart')
        all_presets = scan_presets(root)
        items = all_presets.get(variant_dir, [])

        if not items:
            layout.label(text=f"No presets in '{variant_dir}/' yet.",
                         icon="INFO")
            return

        total = len(items)
        total_pages = max(1, (total + MAX_PRESETS_PER_PAGE - 1) // MAX_PRESETS_PER_PAGE)
        if st.preset_page < 1:
            st.preset_page = 1
        if st.preset_page > total_pages:
            st.preset_page = total_pages

        if total_pages > 1:
            prow = layout.row(align=True)
            left = prow.row(align=True)
            left.enabled = st.preset_page > 1
            left.operator("nfr.kart_preset_prev_page", text="", icon="TRIA_LEFT")
            prow.label(text=f"Page {st.preset_page} / {total_pages}  ({total} total)")
            right = prow.row(align=True)
            right.enabled = st.preset_page < total_pages
            right.operator("nfr.kart_preset_next_page", text="", icon="TRIA_RIGHT")

        start = (st.preset_page - 1) * MAX_PRESETS_PER_PAGE
        end = min(start + MAX_PRESETS_PER_PAGE, total)
        page_items = items[start:end]

        for name, path in page_items:
            row = layout.row(align=True)

            icon_png = path / "kart_00.png"
            icon_key = f"__preset__{variant_dir}__{name}"
            icon = _get_icon(icon_key, icon_png) if icon_png.is_file() else None
            if icon is not None:
                row.template_icon(icon_value=icon.icon_id, scale=1.4)
            else:
                row.label(text="", icon="IMAGE_DATA")

            row.label(text=name)

            sub = row.row(align=True)
            sub.enabled = can_apply
            op = sub.operator("nfr.kart_apply_preset",
                              text="Apply", icon="CHECKMARK")
            op.preset_dir = str(path)

    def _draw_anim(self, context, layout):
        scene = context.scene
        st = scene.nfr_anim

        request_sync_from_prefs(scene)

        layout.label(text="Animation clips", icon="ACTION")

        clip = st.selected_clip

        row = layout.row(align=True)
        row.scale_y = 1.4
        row.prop(st, "selected_clip", text="")
        row.prop(st, f"{clip}_start", text="Start:")
        row.prop(st, f"{clip}_end", text="End:")
        row.operator("nfr.anim_jump_to_clip", text="", icon="PLAY")
        row.operator("nfr.anim_toggle_markers", text="", icon="MARKER")

        # Test setup (both on one row)
        layout.separator()
        row = layout.row(align=True)
        row.operator("nfr.anim_mark_kart",
                     text="Mark Kart",
                     icon="GROUP_VERTEX")
        row.operator("nfr.anim_generate_test_shape_keys",
                     text="Generate ShapeKeys",
                     icon="SHAPEKEY_DATA")

    def _draw_dance(self, context, layout):
        st = context.scene.nfr_dance

        layout.label(text="Custom Podium Dance", icon="ARMATURE_DATA")
        layout.label(text="Same mesh, two timelines: Win (rank 0) and",
                     icon="INFO")
        layout.label(text="Loose (rank 1-2). Shared Sentinel textures.")

        layout.separator()

        obj = context.active_object
        if obj is None or obj.type != "MESH":
            layout.label(text="Select the dance mesh first", icon="ERROR")
        else:
            layout.label(text=f"Mesh: {obj.name} "
                              f"({len(obj.data.vertices)} verts)",
                         icon="MESH_DATA")

        col = layout.column(align=True)
        col.prop(st, "slug", text="Slug")

        # --- Win (rank 0) ---
        layout.separator()
        win_box = layout.box()
        win_box.label(text="Win (rank 0)", icon="TRIA_RIGHT")
        row = win_box.row(align=True)
        row.prop(st, "win_start", text="Start")
        row.prop(st, "win_end",   text="End")

        # --- Loose (rank 1-2) ---
        loose_box = layout.box()
        loose_box.label(text="Loose (rank 1-2)", icon="TRIA_RIGHT")
        row = loose_box.row(align=True)
        row.prop(st, "loose_start", text="Start")
        row.prop(st, "loose_end",   text="End")

        # --- Podium Music (rank 0) ---
        music_box = layout.box()
        music_box.label(text="Podium Music (rank 0)", icon="SOUND")
        music_box.prop(st, "podium_music_path", text="WAV")
        row = music_box.row(align=True)
        row.scale_y = 1.3
        row.enabled = bool(st.slug)
        row.operator("nfr.dance_build_music",
                     text="Build Music Bank", icon="PLAY")

        # --- Dance SFX (per-frame) ---
        sfx_box = layout.box()
        sfx_box.label(text="Dance SFX (per-frame)", icon="SPEAKER")
        sfx_box.label(text="Fires a WAV when the dance hits a frame.",
                      icon="INFO")
        sfx_box.label(text="Frames are 0-based within the dance clip.")

        if len(st.sfx_entries) == 0:
            sfx_box.label(text="(none — click Add SFX to create one)",
                          icon="INFO")
        else:
            for i, e in enumerate(st.sfx_entries):
                row = sfx_box.row(align=True)
                row.prop(e, "frame", text="")
                row.prop(e, "wav_path", text="")
                op = row.operator("nfr.dance_sfx_remove",
                                  text="", icon="X")
                op.index = i

        row = sfx_box.row(align=True)
        row.scale_y = 1.2
        row.enabled = bool(st.slug)
        row.operator("nfr.dance_sfx_add", text="Add SFX", icon="ADD")
        row.operator("nfr.dance_build_sfx",
                     text="Build Dance SFX", icon="PLAY")

        # --- Actions ---
        layout.separator()
        row = layout.row(align=True)
        row.scale_y = 1.3
        op = row.operator("nfr.dance_export", text="Export Win", icon="EXPORT")
        op.variant = 'WIN'
        op = row.operator("nfr.dance_export", text="Export Loose")
        op.variant = 'LOOSE'

        row = layout.row(align=True)
        row.scale_y = 1.4
        op = row.operator("nfr.dance_export",
                          text="Export Both", icon="DUPLICATE")
        op.variant = 'BOTH'

    def _draw_voices(self, context, layout):
        st = context.scene.nfr_voices
        prefs = _get_prefs(context)

        layout.label(text="Custom Voicelines", icon="SPEAKER")
        layout.label(text="Pick WAVs per event. They are copied to",
                     icon="INFO")
        layout.label(text="<slug>/voices/<event>.wav, then the pipeline")
        layout.label(text="regenerates ENG.XNF + S18.XA+ sidecars.")

        layout.separator()

        # --- Voice bank freshness (VOICELINES-ROSTER-FINGERPRINT) ---
        repo_root = Path(DEFAULT_REPO)
        pstatus, pdata = _pipeline_status(repo_root)
        if pstatus == "missing":
            warn = layout.row()
            warn.alert = True
            warn.label(text="Voice banks never built.", icon="ERROR")
            layout.label(text="Click Build Voice Banks to generate them.")
        elif pstatus == "stale":
            warn = layout.row()
            warn.alert = True
            warn.label(text="Voice banks are STALE (roster changed).",
                       icon="ERROR")
            layout.label(text="Click Build Voice Banks to regenerate.")
        elif pstatus == "stale_layout":
            warn = layout.row()
            warn.alert = True
            warn.label(text="Voice banks use the OLD event layout.",
                       icon="ERROR")
            layout.label(text="Click Build Voice Banks to regenerate.")
        elif pstatus == "fresh" and pdata is not None:
            n_banks = pdata.get("banks_written", "?")
            gen = pdata.get("generated_at", "?")
            layout.label(text=f"Voice banks up to date "
                              f"({n_banks} banks, {gen}).",
                         icon="CHECKMARK")
        # 'no_roster' -> silent

        layout.separator()

        active_racer = _active_racer(context)
        active_slug = active_racer.slug if active_racer else None

        col = layout.column(align=True)
        col.prop(st, "slug", text="Slug")

        slug = (st.slug or "").strip()
        if slug:
            slug_dir = prefs.racers_dir() / slug
            if slug_dir.is_dir():
                layout.label(text=f"Racer folder exists: {slug}",
                             icon="CHECKMARK")
            else:
                layout.label(text=f"Racer folder not found: {slug}",
                             icon="ERROR")
        elif active_slug:
            layout.label(text=f"Active racer: {active_slug}",
                         icon="INFO")

        # Source folder: pick any folder on disk with the source WAVs.
        src_box = layout.box()
        src_box.label(text="Source Folder", icon="FILE_FOLDER")
        src_box.prop(st, "source_dir", text="")
        row = src_box.row(align=True)
        row.scale_y = 1.3
        src_str = (st.source_dir or "").strip()
        row.enabled = bool(src_str) and Path(bpy.path.abspath(src_str)).is_dir()
        row.operator("nfr.voices_auto_detect",
                     text="Auto-detect from folder", icon="FILE_REFRESH")

        layout.separator()

        box = layout.box()
        box.label(text="Gameplay Events", icon="SOUND")
        for event, label, _desc in VOICE_EVENTS[:MENU_SPLIT_INDEX]:
            row = box.row(align=True)
            row.label(text=f"{label}:")
            row.prop(st, event, text="")

        box = layout.box()
        box.label(text="Menu Events", icon="SOUND")
        for event, label, _desc in VOICE_EVENTS[MENU_SPLIT_INDEX:]:
            row = box.row(align=True)
            row.label(text=f"{label}:")
            row.prop(st, event, text="")

        layout.separator()
        row = layout.row(align=True)
        row.scale_y = 1.4
        row.enabled = bool(slug)
        row.operator("nfr.voices_build",
                     text="Build Voice Banks", icon="PLAY")


_classes = (NFR_PT_Racer,)


def register():
    for c in _classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)