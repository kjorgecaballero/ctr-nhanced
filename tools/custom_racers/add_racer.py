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
    ap.add_argument("slot", type=int, help="slot within the page (0..17 for pages 1..8; 16..17 for page 0)")
    ap.add_argument("engine",         choices=sorted(VALID_ENGINES))
    ap.add_argument("display_name",   help="label shown in character select")
    ap.add_argument("--icon", default=None, help="optional path to icon.png")
    ap.add_argument("--color", default=None,
                    help="optional minimap color #RRGGBB")
    ap.add_argument("--mask", choices=["good", "bad"], default="good",
                    help="Aku Aku (good, default) or Uka Uka (bad)")
    ap.add_argument("--wheels", choices=["yes", "no"], default="yes",
                    help="wheels visible (default) or hidden (Oxide-style)")
    ap.add_argument("--no-clean-stale", action="store_true",
                    help="keep same-slug entries on other slots of the same page "
                         "(default: remove them, so moving a racer to a new slot "
                         "does not leave the old entry orphaned)")
    ap.add_argument("--sentinel", action="store_true",
                    help="emit Sentinel CLUT textures instead of the VRAM "
                         "atlas. Skips textures.vrm and copies sentinel_NN.bin "
                         "into the racer folder. Requires the C-side runtime "
                         "to support sentinel_00.bin (commit 95cf1cf70+)")
    args = ap.parse_args()

    # Validate arguments before touching the filesystem.
    if not (0 <= args.page <= 8):
        sys.exit("ERROR: page must be 0..8")
    if args.page == 0:
        if args.slot not in (16, 17):
            sys.exit("ERROR: page 0 accepts only custom slots 16 and 17")
    else:
        if not (0 <= args.slot <= 17):
            sys.exit("ERROR: slot must be 0..17 for pages 1..8")

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
    # Clear sentinel side-cars from any previous build in TOOLS. Both
    # branches need this: sentinel mode copies the .bin to dest, VRM
    # mode regenerates textures.vrm and would otherwise let TOOLS
    # accumulate orphan .png files from the last sentinel run.
    for stale in list(TOOLS.glob("sentinel_*.bin")) + \
                 list(TOOLS.glob("sentinel_*.png")):
        stale.unlink()
    for s in range(4):
        out_name = f"model_p{s}.ctr"
        cmd = [sys.executable, TOOLS / "build_character.py",
               src, slug, out_name, "--player_slot", str(s)]
        if args.sentinel:
            cmd.append("--sentinel")
        run(cmd)
        shutil.copy(TOOLS / out_name, dest / out_name)

    # 2. VRM path (default) OR Sentinel side-car copy. Never both.
    if args.sentinel:
        print("--- sentinel mode: textures.vrm skipped ---")
        for stale in list(dest.glob("sentinel_*.bin")) + \
                     list(dest.glob("sentinel_*.png")):
            stale.unlink()
        bins = sorted(TOOLS.glob("sentinel_*.bin"))
        for b in bins:
            shutil.copy(b, dest / b.name)
        print(f"  copied {len(bins)} sentinel_*.bin -> {dest}")
        # Cleanup: canonical copies are already in dest/. Wipe the
        # TOOLS working files (bins + debug PNGs) so they don't
        # accumulate between exports.
        for stale in list(TOOLS.glob("sentinel_*.bin")) + \
                     list(TOOLS.glob("sentinel_*.png")):
            stale.unlink()
    else:
        print("--- building textures.vrm ---")
        for stale in list(dest.glob("sentinel_*.bin")) + \
                     list(dest.glob("sentinel_*.png")):
            stale.unlink()
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
    # Two dedup rules, applied in order:
    #   (a) (page, slot): the target slot is replaced in place, regardless
    #       of the previous slug — a different custom can take over a slot.
    #   (b) (slug, page): any OTHER slot on the same page that had this
    #       slug is removed, so moving a racer to a new slot doesn't leave
    #       the old entry orphaned. Controlled by --no-clean-stale.
    # A slug may still live on multiple PAGES (page 0 + page 1) because
    # rule (b) is scoped to a single page.
    roster_path = RACERS / "roster.txt"
    lines = roster_path.read_text().splitlines()
    new_line = f"{args.page}\t{args.slot}\t{slug}\t{args.engine}\t\"{args.display_name}\""
    if color is not None:
        new_line += f"\t{color}"
    new_line += f"\tmask={args.mask}"
    new_line += f"\twheels={args.wheels}"

    def _parse_ps(line):
        parts = line.split()
        if len(parts) < 3:
            return None
        try:
            return int(parts[0]), int(parts[1]), parts[2]
        except ValueError:
            return None

    cleaned = []
    updated = False
    for l in lines:
        ps = _parse_ps(l)
        if ps is None:
            cleaned.append(l)
            continue
        line_page, line_slot, line_slug = ps
        # Rule (a): replace the target slot in place.
        if line_page == args.page and line_slot == args.slot:
            cleaned.append(new_line)
            updated = True
            continue
        # Rule (b): drop stale same-slug entries on the same page.
        if (not args.no_clean_stale) and line_page == args.page and line_slug == slug:
            print(f"  removing stale entry: page {line_page} slot {line_slot} ({line_slug})")
            continue
        cleaned.append(l)
    if not updated:
        cleaned.append(new_line)
    roster_path.write_text("\n".join(cleaned) + "\n")
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