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

DEFAULT_REPO   = ""
DEFAULT_PYTHON = ""

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
    ('LEVELS', 'Levels', 'Custom levels and adventure packs'),
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
        ('LEVELS',    'Tracks',    'Custom track builder'),
        ('ADVENTURE', 'Garage', 'Custom Adventure Garages + Audio + Karts'),
    ],
}

UI_MODE_OF_TAB = {
    tab_id: mode
    for mode, tabs in UI_TABS_BY_MODE.items()
    for tab_id, _label, _desc in tabs
}
RETAIL_CHARACTERS = [
    (0, "Crash", "crash"), (1, "Cortex", "cortex"), (2, "Tiny", "tiny"), (3, "Coco", "coco"),
    (4, "N. Gin", "n_gin"), (5, "Dingodile", "dingo"), (6, "Polar", "polar"), (7, "Pura", "pura"),
    (8, "Pinstripe", "pinstripe"), (9, "Papu Papu", "papu"), (10, "Ripper Roo", "roo"), (11, "Komodo Joe", "joe"),
    (12, "N. Tropy", "ntropy"), (13, "Penta Penguin", "penta"), (14, "Fake Crash", "fake"), (15, "Oxide", "oxide")
]
