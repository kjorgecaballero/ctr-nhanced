# =========================================================================
# MODULE: kart — templates
# =========================================================================
"""Static definitions of the bundled kart templates."""

KART_TEMPLATES = {
    "KART": {
        "display_name":    "Kart",
        "fbx_name":        "kart_template.fbx",
        "material_prefix": "template",
        "variant_textures": {
            "DEFAULT": {
                "atlas":  "template01.png",
                "pipes":  "template02.png",
                "extra1": "template06.png",
                "extra2": "template07.png",
            },
            "GOLD_PIPES": {
                "atlas":  "template05.png",
                "pipes":  "template03.png",
                "extra1": "template06.png",
                "extra2": "template07.png",
            },
            "SILVER_PIPES": {
                "atlas":  "template05.png",
                "pipes":  "template04.png",
                "extra1": "template06.png",
                "extra2": "template07.png",
            },
        },
        "zones": [
            ("Body",    "atlas"),
            ("Pipes",   "pipes"),
            ("Extra 1", "extra1"),
            ("Extra 2", "extra2"),
        ],
        # Fase 2 -- bake + cut + save.
        # bake_size = (width, height). All Kart template PNGs are 112x107.
        "bake_size": (112, 107),
        # Cut coords in GIMP convention (xmin, ymin, xmax, ymax) with
        # bottom-left origin. The baker flips Y against bake_size[1]
        # before cropping. Order matches the original
        # kart_clean_textures.py cutter:
        #   front, back, bridge, floor, red, exhaust, motortop, side, exhaust_pipe
        "cutter": [
            ("kart_00", (3,   3,  35,  19)),   # front
            ("kart_01", (38,  3,  70,  19)),   # back
            ("kart_02", (82,  3,  98,  19)),   # bridge
            ("kart_03", (12, 41,  28,  49)),   # floor
            ("kart_04", (46, 43,  62,  47)),   # red
            ("kart_05", (82, 38,  98,  54)),   # exhaust
            ("kart_06", (7,  71,  39,  87)),   # motortop
            ("kart_07", (64, 71,  96,  87)),   # side
            ("kart_08", (46, 89,  62, 105)),   # exhaust_pipe
        ],
        # variant -> subfolder name inside kart_presets_root.
        "variant_dirs": {
            "DEFAULT":      "kart",
            "GOLD_PIPES":   "gold",
            "SILVER_PIPES": "silver",
        },
        "variant_enum": [
            ("DEFAULT",      "Default",      "Default pipes"),
            ("GOLD_PIPES",   "Gold Pipes",   "Gold pipes"),
            ("SILVER_PIPES", "Silver Pipes", "Silver pipes"),
        ],
    },
    # KART_HI, VELO_CHOPPER -> Fase 4.
}