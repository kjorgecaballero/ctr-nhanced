# =========================================================================
# MODULE: constants
# =========================================================================
"""Static constants shared across the addon.

No bpy imports, no side effects. Safe to import from anywhere in the
package.
"""

ADDON_ID = __package__  # "ctr_racer" when installed as a package


ENGINES = [
    ("SPEED",    "Speed",    ""),
    ("BALANCED", "Balanced", ""),
    ("ACCEL",    "Accel",    ""),
    ("TURN",     "Turn",     ""),
]
_ENGINE_SET = {"SPEED", "BALANCED", "ACCEL", "TURN"}

BLEND_MODES = [
    ("half",     "Half Transparent",     "50% transparency (default)"),
    ("add",      "Additive",             "Additive blending"),
    ("subtract", "Subtractive",          "Subtractive blending"),
    ("add_25",   "Additive Translucent", "Additive at 25%"),
]
_BLEND_MODE_SET = {m[0] for m in BLEND_MODES}

DEFAULT_REPO   = r"C:\Users\Kevin\Desktop\Kevin\CTR\native_fork\nhanced"
DEFAULT_PYTHON = r"C:\Users\Kevin\AppData\Local\Programs\Python\Python312\python.exe"

MAX_PAGES = 8
MAX_MATS_PER_PAGE = 10
MAX_PRESETS_PER_PAGE = 10

# =========================================================================
# UI modes: 4 top-level groups. Panel shows 1 row:
#   [Setup] [Kart] [Custom] [Levels]     [sub-tab dropdown]
# # NFR_UI_SINGLE_BAR_V1
# =========================================================================
UI_MODES = [
    ('SETUP',  'Setup',  'Racer settings, slot roster, materials'),
    ('KART',   'Kart',   'Kart editor, presets, animation clips'),
    ('CUSTOM', 'Custom', 'Dance, items, SFX, voices'),
    ('LEVELS', 'Levels', 'Custom level builder'),
]

UI_TABS_BY_MODE = {
    'SETUP':  [
        ('SETTINGS',  'Settings',  'Racer settings and dev tools'),
        ('SLOTS',     'Slots',     'Page/slot grid and roster'),
        ('MATERIALS', 'Materials', 'Per-material render settings'),
    ],
    'KART':   [
        ('KART',    'Kart',    'Kart template editor'),
        ('PRESETS', 'Presets', 'Apply saved kart presets'),
    ],
    'CUSTOM': [
        ('ANIM',   'Anim',   'Animation clips and markers'),
        ('DANCE',  'Dance',  'Podium dance + music + SFX'),
        ('ITEMS',  'Items',  'Custom item models + icons'),
        ('SFX',    'SFX',    'Custom kart SFX'),
        ('VOICES', 'Voices', 'Custom voiceline WAVs'),
    ],
    'LEVELS': [
        ('LEVELS', 'Tracks', 'Custom track builder'),
    ],
}

UI_MODE_OF_TAB = {
    tab_id: mode
    for mode, tabs in UI_TABS_BY_MODE.items()
    for tab_id, _label, _desc in tabs
}
