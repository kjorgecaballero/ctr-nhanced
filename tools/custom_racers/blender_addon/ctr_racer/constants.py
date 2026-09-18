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