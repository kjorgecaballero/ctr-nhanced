"""Add a custom racer end-to-end from a source_mesh.json."""
import argparse
import re
import shutil
import subprocess
import sys
import json
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


def generate_rot_bin(mesh, dest_dir):
    if not mesh.get("jump_rot_enable"):
        return
    import math, struct
    pitch = mesh.get("jump_rot_pitch", 0)
    roll  = mesh.get("jump_rot_roll", 0)
    yaw   = mesh.get("jump_rot_yaw", 0)
    pz    = mesh.get("jump_rot_pivot_z", 0.35)
    frames = mesh.get("jump_rot_frames", 4)
    
    c = [0, pz * 64, 0]
    
    blob = b""
    for i in range(frames):
        t = i / max(1, frames - 1)
        p_rad = math.radians(pitch * t)
        r_rad = math.radians(roll * t)
        y_rad = math.radians(yaw * t)
        
        cp, sp = math.cos(p_rad), math.sin(p_rad)
        cr, sr = math.cos(r_rad), math.sin(r_rad)
        cy, sy = math.cos(y_rad), math.sin(y_rad)
        
        B = [
            [cy*cr + sy*sp*sr, -cy*sr + sy*sp*cr, sy*cp],
            [cp*sr, cp*cr, -sp],
            [-sy*cr + cy*sp*sr, sy*sr + cy*sp*cr, cy*cp]
        ]
        
        Bc = [sum(B[r_][k]*c[k] for k in range(3)) for r_ in range(3)]
        v = [(c[k] - Bc[k]) * 256 for k in range(3)]
        
        blob += struct.pack("<4h", int(round(v[0])), int(round(v[1])), int(round(v[2])), 0)
        blob += struct.pack("<9h", *[int(round(B[r_][c_]*4096)) for r_ in range(3) for c_ in range(3)])
        blob += b"\0" * 6
    
    blob += b"\0" * 8
    with open(dest_dir / "rot.bin", "wb") as f:
        f.write(blob)
    print("  rot.bin generado (custom rotation)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug",           help="folder name and internal .ctr name")
    ap.add_argument("source_mesh",    help="path to source_mesh_<slug>.json")
    ap.add_argument("page", type=int, help="roster page")
    ap.add_argument("slot", type=int, help="slot within the page")
    ap.add_argument("engine",         choices=sorted(VALID_ENGINES))
    ap.add_argument("display_name",   help="label shown in character select")
    ap.add_argument("--icon", default=None, help="optional path to icon.png")
    ap.add_argument("--color", default=None, help="optional minimap color #RRGGBB")
    ap.add_argument("--mask", choices=["good", "bad", "custom_good", "custom_bad"],
                    default="good")
    ap.add_argument("--wheels", choices=["yes", "no"], default="yes")
    ap.add_argument("--rot", default="auto", help="kart rotation style")
    ap.add_argument("--no-clean-stale", action="store_true")
    ap.add_argument("--sentinel", action="store_true")
    args = ap.parse_args()

    if not (0 <= args.page <= 8):
        sys.exit("ERROR: page must be 0..8")
    if args.page == 0:
        if not (16 <= args.slot <= 23):
            sys.exit("ERROR: page 0 accepts only custom slots 16..23")
    else:
        if not (0 <= args.slot <= 23):
            sys.exit("ERROR: slot must be 0..23 for pages 1..8")

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

    # Load JSON to get rotation data
    try:
        mesh_data = json.loads(src.read_text(encoding="utf-8"))
    except Exception as e:
        sys.exit(f"ERROR: no se pudo leer el JSON: {e}")

    dest = RACERS / slug
    dest.mkdir(parents=True, exist_ok=True)
    print(f"source:  {src}")
    print(f"runtime: {dest}")
    print()

    # 1. Build 4 .ctr files
    for stale in list(TOOLS.glob("sentinel_*.bin")) + list(TOOLS.glob("sentinel_*.png")):
        stale.unlink()
    for s in range(4):
        out_name = f"model_p{s}.ctr"
        cmd = [sys.executable, TOOLS / "build_character.py",
               src, slug, out_name, "--player_slot", str(s)]
        if args.sentinel:
            cmd.append("--sentinel")
        run(cmd)
        shutil.copy(TOOLS / out_name, dest / out_name)

    # 2. VRM path OR Sentinel copy
    if args.sentinel:
        print("--- sentinel mode: textures.vrm skipped ---")
        for stale in list(dest.glob("sentinel_*.bin")) + list(dest.glob("sentinel_*.png")):
            stale.unlink()
        bins = sorted(TOOLS.glob("sentinel_*.bin"))
        for b in bins:
            shutil.copy(b, dest / b.name)
        print(f"  copied {len(bins)} sentinel_*.bin -> {dest}")
        for stale in list(TOOLS.glob("sentinel_*.bin")) + list(TOOLS.glob("sentinel_*.png")):
            stale.unlink()
    else:
        print("--- building textures.vrm ---")
        for stale in list(dest.glob("sentinel_*.bin")) + list(dest.glob("sentinel_*.png")):
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
        print(f"WARNING: no icon.png for '{slug}'")

    # 4. roster.txt
    roster_path = RACERS / "roster.txt"
    if roster_path.exists():
        lines = roster_path.read_text().splitlines()
    else:
        lines = []
    new_line = f"{args.page}\t{args.slot}\t{slug}\t{args.engine}\t\"{args.display_name}\""
    if color is not None:
        new_line += f"\t{color}"
    new_line += f"\tmask={args.mask}"
    new_line += f"\twheels={args.wheels}"
    new_line += f"\trot={args.rot}"

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
        if line_page == args.page and line_slot == args.slot:
            cleaned.append(new_line)
            updated = True
            continue
        if (not args.no_clean_stale) and line_slug == slug:
            print(f"  removing stale entry: page {line_page} slot {line_slot} ({line_slug})")
            continue
        cleaned.append(l)
    if not updated:
        cleaned.append(new_line)
    roster_path.write_text("\n".join(cleaned) + "\n")
    print(f"roster.txt {'updated' if updated else 'appended'}: {slug}")

    # Generar el rot.bin
    generate_rot_bin(mesh_data, dest)

    # 5. Regenerate page icons
    run([sys.executable, TOOLS / "build_icons.py", "--page", str(args.page)])

    print()
    print("=" * 64)
    print(f"DONE  {slug}  ->  page {args.page}, slot {args.slot}, {args.engine}")
    print(f"      {dest}")
    print("=" * 64)


if __name__ == "__main__":
    main()