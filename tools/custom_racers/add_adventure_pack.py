"""
add_adventure_pack.py - Build a custom Adventure Garage pack.

Copies the LEV/VRM, writes level.json + cameras.json, injects the retail garage
models with lev_inject.py (when tools/custom_racers/garage/* exist) and installs
the per-character garage audio under assets/mods/racers/<char_slug>/garage/.

Audio: .vag files are copied as is; a .wav needs a sibling .vag with the same
name or an external encoder in the NFR_VAG_ENCODER environment variable
(template with {wav} and {out}).

See docs/CUSTOM_GARAGE_CONTEXT.md for the full pipeline.
"""
import argparse
import json
import os
import shlex
import shutil
import struct
import subprocess
import sys


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LEVELS_ROOT = os.path.join(REPO_ROOT, "assets", "mods", "levels")


def _copy(src, dst):
    """copy2 que no falla (SameFileError) si origen y destino son el mismo archivo."""
    if os.path.exists(dst) and os.path.samefile(src, dst):
        return
    shutil.copy2(src, dst)


# ---------------------------------------------------------------------------
# Audio del garaje. El motor lee SOLO (native_custom_racer.c):
#   assets/mods/racers/<char_slug>/garage/ambient.vag
#   assets/mods/racers/<char_slug>/garage/sfx_<n>.vag
#   assets/mods/racers/<char_slug>/garage/sfx.bin   ("GSFX", u32 count, u32 frames[])
# sfx.bin se lee al cargar el roster: hay que reiniciar el juego tras cambiarlo.
# ---------------------------------------------------------------------------
VAG_ENCODER_ENV = "NFR_VAG_ENCODER"


def _racer_garage_dir(slug):
    return os.path.join(REPO_ROOT, "assets", "mods", "racers", slug, "garage")


def _install_vag(src, dst, max_seconds=0, fade=0.0):
    """Deja un .vag en dst. Devuelve (ok, mensaje).

    src puede ser: un .vag (se copia); un .wav con un .vag gemelo (mismo nombre,
    se usa el gemelo); o un .wav y un encoder externo definido en la variable de
    entorno NFR_VAG_ENCODER como plantilla, p. ej.:
        python tools/loquesea/wav2vag.py {wav} {out}
    """
    if not src or not os.path.isfile(src):
        return False, "no existe: %r" % src
    stem, ext = os.path.splitext(src)
    if ext.lower() == ".vag":
        _copy(src, dst)
        return True, "copiado"
    twin = stem + ".vag"
    if os.path.isfile(twin):
        _copy(twin, dst)
        return True, "usado %s (junto al WAV)" % os.path.basename(twin)
    tmpl = os.environ.get(VAG_ENCODER_ENV, "").strip()
    if not tmpl:
        # AUTO-FIX: Usar el vag_codec del repositorio por defecto
        vag_codec = os.path.join(REPO_ROOT, "tools", "custom_racers", "vag_codec.py")
        if os.path.exists(vag_codec):
            extras = ""
            if max_seconds > 0:
                extras += f" --max-seconds {max_seconds}"
            if fade > 0:
                extras += f" --fade {fade}"
            tmpl = f'"{sys.executable}" "{vag_codec}" encode --rate 11025 --norm --loop{extras} {{wav}} {{out}}'
        else:
            return False, ("es un WAV y no hay .vag gemelo ni encoder: define %s "
                           "o deja un .vag con el mismo nombre junto al WAV" % VAG_ENCODER_ENV)
    argv = [a.format(wav=src, out=dst).strip('"')
            for a in shlex.split(tmpl, posix=(os.name != "nt"))]
    r = subprocess.run(argv, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.isfile(dst):
        return False, "el encoder fallo: " + (r.stderr or r.stdout).strip()[:300]
    return True, "codificado"


def _write_gsfx(path, frames):
    with open(path, "wb") as f:
        f.write(b"GSFX")
        f.write(struct.pack("<I", len(frames)))
        if frames:
            f.write(struct.pack("<%dI" % len(frames), *[max(0, int(v)) for v in frames]))


def _install_audio(slots):
    ok_all = True
    for i, s in enumerate(slots):
        amb = s.get("ambient_wav", "")
        sfx = s.get("sfx", [])
        if not amb and not sfx:
            continue
        slug = s.get("char", "")
        if not slug:
            print("WARNING: slot %d tiene audio pero no personaje; se omite" % i, file=sys.stderr)
            ok_all = False
            continue
        racer_dir = os.path.join(REPO_ROOT, "assets", "mods", "racers", slug)
        if not os.path.isdir(racer_dir):
            print("WARNING: slot %d: no existe %s; se omite el audio" % (i, racer_dir), file=sys.stderr)
            ok_all = False
            continue
        gdir = _racer_garage_dir(slug)
        os.makedirs(gdir, exist_ok=True)

        if amb:
            ok, msg = _install_vag(amb, os.path.join(gdir, "ambient.vag"),
                                   max_seconds=10, fade=0.2)
            print("  audio slot %d (%s) ambient.vag: %s" % (i, slug, msg))
            ok_all &= ok
        if sfx:
            frames = []
            for j, e in enumerate(sfx):
                frames.append(e.get("frame", 0))
                ok, msg = _install_vag(e.get("wav", ""), os.path.join(gdir, "sfx_%d.vag" % j))
                print("  audio slot %d (%s) sfx_%d.vag @frame %s: %s" % (i, slug, j, e.get("frame", 0), msg))
                ok_all &= ok
            _write_gsfx(os.path.join(gdir, "sfx.bin"), frames)
    return ok_all


def _empty_slots():
    return [{"char": "", "kart": "", "x": 0, "y": 0, "z": 0, "rot": 0,
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
    dst_lev = os.path.join(dst, "data.lev")
    bak = dst_lev + ".bak"
    clean_lev = args.lev
    if os.path.exists(dst_lev) and os.path.samefile(args.lev, dst_lev) and os.path.isfile(bak):
        # Reconstruyendo sobre un pack ya inyectado: el LEV limpio es el .bak.
        clean_lev = bak
        print("  --lev apunta al data.lev ya inyectado; se usa data.lev.bak como LEV limpio")
    _copy(clean_lev, dst_lev)
    _copy(args.vrm, os.path.join(dst, "data.vrm"))

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
        # GARAGE-ANIMS: frame ranges live in .ctr clips, not JSON.
    }


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
    # OJO: NativeAdventurePack_LoadCameras NO parsea JSON, saca todos los enteros
    # en orden: 5 de camara + 8*4 de slots + flag. Por eso "use_rot" va el ULTIMO
    # y ninguna clave nueva con numeros puede ir antes. Con use_rot=1 el garaje
    # usa el pitch/yaw capturado en Blender (rot_x = pitch, rot_y = yaw, ANG 0x1000).
    captured = 1 if cam.get("captured") else 0
    cameras["use_rot"] = captured
    cameras["kart_slots"] = [{"x": s.get("kx", 0), "y": s.get("ky", 0),
                              "z": s.get("kz", 0), "rot_y": s.get("krot", 0)} for s in slots]

    # Per-slot cameras: 40 valores (5 por slot) despues de kart_slots.
    # NativeAdventurePack_LoadCameras los lee como s_cam_per_slot[8][5].
    per_slot_cameras = []
    for s in slots:
        if s.get("cam_captured"):
            per_slot_cameras.extend([
                s.get("cam_x", 0), s.get("cam_y", 100), s.get("cam_z", 500),
                s.get("cam_rot_x", 0), s.get("cam_rot_y", 0),
            ])
        else:
            per_slot_cameras.extend([
                cam.get("x", 0), cam.get("y", 100), cam.get("z", 500),
                cam.get("rot_x", 0), cam.get("rot_y", 0),
            ])
    cameras["per_slot_cameras"] = per_slot_cameras
    
    # Stats side: 8 valores al final (0=Der, 1=Izq)
    cameras["stats_sides"] = [s.get("stats_side", 0) for s in slots]

    cam_path = os.path.join(dst, "cameras.json")
    has_slot_pos = any(s.get(k, 0) for s in slots for k in ("x", "y", "z", "rot", "kx", "ky", "kz", "krot"))
    if captured or has_slot_pos:
        with open(cam_path, "w", encoding="utf-8") as f:
            json.dump(cameras, f, separators=(',', ':'))
    elif os.path.isfile(cam_path):
        os.remove(cam_path)   # nada capturado: el motor usa su camara y slots por defecto


    # Audio por personaje -> assets/mods/racers/<char_slug>/garage/ (lo que lee el motor)
    audio_ok = _install_audio(slots)

    # --- Inyeccion automatica del garaje retail (16 modelos + 17 instancias) ---
    garage_dir = os.path.join(REPO_ROOT, "tools", "custom_racers", "garage")
    retail_lev = os.path.join(garage_dir, "garage_retail.lev")
    retail_vrm = os.path.join(garage_dir, "garage_retail.vrm")
    injector = os.path.join(garage_dir, "lev_inject.py")
    if all(os.path.isfile(x) for x in (retail_lev, retail_vrm, injector)):
        _copy(clean_lev, bak)   # LEV limpio exportado de CTR Editor (no se pisa si ya es el .bak)
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
        _copy(retail_vrm, os.path.join(dst, "model_textures.vrm"))
        print("  retail garage injected + model_textures.vrm copied")
    else:
        print("WARNING: falta garage_retail.lev/.vrm o lev_inject.py en "
              + garage_dir + " -> NO se inyectaron modelos", file=sys.stderr)

    print(f"Pack built at {dst}")
    print("  level.json, cameras.json, data.lev, data.vrm")
    if not audio_ok:
        print("WARNING: algun audio no se pudo instalar (ver mensajes arriba).", file=sys.stderr)
    print("Si cambiaste SFX por frame (sfx.bin), reinicia el juego: se lee al cargar el roster.")


if __name__ == "__main__":
    main()