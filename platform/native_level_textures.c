#include <common.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "platform/native_gpu.h"
#include "platform/native_glad.h"
#include "LevelRegistry.h"

extern int  NativeCustomRacer_AllocTexIdx(void);
extern void NativeCustomRacer_FreeTexIdx(int idx);
extern int LOAD_GetBigfileIndex(int levelID, int levelLOD, int subfileIndex);

#define NLT_MAX       64     /* TIMs (rects) per VRM */
#define NLT_MAX_PAGES 256    /* pages (tpage, clut) per level */
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
 * NLT_DUMP=1 dumps nlt_timN.tga (raw VRM read as RGB555, for inspection
 * only) and nlt_page_<tpage>_<clutX>_<clutY>.tga (final pages).
 * NLT_MAP has no effect anymore.
 */

struct NltEntry { int x, y, w, h; u16 idx; u8 *rgba; };
static struct NltEntry s_lt[NLT_MAX];
static int s_ltCount = 0;

/* GL 256x256 page already built for a concrete (tpage, clut). */
struct NltPage { u16 tpage, clut, idx; };
static struct NltPage s_pg[NLT_MAX_PAGES];
static int s_pgCount = 0;

/* Raw VRAM copy as left by the VRM (1024x512 halfwords). */
static u16 s_vv[1024 * 512];

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
    dst[3] = 0xFF;
}

static int NltDecodeTIM(const u8 *tim, const u8 **px,
                        int *rx, int *ry, int *rw, int *rh,
                        const u16 **clut, int *bpp, int *hasClut)
{
    if (*(const u32 *)tim != 0x10) return 0;
    u32 flags = *(const u32 *)(tim + 4);
    *bpp = flags & 0x3;
    *hasClut = (flags >> 3) & 1;
    const u8 *p = tim + 8;
    if (*hasClut) {
        u32 clutSize = *(const u32 *)p;
        *clut = (const u16 *)(p + 4);
        p += 4 + clutSize;
    } else {
        *clut = NULL;
    }
    u32 imgSize = *(const u32 *)p;
    const u16 *r = (const u16 *)(p + 4);
    *rx = r[0]; *ry = r[1]; *rw = r[2]; *rh = r[3];
    *px = p + 4 + 8;
    return (int)(p + 4 + imgSize - tim);
}

static void NltDecodePixels(const u8 *px, const u16 *clut, int bpp, int hasClut,
                            int w, int h, u8 *dst)
{
    int n = w * h;
    if (bpp == 2) {
        const u16 *in = (const u16 *)px;
        for (int i = 0; i < n; i++) NltExpand16(in[i], dst + i*4);
    } else if (bpp == 1 && hasClut) {
        for (int i = 0; i < n; i++) NltExpand16(clut[px[i]], dst + i*4);
    } else if (bpp == 0 && hasClut) {
        for (int i = 0; i < n; i++) {
            u8 b = px[i/2];
            u8 nib = (i & 1) ? (u8)(b >> 4) : (u8)(b & 0xF);
            NltExpand16(clut[nib], dst + i*4);
        }
    } else {
        memset(dst, 0, (size_t)n * 4);
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
        NativeGpu_FreeCustomTexture(s_lt[i].idx);
        NativeCustomRacer_FreeTexIdx((int)s_lt[i].idx);
    }
    s_ltCount = 0;

    for (int i = 0; i < s_pgCount; i++) {
        NativeGpu_FreeCustomTexture(s_pg[i].idx);
        NativeCustomRacer_FreeTexIdx((int)s_pg[i].idx);
    }
    s_pgCount = 0;
}

int NativeLevelTextures_DecodeVRM(const u8 *buf, int size)
{
    NltInitEnv();
    NltFreeDecoded();
    memset(s_vv, 0, sizeof(s_vv));

    if (size < 4 || *(const u32 *)buf != 0x20) {
        fprintf(stderr, "[NLT] DecodeVRM: invalid magic or too small (%d)\n", size);
        return 0;
    }

    int off = 4;
    while (off + 4 <= size && s_ltCount < NLT_MAX) {
        u32 timSize = *(const u32 *)(buf + off);
        if (timSize == 0) break;
        if (off + 4 + (int)timSize > size) break;

        const u8 *px; const u16 *clut;
        int rx, ry, rw, rh, bpp, hasClut;
        if (!NltDecodeTIM(buf + off + 4, &px, &rx, &ry, &rw, &rh,
                          &clut, &bpp, &hasClut)) {
            off += 4 + (int)timSize;
            continue;
        }

        fprintf(stderr, "[NLT] TIM rect=(%d,%d,%d,%d) bpp=%d hasClut=%d\n",
                rx, ry, rw, rh, bpp, hasClut);

        /* VRM = raw VRAM: store halfwords as-is in the virtual VRAM. */
        if (bpp == 2 && rx >= 0 && ry >= 0 && rx < 1024 && ry < 512) {
            int cw = (rx + rw > 1024) ? 1024 - rx : rw;
            for (int y = 0; y < rh && ry + y < 512; y++)
                memcpy(&s_vv[(ry + y) * 1024 + rx], px + (size_t)y * rw * 2, (size_t)cw * 2);
        }

        int n = rw * rh;
        u8 *rgba = (u8 *)malloc((size_t)n * 4);
        if (!rgba) { off += 4 + (int)timSize; continue; }

        NltDecodePixels(px, clut, bpp, hasClut, rw, rh, rgba);

        if (s_dump) {
            char nm[64];
            snprintf(nm, sizeof(nm), "nlt_tim%d.tga", s_ltCount);
            NltDumpTGA(nm, rgba, rw, rh);
        }

        TextureID tex = NltUpload(rgba, rw, rh);

        if (tex != 0) {
            int idx = NativeCustomRacer_AllocTexIdx();
            if (idx >= 0) {
                NativeGpu_RegisterCustomTexture((u16)idx, tex, rw, rh);
                s_lt[s_ltCount].x = rx;
                s_lt[s_ltCount].y = ry;
                s_lt[s_ltCount].w = rw;
                s_lt[s_ltCount].h = rh;
                s_lt[s_ltCount].idx = (u16)idx;
                s_lt[s_ltCount].rgba = rgba;
                s_ltCount++;
            } else {
                free(rgba);
            }
        } else {
            free(rgba);
        }
        off += 4 + (int)timSize;
    }

    fprintf(stderr, "[NLT] DecodeVRM: %d TIMs\n", s_ltCount);
    for (int i = 0; i < s_ltCount; i++)
        fprintf(stderr, "[NLT]   [%d] x=%d y=%d w=%d h=%d idx=%d\n",
                i, s_lt[i].x, s_lt[i].y, s_lt[i].w, s_lt[i].h, s_lt[i].idx);
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
    return result;
}

int NativeLevelTextures_IsCustomLevelActive(void)
{
    if (sdata == NULL || sdata->gGT == NULL) return 0;
    int levelID = sdata->gGT->levelID;
    const struct LevelDef *active = LevelRegistry_GetActive();
    if (active != NULL && active->baseLevelID == levelID) return 1;
    if (levelID == MAIN_MENU_LEVEL) return 0;
    return LevelRegistry_GetReplacement(levelID) != NULL;
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
    for (int i = 0; i < s_ltCount; i++) {
        const struct NltEntry *e = &s_lt[i];
        if (x >= e->x && x < e->x + e->w && y >= e->y && y < e->y + e->h) return 1;
    }
    return 0;
}

/* 1 if rect (x,y,w,h) in halfwords touches any VRM rect. */
static int NltTouches(int x, int y, int w, int h)
{
    for (int i = 0; i < s_ltCount; i++) {
        const struct NltEntry *e = &s_lt[i];
        if (x < e->x + e->w && x + w > e->x && y < e->y + e->h && y + h > e->y) return 1;
    }
    return 0;
}

/* Halfword from virtual VRAM, or -1 if the VRM does not cover that position. */
static int NltVV(int x, int y)
{
    x &= 1023; y &= 511;
    return NltCovered(x, y) ? (int)s_vv[y * 1024 + x] : -1;
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
        if (s_pg[i].tpage == key && s_pg[i].clut == clut) return s_pg[i].idx;
    if (s_pgCount >= NLT_MAX_PAGES) return -1;

    const int tpX = (tpage & 0xF) * 64;
    const int tpY = ((tpage >> 4) & 1) * 256;
    const int mode = (tpage >> 7) & 3;              /* 0=4bpp 1=8bpp 2=16bpp */
    const int cx = (clut & 0x3F) << 4, cy = clut >> 6;

    u8 *page = (u8 *)calloc(256 * 256, 4);
    if (!page) return -1;
    int miss = 0;
    for (int v = 0; v < 256; v++) {
        for (int u = 0; u < 256; u++) {
            int c = NltFetch(mode, tpX, tpY, cx, cy, u, v);
            if (c < 0) { miss++; continue; }        /* alpha 0 */
            if (c == 0) continue;                   /* 0x0000 = transparent on PSX */
            NltExpand16((u16)c, page + ((size_t)v * 256 + u) * 4);
        }
    }

    if (s_dump) {
        char nm[64];
        snprintf(nm, sizeof(nm), "nlt_page_%04X_%d_%d.tga", key, cx, cy);
        NltDumpTGA(nm, page, 256, 256);
    }

    TextureID tex = NltUpload(page, 256, 256);
    free(page);
    if (tex == 0) return -1;
    int idx = NativeCustomRacer_AllocTexIdx();
    if (idx < 0) return -1;
    NativeGpu_RegisterCustomTexture((u16)idx, tex, 256, 256);

    s_pg[s_pgCount].tpage = key;
    s_pg[s_pgCount].clut = clut;
    s_pg[s_pgCount].idx = (u16)idx;
    s_pgCount++;

    fprintf(stderr, "[NLT] page tpage=0x%04X clut=(%d,%d) mode=%d -> idx=%d miss=%d\n",
            key, cx, cy, mode, idx, miss);
    return idx;
}

static struct TextureLayout *s_seen[4096];
static int s_seenCount = 0;

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
    if (s_seenCount < 4096) s_seen[s_seenCount++] = tl;

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
    int pg = inVrm ? NltGetPage(tpage, clut) : -1;
    if (pg >= 0) {
        tl->clut = (u16)(NLT_SENT | pg);
        NltDbgCount(tpage, isLow, pg, 1);
    } else {
        NltDbgCount(tpage, isLow, -1, 0);
        tl->clut &= 0x7FFF;
    }
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
    struct mesh_info *mesh = lev->ptr_mesh_info;
    struct QuadBlock *qb = mesh->ptrQuadBlockArray;
    for (int i = 0; i < mesh->numQuadBlock; i++, qb++) {
        for (int f = 0; f < 4; f++)
            NltPatchOne(NltResolveTL((u32)qb->ptr_texture_mid[f]), 0);
        NltPatchOne(NltResolveTL((u32)qb->ptr_texture_low), 1);
    }
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
    const u16 key = tpage & 0x019F;
    for (int i = 0; i < s_pgCount; i++)
        if (s_pg[i].tpage == key && s_pg[i].clut == clut) return s_pg[i].idx;
    return -1;
}

void NativeLevelTextures_PatchTL(struct TextureLayout *tl)
{
    NltPatchOne(tl, 1);
}