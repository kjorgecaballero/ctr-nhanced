#!/usr/bin/env python3
"""
Fase 1: raw VRAM per-character infrastructure (INERT, CTR_RAW_CHARS=0 default).
Solo inserciones + 1 reemplazo de anchor exacto. Nada de lógica existente se modifica.

Uso:
    python tools/migrate_raw_chars_fase1.py            # dry-run (default)
    python tools/migrate_raw_chars_fase1.py --apply    # aplica + crea .bak
    python tools/migrate_raw_chars_fase1.py --revert   # restaura desde .bak
"""
import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent  # tools/.. -> repo root
RENDERER = REPO / "platform/native_renderer.c"
GPU      = REPO / "platform/native_gpu.c"

# ---------- ANCHORS (verificados contra los archivos que pegaste) ----------

ANCHOR_RENDERER_INSERT = "TextureID NativeRenderer_GetCustomVramModels(void) { return s_customVramModels; }\n"

RENDERER_INSERT = r"""
/* ====================================================================
 * Raw VRAM per-character pool (Fase 1: INERT, gated by CTR_RAW_CHARS=1)
 * 16 LRU slots x 5 sub-slots (body0, body1_overflow, kart, items, dance+mask)
 * ==================================================================== */
#define RAWCHAR_POOL_SLOTS   16
#define RAWCHAR_SUBSLOTS     5

static TextureID s_charVramTex[RAWCHAR_POOL_SLOTS][RAWCHAR_SUBSLOTS];
static int       s_charVramCharID[RAWCHAR_POOL_SLOTS];
static u32       s_charVramLastUse[RAWCHAR_POOL_SLOTS];
static int       s_charVramInit = 0;

static void EnsureCharVramInit_(void) {
    if (!s_charVramInit) {
        for (int i = 0; i < RAWCHAR_POOL_SLOTS; i++) s_charVramCharID[i] = -1;
        s_charVramInit = 1;
    }
}

int NativeRenderer_IsRawCharsEnabled(void) {
    static int s_enabled = -1;
    if (s_enabled < 0) {
        const char *e = getenv("CTR_RAW_CHARS");
        s_enabled = (e && e[0] == '1') ? 1 : 0;
    }
    return s_enabled;
}

/* Forward decl: AcquireCharVram needs ReleaseCharVram on the LRU evict path. */
void NativeRenderer_ReleaseCharVram(u32 slot);

u32 NativeRenderer_AcquireCharVram(int charID) {
    EnsureCharVramInit_();
    for (u32 i = 0; i < RAWCHAR_POOL_SLOTS; i++)
        if (s_charVramCharID[i] == charID) { s_charVramLastUse[i] = s_dbgFrame; return i; }
    for (u32 i = 0; i < RAWCHAR_POOL_SLOTS; i++)
        if (s_charVramCharID[i] == -1) {
            s_charVramCharID[i] = charID; s_charVramLastUse[i] = s_dbgFrame; return i;
        }
    u32 oldest = 0;
    for (u32 i = 1; i < RAWCHAR_POOL_SLOTS; i++)
        if (s_charVramLastUse[i] < s_charVramLastUse[oldest]) oldest = i;
    NativeRenderer_ReleaseCharVram(oldest);
    s_charVramCharID[oldest] = charID; s_charVramLastUse[oldest] = s_dbgFrame;
    return oldest;
}

TextureID NativeRenderer_GetCharVramTex(u32 slot, int sub) {
    if (slot >= RAWCHAR_POOL_SLOTS || sub < 0 || sub >= RAWCHAR_SUBSLOTS) return 0;
    return s_charVramTex[slot][sub];
}

void NativeRenderer_UploadCharVram(u32 slot, int sub, const u16 *vv, int w, int h) {
    if (slot >= RAWCHAR_POOL_SLOTS || sub < 0 || sub >= RAWCHAR_SUBSLOTS) return;
    UploadVram_(&s_charVramTex[slot][sub], vv, w, h, "char");
}

void NativeRenderer_ReleaseCharVram(u32 slot) {
    if (slot >= RAWCHAR_POOL_SLOTS) return;
    for (int s = 0; s < RAWCHAR_SUBSLOTS; s++) {
        if (s_charVramTex[slot][s]) { glDeleteTextures(1, &s_charVramTex[slot][s]); s_charVramTex[slot][s] = 0; }
    }
    s_charVramCharID[slot] = -1;
}
"""

# En native_gpu.c, insertar branch per-char ANTES del branch level/garage.
# Se reemplaza el encabezado del if actual por if/else-if.
GPU_OLD = """\t\tif (sentinelSrc == 0 || sentinelSrc == 1)
\t\t{
\t\t\tint sp_mode = (tpage >> 7) & 3;"""

GPU_NEW = """\t\tif (sentinelSrc >= 2 && sentinelSrc < 2 + 16 * 5)
\t\t{
\t\t\t/* Per-character raw VRAM (Fase 2+): src = 2 + slot*5 + sub */
\t\t\tu32 _pack = sentinelSrc - 2;
\t\t\tu32 _slot = _pack / 5;
\t\t\tint _sub  = _pack % 5;
\t\t\ttextureId = NativeRenderer_GetCharVramTex(_slot, _sub);
\t\t\tif (textureId == 0) {
\t\t\t\t/* src >= 2 but no texture: fallback to level so nothing renders garbage */
\t\t\t\ttextureId = NativeRenderer_GetCustomVramLevel();
\t\t\t}
\t\t\tint sp_mode = (tpage >> 7) & 3;
\t\t\ttexFormat = (sp_mode == 0) ? TF_4_BIT : (sp_mode == 1) ? TF_8_BIT : TF_16_BIT;
\t\t\toverrideW = 1024;
\t\t\toverrideH = 512;
\t\t\tpsxTexturedSemiTrans = semiTrans;
\t\t\tblendMode = semiTrans ? GET_TPAGE_BLEND(tpage) : BM_NONE;
\t\t\tpsxTextureOutputSTP = true;
\t\t\tpsxKeepTextureAlpha = false;
\t\t\t/* TODO Fase 2: per-char clut lookup */
\t\t}
\t\telse if (sentinelSrc == 0 || sentinelSrc == 1)
\t\t{
\t\t\tint sp_mode = (tpage >> 7) & 3;"""

# En native_gpu.c, agregar extern declarations al inicio de AddSplit.
# Ancla exacta justo antes del if-chain de sentinel.
GPU_EXTERN_OLD = """\telse if (textured && (effClut & NATIVE_GPU_CLUT_SENTINEL))
\t{
\t\t// Sentinel CLUT: sample from a dedicated OpenGL texture instead of VRAM.
\t\tconst u16 sentinelIdx = effClut & 0x7FFF;
\t\tu8 sentinelSrc = NativeGpu_GetSrcLookup(sentinelIdx);"""

GPU_EXTERN_NEW = """\telse if (textured && (effClut & NATIVE_GPU_CLUT_SENTINEL))
\t{
\t\t// Sentinel CLUT: sample from a dedicated OpenGL texture instead of VRAM.
\t\tconst u16 sentinelIdx = effClut & 0x7FFF;
\t\tu8 sentinelSrc = NativeGpu_GetSrcLookup(sentinelIdx);
\t\textern TextureID NativeRenderer_GetCharVramTex(u32 slot, int sub);
\t\textern TextureID NativeRenderer_GetCustomVramLevel(void);"""


# ---------- Helpers ----------

def check_anchor(path: Path, anchor: str, expected=1):
    if not path.exists():
        return False, f"MISSING FILE: {path}"
    text = path.read_text(encoding="utf-8")
    n = text.count(anchor)
    if n != expected:
        return False, f"{path.name}: anchor found {n}x, expected {expected}x\n   first 120: {anchor[:120]!r}"
    return True, f"{path.name}: anchor OK ({n}x)"


def insert_after(path: Path, anchor: str, code: str, dry: bool):
    text = path.read_text(encoding="utf-8")
    idx = text.find(anchor)
    if idx < 0:
        return False, f"{path.name}: anchor not found at insert"
    pos = idx + len(anchor)
    if not dry:
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists(): shutil.copy(path, bak)
        path.write_text(text[:pos] + code + text[pos:], encoding="utf-8")
    return True, f"{path.name}: insert @{pos} (+{len(code)} bytes)"


def replace_once(path: Path, old: str, new: str, dry: bool):
    text = path.read_text(encoding="utf-8")
    n = text.count(old)
    if n != 1:
        return False, f"{path.name}: replace anchor found {n}x, expected 1"
    if not dry:
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists(): shutil.copy(path, bak)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True, f"{path.name}: replace ({len(new) - len(old):+d} bytes)"


# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply",  action="store_true")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()

    if args.revert:
        for f in (RENDERER, GPU):
            bak = f.with_suffix(f.suffix + ".bak")
            if bak.exists():
                shutil.copy(bak, f)
                print(f"[REVERT] {f.name}")
        return 0

    dry = not args.apply
    print(f"=== Fase 1 raw chars (DRY-RUN={dry}) ===")

    checks = [
        check_anchor(RENDERER, ANCHOR_RENDERER_INSERT),
        check_anchor(GPU,      GPU_OLD),
        check_anchor(GPU,      GPU_EXTERN_OLD),
    ]
    ok_all = True
    for ok, msg in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {msg}")
        ok_all = ok_all and ok
    if not ok_all:
        print("\n[ABORT] Anchor mismatch. No files touched.")
        return 1

    print("\n--- Applying ---")
    steps = [
        insert_after(RENDERER, ANCHOR_RENDERER_INSERT, RENDERER_INSERT, dry),
        replace_once(GPU,      GPU_EXTERN_OLD,        GPU_EXTERN_NEW,  dry),
        replace_once(GPU,      GPU_OLD,               GPU_NEW,         dry),
    ]
    for ok, msg in steps:
        print(f"  [{'OK' if ok else 'FAIL'}] {msg}")
        ok_all = ok_all and ok

    if not ok_all:
        print("\n[PARTIAL] Some steps failed. Review, then --revert if needed.")
        return 1

    if dry:
        print("\n[DRY-RUN] No files written. Run with --apply to write.")
    else:
        print("\n[APPLIED] Backups created as *.bak. Run --revert to undo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())