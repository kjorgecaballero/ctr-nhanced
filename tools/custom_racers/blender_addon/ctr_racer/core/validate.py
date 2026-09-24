# =========================================================================
# MODULE: core — validate
# =========================================================================
"""validate_racer: pre-export sanity checks for a racer mesh.

Pure function. No classes, no registration.

validate_racer returns (ok, warnings, errors) where warnings and
errors are lists of (short, long) tuples:
  - short: one-line label for the panel row (~30 chars)
  - long:  full explanation, shown in the click popup
"""
import math
import os
import re

import bpy


_SLUG_BAD_CHARS = re.compile(r"[^a-z0-9_]+")


def _slugify(name):
    """Normalize a display name into a filesystem/slug-safe string."""
    s = (name or "").strip().lower().replace(" ", "_")
    s = _SLUG_BAD_CHARS.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "racer"


def _uv_out_of_range(obj, tol=1e-4):
    """Count mesh loops whose UVs fall outside [0,1].

    Returns (n_oob, min_u, max_u, min_v, max_v). Scans the active UV
    layer via foreach_get so it stays fast on large meshes. The build
    pipeline clamps UVs to the texture edge before quantizing to u8
    (build_character.py:590-603), so out-of-range UVs render clamped
    in-game with no warning."""
    m = obj.data
    if m.uv_layers.active is None:
        return 0, 0.0, 0.0, 0.0, 0.0
    uv_data = m.uv_layers.active.data
    n = len(uv_data)
    if n == 0:
        return 0, 0.0, 0.0, 0.0, 0.0
    buf = [0.0] * (n * 2)
    uv_data.foreach_get("uv", buf)
    n_oob = 0
    min_u = min_v = float('inf')
    max_u = max_v = float('-inf')
    for i in range(0, len(buf), 2):
        u = buf[i]
        v = buf[i + 1]
        if u < min_u: min_u = u
        if u > max_u: max_u = u
        if v < min_v: min_v = v
        if v > max_v: max_v = v
        if u < -tol or u > 1.0 + tol or v < -tol or v > 1.0 + tol:
            n_oob += 1
    return n_oob, min_u, max_u, min_v, max_v


def _estimate_palette_count(obj):
    """Approximate how many RGB555 palettes the .ctr builder will need.

    The builder quantizes opaque vertex colors to RGB555 (5 bits per
    channel) and groups unique values into palettes of 15 usable slots
    (index 0 is reserved for transparency). This mirrors the
    quantization but not the exact grouping heuristic, so treat the
    result as approximate."""
    m = obj.data
    if "Color" not in m.color_attributes:
        return 0
    ca = m.color_attributes["Color"]
    n = len(ca.data)
    if n == 0:
        return 0
    buf = [0.0] * (n * 4)
    ca.data.foreach_get("color_srgb", buf)
    unique = set()
    for i in range(0, len(buf), 4):
        if buf[i + 3] < 0.5:
            continue
        r = int(round(buf[i] * 255))
        g = int(round(buf[i + 1] * 255))
        b = int(round(buf[i + 2] * 255))
        rgb555 = ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)
        unique.add(rgb555)
    return math.ceil(len(unique) / 15) if unique else 0


def validate_racer(obj):
    errors = []      # list of (short, long)
    warnings = []    # list of (short, long)
    props = obj.racer

    if not props.slug:
        errors.append((
            "Slug missing",
            "Slug is empty. Every racer needs a slug — it is the folder "
            "name and the internal .ctr name. Set it in the Settings tab."
        ))
    elif " " in props.slug:
        fixed = _slugify(props.slug)
        errors.append((
            "Slug has spaces",
            f"Slug contains spaces: '{props.slug}'. Spaces break the "
            f"pipeline — the folder is created with the wrong name, the "
            f"icon fails to load, and the export appears to succeed. "
            f"Click Fix Slug to rewrite as '{fixed}'."
        ))
    if not props.long_name:
        warnings.append((
            "Long Name missing",
            "Long Name is empty. In-game the display name will fall "
            "back to the slug. Set a proper display name in the "
            "Settings tab."
        ))

    m = obj.data
    if m.shape_keys is None or "Basis" not in m.shape_keys.key_blocks:
        errors.append((
            "Basis missing",
            "Mesh has no 'Basis' shape key. The exporter requires a "
            "Basis key to quantize vertex positions. Add one in "
            "Object Data > Shape Keys."
        ))
    if m.uv_layers.active is None:
        errors.append((
            "UV layer missing",
            "No active UV layer. The build pipeline samples the texture "
            "through UVs; without one the model exports untextured. Add "
            "a UV layer in the UV Editor."
        ))
    if "Color" not in m.color_attributes:
        errors.append((
            "Color attribute missing",
            "No 'Color' color attribute. Vertex colors carry the "
            "per-face color and the alpha/STP bit routing. Add a Color "
            "attribute of type Byte Color in Object Data > Color "
            "Attributes."
        ))

    unpacked = []  # names of images not packed into the .blend

    for mat in m.materials:
        if mat is None:
            continue
        if not mat.use_nodes:
            warnings.append((
                f"Material w/o nodes: {mat.name}",
                f"Material '{mat.name}' has no nodes. It will export as "
                f"a solid color. Enable 'Use Nodes' on the material."
            ))
            continue
        imgs = [n.image for n in mat.node_tree.nodes
                if n.type == "TEX_IMAGE" and n.image]
        if len(imgs) > 1:
            errors.append((
                f"{len(imgs)} images in {mat.name}",
                f"Material '{mat.name}' has {len(imgs)} image texture "
                f"nodes. Only the first is exported. Remove the extra "
                f"TEX_IMAGE nodes or split the material."
            ))
        for im in imgs:
            if im.packed_file is None:
                if im.name not in unpacked:
                    unpacked.append(im.name)
            else:
                # Diagnostic only — printed to the console, not added
                # to `warnings`. A racer .blend has 30+ packed images;
                # listing each one would drown the real warnings.
                print(f"[Racer Validate] {im.name}: "
                      f"{im.size[0]}x{im.size[1]} packed")

    # One aggregated error instead of one row per unpacked image:
    # the short label stays compact, and the popup lists every
    # offending name plus the fix.
    if unpacked:
        n = len(unpacked)
        noun = "image" if n == 1 else "images"
        listing = "\n".join(f"  • {name}" for name in unpacked)
        errors.append((
            f"{n} {noun} not packed",
            f"The following {noun} are not packed into the .blend:\n"
            f"{listing}\n\n"
            f"Pack them via File > External Data > Pack Resources so "
            f"the export has the pixel data."
        ))

    if props.icon_path:
        resolved = bpy.path.abspath(props.icon_path)
        if not os.path.isfile(resolved):
            errors.append((
                "Icon PNG missing",
                f"Icon file not found: '{props.icon_path}' "
                f"(resolved to: {resolved}). Set a valid icon PNG in "
                f"the Settings tab."
            ))
    else:
        warnings.append((
            "Icon missing",
            "No icon PNG selected. In-game char-select will fall back "
            "to the default placeholder icon. Set a 44x26 PNG in the "
            "Settings tab."
        ))

    n_pal = _estimate_palette_count(obj)
    if n_pal > 128:
        warnings.append((
            "Palette overflow",
            f"Estimated {n_pal} RGB555 palettes (builder max: 128). The "
            f".ctr builder groups unique vertex colors into palettes of "
            f"15 usable slots and will fail with "
            f"'assert len(palettes) <= 128'. Reduce unique vertex colors "
            f"(quantize the Color attribute or use fewer shades) before "
            f"exporting. This is an estimate, not the exact builder "
            f"count."
        ))

    return (len(errors) == 0, warnings, errors)