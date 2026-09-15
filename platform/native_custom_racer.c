#include <common.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

#include <platform/native_custom_racer.h>
#include <platform/native_renderer.h>
#include <platform/native_gpu.h>
#include <platform/native_glad.h>
#include <ovr_230.h>

#define NATIVE_ROSTER_MAX   128
#define NATIVE_VRM_MAX_BYTES (256 * 1024)
#define NATIVE_CTR_MAX_BYTES (256 * 1024)

/* Width in VRAM words assigned to each player slot. */
#define NATIVE_SLOT_WIDTH 128

#define NATIVE_MODELHEADER_SIZE  0x40
#define NATIVE_MODELHEADER_COUNT 4

/* Pagination */
#define NATIVE_ICON_BASE  32
#define NATIVE_ICON_COUNT 16

static void Log(const char *fmt, ...)
{
    va_list args;
    va_start(args, fmt);
    vfprintf(stderr, fmt, args);
    va_end(args);
    fflush(stderr);
}

typedef struct
{
    int slotID;
    char folder[64];
} RosterEntry;

/* New roster format entry: page slot folder [engine] ["Display Name"] */
typedef struct
{
    int  page;
    int  slot;
    char folder[64];
    int  engineID;
    char displayName[64];
    u32  color[4];       /* packed vertex-color codes (all 4 identical) */
    int  hasColor;       /* 1 if #RRGGBB was present in roster.txt */
} PageEntry;

static RosterEntry s_roster[NATIVE_ROSTER_MAX];
static int s_rosterCount = 0;
static int s_rosterLoaded = 0;

static PageEntry s_pageEntries[NATIVE_ROSTER_MAX];
static int s_pageEntryCount = 0;

static int s_page = 0;
static int s_pageCount = 1;
static int s_appliedPage = -1;

/* Backup of MetaDataCharacters[0..15] to restore between pages. */
static int s_metaBackupDone = 0;
static struct MetaDataCHAR s_metaBackup[16];

/* Phase 1: parallel tables in BSS for IDs 16+.
 * Referenced from other .c files through GET_METADATA (hence not static). */
struct MetaDataCHAR s_customMeta[NATIVE_CUSTOM_COUNT];
s16                 s_customMenuID[NATIVE_CUSTOM_COUNT];

/* Per-custom display name (roster.txt "Display Name" field). Kept in BSS
 * so UI can read it without touching MetaDataCHAR (static_asserts) or
 * name_Debug (used by GetFolder / model lookup). Empty = unset. */
static char s_customDisplayName[NATIVE_CUSTOM_COUNT][64];

/* Phase 2: copy of the menu meta array with custom slots patched to
 * characterID 16+. Filled on demand by NativeCustomRacer_GetPageMeta. */
static struct CharacterSelectMeta s_pageMeta[NATIVE_PAGE_SIZE];

/* Per-custom minimap color (roster.txt optional #RRGGBB field). */
static u32 s_customColor[NATIVE_CUSTOM_COUNT][4];
static u8  s_customHasColor[NATIVE_CUSTOM_COUNT];

/* Menu preview cache: one struct Model* per (custom ID, player index).
 * Each player slot has its own model_pN.ctr whose UVs are baked for slot N,
 * and each textures.vrm is uploaded to the matching VRAM slot N, so four
 * different customs can be previewed simultaneously without UV/VRAM aliasing.
 * Owned by this subsystem; never freed. */
#define NATIVE_MENU_PLAYER_SLOTS 4
static struct Model   *s_menuModel  [NATIVE_CUSTOM_COUNT][NATIVE_MENU_PLAYER_SLOTS];
static unsigned char  *s_menuVrm    [NATIVE_CUSTOM_COUNT][NATIVE_MENU_PLAYER_SLOTS];
static long            s_menuVrmSize[NATIVE_CUSTOM_COUNT][NATIVE_MENU_PLAYER_SLOTS];

/* === Fase 2.5: BUG-MENU-04 side table =====================================
 * data.driverModelExtras[] has only LOAD_DRIVER_MODEL_EXTRA_COUNT (=3)
 * slots; index 3 (P4 in 4P) aliases podiumModel_firstPlace and corrupts
 * the podium pointers, crashing the menu on exit. We keep the 4th player's
 * custom model here, keyed by playerIndex, already offset by
 * LOAD_MODEL_FILE_HEADER_BYTES so it points to a valid struct Model. */
#define NATIVE_PLAYER_MODEL_SLOTS 8
static void *s_playerModelPtr[NATIVE_PLAYER_MODEL_SLOTS];

static int ParseEngineID(const char *s)
{
    if (strcmp(s, "SPEED")    == 0) return SPEED;
    if (strcmp(s, "BALANCED") == 0) return BALANCED;
    if (strcmp(s, "ACCEL")    == 0) return ACCEL;
    if (strcmp(s, "TURN")     == 0) return TURN;
    return BALANCED;
}

/* --------------------------------------------------------------------- */
/* Legacy parser (ext_id folder). Kept for backward compatibility.       */
/* --------------------------------------------------------------------- */
static int Roster_ParseLine(char *line, RosterEntry *out)
{
    char *p = line;
    while (*p == ' ' || *p == '\t')
        p++;

    if (*p == '#' || *p == '\n' || *p == '\0')
        return 0;

    char *end = NULL;
    long slot = strtol(p, &end, 10);
    if (end == p)
        return 0;
    if (slot < 0 || slot >= 256)
        return 0;

    p = end;
    while (*p == ' ' || *p == '\t')
        p++;

    int i = 0;
    while (*p && *p != '\n' && *p != '\r' && *p != ' ' && *p != '\t'
           && i < (int)sizeof(out->folder) - 1)
        out->folder[i++] = *p++;
    out->folder[i] = '\0';

    if (i == 0)
        return 0;

    out->slotID = (int)slot;
    return 1;
}

/* --------------------------------------------------------------------- */
/* New parser: "page slot folder [engine] ["name"]"                      */
/* --------------------------------------------------------------------- */
static int Page_ParseLine(char *line, PageEntry *out)
{
    char *p = line;
    while (*p == ' ' || *p == '\t') p++;
    if (*p == '#' || *p == '\n' || *p == '\0') return 0;

    char *end = NULL;
    long page = strtol(p, &end, 10);
    if (end == p) return 0;
    p = end;
    while (*p == ' ' || *p == '\t') p++;

    long slot = strtol(p, &end, 10);
    if (end == p) return 0;
    p = end;
    while (*p == ' ' || *p == '\t') p++;

    int i = 0;
    while (*p && *p != '\n' && *p != '\r' && *p != ' ' && *p != '\t'
           && i < (int)sizeof(out->folder) - 1)
        out->folder[i++] = *p++;
    out->folder[i] = '\0';
    if (i == 0) return 0;

    /* Optional engine word. If the next token starts with '"', there is no
     * engine and BALANCED is used by default. */
    out->engineID = BALANCED;
    while (*p == ' ' || *p == '\t') p++;
    if (*p != '"')
    {
        char engine[32] = {0};
        i = 0;
        while (*p && *p != '\n' && *p != '\r' && *p != ' ' && *p != '\t'
               && i < (int)sizeof(engine) - 1)
            engine[i++] = *p++;
        if (i > 0)
            out->engineID = ParseEngineID(engine);
    }

    /* Optional "Display Name" in quotes */
    while (*p == ' ' || *p == '\t') p++;
    out->displayName[0] = '\0';
    if (*p == '"')
    {
        p++;
        i = 0;
        while (*p && *p != '"' && *p != '\n' && *p != '\r'
               && i < (int)sizeof(out->displayName) - 1)
            out->displayName[i++] = *p++;
        out->displayName[i] = '\0';
    }
    if (*p == '"') p++;

    /* Optional #RRGGBB (hash optional) */
    out->hasColor = 0;
    out->color[0] = out->color[1] = out->color[2] = out->color[3] = 0;
    while (*p == ' ' || *p == '\t') p++;
    if (*p == '#') p++;
    if (*p && *p != '\n' && *p != '\r')
    {
        unsigned int r = 0, g = 0, b = 0;
        if (sscanf(p, "%2x%2x%2x", &r, &g, &b) == 3)
        {
            /* PS1 packed: byte0=r, byte1=g, byte2=b, byte3=code */
            u32 packed = (r & 0xff) | ((g & 0xff) << 8) | ((b & 0xff) << 16) | (0x20u << 24);
            out->color[0] = out->color[1] = out->color[2] = out->color[3] = packed;
            out->hasColor = 1;
        }
    }

    out->page = (int)page;
    out->slot = (int)slot;
    return 1;
}

void NativeCustomRacer_ReloadRoster(void)
{
    s_rosterCount = 0;
    s_pageEntryCount = 0;
    s_pageCount = 1;
    s_rosterLoaded = 1;

    memset(s_customMeta, 0, sizeof(s_customMeta));
    memset(s_customHasColor, 0, sizeof(s_customHasColor));
    for (int i = 0; i < NATIVE_CUSTOM_COUNT; i++)
        s_customMenuID[i] = -1;

    FILE *f = fopen("assets/mods/racers/roster.txt", "rb");
    if (!f)
        return;

    char line[256];
    int maxPage = 0;
    while (fgets(line, sizeof(line), f) && s_pageEntryCount < NATIVE_ROSTER_MAX)
    {
        PageEntry e;
        if (!Page_ParseLine(line, &e))
            continue;

        s_pageEntries[s_pageEntryCount++] = e;
        if (e.page > maxPage)
            maxPage = e.page;

        /* Phase 1: populate parallel table for IDs 16+.
         * customID = 16 + (page-1)*16 + slot */
        if (e.page > 0)
        {
            int customID = NATIVE_CUSTOM_ID_BASE
                         + (e.page - 1) * NATIVE_PAGE_SIZE
                         + e.slot;
            if (customID >= NATIVE_CUSTOM_ID_BASE &&
                customID <  NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT)
            {
                int idx = customID - NATIVE_CUSTOM_ID_BASE;
                /* s_pageEntries is static, so the pointer outlives this call */
                char *folderStored = s_pageEntries[s_pageEntryCount - 1].folder;

                s_customMeta[idx].name_Debug     = folderStored;
                s_customMeta[idx].name_LNG_long  = -1;   /* TODO Phase 5 */
                s_customMeta[idx].name_LNG_short = -1;   /* TODO Phase 5 */
                s_customMeta[idx].iconID         = (s16)(NATIVE_ICON_BASE + e.slot);
                s_customMeta[idx].engineID       = e.engineID;

                memcpy(s_customColor[idx], e.color, sizeof(e.color));
                s_customHasColor[idx] = (u8)e.hasColor;

                s_customMenuID[idx] = (s16)e.slot;

                {
                    const char *dn = (e.displayName[0] != '\0') ? e.displayName : e.folder;
                    strncpy(s_customDisplayName[idx], dn, sizeof(s_customDisplayName[idx]) - 1);
                    s_customDisplayName[idx][sizeof(s_customDisplayName[idx]) - 1] = '\0';
                }
            }
        }

        /* Compatibility: fill s_roster[] with slotID = page*16 + slot */
        if (s_rosterCount < NATIVE_ROSTER_MAX)
        {
            s_roster[s_rosterCount].slotID = e.page * NATIVE_PAGE_SIZE + e.slot;
            strncpy(s_roster[s_rosterCount].folder, e.folder,
                    sizeof(s_roster[s_rosterCount].folder) - 1);
            s_roster[s_rosterCount].folder[
                sizeof(s_roster[s_rosterCount].folder) - 1] = '\0';
            s_rosterCount++;
        }
    }
    fclose(f);

    s_pageCount = maxPage + 1;
    if (s_pageCount < 1)
        s_pageCount = 1;

    Log("[CustomRacer] Roster: %d entries, %d pages\n",
        s_pageEntryCount, s_pageCount);
}

void NativeCustomRacer_Init(void)
{
    if (!s_rosterLoaded)
    {
        NativeCustomRacer_ReloadRoster();
        NativeCustomRacer_RefreshPage();
    }
}

/* --------------------------------------------------------------------- */
/* Lookup by page + slot                                                 */
/* --------------------------------------------------------------------- */
static const PageEntry *FindPageEntry(int page, int slot)
{
    for (int i = 0; i < s_pageEntryCount; i++)
    {
        if (s_pageEntries[i].page == page && s_pageEntries[i].slot == slot)
            return &s_pageEntries[i];
    }
    return NULL;
}

/* === Fix D: original IDs (0..15) are NEVER custom. The previous code
 * called FindPageEntry(s_page, characterID), which conflated a characterID
 * with a slot of the active page (id=1 -> page 1 slot 1 -> big_norm). === */
int NativeCustomRacer_HasSlot(int characterID)
{
    NativeCustomRacer_Init();
    if (characterID >= NATIVE_CUSTOM_ID_BASE &&
        characterID <  NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT)
    {
        int idx = characterID - NATIVE_CUSTOM_ID_BASE;
        return s_customMeta[idx].name_Debug != NULL;
    }
    return 0;
}

const char *NativeCustomRacer_GetFolder(int characterID)
{
    NativeCustomRacer_Init();
    if (characterID >= NATIVE_CUSTOM_ID_BASE &&
        characterID <  NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT)
    {
        int idx = characterID - NATIVE_CUSTOM_ID_BASE;
        return s_customMeta[idx].name_Debug;
    }
    return NULL;
}

const u32 *NativeCustomRacer_GetColorPtr(int characterID)
{
    if (characterID < NATIVE_CUSTOM_ID_BASE ||
        characterID >= NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT)
        return NULL;
    int idx = characterID - NATIVE_CUSTOM_ID_BASE;
    if (!s_customHasColor[idx])
        return NULL;
    return s_customColor[idx];
}

const char *NativeCustomRacer_GetDisplayName(int characterID)
{
    NativeCustomRacer_Init();
    if (characterID >= NATIVE_CUSTOM_ID_BASE &&
        characterID <  NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT)
    {
        int idx = characterID - NATIVE_CUSTOM_ID_BASE;
        if (s_customDisplayName[idx][0] != '\0')
            return s_customDisplayName[idx];
    }
    return NULL;
}

/* --------------------------------------------------------------------- */
/* File loading                                                          */
/* --------------------------------------------------------------------- */
static unsigned char *LoadFileToMemory(const char *path, long maxSize, long *outSize)
{
    FILE *f = fopen(path, "rb");
    if (!f)
        return NULL;

    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);

    if (sz <= 0 || sz > maxSize)
    {
        fclose(f);
        return NULL;
    }

    unsigned char *buf = (unsigned char *)malloc((size_t)sz);
    if (!buf)
    {
        fclose(f);
        return NULL;
    }

    size_t got = fread(buf, 1, (size_t)sz, f);
    fclose(f);

    if (got != (size_t)sz)
    {
        free(buf);
        return NULL;
    }

    if (outSize)
        *outSize = sz;
    return buf;
}

/* --------------------------------------------------------------------- */
/* .ctr pointer relocation                                               */
/* --------------------------------------------------------------------- */
static void ApplyContainerPtrMap(unsigned char *buf, long fileSize)
{
    if (fileSize < 8)
        return;

    unsigned int dataSize = *(unsigned int *)buf;
    if ((long)(4 + dataSize + 4) > fileSize)
        return;

    unsigned char *modelData = buf + 4;
    unsigned int *patchesHeader = (unsigned int *)(modelData + dataSize);
    unsigned int numBytes = *patchesHeader;
    unsigned int numPatches = numBytes >> 2;

    if ((long)(4 + dataSize + 4 + numBytes) > fileSize)
        return;

    unsigned int *patches = (unsigned int *)(modelData + dataSize + 4);
    unsigned int baseAddr = (unsigned int)modelData;

    for (unsigned int i = 0; i < numPatches; i++)
    {
        unsigned int off = patches[i] & 0xFFFFFFFC;
        if (off + 4 > dataSize)
            continue;
        unsigned int *ptr = (unsigned int *)(modelData + off);
        *ptr = *ptr + baseAddr;
    }
}

/* Model header expansion: duplicates the single header four times with
 * maxDistanceLOD=0xFFFF so any 16-bit projected distance resolves to
 * header[0] (the HI mesh). */
static void ExpandModelHeaders(unsigned char *buf, long fileSize)
{
    if (fileSize < 4 + 0x18)
        return;

    unsigned char *md = buf + 4;

    s16 numHeaders = *(s16 *)(md + 0x12);
    u32 headersPtr = *(u32 *)(md + 0x14);

    if (headersPtr == 0)
        return;
    if (numHeaders >= NATIVE_MODELHEADER_COUNT)
        return;

    u8 *newHeaders = (u8 *)malloc(NATIVE_MODELHEADER_SIZE * NATIVE_MODELHEADER_COUNT);
    if (!newHeaders)
        return;

    for (int i = 0; i < NATIVE_MODELHEADER_COUNT; i++)
    {
        memcpy(newHeaders + i * NATIVE_MODELHEADER_SIZE,
               (u8 *)headersPtr,
               NATIVE_MODELHEADER_SIZE);

        *(u16 *)(newHeaders + i * NATIVE_MODELHEADER_SIZE + 0x14) = 0xFFFF;
    }

    *(s16 *)(md + 0x12) = NATIVE_MODELHEADER_COUNT;
    *(u32 *)(md + 0x14) = (u32)newHeaders;

    Log("[CustomRacer] expanded model headers: %d -> %d (maxDistanceLOD=0xFFFF)\n",
        numHeaders, NATIVE_MODELHEADER_COUNT);
}

void *NativeCustomRacer_LoadModel(int playerIndex, int characterID)
{
    const char *folder = NativeCustomRacer_GetFolder(characterID);
    if (!folder)
        return NULL;

    char path[256];
    snprintf(path, sizeof(path),
             "assets/mods/racers/%s/model_p%d.ctr", folder, playerIndex);

    long sz = 0;
    unsigned char *buf = LoadFileToMemory(path, NATIVE_CTR_MAX_BYTES, &sz);
    if (!buf)
    {
        Log("[CustomRacer] model_p%d.ctr not found: %s\n", playerIndex, path);
        return NULL;
    }

    ApplyContainerPtrMap(buf, sz);
    ExpandModelHeaders(buf, sz);

    Log("[CustomRacer] model_p%d.ctr loaded: %s (player %d, %ld bytes)\n",
        playerIndex, path, playerIndex, sz);
    return buf;
}

/* --------------------------------------------------------------------- */
/* .vrm to VRAM                                                          */
/* --------------------------------------------------------------------- */
static int VRM_ApplyBuffer(const unsigned char *buf, int size, int playerIndex)
{
    if (size < 8)
        return 0;

    unsigned int header = 0;
    memcpy(&header, buf, 4);
    if (header != 0x20)
        return 0;

    int offset = 4;
    int blocks = 0;

    while (offset + 24 <= size)
    {
        unsigned int magic = 0;
        memcpy(&magic, buf + offset + 4, 4);
        if (magic != 0x10)
            break;

        RECT16 rect;
        memcpy(&rect.x, buf + offset + 16, 2);
        memcpy(&rect.y, buf + offset + 18, 2);
        memcpy(&rect.w, buf + offset + 20, 2);
        memcpy(&rect.h, buf + offset + 22, 2);

        if (rect.w == 0 || rect.h == 0)
            break;

        int pixelsSize = rect.w * rect.h * 2;
        int nextOffset = offset + 24 + pixelsSize;
        if (nextOffset > size)
            break;

        rect.x += (short)(playerIndex * NATIVE_SLOT_WIDTH);

        LoadImage(&rect, (void *)(buf + offset + 24));

        offset = nextOffset;
        blocks++;
    }

    return blocks;
}

void NativeCustomRacer_ApplySlot(int playerIndex, int characterID)
{
    const char *folder = NativeCustomRacer_GetFolder(characterID);
    if (!folder)
        return;

    char path[256];
    snprintf(path, sizeof(path),
             "assets/mods/racers/%s/textures.vrm", folder);

    long size = 0;
    unsigned char *buf = LoadFileToMemory(path, NATIVE_VRM_MAX_BYTES, &size);
    if (!buf)
    {
        Log("[CustomRacer] textures.vrm not found: %s\n", path);
        return;
    }

    int blocks = VRM_ApplyBuffer(buf, (int)size, playerIndex);
    free(buf);

    if (blocks > 0)
    {
        Log("[CustomRacer] Slot %d (player %d, %s): %d blocks applied\n",
            characterID, playerIndex, folder, blocks);
    }
}

/* --------------------------------------------------------------------- */
/* VRAM dump                                                             */
/* --------------------------------------------------------------------- */
void NativeCustomRacer_DumpVRAMIfRequested(void)
{
    const char *path = getenv("CTR_DUMP_VRAM");
    if (path == NULL || path[0] == '\0')
        return;

    const int vramBytes = 1024 * 512 * 2;
    u16 *buf = (u16 *)malloc(vramBytes);
    if (buf == NULL)
        return;

    NativeRenderer_ReadVRAM(buf, 0, 0, 1024, 512);

    FILE *f = fopen(path, "wb");
    if (f != NULL)
    {
        fwrite(buf, 1, vramBytes, f);
        fclose(f);
        Log("[CustomRacer] VRAM dumped to %s (%d bytes)\n", path, vramBytes);
    }

    free(buf);
}

/* --------------------------------------------------------------------- */
/* Fase 2.5: 4P side table (BUG-MENU-04)                                 */
/* --------------------------------------------------------------------- */
void NativeCustomRacer_SetPlayerModelPtr(int playerIndex, void *model)
{
    if (playerIndex < 0 || playerIndex >= NATIVE_PLAYER_MODEL_SLOTS)
        return;
    s_playerModelPtr[playerIndex] = model;
}

void *NativeCustomRacer_GetPlayerModelPtr(int playerIndex)
{
    if (playerIndex < 0 || playerIndex >= NATIVE_PLAYER_MODEL_SLOTS)
        return NULL;
    return s_playerModelPtr[playerIndex];
}

/* ===================================================================== */
/* PAGINATION                                                            */
/* ===================================================================== */

static void EnsureMetaBackup(void)
{
    if (s_metaBackupDone)
        return;
    memcpy(s_metaBackup, data.MetaDataCharacters, sizeof(s_metaBackup));
    s_metaBackupDone = 1;
}

/* === BUG-ICON-01 ========================================================
 * Per-slot icon VRAM management. See the header for the rationale.
 *
 * Slot rectangles mirror build_icons.py's SLOTS table. Index = slot
 * (0..12; 13-15 unused by the original engine). */
static const struct {
    u16 px_x, px_y, clut_x, clut_y;
} s_iconSlotRects[16] = {
    {368, 216,  16, 251},  /* 0: crash     */
    {256, 216,  16, 252},  /* 1: cortex    */
    {267, 216,  16, 253},  /* 2: tiny      */
    {278, 216,  16, 254},  /* 3: coco      */
    {289, 216,  16, 255},  /* 4: ngin      */
    {300, 216,  32, 248},  /* 5: dingo     */
    {920, 144,  32, 249},  /* 6: polar     */
    {931, 144,  32, 250},  /* 7: pura      */
    {929, 192,  32, 255},  /* 8: ntropy    */
    {918, 192,  32, 254},  /* 9: pinstripe */
    {942, 144,  32, 251},  /* 10: roo      */
    {896, 192,  32, 252},  /* 11: papu     */
    {907, 192,  32, 253},  /* 12: joe      */
    {0, 0, 0, 0},
    {0, 0, 0, 0},
    {0, 0, 0, 0},
};

/* Per-VRAM-slot page tracker. -1 = unknown, 0 = original atlas,
 * N>0 = custom page N. */
static s16 s_iconSlotLoadedPage[16] = {
    -1, -1, -1, -1, -1, -1, -1, -1,
    -1, -1, -1, -1, -1, -1, -1, -1
};

static void IconSlot_InvalidateAll(void)
{
    for (int i = 0; i < 16; i++)
        s_iconSlotLoadedPage[i] = -1;
}

/* ---- page_0 cache: raw pixel data of the original atlas block ----
 * page_0.vrm is a single big block (0, 216, 512, 48). We keep it in BSS
 * and slice sub-rects out of it on demand. */
static unsigned char *s_page0Pixels = NULL;
static unsigned char *s_page0Data   = NULL;
static u16            s_page0BlockX = 0, s_page0BlockY = 0;
static u16            s_page0BlockW = 0, s_page0BlockH = 0;

static void EnsurePage0Cached(void)
{
    if (s_page0Data != NULL)
        return;

    long size = 0;
    unsigned char *buf = LoadFileToMemory("assets/mods/racers/page_0.vrm",
                                          NATIVE_VRM_MAX_BYTES, &size);
    if (buf == NULL)
        return;

    /* Parse the first (and only) block header. */
    unsigned int magic = 0;
    memcpy(&magic, buf + 4 + 4, 4);
    if (magic != 0x10)
    {
        free(buf);
        return;
    }

    u16 bx, by, bw, bh;
    memcpy(&bx, buf + 4 + 16, 2);
    memcpy(&by, buf + 4 + 18, 2);
    memcpy(&bw, buf + 4 + 20, 2);
    memcpy(&bh, buf + 4 + 22, 2);

    int pixelsSize = bw * bh * 2;
    if ((4 + 24 + pixelsSize) > size || bw == 0 || bh == 0)
    {
        free(buf);
        return;
    }

    s_page0Data   = buf;
    s_page0Pixels = buf + 4 + 24;
    s_page0BlockX = bx;
    s_page0BlockY = by;
    s_page0BlockW = bw;
    s_page0BlockH = bh;
}

/* Upload the sub-rect of the page_0 block corresponding to a VRAM rect. */
static void UploadSubRectFromPage0(u16 rx, u16 ry, u16 rw, u16 rh)
{
    if (s_page0Data == NULL)
        return;
    if (rx < s_page0BlockX || ry < s_page0BlockY)
        return;
    if ((rx + rw) > (s_page0BlockX + s_page0BlockW))
        return;
    if ((ry + rh) > (s_page0BlockY + s_page0BlockH))
        return;

    /* Row-by-row copy into a small stack buffer, then LoadImage.
     * Max size: 11x26 halfwords (pixel) or 16x1 halfwords (clut). */
    unsigned char sub[1024];
    int rowBytes  = rw * 2;
    int srcStride = s_page0BlockW * 2;
    int srcBase   = ((ry - s_page0BlockY) * s_page0BlockW
                   + (rx - s_page0BlockX)) * 2;

    if (rowBytes * rh > (int)sizeof(sub))
        return;

    for (u16 row = 0; row < rh; row++)
    {
        memcpy(sub + row * rowBytes,
               s_page0Pixels + srcBase + row * srcStride,
               rowBytes);
    }

    RECT16 rect;
    rect.x = rx;
    rect.y = ry;
    rect.w = rw;
    rect.h = rh;
    LoadImage(&rect, sub);
}

static void UploadOriginalIconSlot(int slot)
{
    if (slot < 0 || slot >= 13)
        return;
    if (s_iconSlotRects[slot].px_x == 0)
        return;

    EnsurePage0Cached();
    if (s_page0Data == NULL)
        return;

    UploadSubRectFromPage0(s_iconSlotRects[slot].px_x,
                           s_iconSlotRects[slot].px_y,
                           11, 26);

    UploadSubRectFromPage0(s_iconSlotRects[slot].clut_x,
                           s_iconSlotRects[slot].clut_y,
                           16, 1);
}

/* Same as VRM_ApplyBuffer, but only uploads blocks whose rect matches
 * the given pixel rect or CLUT rect. Returns blocks applied. */
static int VRM_ApplyBuffer_Filtered(const unsigned char *buf, int size,
                                    u16 target_px_x, u16 target_px_y,
                                    u16 target_clut_x, u16 target_clut_y)
{
    if (size < 8)
        return 0;

    unsigned int header = 0;
    memcpy(&header, buf, 4);
    if (header != 0x20)
        return 0;

    int offset = 4;
    int applied = 0;

    while (offset + 24 <= size)
    {
        unsigned int magic = 0;
        memcpy(&magic, buf + offset + 4, 4);
        if (magic != 0x10)
            break;

        RECT16 rect;
        memcpy(&rect.x, buf + offset + 16, 2);
        memcpy(&rect.y, buf + offset + 18, 2);
        memcpy(&rect.w, buf + offset + 20, 2);
        memcpy(&rect.h, buf + offset + 22, 2);

        if (rect.w == 0 || rect.h == 0)
            break;

        int pixelsSize = rect.w * rect.h * 2;
        int nextOffset = offset + 24 + pixelsSize;
        if (nextOffset > size)
            break;

        if ((rect.x == target_px_x   && rect.y == target_px_y) ||
            (rect.x == target_clut_x && rect.y == target_clut_y))
        {
            LoadImage(&rect, (void *)(buf + offset + 24));
            applied++;
        }

        offset = nextOffset;
    }

    return applied;
}

void NativeCustomRacer_EnsureIconForChar(int characterID)
{
    int page, slot;

    if (characterID < 0)
        return;

    if (characterID < NATIVE_CUSTOM_ID_BASE)
    {
        slot = characterID;
        if (slot >= 16)
            return;
        if (s_iconSlotLoadedPage[slot] == 0)
            return;

        UploadOriginalIconSlot(slot);
        s_iconSlotLoadedPage[slot] = 0;
        return;
    }

    if (characterID >= NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT)
        return;

    page = 1 + (characterID - NATIVE_CUSTOM_ID_BASE) / NATIVE_PAGE_SIZE;
    slot = (characterID - NATIVE_CUSTOM_ID_BASE) % NATIVE_PAGE_SIZE;

    if (slot >= 16)
        return;
    if (s_iconSlotRects[slot].px_x == 0)
        return;
    if (s_iconSlotLoadedPage[slot] == page)
        return;

    char path[256];
    snprintf(path, sizeof(path), "assets/mods/racers/page_%d.vrm", page);

    long size = 0;
    unsigned char *buf = LoadFileToMemory(path, NATIVE_VRM_MAX_BYTES, &size);
    if (buf == NULL)
        return;

    VRM_ApplyBuffer_Filtered(buf, (int)size,
        s_iconSlotRects[slot].px_x, s_iconSlotRects[slot].px_y,
        s_iconSlotRects[slot].clut_x, s_iconSlotRects[slot].clut_y);

    free(buf);
    s_iconSlotLoadedPage[slot] = page;
}
/* === end BUG-ICON-01 ================================================== */

/* Uploads page_N.vrm to the icon atlas VRAM (see SLOTS in build_icons.py).
 * Reuses VRM_ApplyBuffer with playerIndex=0 so it does not shift rect.x. */
static void ApplyPageIcons(int page)
{
    char path[256];
    snprintf(path, sizeof(path), "assets/mods/racers/page_%d.vrm", page);

    long size = 0;
    unsigned char *buf = LoadFileToMemory(path, NATIVE_VRM_MAX_BYTES, &size);
    if (!buf)
    {
        Log("[CustomRacer] page_%d.vrm not found: %s\n", page, path);
        return;
    }

    int blocks = VRM_ApplyBuffer(buf, (int)size, 0);
    free(buf);
    Log("[CustomRacer] page %d icons: %d blocks\n", page, blocks);

    /* BUG-ICON-01: bulk upload bypasses the per-slot tracker. Page 0 is
     * the full original atlas, so all slots end up correct. Page N>0
     * touches an arbitrary subset, so mark all as unknown. */
    for (int i = 0; i < 16; i++)
        s_iconSlotLoadedPage[i] = (page == 0) ? 0 : -1;
}

/* Rewrites MetaDataCharacters[0..15] for the given page.
 * Does NOT touch name_Debug (used by MM_Characters_GetModelByName). */
static void ApplyPageMeta(int page)
{
    EnsureMetaBackup();

    /* Restore originals first */
    memcpy(data.MetaDataCharacters, s_metaBackup, sizeof(s_metaBackup));

    if (page == 0)
        return;

    /* Override slots that have an entry on this page (0..14) */
    for (int i = 0; i < s_pageEntryCount; i++)
    {
        PageEntry *e = &s_pageEntries[i];
        if (e->page != page)
            continue;
        if (e->slot < 0 || e->slot >= 15)
            continue;

        struct MetaDataCHAR *md = &data.MetaDataCharacters[e->slot];
        md->iconID = NATIVE_ICON_BASE + e->slot;  /* 32..46 */
        /* name_LNG_* and engineID are TODO */
    }
}

/* --------------------------------------------------------------------- */
/* Phase 2: menu meta pagination                                         */
/* --------------------------------------------------------------------- */
struct CharacterSelectMeta *NativeCustomRacer_GetPageMeta(
    struct CharacterSelectMeta *base, int count)
{
    NativeCustomRacer_Init();

    if (base == NULL || count <= 0)
        return base;
    if (count > NATIVE_PAGE_SIZE)
        count = NATIVE_PAGE_SIZE;

    if (s_page == 0)
        return base;

    for (int i = 0; i < count; i++)
        s_pageMeta[i] = base[i];

    for (int i = 0; i < s_pageEntryCount; i++)
    {
        PageEntry *e = &s_pageEntries[i];
        if (e->page != s_page)
            continue;
        if (e->slot < 0 || e->slot >= count)
            continue;

        int customID = NATIVE_CUSTOM_ID_BASE
                     + (e->page - 1) * NATIVE_PAGE_SIZE
                     + e->slot;
        s_pageMeta[e->slot].characterID = (s16)customID;
    }

    return s_pageMeta;
}

int NativeCustomRacer_GetPageCount(void)   { return s_pageCount; }
int NativeCustomRacer_GetCurrentPage(void) { return s_page; }

void NativeCustomRacer_RefreshPage(void)
{
    if (s_appliedPage == s_page)
        return;
    EnsureMetaBackup();
    ApplyPageMeta(s_page);
    ApplyPageIcons(s_page);
    s_appliedPage = s_page;
}

void NativeCustomRacer_SetCurrentPage(int page)
{
    if (page < 0 || page >= s_pageCount)
        return;
    if (page == s_page)
        return;

    s_page = page;
    s_appliedPage = -1;   /* force re-apply */
    NativeCustomRacer_RefreshPage();
    Log("[CustomRacer] page -> %d\n", page);
}

void NativeCustomRacer_NextPage(void)
{
    if (s_page + 1 < s_pageCount)
        NativeCustomRacer_SetCurrentPage(s_page + 1);
}

void NativeCustomRacer_PrevPage(void)
{
    if (s_page > 0)
        NativeCustomRacer_SetCurrentPage(s_page - 1);
}

/* === BUG-ICON-01 / Issue 4: force a full re-apply of the current page ===
 * Called when entering the character-select menu (or any screen that
 * depends on our icons being correct in VRAM). Intermediate screens
 * (track select, etc.) load their own VRAM content and clobber whatever
 * we had. RefreshPage() is a no-op if s_appliedPage == s_page, so we
 * invalidate the tracker first to guarantee a re-upload. */
/* === Sentinel CLUT (BUG-ICON-02) ======================================== */
static TextureID   s_customIconTex      [NATIVE_CUSTOM_COUNT];
static u8          s_customIconAttempted[NATIVE_CUSTOM_COUNT];
static struct Icon s_customIcon         [NATIVE_CUSTOM_COUNT];

static void RegisterCustomIconTexture(int idx, int charID)
{
    if (idx < 0 || idx >= NATIVE_CUSTOM_COUNT || s_customIconAttempted[idx]) return;
    s_customIconAttempted[idx] = 1;

    int page = 1 + idx / NATIVE_PAGE_SIZE;
    int slot = idx % NATIVE_PAGE_SIZE;
    if (slot >= 13 || s_iconSlotRects[slot].px_x == 0) return;

    char path[256];
    snprintf(path, sizeof(path), "assets/mods/racers/page_%d.vrm", page);
    long size = 0;
    unsigned char *buf = LoadFileToMemory(path, NATIVE_VRM_MAX_BYTES, &size);
    if (buf == NULL) return;

    const u16 px_x = s_iconSlotRects[slot].px_x, px_y = s_iconSlotRects[slot].px_y;
    const u16 cx   = s_iconSlotRects[slot].clut_x, cy = s_iconSlotRects[slot].clut_y;
    const u8 *px = NULL, *cl = NULL;

    for (int off = 4; off + 24 <= size; )
    {
        u32 magic = 0; memcpy(&magic, buf + off + 4, 4);
        if (magic != 0x10) break;
        RECT16 r;
        memcpy(&r.x, buf + off + 16, 2); memcpy(&r.y, buf + off + 18, 2);
        memcpy(&r.w, buf + off + 20, 2); memcpy(&r.h, buf + off + 22, 2);
        if (r.w == 0 || r.h == 0) break;
        int next = off + 24 + r.w * r.h * 2;
        if (next > size) break;
        if (r.x == px_x && r.y == px_y) px = buf + off + 24;
        if (r.x == cx   && r.y == cy)   cl = buf + off + 24;
        off = next;
    }
    if (!px || !cl) { free(buf); return; }

    enum { ICON_W = 44, ICON_H = 26, ROW_BYTES = 22 };
    u16 clut[16]; memcpy(clut, cl, sizeof(clut));
    u8 rgba[ICON_W * ICON_H * 4];

    for (int y = 0; y < ICON_H; y++)
    for (int x = 0; x < ICON_W; x++)
    {
        u8 byte = px[y * ROW_BYTES + x / 2];
        u8 nib  = (x & 1) ? (u8)(byte >> 4) : (u8)(byte & 0x0F);
        u16 c   = clut[nib & 0x0F];
        u8 *d   = &rgba[(y * ICON_W + x) * 4];
        if (nib == 0 || (c & 0x7FFF) == 0) { d[0]=d[1]=d[2]=d[3]=0; }
        else {
            d[0]=(u8)(((c>>0 )&0x1F)<<3);
            d[1]=(u8)(((c>>5 )&0x1F)<<3);
            d[2]=(u8)(((c>>10)&0x1F)<<3);
            d[3]=255;
        }
    }
    free(buf);

    GLint pa=0, pb=0;
    glGetIntegerv(GL_ACTIVE_TEXTURE, &pa); glActiveTexture(GL_TEXTURE0);
    glGetIntegerv(GL_TEXTURE_BINDING_2D, &pb);
    GLuint tex=0; glGenTextures(1, &tex); glBindTexture(GL_TEXTURE_2D, tex);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, ICON_W, ICON_H, 0, GL_RGBA, GL_UNSIGNED_BYTE, rgba);
    glBindTexture(GL_TEXTURE_2D, (GLuint)pb); glActiveTexture((GLenum)pa);

    NativeGpu_RegisterCustomTexture((u16)idx, (TextureID)tex, ICON_W, ICON_H);
    s_customIconTex[idx] = (TextureID)tex;

    struct Icon *icon = &s_customIcon[idx];
    memset(icon, 0, sizeof(*icon));
    icon->texLayout.u0=0;      icon->texLayout.v0=0;
    icon->texLayout.u1=ICON_W; icon->texLayout.v1=0;
    icon->texLayout.u2=0;      icon->texLayout.v2=ICON_H;
    icon->texLayout.u3=ICON_W; icon->texLayout.v3=ICON_H;
    icon->texLayout.clut=(u16)(0x8000|idx);
    icon->texLayout.tpage=0;

    Log("[CustomRacer] Sentinel icon: id=%d page=%d slot=%d tex=%u\n",
        charID, page, slot, (unsigned)tex);
}

struct Icon *NativeCustomRacer_GetIconPtr(int characterID)
{
    if (characterID >= NATIVE_CUSTOM_ID_BASE &&
        characterID <  NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT)
    {
        int idx = characterID - NATIVE_CUSTOM_ID_BASE;
        if (!s_customIconAttempted[idx]) RegisterCustomIconTexture(idx, characterID);
        if (s_customIconTex[idx] != 0) return &s_customIcon[idx];
    }
    NativeCustomRacer_EnsureIconForChar(characterID);
    return sdata->gGT->ptrIcons[GET_METADATA(characterID)->iconID];
}

void NativeCustomRacer_ForceReapply(void)
{
    s_appliedPage = -1;
    NativeCustomRacer_RefreshPage();
}

/* === Menu preview === */
#ifndef LOAD_MODEL_FILE_HEADER_BYTES
#define LOAD_MODEL_FILE_HEADER_BYTES 4
#endif

struct Model *NativeCustomRacer_GetMenuModel(int characterID, int playerIndex)
{
    NativeCustomRacer_Init();

    if (characterID <  NATIVE_CUSTOM_ID_BASE ||
        characterID >= NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT)
        return NULL;

    if (playerIndex < 0 || playerIndex >= NATIVE_MENU_PLAYER_SLOTS)
        playerIndex = 0;

    int idx = characterID - NATIVE_CUSTOM_ID_BASE;
    int p   = playerIndex;

    /* Lazy-load the .ctr once per (characterID, playerIndex).
     * model_pN.ctr has its UVs baked for VRAM slot N (see build_character.py
     * --player_slot), so each menu window must use its own copy. */
    if (s_menuModel[idx][p] == NULL)
    {
        void *buf = NativeCustomRacer_LoadModel(p, characterID);
        if (buf == NULL)
            return NULL;

        s_menuModel[idx][p] =
            (struct Model *)((unsigned char *)buf + LOAD_MODEL_FILE_HEADER_BYTES);
        Log("[CustomRacer] menu model cached: id=%d slot=%d folder='%s'\n",
            characterID, p, NativeCustomRacer_GetFolder(characterID));
    }

    /* Lazy-load textures.vrm once per (characterID, playerIndex). The .vrm
     * itself is identical across slots; only the upload target differs. */
    if (s_menuVrm[idx][p] == NULL)
    {
        const char *folder = NativeCustomRacer_GetFolder(characterID);
        if (folder != NULL)
        {
            char path[256];
            snprintf(path, sizeof(path),
                     "assets/mods/racers/%s/textures.vrm", folder);
            s_menuVrm[idx][p] = LoadFileToMemory(path, NATIVE_VRM_MAX_BYTES,
                                                 &s_menuVrmSize[idx][p]);
        }
    }

    /* Upload to the player's own VRAM slot. Cheap: buffer is cached in RAM,
     * only the ~30 LoadImage calls run. Idempotent — the rects of distinct
     * slots are disjoint, so re-uploading the same custom is a no-op. */
    if (s_menuVrm[idx][p] != NULL)
        VRM_ApplyBuffer(s_menuVrm[idx][p], (int)s_menuVrmSize[idx][p], p);

    return s_menuModel[idx][p];
}