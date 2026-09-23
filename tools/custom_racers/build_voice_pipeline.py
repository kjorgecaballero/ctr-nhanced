#!/usr/bin/env python3
"""build_voice_pipeline.py - Encode custom voicelines + podium music,
   patch ENG.XNF.

Voice track base for a racer at roster index i = 314 + i*18.
Event index e -> track 314 + i*18 + e.

Event layout (18 slots, mirrors NATIVE_VOICE_EVENT_* in
include/platform/native_custom_racer.h):

    Gameplay, 8 groups x 2 variants = 16 slots:
      slot  0 = boost_01       slot  1 = boost_02
      slot  2 = hurt_01        slot  3 = hurt_02
      slot  4 = spin_01        slot  5 = spin_02
      slot  6 = jump_01        slot  7 = jump_02
      slot  8 = trap_01        slot  9 = trap_02
      slot 10 = protected_01   slot 11 = protected_02
      slot 12 = overtake_01    slot 13 = overtake_02
      slot 14 = attack_01      slot 15 = attack_02
    Menu, 2 events x 1 variant = 2 slots:
      slot 16 = menu_yes       slot 17 = menu_ouch

Music track base for a racer at roster index i = 13 + i.
One track per custom (rank 0 podium music). Retail MUSIC occupies
xaIDs 0..12; custom MUSIC starts at 13.

XNF layout (post-build):

    [MUSIC retail (13)]         xaID 0..12      physical 0..12
    [MUSIC custom (N)]          xaID 13..12+N   physical 13..12+N
    [EXTRA retail (87)]         xaID 0..86      physical 13+N..99+N
    [GAME retail (764)]         xaID 0..763     physical 100+N..863+N
    [GAME custom voices (V)]    xaID 314..      physical 864+N..863+N+V

If N == 0 the output is byte-identical to the voice-only pipeline.

Banks: voices go to XA/ENG/GAME/S{18+}.XA, music to
XA/MUSIC/S{18+}.XA (separate dirs, same counter — no collision).

Usage:
    python tools/custom_racers/build_voice_pipeline.py
    python tools/custom_racers/build_voice_pipeline.py --restore
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

ROOT             = TOOLS.parents[1]
RACERS           = ROOT / "assets" / "mods" / "racers"
XNF              = ROOT / "assets" / "XA" / "ENG.XNF"
BANKS            = ROOT / "assets" / "XA" / "ENG" / "GAME"
MUSIC_BANKS      = ROOT / "assets" / "XA" / "MUSIC"
SIDECAR          = XNF.parent / (XNF.name + ".voices.json")
MUSIC_SIDECAR    = XNF.parent / (XNF.name + ".music.json")
CACHE_DIR        = ROOT / "assets" / "XA" / ".voices_cache"
MUSIC_CACHE_DIR  = ROOT / "assets" / "XA" / ".music_cache"

VOICE_TRACK_BASE  = 314
VOICE_EVENT_COUNT = 18
VOICE_BANK_BASE   = 18
CHUNK_SIZE        = 8   # XA Form2 audio channels per bank

MUSIC_TRACK_BASE  = 13
MUSIC_BANK_BASE   = 18

EVENTS = [
    "boost_01", "boost_02",
    "hurt_01",  "hurt_02",
    "spin_01",  "spin_02",
    "jump_01",  "jump_02",
    "trap_01",  "trap_02",
    "protected_01", "protected_02",
    "overtake_01",  "overtake_02",
    "attack_01",    "attack_02",
    "menu_yes", "menu_ouch",
]

LEGACY_FALLBACKS = {
    "boost_01":     "boost",
    "hurt_01":      "hurt",
    "spin_01":      "spin",
    "jump_01":      "jump",
    "trap_01":      "trap",
    "protected_01": "protected",
    "overtake_01":  "overtake",
    "attack_01":    "attack",
}

XNF_HEADER      = 0x44
XNF_MAGIC       = 0x464e4958
XNF_MAGIC2      = 102
XA_NUM_TYPES    = 3
OFF_NUM_XAS     = 0x0c
OFF_NUM_TRACKS  = 0x10
OFF_AUX         = 0x1c
OFF_SONGS_MUSIC = 0x2c
OFF_SONGS_EXTRA = 0x30
OFF_SONGS_GAME  = 0x34
OFF_FIRST_MUSIC = 0x38
OFF_FIRST_EXTRA = 0x3c
OFF_FIRST_GAME  = 0x40
SECTOR          = xa_codec.XA_FORM2_SECTOR

SIDECAR_VERSION = 3
MUSIC_SIDECAR_VERSION = 1


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
    payload = "\n".join(f"{p}|{s}|{slug}" for p, s, slug in roster)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def write_sidecar(roster, banks_written, tracks_written):
    data = {
        "version": SIDECAR_VERSION,
        "roster_hash": roster_fingerprint(roster),
        "roster_count": len(roster),
        "event_count": VOICE_EVENT_COUNT,
        "variant_count": 2,
        "chunk_size": CHUNK_SIZE,
        "banks_written": banks_written,
        "tracks_written": tracks_written,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    SIDECAR.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Wrote {SIDECAR.name} (hash {data['roster_hash']})")


def write_music_sidecar(roster, banks_written, tracks_written):
    data = {
        "version": MUSIC_SIDECAR_VERSION,
        "roster_hash": roster_fingerprint(roster),
        "roster_count": len(roster),
        "track_base": MUSIC_TRACK_BASE,
        "bank_base": MUSIC_BANK_BASE,
        "banks_written": banks_written,
        "tracks_written": tracks_written,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    MUSIC_SIDECAR.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Wrote {MUSIC_SIDECAR.name} ({banks_written} bank(s))")


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
    h = hashlib.sha256()
    with open(wav_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def encode_track_cached(wav_path, channel, verbose=False, cache_dir=None):
    cache = cache_dir if cache_dir is not None else CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)
    sha = _wav_sha(wav_path)
    cache_path = cache / f"{sha}_c{channel}.xa"
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


def build_banks(track_bytes_list):
    banks = []
    counts = []
    for start in range(0, len(track_bytes_list), CHUNK_SIZE):
        chunk = list(track_bytes_list[start:start + CHUNK_SIZE])
        while len(chunk) < CHUNK_SIZE:
            chunk.append(None)
        bank, n_audio = build_bank(chunk)
        banks.append(bank)
        counts.append(n_audio)
    return banks, counts


def _pack_entry(entry):
    ch, fn, se = entry
    return struct.pack('<BBH', ch & 0xFF, fn & 0xFF, se & 0xFFFF)


def patch_xnf(original, music_tracks, voice_tracks):
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
    songs_m    = struct.unpack_from('<I', original, OFF_SONGS_MUSIC)[0]
    songs_g    = struct.unpack_from('<I', original, OFF_SONGS_GAME)[0]
    first_m    = struct.unpack_from('<I', original, OFF_FIRST_MUSIC)[0]
    first_e    = struct.unpack_from('<I', original, OFF_FIRST_EXTRA)[0]
    first_g    = struct.unpack_from('<I', original, OFF_FIRST_GAME)[0]

    n_music  = len(music_tracks)
    n_voice  = len(voice_tracks)
    banks_m  = len({fn for _, fn, _ in music_tracks if fn})
    banks_v  = len({fn for _, fn, _ in voice_tracks if fn})
    n_banks  = banks_m + banks_v

    header = bytearray(original[:XNF_HEADER])
    struct.pack_into('<I', header, OFF_NUM_XAS,     num_xas    + n_banks)
    struct.pack_into('<I', header, OFF_NUM_TRACKS,  num_tracks + n_music + n_voice)
    struct.pack_into('<I', header, OFF_AUX,         aux        + n_banks * 4)
    struct.pack_into('<I', header, OFF_SONGS_MUSIC, songs_m    + n_music)
    struct.pack_into('<I', header, OFF_SONGS_GAME,  songs_g    + n_voice)
    struct.pack_into('<I', header, OFF_FIRST_EXTRA, first_e    + n_music)
    struct.pack_into('<I', header, OFF_FIRST_GAME,  first_g    + n_music)
    # firstSongMUSIC stays at 0. firstSongEXTRA/GAME shift by n_music.

    xa_table_end    = XNF_HEADER + num_xas * 4
    track_table_end = xa_table_end + num_tracks * 4
    xa_table    = original[XNF_HEADER:xa_table_end]
    track_table = original[xa_table_end:track_table_end]

    off_mus = (first_m - first_m) * 4
    off_ext = (first_e - first_m) * 4
    off_gam = (first_g - first_m) * 4
    music_retail = track_table[off_mus:off_ext]
    extra_retail = track_table[off_ext:off_gam]
    game_retail  = track_table[off_gam:]

    out = bytearray()
    out += header
    out += xa_table
    out += bytes(n_banks * 4)
    out += music_retail
    for e in music_tracks:
        out += _pack_entry(e)
    out += extra_retail
    out += game_retail
    for e in voice_tracks:
        out += _pack_entry(e)
    return bytes(out)


def cmd_restore():
    bak = XNF.with_suffix(".XNF.bak")
    if bak.is_file():
        shutil.copy(bak, XNF)
        print(f"Restored {XNF}")

    for b in sorted(BANKS.glob("S*.XA")):
        try:
            num = int(b.stem[1:])
        except ValueError:
            continue
        if num >= VOICE_BANK_BASE:
            b.unlink()
            print(f"Removed {b.name}")

    if MUSIC_BANKS.is_dir():
        for b in sorted(MUSIC_BANKS.glob("S*.XA")):
            try:
                num = int(b.stem[1:])
            except ValueError:
                continue
            if num >= MUSIC_BANK_BASE:
                b.unlink()
                print(f"Removed {MUSIC_BANKS.name}/{b.name}")

    if SIDECAR.is_file():
        SIDECAR.unlink()
        print(f"Removed {SIDECAR.name}")
    if MUSIC_SIDECAR.is_file():
        MUSIC_SIDECAR.unlink()
        print(f"Removed {MUSIC_SIDECAR.name}")
    # Caches are intentionally NOT cleaned here.


def _roster_filter(page, slot):
    if page == 0:
        return 16 <= slot <= 17
    if page >= 1:
        return 0 <= slot <= 17
    return False


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

    # ------- MUSIC -------
    music_entries = {}
    music_bank_idx = 0

    for i, (page, slot, slug) in enumerate(roster):
        if not _roster_filter(page, slot):
            continue
        wav = RACERS / slug / "music" / "podium.wav"
        if not wav.is_file():
            continue
        data = encode_track_cached(wav, channel=0, verbose=verbose,
                                   cache_dir=MUSIC_CACHE_DIR)
        bank, counts = build_bank([data] + [None] * (CHUNK_SIZE - 1))
        fn = MUSIC_BANK_BASE + music_bank_idx
        MUSIC_BANKS.mkdir(parents=True, exist_ok=True)
        (MUSIC_BANKS / f"S{fn:02d}.XA").write_bytes(bank)
        se = (counts[0] + 1) * 16
        music_entries[MUSIC_TRACK_BASE + i] = (0, fn, se)
        music_bank_idx += 1
        print(f"  [{i}] {slug}: music S{fn:02d}.XA, xaID {MUSIC_TRACK_BASE + i}")

    music_tracks = []
    if music_entries:
        mx = max(music_entries)
        for t in range(MUSIC_TRACK_BASE, mx + 1):
            music_tracks.append(music_entries.get(t, (0, 0, 0)))

    # ------- VOICES -------
    voice_entries = {}
    bank_idx = 0
    max_track = VOICE_TRACK_BASE - 1

    for i, (page, slot, slug) in enumerate(roster):
        if not _roster_filter(page, slot):
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
            if not wav.is_file():
                legacy = LEGACY_FALLBACKS.get(event)
                if legacy is not None:
                    cand = voices_dir / f"{legacy}.wav"
                    if cand.is_file():
                        wav = cand
            if wav.is_file():
                track_bytes.append(
                    encode_track_cached(wav, channel=len(track_bytes) % CHUNK_SIZE,
                                        verbose=verbose)
                )
                any_present = True
            else:
                track_bytes.append(None)

        if not any_present:
            if verbose:
                print(f"  [{i}] {slug}: no WAVs, skip")
            continue

        banks, chunk_counts = build_banks(track_bytes)
        n_chunks = len(banks)
        base_file = VOICE_BANK_BASE + bank_idx

        for ci, bank in enumerate(banks):
            fn = base_file + ci
            bank_path = BANKS / f"S{fn:02d}.XA"
            bank_path.parent.mkdir(parents=True, exist_ok=True)
            bank_path.write_bytes(bank)

        base = VOICE_TRACK_BASE + i * VOICE_EVENT_COUNT
        for e_idx in range(VOICE_EVENT_COUNT):
            ci = e_idx // CHUNK_SIZE
            ch = e_idx % CHUNK_SIZE
            n_sectors = chunk_counts[ci][ch]
            sector_end = (n_sectors + 1) * 16
            fn = base_file + ci
            voice_entries[base + e_idx] = (ch, fn, sector_end)
            if base + e_idx > max_track:
                max_track = base + e_idx

        bank_idx += n_chunks
        print(f"  [{i}] {slug}: {n_chunks} bank(s) (S{base_file:02d}+), "
              f"tracks {base}..{base+VOICE_EVENT_COUNT-1}")

    voice_tracks = []
    if voice_entries:
        for t in range(VOICE_TRACK_BASE, max_track + 1):
            voice_tracks.append(voice_entries.get(t, (0, 0, 0)))

    if not music_tracks and not voice_tracks:
        print("No tracks to add.")
        write_sidecar(roster, banks_written=0, tracks_written=0)
        write_music_sidecar(roster, banks_written=0, tracks_written=0)
        return

    new_xnf = patch_xnf(original, music_tracks, voice_tracks)
    XNF.write_bytes(new_xnf)
    print(f"\nPatched {XNF.name}: {len(original)} -> {len(new_xnf)}B, "
          f"+{len(music_tracks)} music, +{len(voice_tracks)} voice, "
          f"+{music_bank_idx + bank_idx} banks total")

    write_sidecar(roster, banks_written=bank_idx,
                  tracks_written=len(voice_tracks))
    write_music_sidecar(roster, banks_written=music_bank_idx,
                        tracks_written=len(music_tracks))


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