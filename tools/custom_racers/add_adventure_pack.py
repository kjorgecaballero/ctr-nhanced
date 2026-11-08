import argparse, os, json, shutil, sys
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LEVELS_ROOT = os.path.join(REPO_ROOT, "assets", "mods", "levels")
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--lev", required=True)
    ap.add_argument("--vrm", required=True)
    ap.add_argument("--music", default=None)
    ap.add_argument("--cam", required=True, help="x,y,z,rot_x,rot_y")
    ap.add_argument("--slot", action="append", default=[], help="char,x,y,z,rot_y")
    args = ap.parse_args()

    dst = os.path.join(LEVELS_ROOT, args.slug)
    os.makedirs(dst, exist_ok=True)
    shutil.copy(args.lev, os.path.join(dst, "data.lev"))
    shutil.copy(args.vrm, os.path.join(dst, "data.vrm"))

    chars = []
    slots_data = []
    for s in args.slot:
        parts = s.split(",")
        if len(parts) == 5:
            chars.append(parts[0])
            slots_data.append({"x": int(parts[1]), "y": int(parts[2]), "z": int(parts[3]), "rot_y": int(parts[4])})

    while len(chars) < 8:
        chars.append("crash")
        slots_data.append({"x": 0, "y": 0, "z": 0, "rot_y": 0})

    manifest = {"id": args.slug, "name": args.name, "type": "adventure_garage", "prim_mem": 4194304, "characters": chars[:8]}
    if args.music:
        shutil.copy(args.music, os.path.join(dst, "music.ogg"))
        manifest["music"] = "music.ogg"

    with open(os.path.join(dst, "level.json"), "w") as f: json.dump(manifest, f, indent=2)

    cam = [int(x) for x in args.cam.split(",")]
    cameras = {"camera": {"x": cam[0], "y": cam[1], "z": cam[2], "rot_x": cam[3], "rot_y": cam[4]}, "slots": slots_data[:8]}
    with open(os.path.join(dst, "cameras.json"), "w") as f: json.dump(cameras, f, indent=2)
    print(f"Pack built at {dst}")
if __name__ == "__main__": main()
