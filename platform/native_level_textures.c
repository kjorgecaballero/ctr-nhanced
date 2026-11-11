#include <common.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "platform/native_gpu.h"
#include "platform/native_glad.h"
#include "platform/native_renderer.h"
#include "LevelRegistry.h"

extern int  NativeCustomRacer_AllocTexIdx(void);
extern void NativeCustomRacer_FreeTexIdx(int idx);
extern int LOAD_GetBigfileIndex(int levelID, int levelLOD, int subfileIndex);

/* Forward declaration: used by IsBlockHidden / LookupPage / PatchTL before
 * its definition further down. */
int NativeLevelTextures_IsCustomLevelActive(void);
static void NltLoadModelVrmBeside(const char *relPath);   /* defined before PatchLev */

static u32 s_hideBits[65536 / 32];
static int s_hideBitsLevelID = -1;
static void NltMarkHidden(u32 id) { s_hideBits[(id >> 5) & 0x7ff] |= (1u << (id & 31)); }
int NativeLevelTextures_IsBlockHidden(int blockID) {
    if (sdata == NULL || sdata->gGT == NULL) return 0;
    /* Stale hide bits from a previous custom level must never affect a
     * retail level that shares the same levelID (e.g. base = crash_cove). */
    if (!NativeLevelTextures_IsCustomLevelActive()) return 0;
    if (sdata->gGT->levelID != s_hideBitsLevelID) return 0;
    u32 id = (u16)blockID;
    return (s_hideBits[(id >> 5) & 0x7ff] >> (id & 31)) & 1;
}

#define NLT_MAX       128    /* VRAM rects (image + CLUT of every TIM) per VRM */
#define NLT_NOTEX     0xFFFF /* NltEntry without GL texture (CLUT rects, model VRM) */
#define NLT_MAX_PAGES 1024   /* pages (tpage, clut, src) per level. Was 256: a custom map
                              * already uses >400 distinct pairs, and the garage models add ~190 more. */
#define NLT_SENT      0x8000

/*
 * Custom level Sentinel (CUSTOM-LEVELS-3P4P-VRAM-BLEED)
 * -----------------------------------------------------
 * A custom level VRM is a RAW copy of VRAM (rects of 16-bit halfwords),
 * not color images: the level's tpages are 4bpp / 8bpp (palette indices)
 * and the colors come from the CLUTs that travel inside the VRM itself.
 *
 * Here the VRM is stored as a virtual VRAM (s_vv) and, for each (tpage,
 * clut) pair used by the level's TextureLayouts, a single 256x256 RGBA
 * GL texture is built: each texel (u,v) is read from the virtual VRAM
 * according to the tpage mode (4bpp / 8bpp / 16bpp) and passed through
 * the CLUT. The layout is rewritten to clut = 0x8000 | idx so the
 * Sentinel shader samples that texture instead of real VRAM.
 *
 * The patch is applied in three places:
 *   - PatchLev walks the level QuadBlocks (scenery).
 *   - LookupPage inside AddSplit covers model/instance prims that use
 *     the same (tpage, clut) pairs.
 *   - PatchTL is called from UI_Map_DrawMap for the splitscreen minimap.
 *
 * A layout is only patched if its page (and its CLUT, if indexed) falls
 * within the VRM rects; otherwise it stays on real VRAM as before.
 *
 * All state here is only valid while a custom level is active. It is
 * released by NativeLevelTextures_Reset(), which LOAD_TenStages calls
 * whenever a non-custom level is loaded.
 *
 * NLT_DUMP=1 dumps nlt_timN.tga (raw VRM read as RGB555, for inspection
 * only) and nlt_page_<tpage>_<clutX>_<clutY>.tga (final pages).
 * NLT_MAP has no effect anymore.
 */

struct NltEntry { int x, y, w, h; u16 idx; u8 *rgba; };
static struct NltEntry s_lt[NLT_MAX];
static int s_ltCount = 0;

/* GL 256x256 page already built for a concrete (tpage, clut). */
struct NltPage { u16 tpage, clut, idx, layer; u8 src; };
static struct NltPage s_pg[NLT_MAX_PAGES];
static int s_pgCount = 0;

/* TextureLayouts already patched for the current level. Declared here (not
 * next to NltPatchOne) so NativeLevelTextures_Reset can clear it. */
static struct TextureLayout *s_seen[16384];
static int s_seenCount = 0;

/* Raw VRAM copy as left by the VRM (1024x512 halfwords). */
static u16 s_vv[1024 * 512];

/* Second texture source (MODEL VRM).
 * Models injected into a custom .lev (e.g. the Adventure Garage characters)
 * keep the TextureLayouts of the retail level: their (tpage, clut) point at
 * the retail VRAM, which collides with the custom level's VRM (same rects,
 * different contents). If assets/<level dir>/model_textures.vrm exists it is
 * loaded here as a SEPARATE virtual VRAM and used only to build the pages of
 * model layouts (s_src == 1). The level's own VRM (s_vv) is never touched. */
static u16 s_vv2[1024 * 512];
static struct NltEntry s_mlt[NLT_MAX];      /* only x,y,w,h are used */
static int s_mltCount = 0;
static int s_src = 0;                       /* 0 = level VRM, 1 = model VRM */

/* Foreign models (swapped in by the Adventure Pack): a layout whose page/CLUT
 * is NOT in the model VRM is left untouched instead of getting a blank page. */
static int s_leaveUncovered = 0;
static int s_uncovered = 0;
static u16 s_uncSample[8][2];

static int s_mapInit = 0;
static int s_mapGrid = 0;
static int s_dump = 0;

static void NltInitEnv(void)
{
    if (s_mapInit) return;
    s_mapInit = 1;
    const char *m = getenv("NLT_MAP");
    s_mapGrid = (m && strcmp(m, "grid") == 0) ? 1 : 0;
    const char *d = getenv("NLT_DUMP");
    s_dump = (d && d[0] == '1') ? 1 : 0;
    fprintf(stderr, "[NLT] map mode = %s, dump = %d\n", s_mapGrid ? "grid" : "hw", s_dump);
}

/* ---------- logging ---------- */
struct NltDbg { u16 tpage; int mid, low, tim, sliced; };
static struct NltDbg s_dbg[48];
static int s_dbgN = 0;

static void NltDbgCount(u16 tpage, int isLow, int tim, int sliced)
{
    int i;
    for (i = 0; i < s_dbgN; i++) if (s_dbg[i].tpage == tpage) break;
    if (i == s_dbgN) {
        if (s_dbgN >= 48) return;
        memset(&s_dbg[i], 0, sizeof(s_dbg[i]));
        s_dbg[i].tpage = tpage;
        s_dbg[i].tim = tim;
        s_dbg[i].sliced = sliced;
        s_dbgN++;
    }
    if (isLow) s_dbg[i].low++; else s_dbg[i].mid++;
}

static void NltDumpTGA(const char *path, const u8 *rgba, int w, int h)
{
    FILE *f = fopen(path, "wb");
    if (!f) return;
    u8 hdr[18] = {0};
    hdr[2] = 2;
    hdr[12] = (u8)(w & 255); hdr[13] = (u8)(w >> 8);
    hdr[14] = (u8)(h & 255); hdr[15] = (u8)(h >> 8);
    hdr[16] = 32; hdr[17] = 0x28;
    fwrite(hdr, 1, 18, f);
    for (int i = 0; i < w * h; i++) {
        u8 px[4] = { rgba[i*4+2], rgba[i*4+1], rgba[i*4+0], rgba[i*4+3] };
        fwrite(px, 1, 4, f);
    }
    fclose(f);
}

static TextureID NltUpload(const u8 *rgba, int w, int h)
{
    GLuint tex = 0;
    glGenTextures(1, &tex);
    if (!tex) return 0;
    glBindTexture(GL_TEXTURE_2D, tex);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, rgba);
    glBindTexture(GL_TEXTURE_2D, 0);
    return (TextureID)tex;
}

static void NltExpand16(u16 px, u8 *dst)
{
    dst[0] = (u8)(((px >>  0) & 0x1F) << 3);
    dst[1] = (u8)(((px >>  5) & 0x1F) << 3);
    dst[2] = (u8)(((px >> 10) & 0x1F) << 3);
    /* 3-way alpha:
     *   0   = fully transparent texel (never drawn, used by 0x0000)
     *   128 = STP=1 (pass 2, blended)
     *   255 = STP=0 (pass 1, opaque)
     * The 32-bit shader reads these three values. */
    dst[3] = (px & 0x8000) ? 128 : 255;
}

/* ---------------------------------------------------------------------------
 * TIM parsing (PSX TIM, as stored inside .vrm files)
 *
 *   u32 0x10 | u32 flags (bits0-1 = bpp mode 0:4 1:8 2:16, bit3 = has CLUT)
 *   [CLUT block]  u32 bnum | u16 x,y,w,h | u16 data[w*h]
 *   [image block] u32 bnum | u16 x,y,w,h | u16 data[w*h]
 *
 * IMPORTANT: 'bnum' counts the block INCLUDING its own 4 bytes, and 'w' is
 * ALWAYS in VRAM halfwords, whatever the bpp (a 4bpp image is 4*w texels wide,
 * an 8bpp image 2*w). Both blocks are therefore plain rects of halfwords that
 * can be blitted straight into a 1024x512 halfword VRAM.
 * (The old parser skipped 4+bnum, i.e. 4 bytes too far, so every TIM with a
 * CLUT was read shifted: garbage rw/rh => out-of-bounds memcpy => segfault.)
 * Every size is validated against 'end' so a bad file can never read or write
 * out of bounds.
 * ------------------------------------------------------------------------- */
struct NltTim {
    int bpp, hasClut;
    int cx, cy, cw, ch;  const u8 *clutPx;     /* CLUT rect (halfwords) */
    int rx, ry, rw, rh;  const u8 *px;         /* image rect (halfwords) */
};

static u32 NltRd32(const u8 *p) { u32 v; memcpy(&v, p, 4); return v; }
static int NltRd16(const u8 *p) { u16 v; memcpy(&v, p, 2); return (int)v; }

/* Returns the number of bytes the TIM occupies, or 0 if it is invalid. */
static int NltParseTim(const u8 *tim, const u8 *end, struct NltTim *t)
{
    memset(t, 0, sizeof(*t));
    if (tim == NULL || end <= tim || (size_t)(end - tim) < 8 + 12) return 0;
    if (NltRd32(tim) != 0x10) return 0;
    u32 flags = NltRd32(tim + 4);
    t->bpp = (int)(flags & 3);
    if (t->bpp > 2) return 0;                          /* 24bpp: not supported */
    t->hasClut = (int)((flags >> 3) & 1);

    const u8 *p = tim + 8;
    if (t->hasClut) {
        if ((size_t)(end - p) < 12) return 0;
        u32 bn = NltRd32(p);
        if (bn < 12 || bn > (size_t)(end - p)) return 0;
        t->cx = NltRd16(p + 4); t->cy = NltRd16(p + 6);
        t->cw = NltRd16(p + 8); t->ch = NltRd16(p + 10);
        if ((size_t)t->cw * (size_t)t->ch * 2 + 12 > bn) return 0;
        t->clutPx = p + 12;
        p += bn;
    }
    if ((size_t)(end - p) < 12) return 0;
    u32 bn = NltRd32(p);
    if (bn < 12 || bn > (size_t)(end - p)) return 0;
    t->rx = NltRd16(p + 4); t->ry = NltRd16(p + 6);
    t->rw = NltRd16(p + 8); t->rh = NltRd16(p + 10);
    if (t->rw > 1024 || t->rh > 512) return 0;
    if ((size_t)t->rw * (size_t)t->rh * 2 + 12 > bn) return 0;
    t->px = p + 12;
    return (int)(p + bn - tim);
}

/* Copies a rect of raw halfwords into a virtual VRAM, clipped to 1024x512. */
static void NltBlit(u16 *vv, const u8 *src, int x, int y, int w, int h)
{
    if (x < 0 || y < 0 || x >= 1024 || y >= 512 || w <= 0 || h <= 0) return;
    int cw = (x + w > 1024) ? 1024 - x : w;
    for (int r = 0; r < h && y + r < 512; r++)
        memcpy(&vv[(y + r) * 1024 + x], src + (size_t)r * w * 2, (size_t)cw * 2);
}

static int NltAddRect(struct NltEntry *arr, int *count, int x, int y, int w, int h)
{
    if (*count >= NLT_MAX) return 0;
    struct NltEntry *e = &arr[(*count)++];
    e->x = x; e->y = y; e->w = w; e->h = h; e->idx = NLT_NOTEX; e->rgba = NULL;
    return 1;
}

/* Blits the CLUT (if any) and the image of a TIM into 'vv' and records both
 * rects in 'cov' as covered. Works for 4bpp, 8bpp and 16bpp TIMs alike. */
static void NltBlitTim(u16 *vv, struct NltEntry *cov, int *covCount, const struct NltTim *t)
{
    if (t->hasClut) {
        NltBlit(vv, t->clutPx, t->cx, t->cy, t->cw, t->ch);
        NltAddRect(cov, covCount, t->cx, t->cy, t->cw, t->ch);
    }
    NltBlit(vv, t->px, t->rx, t->ry, t->rw, t->rh);
}

/* Decodes the image of one TIM to RGBA (only used for the per-TIM GL texture /
 * dump). Output is (rw * texelsPerHalfword) x rh. Palette indices are clamped
 * to the CLUT actually present in the TIM. */
static void NltDecodePixels(const struct NltTim *t, u8 *dst, int pw)
{
    const int h = t->rh;
    const size_t stride = (size_t)t->rw * 2;          /* bytes per image row */
    const int nclut = t->hasClut ? t->cw * t->ch : 0;
    for (int y = 0; y < h; y++) {
        const u8 *row = t->px + (size_t)y * stride;
        u8 *o = dst + (size_t)y * pw * 4;
        for (int x = 0; x < pw; x++, o += 4) {
            if (t->bpp == 2) {
                NltExpand16((u16)NltRd16(row + (size_t)x * 2), o);
            } else {
                int idx = (t->bpp == 1) ? row[x]
                                        : ((row[x >> 1] >> ((x & 1) * 4)) & 0xF);
                if (idx < nclut) NltExpand16((u16)NltRd16(t->clutPx + (size_t)idx * 2), o);
                else memset(o, 0, 4);
            }
        }
    }
}

static void NltFreeDecoded(void)
{
    /* Free the GL texture and the pool index for every previously
     * allocated entry. Without this, each custom level load leaks
     * ~34 indices + ~34 GL textures from the shared Sentinel pool
     * (GL-INDEX-LEAK). Once exhausted, NltGetPage returns -1,
     * NltPatchOne falls back to real VRAM and the bleed returns.
     *
     * The CPU-side rgba buffer of each TIM is also freed (existing
     * behavior); the 256x256 page scratch buffer is already freed
     * inside NltGetPage. */
    for (int i = 0; i < s_ltCount; i++) {
        free(s_lt[i].rgba);
        s_lt[i].rgba = NULL;
        if (s_lt[i].idx == NLT_NOTEX) continue;      /* CLUT rect: no GL texture */
        NativeGpu_FreeCustomTexture(s_lt[i].idx);
        NativeCustomRacer_FreeTexIdx((int)s_lt[i].idx);
    }
    s_ltCount = 0;

    for (int i = 0; i < s_pgCount; i++) {
        NativeGpu_FreeCustomTexture(s_pg[i].idx);
        NativeCustomRacer_FreeTexIdx((int)s_pg[i].idx);
    }
    s_pgCount = 0;
    s_mltCount = 0;     /* model VRM coverage is reloaded together with the level VRM */

    /* FASE 2: release the array layer counter so the next build cycle
     * reuses layers 0..N-1. The GL_TEXTURE_2D_ARRAY itself is persistent
     * (its 256MB are allocated once at NativeRenderer_InitSentinelArray). */
    NativeRenderer_ResetSentinelLayerCount();
}

/* Drops ALL custom-level state (GL textures, virtual VRAM, hide bits, patch
 * bookkeeping). Called by LOAD_TenStages when a non-custom level is loaded,
 * so nothing from a previous custom track leaks into retail tracks that
 * share the same levelID (e.g. a custom track with base = crash_cove).
 * Safe to call repeatedly: when nothing is allocated it only clears memory. */
void NativeLevelTextures_Reset(void)
{
    NltFreeDecoded();
    memset(s_vv, 0, sizeof(s_vv));
    memset(s_vv2, 0, sizeof(s_vv2));
    memset(s_hideBits, 0, sizeof(s_hideBits));
    s_hideBitsLevelID = -1;
    s_seenCount = 0;
    s_dbgN = 0;
}

int NativeLevelTextures_DecodeVRM(const u8 *buf, int size)
{
    NltInitEnv();
    if (s_pgCount > 0)
        fprintf(stderr, "[NLT] WARNING: DecodeVRM called with %d pages alive; their GL textures are "
                        "freed now (TextureLayouts patched earlier would point at freed pages)\n", s_pgCount);
    NltFreeDecoded();
    memset(s_vv, 0, sizeof(s_vv));

    if (size < 4 || NltRd32(buf) != 0x20) {
        fprintf(stderr, "[NLT] DecodeVRM: invalid magic or too small (%d)\n", size);
        return 0;
    }

    int off = 4;
    int nTim = 0;
    while (off + 4 <= size && s_ltCount < NLT_MAX) {
        u32 timSize = NltRd32(buf + off);
        if (timSize == 0) break;
        if (timSize > (u32)(size - off - 4)) break;

        struct NltTim t;
        if (!NltParseTim(buf + off + 4, buf + off + 4 + timSize, &t)) {
            fprintf(stderr, "[NLT] TIM #%d at +%d: invalid/unsupported, skipped\n", nTim, off);
            off += 4 + (int)timSize;
            nTim++;
            continue;
        }

        fprintf(stderr, "[NLT] TIM rect=(%d,%d,%d,%d) bpp=%d hasClut=%d clutRect=(%d,%d,%d,%d)\n",
                t.rx, t.ry, t.rw, t.rh, t.bpp, t.hasClut, t.cx, t.cy, t.cw, t.ch);

        /* VRM = raw VRAM: CLUT and image rects are copied as halfwords into the
         * virtual VRAM, whatever the bpp of the TIM. */
        NltBlitTim(s_vv, s_lt, &s_ltCount, &t);

        if (s_ltCount >= NLT_MAX) break;
        const int pw = t.rw << (t.bpp == 0 ? 2 : (t.bpp == 1 ? 1 : 0));   /* texels per row */
        u8 *rgba = (t.rw > 0 && t.rh > 0) ? (u8 *)malloc((size_t)pw * t.rh * 4) : NULL;
        if (rgba) {
            NltDecodePixels(&t, rgba, pw);
            if (s_dump) {
                char nm[64];
                snprintf(nm, sizeof(nm), "nlt_tim%d.tga", nTim);
                NltDumpTGA(nm, rgba, pw, t.rh);
            }
            TextureID tex = NltUpload(rgba, pw, t.rh);
            int idx = tex ? NativeCustomRacer_AllocTexIdx() : -1;
            if (tex != 0 && idx >= 0) {
                NativeGpu_RegisterCustomTexture((u16)idx, tex, pw, t.rh);
                /* x,y,w,h stay in VRAM halfwords: that is what NltCovered/NltTouches use. */
                struct NltEntry *e = &s_lt[s_ltCount++];
                e->x = t.rx; e->y = t.ry; e->w = t.rw; e->h = t.rh;
                e->idx = (u16)idx; e->rgba = rgba;
            } else {
                free(rgba);
                /* Still has to count as covered, even without a GL copy. */
                NltAddRect(s_lt, &s_ltCount, t.rx, t.ry, t.rw, t.rh);
            }
        } else {
            NltAddRect(s_lt, &s_ltCount, t.rx, t.ry, t.rw, t.rh);
        }
        off += 4 + (int)timSize;
        nTim++;
    }

    fprintf(stderr, "[NLT] DecodeVRM: %d TIMs, %d covered rects\n", nTim, s_ltCount);
    NativeRenderer_UploadCustomVramLevel(s_vv, 1024, 512);
    for (int i = 0; i < s_ltCount; i++)
        fprintf(stderr, "[NLT]   [%d] x=%d y=%d w=%d h=%d idx=%d\n",
                i, s_lt[i].x, s_lt[i].y, s_lt[i].w, s_lt[i].h, s_lt[i].idx == NLT_NOTEX ? -1 : (int)s_lt[i].idx);
    return s_ltCount;
}

int NativeLevelTextures_DecodeVRMFromDisk(int levelID, int levelLOD, int subfileIndex)
{
    int bigfileIndex = LOAD_GetBigfileIndex(levelID, levelLOD, subfileIndex);
    const char *relPath = LevelRegistry_GetOverrideForBigfileEntry(
        levelID, levelLOD, bigfileIndex);
    if (relPath == NULL) {
        fprintf(stderr, "[NLT] no override for level %d lod %d subfile %d (bigfile %d)\n",
                levelID, levelLOD, subfileIndex, bigfileIndex);
        return 0;
    }

    char path[512];
    snprintf(path, sizeof(path), "assets/%s", relPath);

    FILE *f = fopen(path, "rb");
    if (!f) {
        fprintf(stderr, "[NLT] fopen failed: %s\n", path);
        return 0;
    }
    fseek(f, 0, SEEK_END);
    long fileSize = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (fileSize <= 0 || fileSize > 8 * 1024 * 1024) {
        fclose(f);
        return 0;
    }
    unsigned char *buf = (unsigned char *)malloc((size_t)fileSize);
    if (!buf) { fclose(f); return 0; }
    size_t got = fread(buf, 1, (size_t)fileSize, f);
    fclose(f);
    if (got != (size_t)fileSize) { free(buf); return 0; }

    fprintf(stderr, "[NLT] loading %s (%ld bytes)\n", path, fileSize);
    int result = NativeLevelTextures_DecodeVRM(buf, (int)fileSize);
    free(buf);
    if (result > 0) NltLoadModelVrmBeside(relPath);
    return result;
}

int NativeLevelTextures_IsCustomLevelActive(void)
{
    if (sdata == NULL || sdata->gGT == NULL) return 0;
    int levelID = sdata->gGT->levelID;
    const struct LevelDef *active = LevelRegistry_GetActive();
    if (active != NULL && active->baseLevelID == levelID) return 1;
    return 0;
}

static struct TextureLayout *NltResolveTL(u32 p)
{
    if (p == 0) return NULL;
    if ((p & 1) != 0) return *(struct TextureLayout **)(p - 1);
    return (struct TextureLayout *)p;
}

/* ---------- virtual VRAM ---------- */

/* 1 if halfword (x,y) belongs to any VRM rect. */
static int NltCovered(int x, int y)
{
    const struct NltEntry *lt = s_src ? s_mlt : s_lt;
    const int n = s_src ? s_mltCount : s_ltCount;
    for (int i = 0; i < n; i++) {
        const struct NltEntry *e = &lt[i];
        if (x >= e->x && x < e->x + e->w && y >= e->y && y < e->y + e->h) return 1;
    }
    return 0;
}

/* 1 if rect (x,y,w,h) in halfwords touches any VRM rect. */
static int NltTouches(int x, int y, int w, int h)
{
    const struct NltEntry *lt = s_src ? s_mlt : s_lt;
    const int n = s_src ? s_mltCount : s_ltCount;
    for (int i = 0; i < n; i++) {
        const struct NltEntry *e = &lt[i];
        if (x < e->x + e->w && x + w > e->x && y < e->y + e->h && y + h > e->y) return 1;
    }
    return 0;
}

/* Halfword from virtual VRAM, or -1 if the VRM does not cover that position. */
static int NltVV(int x, int y)
{
    x &= 1023; y &= 511;
    const u16 *vv = s_src ? s_vv2 : s_vv;
    return NltCovered(x, y) ? (int)vv[y * 1024 + x] : -1;
}

/* 15-bit color of page texel (u,v), or -1 if missing in the VRM. */
static int NltFetch(int mode, int tpX, int tpY, int cx, int cy, int u, int v)
{
    int hw, idx;
    if (mode >= 2) return NltVV(tpX + u, tpY + v);          /* 16bpp direct */
    if (mode == 0) {                                        /* 4bpp: 4 texels per halfword */
        hw = NltVV(tpX + (u >> 2), tpY + v);
        if (hw < 0) return -1;
        idx = (hw >> ((u & 3) * 4)) & 0xF;
    } else {                                                /* 8bpp: 2 texels per halfword */
        hw = NltVV(tpX + (u >> 1), tpY + v);
        if (hw < 0) return -1;
        idx = (hw >> ((u & 1) * 8)) & 0xFF;
    }
    return NltVV(cx + idx, cy);                             /* palette */
}

/* Returns the GL idx of the 256x256 page for (tpage, clut), or -1. */
static int NltGetPage(u16 tpage, u16 clut)
{
    const u16 key = tpage & 0x019F;                 /* X, Y and color mode */
    for (int i = 0; i < s_pgCount; i++)
        if (s_pg[i].tpage == key && s_pg[i].clut == clut && s_pg[i].src == (u8)s_src) return s_pg[i].idx;
    if (s_pgCount >= NLT_MAX_PAGES) {
        fprintf(stderr, "[NLT] page table full (%d): tpage=0x%04X clut=0x%04X src=%d NOT built\n",
                NLT_MAX_PAGES, key, clut, s_src);
        return -1;
    }

    const int tpX = (tpage & 0xF) * 64;
    const int tpY = ((tpage >> 4) & 1) * 256;
    const int mode = (tpage >> 7) & 3;              /* 0=4bpp 1=8bpp 2=16bpp */
    const int cx = (clut & 0x3F) << 4, cy = clut >> 6;

    /* FASE 2: no RGBA page. Reserve idx + mark source, return early.
     * AddSplit reads s_srcLookup[idx] and binds s_customVramLevel/Models
     * with the retail gte_shader_4/8/16 (CLUT lookup per-texel). */
    {
        int _newidx = NativeCustomRacer_AllocTexIdx();
        if (_newidx < 0) return -1;
        NativeGpu_SetSrcLookup((u16)_newidx, (u8)s_src);
        s_pg[s_pgCount].tpage = key;
        s_pg[s_pgCount].clut = clut;
        s_pg[s_pgCount].src = (u8)s_src;
        s_pg[s_pgCount].idx = (u16)_newidx;
        s_pg[s_pgCount].layer = 0xFFFF;
        s_pgCount++;
        fprintf(stderr, "[NLT] page%s tpage=0x%04X clut=0x%04X src=%d -> idx=%d (VRAM raw)\n",
                s_src ? "(model)" : "", key, clut, s_src, _newidx);
        return _newidx;
    }

    /* (legacy RGBA builder below, unreachable in Fase 2) */
    u8 *page = (u8 *)calloc(256 * 256, 4);
    if (!page) return -1;
    int miss = 0, opaque = 0;
    for (int v = 0; v < 256; v++) {
        for (int u = 0; u < 256; u++) {
            int c = NltFetch(mode, tpX, tpY, cx, cy, u, v);
            if (c < 0) { miss++; continue; }        /* alpha 0 */
            if (c == 0) continue;                   /* 0x0000 = transparent on PSX */
            NltExpand16((u16)c, page + ((size_t)v * 256 + u) * 4);
            opaque++;
        }
    }

    /* NLT_MODEL_FLAT=1: every MODEL page becomes solid magenta. Bisect tool:
     *  - bodies appear magenta  => sentinel/page path works, the page CONTENT was the problem;
     *  - bodies still invisible => not a texture problem (instance flags, LOD,
     *    position/scale, render list...). */
    static int s_modelFlat = -1;
    if (s_modelFlat < 0) { const char *e = getenv("NLT_MODEL_FLAT"); s_modelFlat = (e && e[0] == '1'); }
    if (s_src && s_modelFlat)
        for (int i = 0; i < 256 * 256; i++) { page[i*4+0] = 255; page[i*4+1] = 0; page[i*4+2] = 255; page[i*4+3] = 255; }

    if (s_dump) {
        char nm[64];
        snprintf(nm, sizeof(nm), "nlt_%spage_%04X_%d_%d.tga", s_src ? "m" : "", key, cx, cy);
        NltDumpTGA(nm, page, 256, 256);
    }

    TextureID tex = NltUpload(page, 256, 256);

    /* FASE 2 (shadow): upload the 256x256 page to the Sentinel array too.
     * The array is not sampled yet (AddSplit still binds s_gpu.customTextures
     * [idx] as sampler2D). Fase 3 flips the switch. */
    int sentinelLayer = NativeRenderer_AllocSentinelLayer();
    if (sentinelLayer >= 0)
        NativeRenderer_UploadSentinelPage(sentinelLayer, page);

    free(page);
    if (tex == 0) return -1;
    int idx = NativeCustomRacer_AllocTexIdx();
    if (idx < 0) return -1;
    NativeGpu_RegisterCustomTexture((u16)idx, tex, 256, 256);

    s_pg[s_pgCount].tpage = key;
    s_pg[s_pgCount].clut = clut;
    s_pg[s_pgCount].src = (u8)s_src;
    s_pg[s_pgCount].idx = (u16)idx;
    s_pg[s_pgCount].layer = (sentinelLayer >= 0) ? (u16)sentinelLayer : 0xFFFF;
    s_pgCount++;

    fprintf(stderr, "[NLT] page%s tpage=0x%04X clut=(%d,%d) mode=%d -> idx=%d miss=%d opaque=%d%s\n",
            s_src ? "(model)" : "", key, cx, cy, mode, idx, miss, opaque,
            opaque == 0 ? "  <-- EMPTY PAGE" : "");
    return idx;
}

/* 1 if 'idx' is the index of a page built for the current level. */
static int NltIsPageIdx(u16 idx)
{
    for (int i = 0; i < s_pgCount; i++)
        if (s_pg[i].idx == idx) return 1;
    return 0;
}

static void NltPatchOne(struct TextureLayout *tl, int isLow)
{
    if (!tl) return;
    for (int i = 0; i < s_seenCount; i++)
        if (s_seen[i] == tl) return;
    if (s_seenCount < 16384) s_seen[s_seenCount++] = tl;

    /* Already patched (e.g. PatchLev called more than once on the same
     * Level): 'clut' is 0x8000|idx already, and re-reading it as a real
     * CLUT would yield garbage, losing the sentinel. PatchLev must be
     * idempotent. */
    if ((tl->clut & NLT_SENT) && NltIsPageIdx((u16)(tl->clut & 0x7FFF))) return;

    const u16 tpage = tl->tpage;
    const u16 clut = tl->clut;                      /* original, before touching it */
    const int tpX = (tpage & 0xF) * 64;
    const int tpY = ((tpage >> 4) & 1) * 256;
    const int mode = (tpage >> 7) & 3;
    const int cx = (clut & 0x3F) << 4, cy = clut >> 6;
    const int wHW = (mode == 0) ? 64 : (mode == 1) ? 128 : 256;

    /* Only patch what the VRM provides: the page and, if indexed, the CLUT
     * row. Everything else stays on real VRAM as before. */
    int inVrm = NltTouches(tpX, tpY, wHW, 256) && (mode >= 2 || NltCovered(cx, cy));

    if (!inVrm && s_leaveUncovered) {
        if (s_uncovered < 8) { s_uncSample[s_uncovered][0] = tpage; s_uncSample[s_uncovered][1] = clut; }
        s_uncovered++;
        return;
    }

    /* A level layout whose page/CLUT is NOT in the VRM can only point at stale
     * VRAM (previous scene / framebuffer) => rainbow/magenta bleed. The custom
     * VRM is the only texture source a level has, so build an empty page
     * (transparent) instead of sampling raw VRAM. NLT_BLEED_RAW=1 restores the
     * old fallback for comparison. */
    static int s_bleedRaw = -1, s_bleedTrace = -1;
    if (s_bleedRaw < 0) {
        const char *e = getenv("NLT_BLEED_RAW");
        s_bleedRaw = (e && e[0] == '1');
        e = getenv("NLT_BLEED");
        s_bleedTrace = (e && e[0] == '1');
    }
    int blank = 0;
    if (!inVrm && !s_bleedRaw) { inVrm = 1; blank = 1; }

    int pg = inVrm ? NltGetPage(tpage, clut) : -1;
    if (blank && s_bleedTrace) {
        fprintf(stderr, "[BLEED] tpage=0x%04X clut=0x%04X mode=%d tpX=%d tpY=%d cx=%d cy=%d low=%d -> blank page idx=%d\n",
                tpage, clut, mode, tpX, tpY, cx, cy, isLow, pg);
    }
    if (pg >= 0) {
        tl->clut = (u16)(NLT_SENT | pg);
        NltDbgCount(tpage, isLow, pg, 1);
    } else {
        NltDbgCount(tpage, isLow, -1, 0);
        tl->clut &= 0x7FFF;
    }
}

static int NltPointsIntoLevelHeader(const struct TextureLayout *tl, const struct Level *lev)
{
    return ((const unsigned char *)tl >= (const unsigned char *)lev) &&
           ((const unsigned char *)tl < (const unsigned char *)lev + sizeof(struct Level));
}

static int NltIsTriggerOnlyBlock(const struct QuadBlock *qb)
{
    return (qb->quadFlags & (0x0040 | 0x8000)) != 0;
}

/* Animated textures.
 * CTR_CycleTex_LEV / CTR_CycleTex_Model swap AnimTex->ptrActiveTex between
 * the frames of ptrarray[] every tick. The QuadBlock walk in PatchLev only
 * resolves ptrActiveTex once, so only the frame that was active at load time
 * got a sentinel clut. Every other frame kept its raw VRAM clut and sampled
 * real VRAM, which no longer holds the custom VRM (=> rainbow noise).
 * Walk every frame of every AnimTex and patch it like a normal layout.
 * Traversal mirrors CTR_CycleTex_LEV (list ends when the first word equals
 * the address of the first AnimTex). */
static int NltPatchAnimList(struct AnimTex *first, const struct Level *lev)
{
    if (first == NULL) return 0;

    int patched = 0;
    int guard = 0;
    struct AnimTex *cur = first;

    while (*(int *)cur != (int)first && guard++ < 1024) {
        int n = cur->numFrames;
        struct IconGroup4 **arr = ANIMTEX_GETARRAY(cur);
        if (n <= 0 || n > 1024) break;

        for (int i = 0; i < n; i++) {
            /* Each frame is an IconGroup4* (far/middle/near/mosaic), not a
             * TextureLayout*. Patch all four; NltPatchOne dedups. */
            struct IconGroup4 *g = arr[i];
            if (g == NULL) continue;
            if (NltPointsIntoLevelHeader(&g->far, lev)) continue;
            NltPatchOne(&g->far, 1);
            NltPatchOne(&g->middle, 0);
            NltPatchOne(&g->near, 0);
            NltPatchOne(&g->mosaic, 0);
            patched++;
        }
        cur = (struct AnimTex *)&arr[n];
    }
    return patched;
}

static void NltPatchAnimTex(struct Level *lev)
{
    int levFrames = NltPatchAnimList(lev->ptr_anim_tex, lev);
    int modelFrames = 0;

    if (lev->ptrModelsPtrArray != NULL) {
        const int prevSrc = s_src;
        s_src = (s_mltCount > 0) ? 1 : 0;      /* model frames read the model VRM when present */
        for (u32 m = 0; m < lev->numModels; m++) {
            struct Model *pModel = lev->ptrModelsPtrArray[m];
            if (pModel == NULL) break;
            for (int h = 0; h < pModel->numHeaders; h++) {
                struct ModelHeader *hdr = &pModel->headers[h];
                if (hdr->animtex != NULL && (hdr->flags & 2) == 0)
                    modelFrames += NltPatchAnimList(hdr->animtex, lev);
            }
        }
        s_src = prevSrc;
    }
    fprintf(stderr, "[NLT] AnimTex: patched %d level frames, %d model frames\n",
            levFrames, modelFrames);
}

/* ---- Model layouts (injected models) --------------------------------------
 * ModelHeader offsets, same ones RegisterModelTextures() relies on
 * (data[88] = command list, data[64] = TextureLayout*[] for header 0;
 * header 0 sits at Model+0x18, so +0x20 / +0x28 inside the header).
 * If struct ModelHeader exposes these fields by name, prefer the names. */
#define NLT_MH_CMD  0x20
#define NLT_MH_TEX  0x28

/* ---- pointer sanity (models we did not build ourselves) --------------------
 * A model's headers, command list, TextureLayout array and layouts all live in
 * the same file blob as the model itself, so any pointer farther than
 * NLT_WINDOW from the model, null, tiny or misaligned is garbage and is skipped
 * instead of dereferenced. 'trace' variables record the last step so a fault
 * (see NltGuard* below) can say exactly where it happened. */
#define NLT_WINDOW 0x800000u
static volatile int s_trModel = -1, s_trHdr = -1, s_trCmd = -1, s_trTi = -1;
static volatile const char *s_trWhat = "";
static int s_badPtrs = 0;

static int NltNear(const void *p, const void *base)
{
    uintptr_t a = (uintptr_t)p, b = (uintptr_t)base;
    if (a < 0x10000u || (a & 3u) != 0) return 0;
    return (a > b ? a - b : b - a) < NLT_WINDOW;
}

static int NltPatchModelLayouts(struct Model *pModel)
{
    int n = 0;
    s_trWhat = "model fields";
    if (pModel->numHeaders <= 0 || pModel->numHeaders > 16 || !NltNear(pModel->headers, pModel)) {
        s_badPtrs++;
        fprintf(stderr, "[NLT] model %p: bad numHeaders=%d headers=%p, skipped\n",
                (void *)pModel, (int)pModel->numHeaders, (void *)pModel->headers);
        return 0;
    }
    for (int h = 0; h < pModel->numHeaders; h++) {
        s_trHdr = h;
        u8 *hdr = (u8 *)&pModel->headers[h];
        s_trWhat = "header ptrs";
        u32 *cmd = *(u32 **)(hdr + NLT_MH_CMD);
        struct TextureLayout **arr = *(struct TextureLayout ***)(hdr + NLT_MH_TEX);
        if (cmd == NULL || arr == NULL) continue;
        if (!NltNear(cmd, pModel) || !NltNear(arr, pModel)) {
            s_badPtrs++;
            fprintf(stderr, "[NLT] model %p hdr %d: cmd=%p tex=%p outside model blob, skipped\n",
                    (void *)pModel, h, (void *)cmd, (void *)arr);
            continue;
        }

        u8 seen[512 / 8];
        memset(seen, 0, sizeof(seen));
        int guard = 0;
        s_trWhat = "command list";
        for (cmd++; *cmd != 0xFFFFFFFFu && guard++ < (1 << 18); cmd++) {   /* [0] = palette count */
            s_trCmd = guard;
            u32 ti = *cmd & 0x1FF;
            if (ti == 0 || ti >= 512) continue;
            if (seen[ti >> 3] & (1u << (ti & 7))) continue;
            seen[ti >> 3] |= (u8)(1u << (ti & 7));
            s_trTi = (int)ti;

            s_trWhat = "tex array entry";
            struct TextureLayout *tl = arr[ti - 1];                         /* ti is 1-based */
            if (tl == NULL) continue;
            if (!NltNear(tl, pModel)) { s_badPtrs++; continue; }
            s_trWhat = "layout";
            if ((tl->clut & NLT_SENT) && !NltIsPageIdx((u16)(tl->clut & 0x7FFF)))
                continue;                                                    /* other Sentinel (custom racer) */
            NltPatchOne(tl, 0);
            n++;
            s_trWhat = "command list";
        }
    }
    return n;
}

static void NltPatchModels(struct Level *lev)
{
    if (lev->ptrModelsPtrArray == NULL || s_mltCount == 0) {         /* no model VRM: legacy behaviour */
        fprintf(stderr, "[NLT] Models: NOT patched (ptrModelsPtrArray=%p, model VRM rects=%d)\n",
                (void *)lev->ptrModelsPtrArray, s_mltCount);
        return;
    }
    const int prevSrc = s_src;
    const int pagesBefore = s_pgCount;
    int layouts = 0;
    s_src = 1;
    for (u32 m = 0; m < lev->numModels; m++) {
        struct Model *pModel = lev->ptrModelsPtrArray[m];
        if (pModel == NULL) break;
        layouts += NltPatchModelLayouts(pModel);
    }
    s_src = prevSrc;
    fprintf(stderr, "[NLT] Models: %d models, %d layouts patched from model VRM, %d new pages\n",
            (int)lev->numModels, layouts, s_pgCount - pagesBefore);
}

/* Patches ONE model (e.g. the character model list[18] of an Adventure Pack MPK:
 * id = -1, so it can not be found through gGT->modelPtr[id]). Call it from the
 * pack code right after picking the model, once the custom level is loaded
 * (after PatchLev). Texture source = model_textures.vrm; layouts it does not
 * cover are left untouched. Safe to call more than once on the same model.
 * Returns the number of layouts patched. */
int NativeLevelTextures_PatchModel(struct Model *m)
{
    if (m == NULL || (uintptr_t)m < 0x10000u || ((uintptr_t)m & 3u) != 0) return 0;
    if (sdata == NULL || sdata->gGT == NULL || !NativeLevelTextures_IsCustomLevelActive()) return 0;
    if (s_mltCount == 0) {
        fprintf(stderr, "[NLT] PatchModel(%p): no model VRM loaded\n", (void *)m);
        return 0;
    }
    struct Level *lev = sdata->gGT->level1;
    const int prevSrc = s_src, prevLeave = s_leaveUncovered;
    const int pagesBefore = s_pgCount;
    s_src = 1; s_leaveUncovered = 1; s_uncovered = 0; s_badPtrs = 0;
    int n = NltPatchModelLayouts(m);
    if (lev != NULL && m->numHeaders > 0 && m->numHeaders <= 16 && NltNear(m->headers, m)) {
        for (int h = 0; h < m->numHeaders; h++) {
            struct ModelHeader *hdr = &m->headers[h];
            if (hdr->animtex != NULL && (hdr->flags & 2) == 0 && NltNear(hdr->animtex, m))
                NltPatchAnimList(hdr->animtex, lev);
        }
    }
    s_src = prevSrc; s_leaveUncovered = prevLeave;
    fprintf(stderr, "[NLT] PatchModel '%.16s' @%p: %d layouts patched, %d new pages, "
                    "%d NOT in model VRM, %d bad pointers\n",
            m->name, (void *)m, n, s_pgCount - pagesBefore, s_uncovered, s_badPtrs);
    for (int i = 0; i < s_uncovered && i < 8; i++)
        fprintf(stderr, "[NLT]   uncovered tpage=0x%04X clut=0x%04X\n", s_uncSample[i][0], s_uncSample[i][1]);
    return n;
}

/* ---- fault guard -----------------------------------------------------------
 * Patching foreign models walks pointers we cannot fully validate. On POSIX we
 * trap SIGSEGV/SIGBUS around that walk, report the exact step, and give up on
 * the patch instead of killing the game. (No-op elsewhere.) */
static void *volatile s_guardAddr = NULL;

#if defined(__unix__) || defined(__APPLE__)
#include <setjmp.h>
#include <signal.h>
static volatile sig_atomic_t s_guardOn = 0;
static void NltFaultHandler(int sig, siginfo_t *si, void *ctx)
{
    (void)ctx;
    if (s_guardOn) { s_guardAddr = si ? si->si_addr : NULL; s_guardOn = 0; siglongjmp(s_guardJmp, 1); }
    signal(sig, SIG_DFL);
    raise(sig);
}
#define NLT_GUARD_BEGIN(oldSegv, oldBus, faulted)                                   \
    struct sigaction _sa, oldSegv, oldBus;                                          \
    memset(&_sa, 0, sizeof(_sa));                                                   \
    _sa.sa_sigaction = NltFaultHandler; _sa.sa_flags = SA_SIGINFO | SA_NODEFER;     \
    sigemptyset(&_sa.sa_mask);                                                      \
    sigaction(SIGSEGV, &_sa, &oldSegv); sigaction(SIGBUS, &_sa, &oldBus);           \
    s_guardOn = 1;                                                                  \
    int faulted = sigsetjmp(s_guardJmp, 1)
#define NLT_GUARD_END(oldSegv, oldBus)                                              \
    s_guardOn = 0; sigaction(SIGSEGV, &oldSegv, NULL); sigaction(SIGBUS, &oldBus, NULL)
#else
#define NLT_GUARD_BEGIN(oldSegv, oldBus, faulted) int oldSegv = 0, oldBus = 0, faulted = 0; (void)oldSegv; (void)oldBus
#define NLT_GUARD_END(oldSegv, oldBus) ((void)0)
#endif

/* Models that something else swapped into gGT->modelPtr[] in place of the ones
 * this .lev ships (Adventure Pack: LOAD_TenStages case 7 ->
 * NativeAdventurePack_OverrideModelPtrs). RenderBucket draws through
 * idpp->ptrTexLayout = header->ptrTexLayout of THE MODEL IN USE, so patching only
 * lev->ptrModelsPtrArray (NltPatchModels) leaves the replacement models on raw
 * VRAM, where the custom data.vrm has overwritten the retail garage textures =>
 * transparent/invisible bodies. Call this right after the override. */
int NativeLevelTextures_PatchOverriddenModels(struct Level *lev)
{
    _Static_assert(sizeof(((struct GameTracker *)0)->modelPtr) > 64, "gGT->modelPtr must be an array");
    if (lev == NULL || lev->ptrModelsPtrArray == NULL || sdata == NULL || sdata->gGT == NULL) return 0;
    if (s_mltCount == 0) {
        fprintf(stderr, "[NLT] PatchOverriddenModels: no model VRM loaded, nothing done\n");
        return 0;
    }
    struct GameTracker *gGT = sdata->gGT;
    const int nSlots = (int)(sizeof(gGT->modelPtr) / sizeof(gGT->modelPtr[0]));
    const int prevSrc = s_src, prevLeave = s_leaveUncovered;
    const int pagesBefore = s_pgCount;
    volatile int models = 0, layouts = 0;
    s_src = 1; s_leaveUncovered = 1; s_uncovered = 0; s_badPtrs = 0;
    s_trModel = s_trHdr = s_trCmd = s_trTi = -1; s_trWhat = "start";
    fprintf(stderr, "[NLT] PatchOverriddenModels: start (lev models=%u, slots=%d)\n", (unsigned)lev->numModels, nSlots);
    fflush(stderr);

    NLT_GUARD_BEGIN(oldSegv, oldBus, faulted);
    if (!faulted) {
        for (u32 m = 0; m < lev->numModels && m < 64; m++) {
            struct Model *own = lev->ptrModelsPtrArray[m];
            if (own == NULL) break;
            int id = (int)own->id;
            if (id < 0 || id >= nSlots) continue;
            struct Model *cur = gGT->modelPtr[id];
            if (cur == NULL || cur == own) continue;               /* not overridden */
            s_trModel = id;
            fprintf(stderr, "[NLT] overridden model id=%d own=%p replacement=%p\n", id, (void *)own, (void *)cur);
            fflush(stderr);
            if ((uintptr_t)cur < 0x10000u || ((uintptr_t)cur & 3u) != 0) {
                fprintf(stderr, "[NLT]   replacement pointer invalid, skipped\n");
                continue;
            }
            fprintf(stderr, "[NLT]   numHeaders=%d headers=%p\n", (int)cur->numHeaders, (void *)cur->headers);
            fflush(stderr);
            models++;
            layouts += NltPatchModelLayouts(cur);
            if (cur->numHeaders > 0 && cur->numHeaders <= 16 && NltNear(cur->headers, cur)) {
                for (int h = 0; h < cur->numHeaders; h++) {
                    struct ModelHeader *hdr = &cur->headers[h];
                    s_trHdr = h; s_trWhat = "animtex";
                    if (hdr->animtex != NULL && (hdr->flags & 2) == 0 && NltNear(hdr->animtex, cur))
                        NltPatchAnimList(hdr->animtex, lev);
                }
            }
        }
    }
    NLT_GUARD_END(oldSegv, oldBus);

    if (faulted) {
        fprintf(stderr, "[NLT] !! FAULT while patching overridden models: addr=%p model id=%d hdr=%d cmdIdx=%d ti=%d step='%s'\n"
                        "[NLT] !! patch aborted, game continues (these models stay on raw VRAM)\n",
                (void *)s_guardAddr, s_trModel, s_trHdr, s_trCmd, s_trTi, (const char *)s_trWhat);
    }
    s_src = prevSrc; s_leaveUncovered = prevLeave;
    fprintf(stderr, "[NLT] PatchOverriddenModels: %d replaced models, %d layouts, %d new pages, "
                    "%d layouts NOT in model VRM (left on raw VRAM), %d bad pointers skipped\n",
            (int)models, (int)layouts, s_pgCount - pagesBefore, s_uncovered, s_badPtrs);
    for (int i = 0; i < s_uncovered && i < 8; i++)
        fprintf(stderr, "[NLT]   uncovered tpage=0x%04X clut=0x%04X\n", s_uncSample[i][0], s_uncSample[i][1]);
    fflush(stderr);
    return (int)models;
}

/* model_textures.vrm: same container as a level VRM (magic 0x20 + TIMs of raw
 * 16bpp VRAM rects), but only copied into s_vv2 -- no GL texture per TIM. */
int NativeLevelTextures_DecodeModelVRM(const u8 *buf, int size)
{
    s_mltCount = 0;
    memset(s_vv2, 0, sizeof(s_vv2));
    if (size < 4 || NltRd32(buf) != 0x20) {
        fprintf(stderr, "[NLT] DecodeModelVRM: invalid magic or too small (%d)\n", size);
        return 0;
    }
    int off = 4, nTim = 0;
    while (off + 4 <= size && s_mltCount < NLT_MAX) {
        u32 timSize = NltRd32(buf + off);
        if (timSize == 0) break;
        if (timSize > (u32)(size - off - 4)) break;

        struct NltTim t;
        if (NltParseTim(buf + off + 4, buf + off + 4 + timSize, &t)) {
            /* Any bpp: rects are raw VRAM halfwords. The CLUT rect (if the TIM has
             * one) is blitted and marked as covered too. */
            NltBlitTim(s_vv2, s_mlt, &s_mltCount, &t);
            NltAddRect(s_mlt, &s_mltCount, t.rx, t.ry, t.rw, t.rh);
            fprintf(stderr, "[NLT] model VRM TIM#%d bpp=%d rect=(%d,%d,%d,%d)%s\n",
                    nTim, t.bpp, t.rx, t.ry, t.rw, t.rh, t.hasClut ? " +CLUT" : "");
        } else {
            fprintf(stderr, "[NLT] model VRM TIM#%d at +%d: invalid/unsupported, skipped\n", nTim, off);
        }
        off += 4 + (int)timSize;
        nTim++;
    }
    int nz = 0;
    for (int i = 0; i < 1024 * 512; i++) nz += (s_vv2[i] != 0);
    fprintf(stderr, "[NLT] DecodeModelVRM: %d rects, %d non-zero halfwords%s\n", s_mltCount, nz,
            nz == 0 ? "  <-- EMPTY: model pages will be blank" : "");
    NativeRenderer_UploadCustomVramModels(s_vv2, 1024, 512);
    return s_mltCount;
}

/* Optional: <dir of the level VRM>/model_textures.vrm. Absent => nothing changes. */
static void NltLoadModelVrmBeside(const char *relPath)
{
    char path[512];
    snprintf(path, sizeof(path), "assets/%s", relPath);
    char *sl = strrchr(path, '/');
    char *bs = strrchr(path, '\\');
    if (bs != NULL && (sl == NULL || bs > sl)) sl = bs;
    if (sl != NULL) sl[1] = '\0'; else path[0] = '\0';
    strncat(path, "model_textures.vrm", sizeof(path) - strlen(path) - 1);

    FILE *f = fopen(path, "rb");
    if (!f) { s_mltCount = 0; return; }
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (sz <= 0 || sz > 8 * 1024 * 1024) { fclose(f); return; }
    unsigned char *b = (unsigned char *)malloc((size_t)sz);
    if (!b) { fclose(f); return; }
    size_t got = fread(b, 1, (size_t)sz, f);
    fclose(f);
    if (got == (size_t)sz) {
        fprintf(stderr, "[NLT] loading model VRM %s (%ld bytes)\n", path, sz);
        NativeLevelTextures_DecodeModelVRM(b, (int)sz);
    }
    free(b);
}

void NativeLevelTextures_PatchLev(struct Level *lev)
{
    NltInitEnv();
    if (!lev || !lev->ptr_mesh_info) {
        fprintf(stderr, "[NLT] PatchLev: no mesh_info\n");
        return;
    }
    s_seenCount = 0;
    s_dbgN = 0;
    memset(s_hideBits, 0, sizeof(s_hideBits));
    s_hideBitsLevelID = sdata->gGT->levelID;
    int skippedHeader = 0;
    struct mesh_info *mesh = lev->ptr_mesh_info;
    struct QuadBlock *qb = mesh->ptrQuadBlockArray;


    for (int i = 0; i < mesh->numQuadBlock; i++, qb++) {
        for (int f = 0; f < 4; f++) {
            struct TextureLayout *tl = NltResolveTL((u32)qb->ptr_texture_mid[f]);
            if (NltPointsIntoLevelHeader(tl, lev)) { skippedHeader++; continue; }
            NltPatchOne(tl, 0);
        }
        {
            struct TextureLayout *tl = NltResolveTL((u32)qb->ptr_texture_low);
            if (NltPointsIntoLevelHeader(tl, lev)) { skippedHeader++; }
            else if (tl != NULL) NltPatchOne(tl, 1);
        }

        if (NltIsTriggerOnlyBlock(qb)) {
            NltMarkHidden((u16)qb->blockID);
            if (sdata && sdata->gGT && sdata->gGT->levelID == 6) {
                fprintf(stderr, "[HIDE] blockID=%u quadFlags=0x%04X\n",
                        (unsigned)qb->blockID, (unsigned)qb->quadFlags);
            }
        }
    }
    NltPatchAnimTex(lev);
    NltPatchModels(lev);

    fprintf(stderr, "[NLT] skipped %d texture ptrs that pointed into the Level header\n", skippedHeader);
    fprintf(stderr, "[NLT] PatchLev: %d QB, %d unique TL, %d decoded, %d pages\n",
            mesh->numQuadBlock, s_seenCount, s_ltCount, s_pgCount);

    for (int i = 0; i < s_dbgN; i++) {
        int t = s_dbg[i].tpage;
        fprintf(stderr, "[NLT] tpage=0x%04X X=%d Y=%d mode=%dbpp mid=%d low=%d tim=%d sliced=%d\n",
                t, (t & 0xF) * 64, ((t >> 4) & 1) * 256, 4 << ((t >> 7) & 3),
                s_dbg[i].mid, s_dbg[i].low, s_dbg[i].tim, s_dbg[i].sliced);
    }
}

int NativeLevelTextures_LookupPage(u16 tpage, u16 clut)
{
    if (s_pgCount == 0) return -1;
    if (!NativeLevelTextures_IsCustomLevelActive()) return -1;

    const u16 key = tpage & 0x019F;
    for (int i = 0; i < s_pgCount; i++)
        if (s_pg[i].tpage == key && s_pg[i].clut == clut && s_pg[i].src == 0) return s_pg[i].idx;
    return -1;
}

/* FASE 2 fix: original clut of a page (before Sentinel patching). The VRAM
 * raw shader needs the original CLUT position for v_page_clut.zw. The vertex
 * clut would otherwise carry 0x8000|pg (Sentinel marker) which the shader
 * interprets as a Y offset of half-VRAM. Returns 0xFFFF for invalid idx. */
u16 NativeLevelTextures_GetPageClut(u16 idx)
{
    /* idx is a GL pool index (256..N), NOT an s_pg[] array position.
     * Loop linear search on .idx to find the correct entry. */
    for (int i = 0; i < s_pgCount; i++)
        if (s_pg[i].idx == idx) return s_pg[i].clut;
    return 0xFFFF;
}

void NativeLevelTextures_PatchTL(struct TextureLayout *tl)
{
    if (!NativeLevelTextures_IsCustomLevelActive()) return;
    NltPatchOne(tl, 1);
}