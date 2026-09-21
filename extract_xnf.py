#!/usr/bin/env python3
"""Extract XA/ENG.XNF from the ctr-u.bin disc image to assets/XA/ENG.XNF.

After extraction, the engine (NativeAudio_XaSourceOpen) prefers the host
file via NativeAssets_ResolvePath, so the disc is no longer consulted for
the XNF. Banks stay on disc; only the XNF (and later, custom banks) live
on disk.

Requires: assets/ctr-u.bin
Outputs:  assets/XA/ENG.XNF
"""
import struct
import sys
from pathlib import Path

DISC = Path("assets/ctr-u.bin")

def detect_sector_size(size):
    for s in (2352, 2048):
        if size % s == 0:
            return s
    raise ValueError(f"size {size} not divisible by 2352 or 2048")

def read_sector(raw, sector, sector_size):
    off = sector * sector_size
    chunk = raw[off:off + sector_size]
    if sector_size == 2048:
        return chunk
    mode = chunk[15]
    if mode == 2:
        return chunk[24:24 + 2048]
    if mode == 1:
        return chunk[16:16 + 2048]
    raise ValueError(f"unknown sector mode {mode} at sector {sector}")

def read_at(raw, lba, size, sector_size):
    n = (size + 2047) // 2048
    return b"".join(read_sector(raw, lba + i, sector_size) for i in range(n))[:size]

def parse_dir_records(data, prefix=""):
    off = 0
    out = []
    while off < len(data):
        rec_len = data[off]
        if rec_len == 0:
            off = ((off // 2048) + 1) * 2048
            continue
        rec = data[off:off + rec_len]
        name_len = rec[32]
        name = rec[33:33 + name_len].decode("ascii", errors="replace")
        if name in ("\x00", "\x01"):
            off += rec_len
            continue
        if ";" in name:
            name = name.split(";")[0]
        lba = struct.unpack_from("<I", rec, 2)[0]
        size = struct.unpack_from("<I", rec, 10)[0]
        is_dir = bool(rec[25] & 0x02)
        out.append((prefix + name, lba, size, is_dir))
        off += rec_len
    return out

def walk_iso(raw, sector_size):
    pvd = read_sector(raw, 16, sector_size)
    if pvd[1:6] != b"CD001":
        raise ValueError(f"no CD001 at sector 16 (got {pvd[1:6].hex()})")
    root = pvd[156:156 + 34]
    root_lba = struct.unpack_from("<I", root, 2)[0]
    root_size = struct.unpack_from("<I", root, 10)[0]
    entries = {}
    def recurse(lba, size, prefix=""):
        data = read_at(raw, lba, size, sector_size)
        for name, elba, esize, is_dir in parse_dir_records(data, prefix):
            if is_dir:
                recurse(elba, esize, name + "/")
            else:
                entries[name] = (elba, esize)
    recurse(root_lba, root_size)
    return entries

def main():
    if not DISC.is_file():
        sys.exit(f"DISC not found: {DISC}")
    size = DISC.stat().st_size
    ss = detect_sector_size(size)
    print(f"Disc: {DISC} ({size} bytes, {ss}-byte sectors)")
    raw = DISC.read_bytes()

    head = raw[:16]
    if head[:12] == bytes([0x00] + [0xFF] * 10 + [0x00]):
        print("Sync pattern present (raw CD image)")
    else:
        print(f"WARN: no sync pattern, first 16 bytes: {head.hex()}")

    entries = walk_iso(raw, ss)
    print(f"Files in ISO: {len(entries)}")

    xa = {k: v for k, v in entries.items() if k.upper().startswith("XA/")}
    print(f"XA/* entries: {len(xa)}")
    for k in sorted(xa)[:25]:
        lba, sz = xa[k]
        print(f"  {k}  size={sz}  lba={lba}")

    target = None
    for k in xa:
        if k.upper() == "XA/ENG.XNF":
            target = k
            break
    if not target:
        for k in xa:
            if k.upper().endswith("ENG.XNF"):
                target = k
                break
    if not target:
        print("ERROR: ENG.XNF not found in ISO")
        return

    lba, sz = xa[target]
    data = read_at(raw, lba, sz, ss)
    out = Path("assets/XA/ENG.XNF")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"\nWrote {out} ({len(data)} bytes)")

    print(f"\n=== XNF header (68 bytes, 17 words) ===")
    for i in range(0, min(68, len(data)), 4):
        v = struct.unpack_from("<I", data, i)[0]
        print(f"  off {i:3} (0x{i:02x}): {v:12d}  0x{v:08x}")

if __name__ == "__main__":
    main()