# =========================================================================
# MODULE: core — validate
# =========================================================================
"""validate_racer: pre-export sanity checks for a racer mesh.

Pure function. No classes, no registration.
"""
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
    n = len(m.loops)
    if n == 0:
        return 0, 0.0, 0.0, 0.0, 0.0
    buf = [0.0] * (n * 2)
    m.uv_layers.active.data.foreach_get("uv", buf)
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


def validate_racer(obj):
    errors = []
    warnings = []
    props = obj.racer

    if not props.slug:
        errors.append("Slug is empty")
    elif " " in props.slug:
        fixed = _slugify(props.slug)
        errors.append(
            f"Slug has spaces: '{props.slug}'. Spaces break the pipeline "
            f"(missing icon, wrong folder). Use '{fixed}' — or click Fix Slug."
        )
    if not props.long_name:
        warnings.append("Long Name is empty (will fall back to slug)")

    m = obj.data
    if m.shape_keys is None or "Basis" not in m.shape_keys.key_blocks:
        errors.append("No 'Basis' shape key")
    if m.uv_layers.active is None:
        errors.append("No active UV layer")
    if "Color" not in m.color_attributes:
        errors.append("No 'Color' color attribute")

    for mat in m.materials:
        if mat is None:
            continue
        if not mat.use_nodes:
            warnings.append(f"Material '{mat.name}' has no nodes")
            continue
        imgs = [n.image for n in mat.node_tree.nodes
                if n.type == "TEX_IMAGE" and n.image]
        if len(imgs) > 1:
            errors.append(f"Material '{mat.name}' has {len(imgs)} images (max 1)")
        for im in imgs:
            if im.packed_file is None:
                errors.append(f"Image '{im.name}' is NOT packed into the .blend")
            else:
                warnings.append(f"Image '{im.name}': {im.size[0]}x{im.size[1]} packed")

    if props.icon_path:
        resolved = bpy.path.abspath(props.icon_path)
        if not os.path.isfile(resolved):
            errors.append(
                f"Icon file not found: {props.icon_path} "
                f"(resolved to: {resolved})")
    else:
        warnings.append("No icon PNG selected")

    return (len(errors) == 0, warnings, errors)