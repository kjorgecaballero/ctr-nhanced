# =========================================================================
# MODULE: kart — templates
# =========================================================================
"""Static definitions of the bundled kart templates.

Each template entry describes:
  - display_name:      human label for the dropdown
  - fbx_name:          filename inside assets/kart_template/
  - material_prefix:   prefix of the material name to find after FBX import
  - variant_textures:  variant_id -> {slot -> png_filename}
  - zones:             ordered list of (display_name, slot). The index of
                       each zone equals the creation order of the RGB node
                       in the graph (matches the original kart_editor.py).
  - cutter_output_names: Fase 2 -- names for the auto-cut pieces.
  - variant_enum:      items tuple for the variant EnumProperty.
"""

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
        # (zone display name, texture slot). Slot -> variant_textures key.
        "zones": [
            ("Body",    "atlas"),
            ("Pipes",   "pipes"),
            ("Extra 1", "extra1"),
            ("Extra 2", "extra2"),
        ],
        # Fase 2 -- used by the auto-cutter. Order follows the
        # original kart_clean_textures.py cutter (front, back, bridge,
        # floor, red, exhaust, motortop, side, exhaust_pipe) renamed
        # to kart_NN.
        "cutter_output_names": [
            "kart_00", "kart_01", "kart_02", "kart_03", "kart_04",
            "kart_05", "kart_06", "kart_07", "kart_08",
        ],
        "variant_enum": [
            ("DEFAULT",      "Default",      "Default pipes"),
            ("GOLD_PIPES",   "Gold Pipes",   "Gold pipes"),
            ("SILVER_PIPES", "Silver Pipes", "Silver pipes"),
        ],
    },
    # KART_HI, VELO_CHOPPER -> Fase 4.
}