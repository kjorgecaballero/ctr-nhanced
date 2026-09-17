"""Add a custom racer end-to-end from a source_mesh.json.

Usage:
    python add_racer.py <slug> <source_mesh.json> <page> <slot> <engine> "<Display Name>" [--icon <icon.png>]

Example:
    python add_racer.py ernest ../native_fork/racers/source_mesh_ernest.json 1 3 SPEED "Ernest"

Runtime output goes to <repo>/nhanced/assets/mods/racers/<slug>/
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

TOOLS  = Path(__file__).resolve().parent
ROOT   = TOOLS.parents[1]
RACERS = ROOT / "assets" / "mods" / "racers"
VALID_ENGINES = {"SPEED", "BALANCED", "ACCEL", "TURN"}


def run(cmd, cwd=TOOLS, quiet=False):
    printable = ' '.join(str(c) for c in cmd)
    if not quiet:
        print(f"$ {printable}")
    r = subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd),
        stdout=subprocess.DEVNULL if quiet else None,
    )
    if r.returncode != 0:
        sys.exit(f"FAILED (exit {r.returncode}): {printable}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug",           help="folder name and internal .ctr name, e.g. 'ernest'")
    ap.add_argument("source_mesh",    help="path to source_mesh_<slug>.json")
    ap.add_argument("page", type=int, help="roster page (0 = originals page, slots 16-17 only; 1..8 = custom pages)")
    ap.add_argument("slot", type=int, help="slot within the page (0..15 for pages 1..8; 16..17 for page 0)")
    ap.add_argument("engine",         choices=sorted(VALID_ENGINES))
    ap.add_argument("display_name",   help="label shown in character select")
    ap.add_argument("--icon", default=None, help="optional path to icon.png")
    ap.add_argument("--color", default=None,
                    help="optional minimap color #RRGGBB")
    ap.add_argument("--mask", choices=["good", "bad"], default="good",
                    help="Aku Aku (good, default) or Uka Uka (bad)")
    ap.add_argument("--wheels", choices=["yes", "no"], default="yes",
                    help="wheels visible (default) or hidden (Oxide-style)")
    args = ap.parse_args()

    # Validate arguments before touching the filesystem.
    if not (0 <= args.page <= 8):
        sys.exit("ERROR: page must be 0..8")
    if args.page == 0:
        if args.slot not in (16, 17):
            sys.exit("ERROR: page 0 accepts only custom slots 16 and 17")
    else:
        if not (0 <= args.slot <= 15):
            sys.exit("ERROR: slot must be 0..15 for pages 1..8")

    color = args.color
    if color is not None:
        if not re.fullmatch(r"#?[0-9A-Fa-f]{6}", color):
            sys.exit("ERROR: --color must be #RRGGBB or RRGGBB")
        if not color.startswith("#"):
            color = "#" + color
    else:
        color = None

    slug = args.slug
    src  = Path(args.source_mesh).resolve()
    icon = Path(args.icon).resolve() if args.icon else None

    if not src.exists():
        sys.exit(f"ERROR: source_mesh not found: {src}")
    if icon and not icon.exists():
        sys.exit(f"ERROR: icon not found: {icon}")

    dest = RACERS / slug
    dest.mkdir(parents=True, exist_ok=True)
    print(f"source:  {src}")
    print(f"runtime: {dest}")
    print()

    # 1. Build 4 .ctr files
    for s in range(4):
        out_name = f"model_p{s}.ctr"
        run([sys.executable, TOOLS / "build_character.py",
             src, slug, out_name, "--player_slot", str(s)])
        shutil.copy(TOOLS / out_name, dest / out_name)

    # 2. Regenerate base p0 + textures.vrm
    print("--- building textures.vrm ---")
    run([sys.executable, TOOLS / "build_character.py",
         src, slug, "model_p0.ctr", "--player_slot", "0"], quiet=True)
    run([sys.executable, TOOLS / "make_racer_vrm.py",
         TOOLS / "texture_uploads.json", TOOLS / "textures.vrm"])
    shutil.copy(TOOLS / "textures.vrm", dest / "textures.vrm")

    # 3. Icon
    if icon:
        src_abs = icon.resolve()
        dst_abs = (dest / "icon.png").resolve()
        if src_abs != dst_abs:
            shutil.copy(icon, dest / "icon.png")
            print(f"icon copied -> {dest / 'icon.png'}")
        else:
            print(f"icon already in place: {dst_abs}")
    elif not (dest / "icon.png").exists():
        print(f"WARNING: no icon.png for '{slug}'; character select will show a blank cell")

    # 4. roster.txt
    roster_path = RACERS / "roster.txt"
    lines = roster_path.read_text().splitlines()
    new_line = f"{args.page}\t{args.slot}\t{slug}\t{args.engine}\t\"{args.display_name}\""
    if color is not None:
        new_line += f"\t{color}"
    new_line += f"\tmask={args.mask}"
    new_line += f"\twheels={args.wheels}"
    updated = False
    for i, l in enumerate(lines):
        parts = l.split()
        if len(parts) >= 3 and parts[2] == slug:
            lines[i] = new_line
            updated = True
            break
    if not updated:
        lines.append(new_line)
    roster_path.write_text("\n".join(lines) + "\n")
    print(f"roster.txt {'updated' if updated else 'appended'}: {slug}")

    # 5. Regenerate page icons
    run([sys.executable, TOOLS / "build_icons.py", "--page", str(args.page)])

    print()
    print("=" * 64)
    print(f"DONE  {slug}  ->  page {args.page}, slot {args.slot}, {args.engine}")
    print(f"      {dest}")
    print("=" * 64)


if __name__ == "__main__":
    main()