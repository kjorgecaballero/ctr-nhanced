\
"""Build a .bin (RGBA8 + <II w h> header) from a PNG for the Sentinel
texture path. Used by the mask HUD icon (see Mask tab in the addon).

Usage:
    python build_icon_bin.py <input.png> <output.bin>

The output format matches sentinel_NN.bin: u32 width, u32 height,
then width*height*4 bytes of RGBA8.
"""
import struct
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("ERROR: Pillow is required (pip install pillow)")


def main():
    if len(sys.argv) != 3:
        sys.exit(f"Usage: {sys.argv[0]} <input.png> <output.bin>")

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])

    if not src.is_file():
        sys.exit(f"ERROR: input not found: {src}")

    img = Image.open(src).convert("RGBA")
    w, h = img.size

    if w == 0 or h == 0 or w > 4096 or h > 4096:
        sys.exit(f"ERROR: bad size {w}x{h} (must be 1..4096)")

    data = img.tobytes("raw", "RGBA")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(struct.pack("<II", w, h) + data)
    print(f"Wrote {dst} ({w}x{h}, {len(data)} bytes RGBA)")


if __name__ == "__main__":
    main()
