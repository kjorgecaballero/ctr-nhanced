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
from bpy.props import BoolProperty, EnumProperty

from ..constants import BLEND_MODES, _BLEND_MODE_SET
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
            ('MASK',      "Mask",      "Custom mask model + beam export"),
            ('SFX',       "SFX",       "Custom kart SFX (boost, weapons, etc.)"),
            ('SFX',       "SFX",       "Custom kart SFX (boost, weapons, etc.)"),
            ('VOICES',    "Voices",    "Custom voiceline WAV export"),
        ],
        default='SETTINGS',
    )

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
    del bpy.types.Scene.nfr_ui_tab
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