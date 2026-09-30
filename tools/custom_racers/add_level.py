#!/usr/bin/env python3
"""
Add a custom level to the CTR Native custom level system.

Usage:
    # Add a new track from CTR Editor exports
    python add_level.py --lev track.lev --vrm track.vrm \
                        --name "My Track" [--music song.wav]

    # Advanced: replace a retail slot
    python add_level.py --lev track.lev --vrm track.vrm \
                        --name "My Track" --replace crash_cove

    # List existing tracks
    python add_level.py --list

    # Delete a track
    python add_level.py --delete my_track
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

# Repo root: this file lives in tools/custom_racers/.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LEVELS_ROOT = os.path.join(REPO_ROOT, "assets", "mods", "levels")

# Matches C-side s_retailLevelNames[].
RETAIL_TRACKS = [
    "crash_cove", "mystery_caves", "sewer_speedway", "roo_tubes",
    "slide_coliseum", "turbo_track", "coco_park", "tiger_temple",
    "papu_pyramid", "dingo_canyon", "polar_pass", "tiny_arena",
    "dragon_mines", "blizzard_bluff", "hot_air_skyway",
    "cortex_castle", "n_gin_labs", "oxide_station",
]
REPLACE_TRACKS = RETAIL_TRACKS  # excludes main_menu


def slugify(name):
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s or "custom_track"


def has_ffmpeg():
    return shutil.which("ffmpeg") is not None


def encode_music(wav_path, folder):
    if not has_ffmpeg():
        print("WARN: ffmpeg not in PATH — music skipped", file=sys.stderr)
        return None, None

    music_dir = os.path.join(folder, "music")
    os.makedirs(music_dir, exist_ok=True)
    ogg = os.path.join(music_dir, "music.ogg")
    ogg_final = os.path.join(music_dir, "music_final.ogg")

    base = ["ffmpeg", "-y", "-i", wav_path,
            "-c:a", "libvorbis", "-q:a", "6",
            "-ar", "22050", "-ac", "2"]

    r = subprocess.run(base + [ogg], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ERROR: ffmpeg (music.ogg) failed:\n{r.stderr[-400:]}",
              file=sys.stderr)
        return None, None

    r = subprocess.run(base + ["-filter_complex", "atempo=1.12", ogg_final],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"WARN: ffmpeg (music_final.ogg) failed:\n{r.stderr[-400:]}",
              file=sys.stderr)
        return "music/music.ogg", None

    return "music/music.ogg", "music/music_final.ogg"


def cmd_add(args):
    if not os.path.isfile(args.lev):
        print(f"ERROR: LEV not found: {args.lev}", file=sys.stderr)
        return 1
    if not os.path.isfile(args.vrm):
        print(f"ERROR: VRM not found: {args.vrm}", file=sys.stderr)
        return 1

    slug = args.slug or slugify(args.name)
    folder = os.path.join(LEVELS_ROOT, slug)

    if os.path.isdir(folder) and not args.force:
        ans = input(f"'{slug}' already exists. Overwrite? [y/N] ").strip().lower()
        if ans != "y":
            print("Aborted.")
            return 1
        shutil.rmtree(folder)

    os.makedirs(os.path.join(folder, "1p"), exist_ok=True)
    shutil.copy2(args.lev, os.path.join(folder, "1p", "data.lev"))
    shutil.copy2(args.vrm, os.path.join(folder, "1p", "data.vrm"))

    music_rel = music_final_rel = None
    if args.music:
        if not os.path.isfile(args.music):
            print(f"WARN: music WAV not found: {args.music}", file=sys.stderr)
        else:
            music_rel, music_final_rel = encode_music(args.music, folder)

    manifest = {
        "id": slug,
        "name": args.name,
        "prim_mem": args.prim_mem,
        "force_hi_lod": True,
        "base": args.base or "crash_cove",
    }
    if args.replace:
        if args.replace not in REPLACE_TRACKS:
            print(f"ERROR: unknown replace target '{args.replace}'",
                  file=sys.stderr)
            print(f"  valid: {', '.join(REPLACE_TRACKS)}", file=sys.stderr)
            return 1
        manifest["replace"] = args.replace
    if music_rel:
        manifest["music"] = music_rel
    if music_final_rel:
        manifest["music_final"] = music_final_rel

    with open(os.path.join(folder, "level.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    mode = "replace" if args.replace else "additional"
    print(f"OK: '{slug}' ({mode})")
    print(f"    folder:  {folder}")
    print(f"    manifest: {os.path.join(folder, 'level.json')}")
    if music_rel:
        print(f"    music:   {music_rel}")
    print()
    print("Next: launch the game. The track will appear in Track Select.")
    return 0


def cmd_list(args):
    if not os.path.isdir(LEVELS_ROOT):
        print("(no levels folder yet)")
        return 0
    any_found = False
    for slug in sorted(os.listdir(LEVELS_ROOT)):
        manifest = os.path.join(LEVELS_ROOT, slug, "level.json")
        if not os.path.isfile(manifest):
            continue
        with open(manifest, "r", encoding="utf-8") as f:
            data = json.load(f)
        mode = f"replace:{data['replace']}" if data.get("replace") else "additional"
        music = " +music" if data.get("music") else ""
        print(f"  {slug:24s}  {data.get('name', slug):24s}  [{mode}]{music}")
        any_found = True
    if not any_found:
        print("(no tracks)")
    return 0


def cmd_delete(args):
    folder = os.path.join(LEVELS_ROOT, args.delete)
    if not os.path.isdir(folder):
        print(f"ERROR: not found: {folder}", file=sys.stderr)
        return 1
    shutil.rmtree(folder)
    print(f"Deleted: {args.delete}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lev", help="Path to LEV file")
    ap.add_argument("--vrm", help="Path to VRM file")
    ap.add_argument("--name", help="Display name")
    ap.add_argument("--music", help="Path to WAV (optional)")
    ap.add_argument("--slug", help="Folder slug (default: auto from name)")
    ap.add_argument("--replace", help="Replace this retail track (default: additional)")
    ap.add_argument("--base", help="Base template for gameplay (default: crash_cove)")
    ap.add_argument("--prim-mem", type=int, default=0x300000,
                    help="Primitive buffer size (default: 0x300000 = 3 MB)")

    ap.add_argument("--force", action="store_true",
                    help="Overwrite without prompting")
    ap.add_argument("--list", action="store_true", help="List existing tracks")
    ap.add_argument("--delete", metavar="SLUG", help="Delete a track")

    args = ap.parse_args()

    if args.list:
        return cmd_list(args)
    if args.delete:
        return cmd_delete(args)
    if not (args.lev and args.vrm and args.name):
        ap.error("--lev, --vrm and --name are required for add")
    return cmd_add(args)


if __name__ == "__main__":
    sys.exit(main())