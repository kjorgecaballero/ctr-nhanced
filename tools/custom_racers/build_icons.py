"""
Package each racer's icon.png into page_N.vrm files.

Each icon is TWO blocks:
  - 4bpp pixels: 44x26 pixels = 11 halfwords x 26 rows
  - 16-color CLUT: 16x1 halfwords (32 bytes)

VRAM coordinates per slot (extracted from the engine's Icon data):
  slot 0  (crash):     px(368,216) clut(16,251)
  slot 1  (cortex):    px(256,216) clut(16,252)
  slot 2  (tiny):      px(267,216) clut(16,253)
  slot 3  (coco):      px(278,216) clut(16,254)
  slot 4  (ngin):      px(289,216) clut(16,255)
  slot 5  (dingo):     px(300,216) clut(32,248)
  slot 6  (polar):     px(920,144) clut(32,249)
  slot 7  (pura):      px(931,144) clut(32,250)
  slot 8  (ntropy):    px(929,192) clut(32,255)
  slot 9  (pinstripe): px(918,192) clut(32,254)
  slot 10 (roo):       px(942,144) clut(32,251)
  slot 11 (papu):      px(896,192) clut(32,252)
  slot 12 (joe):       px(907,192) clut(32,253)
  slot 13-17:          synthetic (Sentinel only, no real VRAM)

Usage:
    python build_icons.py
    python build_icons.py --page 1
"""
import argparse
import struct
import sys
import warnings
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("pip install pillow")

warnings.filterwarnings("ignore", category=UserWarning, module="PIL")

NHANCED = Path(__file__).resolve().parents[2]
RACERS  = NHANCED / "assets" / "mods" / "racers"

ICON_W = 44
ICON_H = 26

# slot -> (px_x, px_y, clut_x, clut_y)
SLOTS = {
    0:  (368, 216, 16, 251),
    1:  (256, 216, 16, 252),
    2:  (267, 216, 16, 253),
    3:  (278, 216, 16, 254),
    4:  (289, 216, 16, 255),
    5:  (300, 216, 32, 248),
    6:  (920, 144, 32, 249),
    7:  (931, 144, 32, 250),
    8:  (929, 192, 32, 255),
    9:  (918, 192, 32, 254),
    10: (942, 144, 32, 251),
    11: (896, 192, 32, 252),
    12: (907, 192, 32, 253),
    13: (960, 216, 48, 248),
    14: (971, 216, 48, 249),
    15: (982, 216, 48, 252),
    16: (960, 245, 48, 250),
    17: (971, 245, 48, 251),
}


def parse_roster():
    pages = {}
    txt = (RACERS / "roster.txt").read_text()
    for lineno, line in enumerate(txt.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split()
        if len(parts) < 3:
            print(f"  line {lineno} skipped: {line!r}")
            continue
        try:
            page = int(parts[0])
            slot = int(parts[1])
        except ValueError:
            print(f"  line {lineno} skipped (page/slot not numeric)")
            continue
        pages.setdefault(page, {})[slot] = parts[2]
    return pages


def pack_icon(img):
    """Returns (4bpp_bytes, clut_bytes).

    Alpha routing:
      a < 0.1           -> CLUT index 0 (fully transparent)
      0.1 <= a < 0.9    -> STP bit set (decoder outputs alpha 128)
      a >= 0.9          -> opaque (decoder outputs alpha 255)

    Opacos y semi se cuantizan en DOS paletas separadas. Si se
    mezclan en un mismo bucket, el negro del contorno puede terminar
    con STP=1 y salir al 50% (contorno semitransparente).
    """
    img = img.convert("RGBA").resize((ICON_W, ICON_H), Image.LANCZOS)
    px = img.load()

    SEMI_LO = 0.1
    SEMI_HI = 0.9

    opaque_px = []   # (x, y, r, g, b)
    semi_px   = []   # (x, y, r, g, b)

    for y in range(ICON_H):
        for x in range(ICON_W):
            r, g, b, a = px[x, y]
            a_norm = a / 255.0
            if a_norm < SEMI_LO:
                continue
            if a_norm < SEMI_HI:
                semi_px.append((x, y, r, g, b))
            else:
                opaque_px.append((x, y, r, g, b))

    # Presupuesto: 15 entradas (índice 0 es transparente).
    total = len(opaque_px) + len(semi_px)
    if total == 0 or len(semi_px) == 0:
        n_opaque, n_semi = 15, 0
    elif len(opaque_px) == 0:
        n_opaque, n_semi = 0, 15
    else:
        ratio  = len(semi_px) / total
        n_semi = max(3, min(8, round(15 * ratio)))
        n_opaque = 15 - n_semi

    def quantize(px_list, n_colors):
        if not px_list or n_colors <= 0:
            return [], []
        colors = [(r, g, b) for (_, _, r, g, b) in px_list]
        tmp = Image.new("RGB", (len(colors), 1))
        tmp.putdata(colors)
        tmp_q = tmp.quantize(colors=n_colors, method=Image.MEDIANCUT)
        raw_pal = list(tmp_q.getpalette() or [])
        raw_pal += [0] * (n_colors * 3 - len(raw_pal))
        pal = [(raw_pal[i * 3], raw_pal[i * 3 + 1], raw_pal[i * 3 + 2])
               for i in range(n_colors)]
        idxs = [i & 0xF for i in tmp_q.getdata()]
        return pal, idxs

    idx_grid     = [[0] * ICON_W for _ in range(ICON_H)]
    palette_rgb  = []
    palette_semi = []

    if opaque_px and n_opaque > 0:
        o_pal, o_idx = quantize(opaque_px, n_opaque)
        base = len(palette_rgb) + 1
        palette_rgb.extend(o_pal)
        palette_semi.extend([False] * len(o_pal))
        for k, (x, y, r, g, b) in enumerate(opaque_px):
            idx_grid[y][x] = (o_idx[k] & 0xF) + base

    if semi_px and n_semi > 0:
        s_pal, s_idx = quantize(semi_px, n_semi)
        base = len(palette_rgb) + 1
        palette_rgb.extend(s_pal)
        palette_semi.extend([True] * len(s_pal))
        for k, (x, y, r, g, b) in enumerate(semi_px):
            idx_grid[y][x] = (s_idx[k] & 0xF) + base

    while len(palette_rgb) < 15:
        palette_rgb.append((0, 0, 0))
        palette_semi.append(False)

    # Pack 4bpp: nibble bajo = píxel izquierdo
    pix = bytearray()
    for y in range(ICON_H):
        for hw in range(ICON_W // 4):
            i0 = idx_grid[y][hw * 4 + 0] & 0xF
            i1 = idx_grid[y][hw * 4 + 1] & 0xF
            i2 = idx_grid[y][hw * 4 + 2] & 0xF
            i3 = idx_grid[y][hw * 4 + 3] & 0xF
            pix.append(i0 | (i1 << 4))
            pix.append(i2 | (i3 << 4))

    # CLUT: índice 0 = transparente; 1..15 con STP si el bucket es semi.
    clut = bytearray()
    clut += struct.pack("<H", 0x0000)
    for i in range(15):
        r, g, b = palette_rgb[i]
        c = ((r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)) & 0x7FFF
        if palette_semi[i]:
            c |= 0x8000
        clut += struct.pack("<H", c)

    return bytes(pix), bytes(clut)


def write_vrm(path, blocks):
    """blocks: list of (x, y, w, h, pixel_bytes)."""
    out = bytearray(struct.pack("<I", 0x20))
    for x, y, w, h, pixels in blocks:
        size = w * h * 2
        assert len(pixels) == size, (x, y, w, h, len(pixels), size)
        out += struct.pack(
            "<IIIIHHHH",
            size | 0x14, 0x10, 0x00000002, size | 0x0C,
            x, y, w, h,
        )
        out += pixels
    path.write_bytes(out)
    return len(out)


def build_page(page_num, slots):
    blocks = []
    for slot, folder in sorted(slots.items()):
        if slot not in SLOTS:
            print(f"  slot {slot} not mapped - skipped")
            continue

        png = RACERS / folder / "icon.png"
        if not png.exists():
            print(f"  missing {png} - slot {slot} skipped")
            continue

        px_x, px_y, clut_x, clut_y = SLOTS[slot]
        pix, clut = pack_icon(Image.open(png))

        blocks.append((px_x, px_y, ICON_W // 4, ICON_H, pix))
        blocks.append((clut_x, clut_y, 16, 1, clut))

    if not blocks:
        print(f"  page_{page_num}.vrm: 0 blocks - not written")
        return

    if page_num == 0:
        dst = RACERS / "page_0_custom.vrm"
    else:
        dst = RACERS / f"page_{page_num}.vrm"
    size = write_vrm(dst, blocks)
    print(f"  {dst.name}: {len(blocks) // 2} icons "
          f"({len(blocks)} blocks), {size} bytes")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", type=int, default=None,
                    help="Build only this page")
    args = ap.parse_args()

    if not (RACERS / "roster.txt").exists():
        sys.exit(f"Missing {RACERS / 'roster.txt'}")

    pages = parse_roster()

    for page_num, slots in sorted(pages.items()):
        if page_num == 0:
            slots = {s: f for s, f in slots.items() if s >= 16}
            if not slots:
                continue
        if args.page is not None and args.page != page_num:
            continue
        build_page(page_num, slots)

    print("Done.")


if __name__ == "__main__":
    main()