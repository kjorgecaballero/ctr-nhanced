"""Build a .ctr from a source_mesh.json.

Usage:
    python build_character.py <source_mesh.json> <internal_name> <output.ctr>

The atlas uses the base slot coordinates (0, 264). At runtime, the C code
adds a per-player offset so each player gets their own VRAM region.
"""
import json, math, struct, hashlib, sys
from pathlib import Path
from ctr_animation_codec import encode_animation, pack_delta

ROOT = Path(__file__).parent

# --- Command-line arguments ---
argv = sys.argv[1:]
SOURCE = Path(argv[0]) if len(argv) > 0 else ROOT / 'source_mesh.json'
SLOT_NAME = argv[1] if len(argv) > 1 else 'tiny'
OUT_FILE = argv[2] if len(argv) > 2 else 'tiny.ctr'

MODEL_NAME       = SLOT_NAME
MODEL_NAME_HI    = SLOT_NAME + '_hi'
HEADER_UNK_44    = 0x2000
SLOT_NAMES       = ['turn', 'reverse', 'bump', 'jump']

# Base slot coordinates. The C code adds player_index * 128 to ATLAS_X at runtime.
ATLAS_X, ATLAS_Y = 0, 264
PAGE_W = 128              # total atlas width in words (2 sub-pages of 64)
SUBPAGE_W = 64            # PSX texture page width in words
NUM_SUBPAGES = PAGE_W // SUBPAGE_W  # = 2
TEXTURE_ROWS = 18         # rows available for textures
CLUT_ROWS = 4             # rows available for CLUTs (8 per row = 32 max)

SCALE = 2

CACHE_MIN, CACHE_MAX = 32, 87


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


def quantize_palette_to_16(rgb555):
    """Reduce a list of RGB555 colors to at most 16 unique entries.

    If already <= 16, returns as-is. Otherwise, drops bits per channel
    (5 -> 4 -> 3 -> 2 -> 1) until <= 16 unique colors remain.
    Transparent (0x0000) and marker (0x8000) are preserved.
    """
    palette = sorted(set(rgb555))
    if len(palette) <= 16:
        return rgb555

    for shift in range(1, 6):
        bits = 5 - shift
        if bits < 1:
            bits = 1
        reduced = []
        for c in rgb555:
            if c == 0 or c == 0x8000:
                reduced.append(c)
                continue
            r5 = c & 31
            g5 = (c >> 5) & 31
            b5 = (c >> 10) & 31
            r5 = (r5 >> (5 - bits)) << (5 - bits)
            g5 = (g5 >> (5 - bits)) << (5 - bits)
            b5 = (b5 >> (5 - bits)) << (5 - bits)
            reduced.append(r5 | (g5 << 5) | (b5 << 10))
        rgb555 = reduced
        palette = sorted(set(rgb555))
        if len(palette) <= 16:
            return rgb555

    return rgb555


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

    # Two sub-pages of 64 words each. A texture must fit entirely inside
    # one sub-page (its local word offset + words <= 64).
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

        rgb555 = []
        for r, g, b, a in rgba:
            c = round(r * 31) | (round(g * 31) << 5) | (round(b * 31) << 10)
            rgb555.append(0 if a < .5 else c if c else 0x8000)

        rgb555 = quantize_palette_to_16(rgb555)
        palette = sorted(set(rgb555))
        assert len(palette) <= 16, (name, len(palette))
        lookup = {c: i for i, c in enumerate(palette)}

        pixels = bytearray()
        for row in range(h):
            ids = [lookup[rgb555[row*w+col]] if col < w else 0
                   for col in range(words * 4)]
            pixels.extend(ids[i] | ids[i+1] << 4 for i in range(0, len(ids), 2))

        pal = struct.pack('<16H', *(palette + [0] * (16 - len(palette))))

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
            layout = struct.pack('<BBHBBHBBBB', *coords[0], tex['clut'],
                                 *coords[1], tex['page'],
                                 *coords[2], *coords[2])
            ti = get_index(layouts, layout, True)
        protected = set(c['vertex'] for c in corners)
        for j, c in enumerate(corners):
            vi = c['vertex']
            flags = 0x10 | (0x80 if j == 0 else 0)
            channels = c['color_srgb']
            color = tuple(max(0, min(255, round(x*255))) for x in channels[:3]) + (0,)
            ci = get_index(palettes, color)
            if vi in cache:
                slot = cache[vi]; flags |= 4
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

    print(f"records={len(records)} palettes={len(palettes)} "
          f"layouts={len(layouts)} commands={len(commands)}")
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
    print(f"Written: {OUT_FILE} ({len(blob)} bytes)")


if __name__ == '__main__':
    build()