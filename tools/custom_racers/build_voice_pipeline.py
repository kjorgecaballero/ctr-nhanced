#!/usr/bin/env python3
"""build_voice_pipeline.py - Encode custom voicelines and patch ENG.XNF.

Track base for a racer at roster index i = 314 + i*8.
Event index e -> track 314 + i*8 + e.
Gaps (racers without voices) are written as null entries so the XNF
stays contiguous.

Usage:
    python tools/custom_racers/build_voice_pipeline.py            # build
    python tools/custom_racers/build_voice_pipeline.py --restore  # undo

After a successful build, writes a sidecar next to the XNF
(ENG.XNF.voices.json) containing a hash of the roster. The Blender
addon reads this sidecar to warn the user when the roster has changed
since the last build (VOICELINES-ROSTER-FINGERPRINT).

Also caches per-WAV XA encodes under assets/XA/.voices_cache/ so
subsequent builds skip the (slow) brute-force encoder when a WAV
hasn't changed. Keyed by SHA256 of the WAV contents + channel index.
"""
import argparse
import datetime
import hashlib
import json
import shutil
import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import xa_codec

ROOT      = TOOLS.parents[1]
RACERS    = ROOT / "assets" / "mods" / "racers"
XNF       = ROOT / "assets" / "XA" / "ENG.XNF"
BANKS     = ROOT / "assets" / "XA" / "ENG" / "GAME"
SIDECAR   = XNF.parent / (XNF.name + ".voices.json")
CACHE_DIR = ROOT / "assets" / "XA" / ".voices_cache"

VOICE_TRACK_BASE  = 314
VOICE_EVENT_COUNT = 8
VOICE_BANK_BASE   = 18
EVENTS = ["boost", "hurt", "spin", "jump",
          "trap", "protected", "overtake", "attack"]

XNF_HEADER      = 0x44
XNF_MAGIC       = 0x464e4958
XNF_MAGIC2      = 102
XA_NUM_TYPES    = 3
OFF_NUM_XAS     = 0x0c
OFF_NUM_TRACKS  = 0x10
OFF_AUX         = 0x1c
OFF_SONGS_GAME  = 0x34
SECTOR          = xa_codec.XA_FORM2_SECTOR

SIDECAR_VERSION = 1


def read_roster():
    path = RACERS / "roster.txt"
    if not path.is_file():
        sys.exit(f"roster.txt not found: {path}")
    out = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            page, slot = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        out.append((page, slot, parts[2]))
    return out


def roster_fingerprint(roster):
    """16-hex SHA256 of the roster in the exact order the pipeline
    iterates it. Any change to page, slot, or slug invalidates it."""
    payload = "\n".join(f"{p}|{s}|{slug}" for p, s, slug in roster)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def write_sidecar(roster, banks_written, tracks_written):
    data = {
        "version": SIDECAR_VERSION,
        "roster_hash": roster_fingerprint(roster),
        "roster_count": len(roster),
        "banks_written": banks_written,
        "tracks_written": tracks_written,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    SIDECAR.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Wrote {SIDECAR.name} (hash {data['roster_hash']})")


def silent_sector():
    s = bytearray(SECTOR)
    for g in range(18):
        off = 8 + g * 128
        s[off+0] = s[off+1] = s[off+2] = s[off+3] = 0x0C
    return bytes(s)


def encode_track(wav_path, channel):
    pcm, sr = xa_codec.read_wav(wav_path)
    if sr != xa_codec.SAMPLE_RATE:
        pcm = xa_codec.resample_linear(pcm, sr, xa_codec.SAMPLE_RATE)
    return xa_codec.encode_xa(pcm, channel=channel)


def _wav_sha(wav_path):
    """SHA256 of the file contents, chunked read so it works on large
    files without loading them fully into memory."""
    h = hashlib.sha256()
    with open(wav_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def encode_track_cached(wav_path, channel, verbose=False):
    """encode_track() with a disk cache keyed by (wav sha256, channel).

    Cache lives under assets/XA/.voices_cache/ and is NOT touched by
    --restore. Delete the directory to force a full re-encode."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    sha = _wav_sha(wav_path)
    cache_path = CACHE_DIR / f"{sha}_c{channel}.xa"
    if cache_path.is_file():
        if verbose:
            print(f"      cache hit: {wav_path.name} (ch={channel})")
        return cache_path.read_bytes()
    if verbose:
        print(f"      cache MISS: encoding {wav_path.name} (ch={channel})...")
    data = encode_track(wav_path, channel)
    cache_path.write_bytes(data)
    return data


def build_bank(track_bytes_list):
    silence = silent_sector()
    per_track = []
    for t in track_bytes_list:
        if t is None:
            per_track.append([])
        else:
            per_track.append([t[i:i+SECTOR] for i in range(0, len(t), SECTOR)])
    max_sectors = max((len(s) for s in per_track), default=0)
    n_blocks = max_sectors + 1
    out = bytearray()
    for block in range(n_blocks):
        is_last = (block == n_blocks - 1)
        for ch in range(16):
            if ch < 8:
                s_list = per_track[ch]
                sec = bytearray(s_list[block]) if block < len(s_list) else bytearray(silence)
                sub = bytes([1, ch, 0xE4 if is_last else 0x64, 0])
            else:
                sec = bytearray(SECTOR)
                sub = bytes([1, 15, 0xC8 if is_last else 0x48, 0])
            sec[:8] = sub * 2
            sec[-4:] = bytes(4)
            out.extend(sec)
    return bytes(out), [len(s) for s in per_track]


def patch_xnf(original, custom_tracks):
    if len(original) < XNF_HEADER:
        sys.exit("XNF too small")
    if struct.unpack_from('<I', original, 0)[0] != XNF_MAGIC:
        sys.exit("XNF magic mismatch")
    if struct.unpack_from('<I', original, 4)[0] != XNF_MAGIC2:
        sys.exit("XNF magic2 mismatch")
    if struct.unpack_from('<I', original, 8)[0] != XA_NUM_TYPES:
        sys.exit("XNF numTypes mismatch")

    num_xas    = struct.unpack_from('<I', original, OFF_NUM_XAS)[0]
    num_tracks = struct.unpack_from('<I', original, OFF_NUM_TRACKS)[0]
    aux        = struct.unpack_from('<I', original, OFF_AUX)[0]
    songs_g    = struct.unpack_from('<I', original, OFF_SONGS_GAME)[0]

    new_banks = sorted(set(fn for _, fn, _ in custom_tracks if fn != 0))
    n_banks   = len(new_banks)
    n_tracks  = len(custom_tracks)

    header = bytearray(original[:XNF_HEADER])
    struct.pack_into('<I', header, OFF_NUM_XAS,    num_xas + n_banks)
    struct.pack_into('<I', header, OFF_NUM_TRACKS, num_tracks + n_tracks)
    struct.pack_into('<I', header, OFF_AUX,        aux + n_banks)
    struct.pack_into('<I', header, OFF_SONGS_GAME, songs_g + n_tracks)

    xa_table_end    = XNF_HEADER + num_xas * 4
    track_table_end = xa_table_end + num_tracks * 4

    out = bytearray()
    out += header
    out += original[XNF_HEADER:xa_table_end]
    out += bytes(n_banks * 4)
    out += original[xa_table_end:track_table_end]
    for ch, fn, se in custom_tracks:
        out += struct.pack('<BBH', ch & 0xFF, fn & 0xFF, se & 0xFFFF)
    return bytes(out)


def cmd_restore():
    bak = XNF.with_suffix(".XNF.bak")
    if bak.is_file():
        shutil.copy(bak, XNF)
        print(f"Restored {XNF}")
    for b in sorted(BANKS.glob("S1[89].XA")) + sorted(BANKS.glob("S[2-9][0-9].XA")):
        b.unlink()
        print(f"Removed {b.name}")
    if SIDECAR.is_file():
        SIDECAR.unlink()
        print(f"Removed {SIDECAR.name}")
    # CACHE_DIR is intentionally NOT cleaned here. Delete it manually
    # if you want to force a full re-encode:
    #   rm -rf assets/XA/.voices_cache/


def cmd_build(verbose):
    if not XNF.is_file():
        sys.exit(f"XNF not found: {XNF} - run extract_xnf.py first")

    bak = XNF.with_suffix(".XNF.bak")
    if not bak.is_file():
        shutil.copy(XNF, bak)
        print(f"Backup: {bak}")
    original = bak.read_bytes()

    roster = read_roster()
    print(f"Roster: {len(roster)} entries")

    # track_id -> (channel, file_number, sector_end). 0 file_number = null.
    voice_entries = {}
    bank_idx = 0
    max_track = VOICE_TRACK_BASE - 1

    for i, (page, slot, slug) in enumerate(roster):
        # Mirror the C-side custom-ID check. Entries that don't produce a
        # custom ID get skipped on both sides, so the enumerate index
        # matches s_pageEntryCount - 1 in the C code.
        if page == 0:
            if slot < 16 or slot > 17:
                continue
        elif page >= 1:
            if slot < 0 or slot > 17:
                continue
        else:
            continue

        voices_dir = RACERS / slug / "voices"
        if not voices_dir.is_dir():
            if verbose:
                print(f"  [{i}] {slug}: no voices/, skip")
            continue

        track_bytes = []
        any_present = False
        for event in EVENTS:
            wav = voices_dir / f"{event}.wav"
            if wav.is_file():
                track_bytes.append(
                    encode_track_cached(wav, channel=len(track_bytes), verbose=verbose)
                )
                any_present = True
            else:
                track_bytes.append(None)

        if not any_present:
            if verbose:
                print(f"  [{i}] {slug}: no WAVs, skip")
            continue

        bank, n_audio = build_bank(track_bytes)
        file_number = VOICE_BANK_BASE + bank_idx
        bank_path = BANKS / f"S{file_number:02d}.XA"
        bank_path.parent.mkdir(parents=True, exist_ok=True)
        bank_path.write_bytes(bank)
        bank_idx += 1

        base = VOICE_TRACK_BASE + i * VOICE_EVENT_COUNT
        for e_idx in range(VOICE_EVENT_COUNT):
            sector_end = (n_audio[e_idx] + 1) * 16
            voice_entries[base + e_idx] = (e_idx, file_number, sector_end)
            if base + e_idx > max_track:
                max_track = base + e_idx

        print(f"  [{i}] {slug}: S{file_number:02d}.XA "
              f"({len(bank)}B), tracks {base}..{base+7}")

    if not voice_entries:
        print("No tracks to add.")
        write_sidecar(roster, banks_written=0, tracks_written=0)
        return

    # Pad from 314 to max_track. Roster indices without voices get null
    # entries (channel=0, fileNumber=0, sectorEnd=0). LookupXATrackInfo
    # returns 0 because numSectors=0, so CDSYS_XAPlay fails silently.
    custom_tracks = []
    for t in range(VOICE_TRACK_BASE, max_track + 1):
        custom_tracks.append(voice_entries.get(t, (0, 0, 0)))

    new_xnf = patch_xnf(original, custom_tracks)
    XNF.write_bytes(new_xnf)
    print(f"\nPatched {XNF.name}: {len(original)} -> {len(new_xnf)}B, "
          f"+{len(custom_tracks)} tracks, +{bank_idx} banks")

    write_sidecar(roster, banks_written=bank_idx, tracks_written=len(custom_tracks))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    if a.restore:
        cmd_restore()
    else:
        cmd_build(a.verbose)


if __name__ == "__main__":
    main()