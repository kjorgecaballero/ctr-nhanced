# =========================================================================
# MODULE: state
# =========================================================================
"""Session-scoped UI state.

These are module-level globals, not Blender properties. They reset
when the addon is reloaded. Mutated from operators and read from the
panel; consumers use the `state` module object (e.g.
`state._slot_view_page`), not `from .state import _slot_view_page`.

No bpy imports, no side effects.
"""

# Slots tab: currently displayed page (1..MAX_PAGES)
_slot_view_page = 1

# Slots tab: currently selected cell for the detail box, -1 = none
_slot_sel_page = -1
_slot_sel_slot = -1

# Materials tab: currently displayed page (1..total_pages)
_mat_view_page = 1

# Settings tab: whether the Issues box is expanded.
# Default False so the panel stays uncluttered. Toggled by
# NFR_OT_ToggleValidationDetails. Does NOT re-run validation — that
# is what the [check] Validate button is for.
_validation_show_details = False