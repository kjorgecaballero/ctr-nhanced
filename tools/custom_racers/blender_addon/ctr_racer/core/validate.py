# =========================================================================
# MODULE: core — validate
# =========================================================================
"""validate_racer: pre-export sanity checks for a racer mesh.

Pure function. No classes, no registration.
"""
import os

import bpy


def validate_racer(obj):
    errors = []
    warnings = []
    props = obj.racer

    if not props.slug:
        errors.append("Slug is empty")
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