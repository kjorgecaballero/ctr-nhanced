"""Convert texture_uploads.json to a standalone VRM file."""
import json, struct, sys
from pathlib import Path


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        print("Usage: python make_racer_vrm.py <texture_uploads.json> <output.vrm>")
        sys.exit(1)

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])

    uploads = json.loads(src.read_text())
    print(f"Blocks: {len(uploads)}")

    out = bytearray(struct.pack('<I', 0x20))

    for u in uploads:
        name = u['name']
        x, y, w, h = u['rect']
        pixels = bytes.fromhex(u['bytes'])
        size_bytes = w * h * 2
        assert size_bytes == len(pixels), (name, len(pixels), size_bytes)
        assert size_bytes % 4 == 0, (name, 'size not multiple of 4', size_bytes)

        u0  = size_bytes | 0x14
        u12 = size_bytes | 0x0c
        u8  = 0x00000002

        out.extend(struct.pack('<IIIIHHHH', u0, 0x10, u8, u12, x, y, w, h))
        out.extend(pixels)

    dst.write_bytes(out)
    print(f"Written: {dst} ({len(out)} bytes)")


if __name__ == '__main__':
    main()