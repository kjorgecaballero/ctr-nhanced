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
import os
import re

import bpy


_SLUG_BAD_CHARS = re.compile(r"[^a-z0-9_]+")

# build_character.py:670 asserts len(palettes) <= 128. `palettes`
# there is a list of UNIQUE RGB555 colors (get_index appends on miss),
# so the limit is 128 colors, not 128*15. Match it here.
_BUILDER_COLOR_LIMIT = 128


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


def _count_unique_loop_colors(obj):
    """Count unique per-loop vertex colors.

    Uses the same source as report_vcol_(2).py:
    obj.data.vertex_colors.active.data[i].color (LINEAR RGBA),
    rounded to 4 decimals. Matches what build_character.py groups
    into its `palettes` list before asserting <= 128."""
    m = obj.data
    layer = m.vertex_colors.active
    if layer is None:
        return 0
    n = len(layer.data)
    if n == 0:
        return 0
    buf = [0.0] * (n * 4)
    layer.data.foreach_get("color", buf)
    seen = set()
    for i in range(0, len(buf), 4):
        key = (round(buf[i], 4), round(buf[i + 1], 4),
               round(buf[i + 2], 4), round(buf[i + 3], 4))
        seen.add(key)
    return len(seen)


def _estimate_palette_count(obj):
    """Return the unique vertex-color count the .ctr builder will see.

    build_character.py:670 asserts `len(palettes) <= 128`, where
    `palettes` is the list of unique RGB555 vertex colors that
    `get_index(palettes, color)` grows. The limit is therefore 128
    UNIQUE COLORS, not 128 palettes of 15. We return the raw unique
    count and compare it against _BUILDER_COLOR_LIMIT.

    (Name kept for backwards compatibility — it predates knowing the
    builder's exact limit.)"""
    return _count_unique_loop_colors(obj)


def _kmeans_pp_init(data, k, seed=0):
    """k-means++ init. Returns a (k', D) array of centers with k' <= k.

    k' < k only if the input has fewer than k distinct points (which
    the caller guards against) — in practice it returns exactly k."""
    import numpy as np
    rng = np.random.default_rng(seed)
    centers = [data[rng.integers(len(data))]]
    for _ in range(1, k):
        dists = np.min(
            np.stack([np.sum((data - c) ** 2, axis=1) for c in centers]),
            axis=0,
        )
        s = float(dists.sum())
        if s <= 0.0:
            break
        centers.append(data[rng.choice(len(data), p=dists / s)])
    return np.vstack(centers)


def _kmeans_numpy(data, k, iterations=10, seed=0):
    """Plain k-means on an (N, D) float array. Returns (k', D) centers
    where k' == len(centers) after init (could be < k only if the
    dataset has fewer than k distinct rows)."""
    import numpy as np
    centers = _kmeans_pp_init(data, k, seed)
    for _ in range(iterations):
        dists = np.sum((data[:, None, :] - centers[None, :, :]) ** 2, axis=2)
        labels = np.argmin(dists, axis=1)
        new_centers = []
        for i in range(len(centers)):
            pts = data[labels == i]
            new_centers.append(pts.mean(axis=0) if len(pts) else centers[i])
        centers = np.vstack(new_centers)
    return centers


def _reduce_vertex_colors(obj, target_clusters=None):
    """Reduce vertex colors to at most `target_clusters` unique values.

    Direct port of report_vcol_(2).py's Report + Convert flow:
      1. Collect unique per-loop colors (round 4) and their loop ids.
      2. k-means the unique colors down to `target_clusters` centers.
      3. Assign each unique color to its nearest center.
      4. Snap every loop of that unique color to the center's RGBA.

    Returns (old_unique, new_unique) or None on error."""
    if target_clusters is None:
        target_clusters = _BUILDER_COLOR_LIMIT

    try:
        import numpy as np
    except ImportError:
        return None

    m = obj.data
    layer = m.vertex_colors.active
    if layer is None or len(layer.data) == 0:
        return None

    n = len(layer.data)
    buf = [0.0] * (n * 4)
    layer.data.foreach_get("color", buf)

    # Step 1 — group loops by unique color.
    seen = {}
    unique = []
    loop_map = []
    for li in range(n):
        i = li * 4
        key = (round(buf[i], 4), round(buf[i + 1], 4),
               round(buf[i + 2], 4), round(buf[i + 3], 4))
        idx = seen.get(key)
        if idx is None:
            idx = len(unique)
            seen[key] = idx
            unique.append(key)
            loop_map.append([li])
        else:
            loop_map[idx].append(li)

    old_unique = len(unique)
    target = min(int(target_clusters), old_unique)
    if target >= old_unique:
        return (old_unique, old_unique)

    # Step 2 — k-means over the unique colors (4D, includes alpha).
    data = np.array(unique, dtype=float)
    centers = _kmeans_numpy(data, target, iterations=10, seed=0)

    # If k-means returned fewer than `target` rows (empty clusters
    # dropped during init, or the input had < target distinct rows),
    # pad with random data points so `centers` has exactly `target`
    # rows. This keeps the assignment step positional.
    if centers.shape[0] < target:
        rng = np.random.default_rng(1)
        extra = target - centers.shape[0]
        pick = rng.choice(len(data), extra, replace=False)
        centers = np.vstack([centers, data[pick]])

    # Step 3 — assign each unique color to its nearest center. `picks`
    # has len(unique) entries, each in [0, len(centers)).
    dists = np.sum(
        (data[:, None, :] - centers[None, :, :]) ** 2, axis=2)
    picks = np.argmin(dists, axis=1)

    # Step 4 — snap every loop of each unique color to its center.
    for idx, loop_indices in enumerate(loop_map):
        c = centers[picks[idx]]
        for li in loop_indices:
            i = li * 4
            buf[i]     = float(c[0])
            buf[i + 1] = float(c[1])
            buf[i + 2] = float(c[2])
            buf[i + 3] = float(c[3])

    layer.data.foreach_set("color", buf)
    m.update()

    # Recount from the written buffer.
    new_seen = set()
    for i in range(0, len(buf), 4):
        key = (round(buf[i], 4), round(buf[i + 1], 4),
               round(buf[i + 2], 4), round(buf[i + 3], 4))
        new_seen.add(key)

    return (old_unique, len(new_seen))


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
                print(f"[Racer Validate] {im.name}: "
                      f"{im.size[0]}x{im.size[1]} packed")

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

    # Vertex-color overflow. build_character.py:670 asserts
    # `len(palettes) <= 128`, where `palettes` is the list of unique
    # RGB555 vertex colors the builder collects. The cap is 128
    # unique colors, not 128 * 15. This BLOCKS the export, so it is
    # an error (red alert), not a warning — the panel shows it with
    # r2.alert = True and NFR_OT_Export bails out before invoking
    # build_character.py.
    n_unique = _count_unique_loop_colors(obj)
    if n_unique > _BUILDER_COLOR_LIMIT:
        errors.append((
            "Vertex colors: too many",
            f"Mesh has {n_unique} unique vertex colors. The .ctr "
            f"builder caps at {_BUILDER_COLOR_LIMIT} (build_character.py:670 "
            f"asserts len(palettes) <= 128) and will fail with "
            f"'AssertionError'. Click the Fix button to the right to "
            f"run a k-means reduction down to {_BUILDER_COLOR_LIMIT} "
            f"unique colors. Destructive — Ctrl+Z to revert."
        ))

    return (len(errors) == 0, warnings, errors)