"""Build a .ctr from a source_mesh.json.

Usage:
    python build_character.py <source_mesh.json> <internal_name> <output.ctr>
                              [--player_slot N]

The --player_slot argument (0-3) shifts the atlas to the VRAM region that
the runtime assigns to that player index. The runtime writes the VRM at
the same offset, so both match.

Per-material double-sided: export_character.py records whether each
Blender material has Backface Culling disabled (use_backface_culling
== False, which is Blender's default). For such materials we emit each
triangle twice: once with the original winding (visible from outside)
and once with bit 5 (0x20) set on every vertex, which the engine
interprets as a flipped winding (visible from inside). Net effect:
the triangle renders from both sides, matching Blender's viewport.

Per-material blend mode: export_character.py also records a blend_mode
string per material ('half' | 'add' | 'subtract' | 'add_25'). We map it
to the 2 ABR bits (5-6) of the tpage word inside each TextureLayout.
Because layouts are cached by content, two materials that share an
image but use different blend modes end up with distinct layouts.

Alpha routing: each texel is classified by its alpha into one of three
buckets:
    a <  SEMI_LO            -> transparent (palette index 0)
    SEMI_LO <= a < SEMI_HI  -> semi-transparent (STP bit 15 set on the
                               palette entry, engine blends it)
    a >= SEMI_HI            -> fully opaque (STP bit clear)
Opaque and semi pixels get disjoint palette slots, so a black outline
with a >= SEMI_HI can never inherit the STP bit from a semi neighbour
(this is the same fix as build_icons.py, reimplemented without PIL).

Note: the ABR bits are only honoured by the engine when the primitive
carries the semi-transparency flag. See native_gpu.c AddSplit /
GET_TPAGE_BLEND. Materials with blend_mode='half' keep the previous
behaviour.
"""
import json, math, struct, hashlib, sys
from collections import Counter
from pathlib import Path
from ctr_animation_codec import encode_animation, pack_delta

ROOT = Path(__file__).parent

# --- Command-line arguments ---
argv = sys.argv[1:]
SOURCE = Path(argv[0]) if len(argv) > 0 else ROOT / 'source_mesh.json'
SLOT_NAME = argv[1] if len(argv) > 1 else 'tiny'
OUT_FILE = argv[2] if len(argv) > 2 else 'tiny.ctr'

PLAYER_SLOT = 0
for i, a in enumerate(argv):
    if a == '--player_slot':
        PLAYER_SLOT = int(argv[i + 1])

MODEL_NAME       = SLOT_NAME
MODEL_NAME_HI    = SLOT_NAME + '_hi'
HEADER_UNK_44    = 0x2000
SLOT_NAMES       = ['turn', 'reverse', 'bump', 'jump']

# Each player slot occupies 128 words of VRAM.
NATIVE_SLOT_WIDTH = 128
ATLAS_X = 0 + PLAYER_SLOT * NATIVE_SLOT_WIDTH
ATLAS_Y = 264

PAGE_W = 128
SUBPAGE_W = 64
NUM_SUBPAGES = PAGE_W // SUBPAGE_W  # = 2
TEXTURE_ROWS = 17
CLUT_ROWS = 5

SCALE = 2

CACHE_MIN, CACHE_MAX = 32, 87

# Alpha thresholds for texel classification (match build_icons.py).
SEMI_LO = 0.1
SEMI_HI = 0.9

# Index 0 of every palette is reserved for fully-transparent texels.
# The remaining 15 slots are shared between the opaque and semi buckets.
CLUT_BUDGET = 15

# Material blend mode -> 2-bit ABR field of the tpage word (bits 5-6).
# These map 1:1 to the engine's enum BlendModeDecal:
#   half     00  -> 0.5*B + 0.5*F   (PSX default; previous behaviour)
#   add      01  -> 1.0*B + 1.0*F
#   subtract 10  -> 1.0*B - 1.0*F
#   add_25   11  -> 1.0*B + 0.25*F
# Unknown values fall back to 'half' (ABR = 0).
ABR_MAP = {
    'half':     0,
    'add':      1,
    'subtract': 2,
    'add_25':   3,
}

# Vertex flag layout (byte 3 of each command word).
#   bit 7 (0x80) = first vertex of the triangle
#   bit 5 (0x20) = flipped winding (set only on the DS duplicate pass)
#   bit 4 (0x10) = always set
#   bit 2 (0x04) = vertex already present in the vertex cache
FLAG_FIRST_VERTEX    = 0x80
FLAG_FLIPPED_WINDING = 0x20
FLAG_ALWAYS          = 0x10
FLAG_CACHE_HIT       = 0x04


def name16(s): return s.encode('ascii').ljust(16, b'\0')


def pack_container(data, patches):
    return (struct.pack('<I', len(data)) + data
            + struct.pack('<I', len(patches) * 4)
            + struct.pack(f'<{len(patches)}I', *sorted(set(patches))))


def apply_matrix_world(mesh):
    m = mesh['matrix_world']
    def tf(p):
        x, y, z = p[0], p[1], p[2]
        return [
            m[0][0]*x + m[0][1]*y + m[0][2]*z + m[0][3],
            m[1][0]*x + m[1][1]*y + m[1][2]*z + m[1][3],
            m[2][0]*x + m[2][1]*y + m[2][2]*z + m[2][3],
        ]
    mesh['vertices'] = [tf(v) for v in mesh['vertices']]
    mesh['keys'] = {k: [tf(v) for v in vs] for k, vs in mesh['keys'].items()}
    return mesh


def quantize_palette_to_n(rgb555, n):
    """Reduce a list of RGB555 colors to at most n unique entries.

    Progressive per-channel bit reduction (same family of tricks the old
    quantize_palette_to_16 used), with a frequency-based fallback for
    very small n where even 1-bit-per-channel still yields 8 colors.
    """
    if not rgb555 or n <= 0:
        return rgb555

    palette = sorted(set(rgb555))
    if len(palette) <= n:
        return rgb555

    for shift in range(1, 6):
        bits = max(1, 5 - shift)
        keep = 5 - bits
        reduced = []
        for c in rgb555:
            r5 = ((c      ) & 31) >> keep << keep
            g5 = ((c >>  5) & 31) >> keep << keep
            b5 = ((c >> 10) & 31) >> keep << keep
            reduced.append(r5 | (g5 << 5) | (b5 << 10))
        rgb555 = reduced
        palette = sorted(set(rgb555))
        if len(palette) <= n:
            return rgb555

    # n is so small that even bits=1 (8 possible colors) still exceeds
    # it. Keep the n most frequent colors and snap everything else to
    # the nearest kept color (squared euclidean distance in 5:5:5 space).
    counts = Counter(rgb555)
    top = [c for c, _ in counts.most_common(n)]

    def dist2(a, b):
        dr = ((a      ) & 31) - ((b      ) & 31)
        dg = ((a >>  5) & 31) - ((b >>  5) & 31)
        db = ((a >> 10) & 31) - ((b >> 10) & 31)
        return dr*dr + dg*dg + db*db

    nearest_cache = {}
    out = []
    for c in rgb555:
        if c in nearest_cache:
            out.append(nearest_cache[c])
            continue
        best = min(top, key=lambda t: dist2(c, t))
        nearest_cache[c] = best
        out.append(best)
    return out


def prepare_textures(mesh):
    images = []
    for name, item in mesh['images'].items():
        w, h = item['size']
        w2 = max(4, w // SCALE)
        h2 = max(4, h // SCALE)
        pix = item['pixels_rgba']
        rgba = []
        for y in range(h2):
            for x in range(w2):
                sx = min(w-1, x*SCALE)
                sy = min(h-1, y*SCALE)
                py = h-1-sy
                idx = 4*(py*w+sx)
                rgba.append(tuple(pix[idx+j] for j in range(4)))
        images.append((name, w2, h2, rgba))

    cells = [[[False] * SUBPAGE_W for _ in range(TEXTURE_ROWS)]
             for _ in range(NUM_SUBPAGES)]
    uploads, textures = [], {}

    for index, (name, w, h, rgba) in enumerate(
            sorted(images, key=lambda a: (-a[2], -a[1], a[0]))):
        words = (w + 3) // 4
        if words % 2 == 1:
            words += 1

        if words > SUBPAGE_W:
            raise AssertionError(
                f'{name}: texture too wide for one page '
                f'(words={words}, SUBPAGE_W={SUBPAGE_W})')

        found = None
        for sp in range(NUM_SUBPAGES):
            for y in range(TEXTURE_ROWS - h + 1):
                for x in range(SUBPAGE_W - words + 1):
                    if not any(cells[sp][yy][xx]
                               for yy in range(y, y + h)
                               for xx in range(x, x + words)):
                        found = (sp, x, y); break
                if found: break
            if found: break

        assert found, ('No space in atlas', name, w, h, words, h)

        sp, x, y = found
        for yy in range(y, y + h):
            for xx in range(x, x + words):
                cells[sp][yy][xx] = True

        global_x = sp * SUBPAGE_W + x
        px = ATLAS_X + global_x
        py = ATLAS_Y + y

        page_index = px // 64
        local_u = (px % 64) * 4

        cx = ATLAS_X + 16 * (index % 8)
        cy = ATLAS_Y + TEXTURE_ROWS + index // 8

        # ---- Alpha routing ------------------------------------------
        # Classify each texel by alpha into one of three buckets, then
        # give opaque and semi their own disjoint palette slots. Index
        # 0 is reserved for transparent.
        pixel_bucket = []   # 'T' | 'O' | 'S' per texel
        opaque_px = []      # (r, g, b) floats for a >= SEMI_HI
        semi_px   = []      # (r, g, b) floats for SEMI_LO <= a < SEMI_HI

        for r, g, b, a in rgba:
            if a < SEMI_LO:
                pixel_bucket.append('T')
            elif a < SEMI_HI:
                pixel_bucket.append('S')
                semi_px.append((r, g, b))
            else:
                pixel_bucket.append('O')
                opaque_px.append((r, g, b))

        # Split the 15 usable slots between the two colour buckets,
        # mirroring build_icons.py: 3..8 slots for semi depending on
        # how much of the texture is semi, the rest for opaque.
        if not semi_px:
            n_opaque, n_semi = CLUT_BUDGET, 0
        elif not opaque_px:
            n_opaque, n_semi = 0, CLUT_BUDGET
        else:
            ratio  = len(semi_px) / (len(semi_px) + len(opaque_px))
            n_semi = max(3, min(8, round(CLUT_BUDGET * ratio)))
            n_opaque = CLUT_BUDGET - n_semi

        def quantize_bucket(colors, n):
            """colors: list of (r,g,b) floats. Returns (palette_rgb555, indices)."""
            if not colors or n <= 0:
                return [], []
            rgb555 = [round(r * 31) | (round(g * 31) << 5) | (round(b * 31) << 10)
                      for r, g, b in colors]
            rgb555 = quantize_palette_to_n(rgb555, n)
            palette = sorted(set(rgb555))
            lookup = {c: i for i, c in enumerate(palette)}
            return palette, [lookup[c] for c in rgb555]

        opaque_pal, opaque_idx = quantize_bucket(opaque_px, n_opaque)
        semi_pal,   semi_idx   = quantize_bucket(semi_px,   n_semi)

        # Final palette: [transparent, opaque..., semi | STP bit].
        # The STP bit (0x8000) is only set on the semi entries, so any
        # opaque texel — including a black outline — is drawn solid.
        palette = [0x0000]
        palette.extend(opaque_pal)
        palette.extend(c | 0x8000 for c in semi_pal)
        while len(palette) < 16:
            palette.append(0x0000)
        assert len(palette) == 16, (name, len(palette))

        # Per-texel palette index.
        opaque_base = 1
        semi_base   = 1 + len(opaque_pal)
        palette_idx = []
        oi = si = 0
        for bucket in pixel_bucket:
            if bucket == 'T':
                palette_idx.append(0)
            elif bucket == 'O':
                palette_idx.append(opaque_base + opaque_idx[oi]); oi += 1
            else:  # 'S'
                palette_idx.append(semi_base + semi_idx[si]); si += 1

        pixels = bytearray()
        for row in range(h):
            ids = [palette_idx[row*w+col] if col < w else 0
                   for col in range(words * 4)]
            pixels.extend(ids[i] | ids[i+1] << 4 for i in range(0, len(ids), 2))

        pal = struct.pack('<16H', *palette)

        textures[name] = {
            'size': [w, h],
            'rect': [px, py, words, h],
            'clut_rect': [cx, cy, 16, 1],
            'u': local_u,
            'v': py % 256,
            'page': page_index | 16,
            'clut': cy * 64 + cx // 16,
            'colors': len(palette),
        }
        uploads.extend([
            {'name': name, 'rect': [px, py, words, h], 'bytes': pixels.hex()},
            {'name': name + '_clut', 'rect': [cx, cy, 16, 1], 'bytes': pal.hex()},
        ])

    (ROOT / 'texture_uploads.json').write_text(
        json.dumps(uploads, separators=(',', ':')))
    (ROOT / 'texture_layouts.json').write_text(
        json.dumps(textures, indent=2))
    return textures


def build():
    mesh = json.loads(SOURCE.read_text())
    mesh = apply_matrix_world(mesh)
    textures = prepare_textures(mesh)
    basis = mesh['keys']['Basis']

    def native(p): return (p[0]*64, p[2]*64, -p[1]*64)

    allpts = [native(p) for p in basis]
    lo = [min(p[a] for p in allpts) - 1 for a in range(3)]
    hi = [max(p[a] for p in allpts) + 1 for a in range(3)]
    scale  = [math.ceil((hi[a] - lo[a]) * 4096 / 253) for a in range(3)]
    origin = [math.floor(lo[a] * 4096 / scale[a]) - 1 for a in range(3)]

    print(f"scale:  {scale}")
    print(f"origin: {origin}")

    def quantize(p):
        v = tuple(round(x * 4096 / scale[a] - origin[a])
                  for a, x in enumerate(native(p)))
        assert all(0 <= q <= 255 for q in v), v
        return v

    palettes, layouts, commands, records, face_order = [], [], [], [], []
    def get_index(lst, value, one=False):
        if value not in lst: lst.append(value)
        return lst.index(value) + int(one)

    faces = mesh['triangles']
    remaining = set(range(len(faces)))
    cache, last, tick = {}, {}, 0

    ds_faces = 0

    while remaining:
        fi = max(remaining, key=lambda i: (
            sum(c['vertex'] in cache for c in faces[i]['corners']), -i))
        remaining.remove(fi); face_order.append(fi)
        face = faces[fi]; material = mesh['materials'][face['material']]
        corners = [face['corners'][i] for i in (0, 2, 1)]
        ti = 0
        if material['image']:
            tex = textures[material['image']]; w, h = tex['size']
            coords = []
            for c in corners:
                corner_u = max(0, min(w-1, round(c['uv'][0] * (w-1))))
                corner_v = max(0, min(h-1, round((1 - c['uv'][1]) * (h-1))))
                cu = tex['u'] + corner_u
                cv = tex['v'] + corner_v
                if cu > 255:
                    raise AssertionError(
                        f'u overflow for {material["image"]}: '
                        f'tex_u={tex["u"]} corner_u={corner_u} cu={cu}')
                if cv > 255:
                    raise AssertionError(
                        f'v overflow for {material["image"]}: '
                        f'tex_v={tex["v"]} corner_v={corner_v} cv={cv}')
                coords.append((cu, cv))

            # Per-material blend mode -> 2 ABR bits in tpage (bits 5-6).
            # Two materials sharing the same image but using different
            # blend modes end up with distinct layouts because the cache
            # key includes the full packed struct.
            abr = ABR_MAP.get(material.get('blend_mode', 'half'), 0)
            layout = struct.pack('<BBHBBHBBBB', *coords[0], tex['clut'],
                                 *coords[1], tex['page'] | (abr << 5),
                                 *coords[2], *coords[2])
            ti = get_index(layouts, layout, True)

        double_sided = bool(material.get('double_sided', False))
        if double_sided:
            ds_faces += 1

        # ---- Pass 1: original winding ---------------------------------
        protected = set(c['vertex'] for c in corners)
        for j, c in enumerate(corners):
            vi = c['vertex']
            flags = FLAG_ALWAYS | (FLAG_FIRST_VERTEX if j == 0 else 0)
            channels = c['color_srgb']
            color = tuple(max(0, min(255, round(x*255))) for x in channels[:3]) + (0,)
            ci = get_index(palettes, color)
            if vi in cache:
                slot = cache[vi]; flags |= FLAG_CACHE_HIT
            else:
                unused = set(range(CACHE_MIN, CACHE_MAX + 1)) - set(cache.values())
                if unused:
                    slot = min(unused)
                else:
                    victim = min((v for v in cache if v not in protected),
                                 key=lambda v: last[v])
                    slot = cache.pop(victim)
                cache[vi] = slot; records.append(vi)
            tick += 1; last[vi] = tick
            commands.append((flags << 24) | (slot << 16) | (ci << 9) | ti)

        # ---- Pass 2: DS duplicate with flipped winding ----------------
        # Every vertex was just added to the cache in Pass 1, so this
        # loop never allocates or evicts. It only emits a second copy
        # of the same triangle with bit 5 set, which the engine
        # interprets as reversed winding.
        if double_sided:
            for j, c in enumerate(corners):
                vi = c['vertex']
                flags = (FLAG_ALWAYS | FLAG_FLIPPED_WINDING
                         | (FLAG_FIRST_VERTEX if j == 0 else 0))
                channels = c['color_srgb']
                color = tuple(max(0, min(255, round(x*255))) for x in channels[:3]) + (0,)
                ci = get_index(palettes, color)
                assert vi in cache, (
                    f'vertex {vi} missing from cache during DS duplicate pass')
                slot = cache[vi]; flags |= FLAG_CACHE_HIT
                tick += 1; last[vi] = tick
                commands.append((flags << 24) | (slot << 16) | (ci << 9) | ti)

    print(f"records={len(records)} palettes={len(palettes)} "
          f"layouts={len(layouts)} commands={len(commands)} "
          f"ds_faces={ds_faces}/{len(faces)}")
    assert len(palettes) <= 128
    assert len(layouts) <= 511
    assert len(records) <= 256

    data = bytearray(88); patches = [20]
    data[0:16] = name16(MODEL_NAME)
    struct.pack_into('<hhI', data, 16, -1, 1, 24)
    data[24:40] = name16(MODEL_NAME_HI)
    struct.pack_into('<ihH4h', data, 40, 0, HEADER_UNK_44, 0, *scale, 0)

    def append(raw):
        while len(data) % 4: data.append(0)
        at = len(data); data.extend(raw); return at
    def ptr(field, target):
        struct.pack_into('<I', data, field, target); patches.append(field)

    command_at = append(struct.pack(f'<{len(commands) + 2}I',
                                    len(palettes), *commands, 0xffffffff))
    ptr(24 + 32, command_at)
    colors_at = append(b''.join(bytes(p) for p in palettes))
    ptr(24 + 44, colors_at)
    texarray = append(bytes(len(layouts) * 4))
    ptr(24 + 40, texarray)
    for i, layout in enumerate(layouts):
        ptr(texarray + 4 * i, append(layout))

    frame = [quantize(basis[vi]) for vi in records]
    clips = {name: [frame] for name in SLOT_NAMES}

    animarray = append(bytes(len(clips) * 4))
    ptr(24 + 56, animarray)
    struct.pack_into('<I', data, 24 + 52, len(clips))

    stats = []
    for index, (name, rows) in enumerate(clips.items()):
        ds, streams, info = encode_animation(rows)
        h = append(name16(name) + struct.pack('<HHI', len(rows),
                                              28 + len(streams[0]), 0))
        ptr(animarray + 4 * index, h)
        for stream in streams:
            data.extend(struct.pack('<4h', *origin, 0) + bytes(16)
                        + struct.pack('<I', 28) + stream)
        dp = append(struct.pack(f'<{len(ds)}I', *(pack_delta(d) for d in ds)))
        ptr(h + 20, dp)
        stats.append({'slot': index, 'name': name, **info})

    while len(data) % 4: data.append(0)
    print(f"model size: {len(data)} bytes")
    assert len(data) < 0x10000

    blob = pack_container(data, patches)
    (ROOT / OUT_FILE).write_bytes(blob)
    print(f"Written: {OUT_FILE} ({len(blob)} bytes, player slot {PLAYER_SLOT})")


if __name__ == '__main__':
    build()