"""
add_adventure_pack.py — Build a custom Adventure Garage pack.

Does NOT run lev_inject.py. The model injection is a separate manual step:

    python tools/custom_racers/garage/lev_inject.py inject \\
        --lev assets/mods/levels/<slug>/data.lev.bak \\
        --models-from-lev tools/custom_racers/garage/garage_retail.lev \\
        --translate=-1500,10,0 --pos-offset=0x30 \\
        -o assets/mods/levels/<slug>/data.lev

Then copy the retail VRM:

    cp tools/custom_racers/garage/garage_retail.vrm \\
       assets/mods/levels/<slug>/model_textures.vrm

See docs/CUSTOM_GARAGE_CONTEXT.md for the full pipeline.
"""
import argparse
import json
import os
import shutil
import sys


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LEVELS_ROOT = os.path.join(REPO_ROOT, "assets", "mods", "levels")


def _empty_slots():
    return [{"char": "", "kart": "", "x": 0, "y": 0, "z": 0, "rot": 0,
             "idle_anim": 0, "idle_start": 0, "idle_end": 0, "idle_loop": 1,
             "select_anim": 0, "select_start": 0, "select_end": 0, "select_loop": 0,
             "ambient_wav": "", "sfx": []}
            for _ in range(8)]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True, help="Display name (e.g. 'My Pack')")
    ap.add_argument("--slug", required=True, help="Folder name (e.g. 'my_pack')")
    ap.add_argument("--lev", required=True, help="Path to the LEV file exported from CTR Editor")
    ap.add_argument("--vrm", required=True, help="Path to the VRM file exported from CTR Editor")
    ap.add_argument("--data-json", required=True, help="Path to JSON with slots + camera (written by Blender operator)")
    args = ap.parse_args()

    if not os.path.isfile(args.lev):
        print(f"ERROR: LEV not found: {args.lev}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(args.vrm):
        print(f"ERROR: VRM not found: {args.vrm}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(args.data_json):
        print(f"ERROR: data JSON not found: {args.data_json}", file=sys.stderr)
        sys.exit(1)

    with open(args.data_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    slots = data.get("slots", [])
    while len(slots) < 8:
        slots.append(_empty_slots()[len(slots)])
    slots = slots[:8]

    cam = data.get("camera", {})

    dst = os.path.join(LEVELS_ROOT, args.slug)
    os.makedirs(dst, exist_ok=True)

    # Copy LEV and VRM (the user's assets)
    shutil.copy2(args.lev, os.path.join(dst, "data.lev"))
    shutil.copy2(args.vrm, os.path.join(dst, "data.vrm"))

    # Build the level.json manifest
    manifest = {
        "id": args.slug,
        "name": args.name,
        "type": "adventure_garage",
        "replace": "-1",
        "base": "40",
        "prim_mem": 4194304,
        "characters":   [s.get("char", "")   for s in slots],
        "karts":        [s.get("kart", "")   for s in slots],
        "idle_anims":   [s.get("idle_anim", 0)   for s in slots],
        "idle_starts":  [s.get("idle_start", 0)  for s in slots],
        "idle_ends":    [s.get("idle_end", 0)    for s in slots],
        "idle_loops":   [s.get("idle_loop", 1)   for s in slots],
        "select_anims": [s.get("select_anim", 0) for s in slots],
        "select_starts":[s.get("select_start", 0) for s in slots],
        "select_ends":  [s.get("select_end", 0)  for s in slots],
        "select_loops": [s.get("select_loop", 0) for s in slots],
    }

    # game/LevelRegistry.c lee estas listas como STRING "0,0,..." (no array JSON)
    for k in ("idle_anims", "idle_starts", "idle_ends", "idle_loops",
              "select_anims", "select_starts", "select_ends", "select_loops"):
        manifest[k] = ",".join(str(int(v)) for v in manifest[k])

    with open(os.path.join(dst, "level.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, separators=(',', ':'))

    # Build cameras.json (used by CS_Garage / NativeAdventurePack_LoadCameras)
    cameras = {
        "camera": {
            "x": cam.get("x", 0),
            "y": cam.get("y", 100),
            "z": cam.get("z", 500),
            "rot_x": cam.get("rot_x", 0),
            "rot_y": cam.get("rot_y", 0),
        },
        "slots": [
            {"x": s.get("x", 0), "y": s.get("y", 0),
             "z": s.get("z", 0), "rot_y": s.get("rot", 0)}
            for s in slots
        ],
    }
    cam_path = os.path.join(dst, "cameras.json")
    if any(cam.get(k, 0) for k in ("x", "y", "z", "rot_x", "rot_y")):
        with open(cam_path, "w", encoding="utf-8") as f:
            json.dump(cameras, f, separators=(',', ':'))
    elif os.path.isfile(cam_path):
        os.remove(cam_path)   # sin camara capturada: usar la del motor


    # Copy per-slot audio files (ambient loop only for now; SFX is future)
    # The C-side audio feature (commit 123ee3d03) expects sidecar files under
    # <slug>/garage/. We copy the WAVs there so the user can run the audio
    # pipeline separately.
    audio_dir = os.path.join(dst, "garage")
    for i, s in enumerate(slots):
        amb = s.get("ambient_wav", "")
        if amb and os.path.isfile(amb):
            os.makedirs(audio_dir, exist_ok=True)
            shutil.copy2(amb, os.path.join(audio_dir, f"ambient_{i}.wav"))
        for j, sfx in enumerate(s.get("sfx", [])):
            wav = sfx.get("wav", "")
            if wav and os.path.isfile(wav):
                os.makedirs(audio_dir, exist_ok=True)
                shutil.copy2(wav, os.path.join(audio_dir, f"sfx_{i}_{j}.wav"))

    # --- Inyeccion automatica del garaje retail (16 modelos + 17 instancias) ---
    import subprocess
    garage_dir = os.path.join(REPO_ROOT, "tools", "custom_racers", "garage")
    retail_lev = os.path.join(garage_dir, "garage_retail.lev")
    retail_vrm = os.path.join(garage_dir, "garage_retail.vrm")
    injector = os.path.join(garage_dir, "lev_inject.py")
    if all(os.path.isfile(x) for x in (retail_lev, retail_vrm, injector)):
        bak = os.path.join(dst, "data.lev.bak")
        shutil.copy2(args.lev, bak)   # LEV limpio exportado de CTR Editor
        r = subprocess.run(
            [sys.executable, injector, "inject", "--lev", bak,
             "--models-from-lev", retail_lev,
             "--translate=-1500,10,0", "--pos-offset=0x30",
             "-o", os.path.join(dst, "data.lev")],
            capture_output=True, text=True)
        print(r.stdout)
        if r.returncode != 0:
            print("ERROR: lev_inject fallo:\n" + r.stderr, file=sys.stderr)
            sys.exit(1)
        shutil.copy2(retail_vrm, os.path.join(dst, "model_textures.vrm"))
        print("  retail garage injected + model_textures.vrm copied")
    else:
        print("WARNING: falta garage_retail.lev/.vrm o lev_inject.py en "
              + garage_dir + " -> NO se inyectaron modelos", file=sys.stderr)

    print(f"Pack built at {dst}")
    print(f"  level.json, cameras.json, data.lev, data.vrm")
    print()
    print("NEXT STEPS (manual):")
    print(f"  1. Backup the LEV:  cp {dst}/data.lev {dst}/data.lev.bak")
    print(f"  2. Inject models:   python tools/custom_racers/garage/lev_inject.py inject \\")
    print(f"         --lev {dst}/data.lev.bak \\")
    print(f"         --models-from-lev tools/custom_racers/garage/garage_retail.lev \\")
    print(f"         --translate=-1500,10,0 --pos-offset=0x30 \\")
    print(f"         -o {dst}/data.lev")
    print(f"  3. Copy VRM:        cp tools/custom_racers/garage/garage_retail.vrm {dst}/model_textures.vrm")
    print(f"  4. Rebuild + run the game.")


if __name__ == "__main__":
    main()