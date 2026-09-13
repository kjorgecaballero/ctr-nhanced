"""
Empaqueta los icon.png de cada racer en page_N.vrm.

Cada icono son DOS bloques:
  - pixels 4bpp: 44x26 pixels = 11 halfwords x 26 rows
  - CLUT 16 colores: 16x1 halfwords (32 bytes)

Coords VRAM por slot (extraídas de los Icon del motor):
  slot 0 (crash):     px(368,216) clut(16,251)
  slot 1 (cortex):    px(256,216) clut(16,252)
  slot 2 (tiny):      px(267,216) clut(16,253)
  slot 3 (coco):      px(278,216) clut(16,254)
  slot 4 (ngin):      px(289,216) clut(16,255)
  slot 5 (dingo):     px(300,216) clut(32,248)
  slot 6 (polar):     px(920,144) clut(32,249)
  slot 7 (pura):      px(931,144) clut(32,250)
  slot 8 (ntropy):    px(929,192) clut(32,255)
  slot 9 (pinstripe): px(918,192) clut(32,254)
  slot 10 (roo):      px(942,144) clut(32,251)
  slot 11 (papu):     px(896,192) clut(32,252)
  slot 12 (joe):      px(907,192) clut(32,253)

Uso:
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
            print(f"  línea {lineno} ignorada: {line!r}")
            continue
        try:
            page = int(parts[0])
            slot = int(parts[1])
        except ValueError:
            print(f"  línea {lineno} ignorada (page/slot no numérico)")
            continue
        pages.setdefault(page, {})[slot] = parts[2]
    return pages


def pack_icon(img):
    """Devuelve (bytes_4bpp, bytes_clut)."""
    img = img.convert("RGBA").resize((ICON_W, ICON_H), Image.LANCZOS)
    px = img.load()

    # Separar opacos de transparentes
    opaque_pixels = []          # lista de (x, y)
    opaque_colors = []          # lista de (r, g, b)
    for y in range(ICON_H):
        for x in range(ICON_W):
            r, g, b, a = px[x, y]
            if a >= 128:
                opaque_pixels.append((x, y))
                opaque_colors.append((r, g, b))

    idx_grid = [[0] * ICON_W for _ in range(ICON_H)]
    palette = [(0, 0, 0)] * 15   # padding por defecto

    if opaque_colors:
        # Cuantizar a 15 colores (índices temporales 0..14 → finales 1..15)
        tmp = Image.new("RGB", (len(opaque_colors), 1))
        tmp.putdata(opaque_colors)
        tmp_q = tmp.quantize(colors=15, method=Image.MEDIANCUT)

        # getpalette() puede devolver None o menos de 45 valores → rellenar
        raw_pal = tmp_q.getpalette() or []
        raw_pal = list(raw_pal) + [0] * (15 * 3 - len(raw_pal))
        palette = [
            (raw_pal[i * 3], raw_pal[i * 3 + 1], raw_pal[i * 3 + 2])
            for i in range(15)
        ]

        # Asignar índices en la rejilla
        tmp_idx = list(tmp_q.getdata())
        for k, (x, y) in enumerate(opaque_pixels):
            idx_grid[y][x] = (tmp_idx[k] & 0xF) + 1   # 1..15

    # Empaquetar 4bpp: nibble bajo = pixel izquierdo
    pix = bytearray()
    for y in range(ICON_H):
        for hw in range(ICON_W // 4):
            i0 = idx_grid[y][hw * 4 + 0] & 0xF
            i1 = idx_grid[y][hw * 4 + 1] & 0xF
            i2 = idx_grid[y][hw * 4 + 2] & 0xF
            i3 = idx_grid[y][hw * 4 + 3] & 0xF
            pix.append(i0 | (i1 << 4))
            pix.append(i2 | (i3 << 4))

    # CLUT: 16 halfwords. Índice 0 = transparente (0x0000, bit 15 = 0).
    clut = bytearray()
    clut += struct.pack("<H", 0x0000)
    for r, g, b in palette:
        c = ((r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)) & 0x7FFF
        clut += struct.pack("<H", c)

    return bytes(pix), bytes(clut)


def write_vrm(path, blocks):
    """blocks: lista de (x, y, w, h, bytes_pixels)."""
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
            print(f"  slot {slot} no mapeado — ignorado")
            continue

        png = RACERS / folder / "icon.png"
        if not png.exists():
            print(f"  falta {png} — slot {slot} ignorado")
            continue

        px_x, px_y, clut_x, clut_y = SLOTS[slot]
        pix, clut = pack_icon(Image.open(png))

        # Bloque de píxeles: 11 halfwords x 26 rows × 2 bytes = 572 bytes.
        # LoadImage lo trata como 16bpp (w*h*2) y copia bytes literales.
        blocks.append((px_x, px_y, ICON_W // 4, ICON_H, pix))

        # Bloque de CLUT: 16 halfwords = 16 pixels 16bpp en 1 fila.
        blocks.append((clut_x, clut_y, 16, 1, clut))

    if not blocks:
        print(f"  page_{page_num}.vrm: 0 bloques — no se escribe")
        return

    dst = RACERS / f"page_{page_num}.vrm"
    size = write_vrm(dst, blocks)
    print(f"  {dst.name}: {len(blocks) // 2} iconos "
          f"({len(blocks)} bloques), {size} bytes")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", type=int, default=None,
                    help="Construir solo esta página")
    args = ap.parse_args()

    if not (RACERS / "roster.txt").exists():
        sys.exit(f"No existe {RACERS / 'roster.txt'}")

    pages = parse_roster()

    for page_num, slots in sorted(pages.items()):
        if page_num == 0:
            continue
        if args.page is not None and args.page != page_num:
            continue
        build_page(page_num, slots)

    print("Listo.")


if __name__ == "__main__":
    main()