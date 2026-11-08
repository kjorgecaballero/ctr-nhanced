# =========================================================================
# MODULE: render — props
# =========================================================================
"""Registration of Scene and Material properties used by the PS1 render.

Owns the registration/unregistration of:
  - Scene.nfr_ui_tab (panel sub-tab selector)
  - Scene.nfr_ps1_* (render state and shadow snapshot)
  - Material.nfr_ps1_* (per-material PS1 settings)
  - Material.nfr_racer_blend_mode (racer blend mode enum, mirrors the
    "blend_mode" custom prop)

Owns the two update callbacks (_nfr_update_ps1_blend_mode,
_nfr_mat_blend_mode_update).

Note: Scene.nfr_ui_tab is semantically UI, but lives here for now to
avoid a circular import. It may move to ui/ in a later batch.
"""
import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from ..constants import BLEND_MODES, _BLEND_MODE_SET, UI_MODES, UI_TABS_BY_MODE
from .material_setup import NFR_PS1MaterialFactory


def _nfr_update_ps1_blend_mode(self, context):
    if getattr(self, 'nfr_ps1_blend_mode', 'NONE') == 'NONE':
        return
    cur_bf = getattr(self, 'nfr_ps1_show_backface', False)
    if context.scene.nfr_ps1_render_active:
        try:
            setup = NFR_PS1MaterialFactory.get_material_setup(self, self.nfr_ps1_blend_mode)
            setup.apply_setup()
            self.nfr_ps1_show_backface = cur_bf
        except Exception as e:
            print(f"[NFR] update blend mode error on '{self.name}': {e}")
    else:
        self.nfr_ps1_last_active_mode = self.nfr_ps1_blend_mode
        self.nfr_ps1_show_backface = cur_bf


def _nfr_mat_blend_mode_update(self, context):
    v = getattr(self, "nfr_racer_blend_mode", "half")
    if v not in _BLEND_MODE_SET:
        return
    current = self.get("blend_mode", "half")
    if current != v:
        self["blend_mode"] = v


# NFR_UI_SINGLE_BAR_V1
def _nfr_ui_mode_update(self, context):
    """Jump nfr_ui_tab to the first sub-tab of the clicked mode."""
    tabs = UI_TABS_BY_MODE.get(self.nfr_ui_mode, [])
    if not tabs:
        return
    valid_ids = [t[0] for t in tabs]
    if self.nfr_ui_tab not in valid_ids:
        self.nfr_ui_tab = valid_ids[0]


# NFR_UI_SINGLE_DROPDOWN_V1
class NFR_MT_ui_tab(bpy.types.Menu):
    bl_label = "Select Tab"
    bl_idname = "NFR_MT_ui_tab"

    def draw(self, context):
        try:
            scene = context.scene
            for mode_id, mode_label, _mode_desc in UI_MODES:
                self.layout.label(text=mode_label, icon='DOT')
                for tab_id, label, _desc in UI_TABS_BY_MODE.get(mode_id, []):
                    op = self.layout.operator(
                        "nfr.set_ui_tab",
                        text="    " + label,
                        icon='CHECKMARK' if scene.nfr_ui_tab == tab_id else 'NONE',
                    )
                    op.tab_id = tab_id
                self.layout.separator()
        except Exception as e:
            print(f"[NFR] menu draw failed: {e}")
            self.layout.label(text="(menu error)")


class NFR_OT_set_ui_tab(bpy.types.Operator):
    bl_description = "Change the current UI tab"
    bl_idname = "nfr.set_ui_tab"
    bl_label = "Set UI Tab"
    bl_options = {'INTERNAL'}

    tab_id: bpy.props.StringProperty()

    def execute(self, context):
        if self.tab_id:
            context.scene.nfr_ui_tab = self.tab_id
        return {'FINISHED'}


_UI_MENU_CLASSES = (NFR_MT_ui_tab, NFR_OT_set_ui_tab)


def register():
    # UI sub-tab
    bpy.types.Scene.nfr_ui_tab = EnumProperty(
        name="Tab",
        description="Section to display in the CTR Racer panel",
        items=[
            ('SETTINGS',  "Settings",  "Racer settings and dev tools"),
            ('SLOTS',     "Slots",     "Page/slot grid and roster"),
            ('MATERIALS', "Materials", "Per-material render settings"),
            ('KART',      "Kart",      "Kart template editor"),
            ('PRESETS',   "Presets",   "Apply saved kart presets to racers"),
            ('ANIM',      "Anim",      "Animation clips and timeline markers"),
            ('DANCE',     "Dance",     "Custom podium dance export"),
            ('ITEMS',     "Items",     "Custom item models + icons (mask, missile, bomb)"),
            ('SFX',       "SFX",       "Custom kart SFX (boost, weapons, etc.)"),
            ('VOICES',    "Voices",    "Custom voiceline WAV export"),
            ('LEVELS', 'Levels', 'Custom level editor'),
            ('ADVENTURE', 'Adventure', ''),
        ],
        default='SETTINGS',
    )

    bpy.types.Scene.nfr_ui_mode = EnumProperty(
        name="Mode",
        description="Top-level panel section",
        items=[(mid, label, desc) for mid, label, desc in UI_MODES],
        default='SETUP',
        update=_nfr_ui_mode_update,
    )
    for _cls in _UI_MENU_CLASSES:
        bpy.utils.register_class(_cls)

    # Kart UX # NFR_KART_UX_V1
    bpy.types.Scene.nfr_mat_search = StringProperty(name="Search", default="")
    bpy.types.Scene.nfr_kart_show_editor = BoolProperty(name="Show Editor", default=True)
    bpy.types.Scene.nfr_kart_show_colors = BoolProperty(name="Show Colors", default=True)
    bpy.types.Scene.nfr_kart_show_preset = BoolProperty(name="Show Preset", default=True)
    bpy.types.Scene.nfr_dance_show_timelines = BoolProperty(name="Show Timelines", default=True)
    bpy.types.Scene.nfr_dance_show_music = BoolProperty(name="Show Music", default=False)
    bpy.types.Scene.nfr_dance_show_sfx = BoolProperty(name="Show SFX", default=False)
    bpy.types.Scene.nfr_items_show_icon = BoolProperty(name="Show Icon", default=True)
    bpy.types.Scene.nfr_items_show_music = BoolProperty(name="Show Music", default=True)
    bpy.types.Scene.nfr_items_show_object = BoolProperty(name="Show Object", default=True)
    bpy.types.Scene.nfr_voices_show_source = BoolProperty(name="Show Source", default=True)
    bpy.types.Scene.nfr_voices_show_gameplay = BoolProperty(name="Show Gameplay", default=True)
    bpy.types.Scene.nfr_voices_show_menu = BoolProperty(name="Show Menu", default=True)

    # Scene
    bpy.types.Scene.nfr_ps1_render_state = BoolProperty(default=False)
    bpy.types.Scene.nfr_ps1_render_active = BoolProperty(default=False)
    bpy.types.Scene.nfr_ps1_prev_shadow_state = BoolProperty(default=True)
    bpy.types.Scene.nfr_ps1_blend_mode = EnumProperty(
        items=[
            ('HALF_TRANSPARENT', "Half Transparent", ""),
            ('ADDITIVE', "Additive", ""),
            ('SUBTRACTIVE', "Subtractive", ""),
            ('ADDITIVE_TRANSLUCENT', "Additive Translucent", ""),
        ],
        default='HALF_TRANSPARENT',
    )

    # Material — PS1 render
    bpy.types.Material.nfr_ps1_blend_mode = EnumProperty(
        items=[
            ('NONE', "None", ""),
            ('ADDITIVE', "Additive", ""),
            ('SUBTRACTIVE', "Subtractive", ""),
            ('HALF_TRANSPARENT', "Half Transparent", ""),
            ('ADDITIVE_TRANSLUCENT', "Additive Translucent", ""),
        ],
        default='NONE',
        update=_nfr_update_ps1_blend_mode,
    )
    bpy.types.Material.nfr_ps1_last_active_mode = EnumProperty(
        items=[
            ('NONE', "None", ""),
            ('ADDITIVE', "Additive", ""),
            ('SUBTRACTIVE', "Subtractive", ""),
            ('HALF_TRANSPARENT', "Half Transparent", ""),
            ('ADDITIVE_TRANSLUCENT', "Additive Translucent", ""),
        ],
        default='NONE',
    )
    bpy.types.Material.nfr_ps1_show_backface = BoolProperty(default=False)
    bpy.types.Material.nfr_ps1_blend_method_override = EnumProperty(
        items=[
            ('AUTO', "Auto", ""),
            ('OPAQUE', "Opaque", ""),
            ('CLIP', "Clip", ""),
            ('HASHED', "Hashed", ""),
            ('BLEND', "Blend", ""),
        ],
        default='AUTO',
    )
    bpy.types.Material.nfr_ps1_transparency_overlap_mode = EnumProperty(
        items=[
            ('DEFAULT', "Default", ""),
            ('MANUAL', "Manual", ""),
        ],
        default='DEFAULT',
    )
    bpy.types.Material.nfr_ps1_transparency_overlap_manual = BoolProperty(
        default=True,
    )

    # Material — racer blend mode
    bpy.types.Material.nfr_racer_blend_mode = EnumProperty(
        name="Blend Mode",
        description="Per-material blend mode forwarded to source_mesh.json",
        items=BLEND_MODES,
        default="half",
        update=_nfr_mat_blend_mode_update,
    )


def unregister():
    for _cls in reversed(_UI_MENU_CLASSES):
        bpy.utils.unregister_class(_cls)
    del bpy.types.Scene.nfr_ui_mode
    del bpy.types.Scene.nfr_ui_tab
    del bpy.types.Scene.nfr_mat_search
    del bpy.types.Scene.nfr_kart_show_editor
    del bpy.types.Scene.nfr_kart_show_colors
    del bpy.types.Scene.nfr_kart_show_preset
    del bpy.types.Scene.nfr_dance_show_timelines
    del bpy.types.Scene.nfr_dance_show_music
    del bpy.types.Scene.nfr_dance_show_sfx
    del bpy.types.Scene.nfr_items_show_icon
    del bpy.types.Scene.nfr_items_show_music
    del bpy.types.Scene.nfr_items_show_object
    del bpy.types.Scene.nfr_voices_show_source
    del bpy.types.Scene.nfr_voices_show_gameplay
    del bpy.types.Scene.nfr_voices_show_menu
    del bpy.types.Scene.nfr_ps1_render_state
    del bpy.types.Scene.nfr_ps1_render_active
    del bpy.types.Scene.nfr_ps1_prev_shadow_state
    del bpy.types.Scene.nfr_ps1_blend_mode
    del bpy.types.Material.nfr_ps1_blend_mode
    del bpy.types.Material.nfr_ps1_last_active_mode
    del bpy.types.Material.nfr_ps1_show_backface
    del bpy.types.Material.nfr_ps1_blend_method_override
    del bpy.types.Material.nfr_ps1_transparency_overlap_mode
    del bpy.types.Material.nfr_ps1_transparency_overlap_manual
    del bpy.types.Material.nfr_racer_blend_mode
