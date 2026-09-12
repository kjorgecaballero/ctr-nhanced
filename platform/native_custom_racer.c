#include <common.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

#include <platform/native_custom_racer.h>
#include <platform/native_renderer.h>

#define NATIVE_ROSTER_MAX 64
#define NATIVE_VRM_MAX_BYTES (256 * 1024)
#define NATIVE_CTR_MAX_BYTES (256 * 1024)

/* Width in VRAM words assigned to each player slot. */
#define NATIVE_SLOT_WIDTH 128

/* Texture pages per slot (128 words / 64 words per page = 2 pages). */
#define NATIVE_SLOT_PAGES 2

/* CLUT index units per slot (128 words / 16 words per CLUT = 8 units). */
#define NATIVE_SLOT_CLUTS 8

/* -------------------------------------------------------------------------
 * Diagnostic logger. Writes to stderr with immediate flush so messages
 * are not lost when a crash occurs.
 * ------------------------------------------------------------------------- */

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

static RosterEntry s_roster[NATIVE_ROSTER_MAX];
static int s_rosterCount = 0;
static int s_rosterLoaded = 0;

/* -------------------------------------------------------------------------
 * Roster parsing
 * Format (one entry per line, "#" starts a comment):
 *     <slot_id> <folder_name>
 * ------------------------------------------------------------------------- */

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

void NativeCustomRacer_ReloadRoster(void)
{
    s_rosterCount = 0;
    s_rosterLoaded = 1;

    FILE *f = fopen("assets/mods/racers/roster.txt", "rb");
    if (!f)
        return;

    char line[256];
    while (fgets(line, sizeof(line), f) && s_rosterCount < NATIVE_ROSTER_MAX)
    {
        RosterEntry entry;
        if (Roster_ParseLine(line, &entry))
            s_roster[s_rosterCount++] = entry;
    }
    fclose(f);

    Log("[CustomRacer] Roster loaded: %d entries\n", s_rosterCount);
}

void NativeCustomRacer_Init(void)
{
    if (!s_rosterLoaded)
        NativeCustomRacer_ReloadRoster();
}

int NativeCustomRacer_HasSlot(int characterID)
{
    NativeCustomRacer_Init();
    for (int i = 0; i < s_rosterCount; i++)
        if (s_roster[i].slotID == characterID)
            return 1;
    return 0;
}

const char *NativeCustomRacer_GetFolder(int characterID)
{
    NativeCustomRacer_Init();
    for (int i = 0; i < s_rosterCount; i++)
        if (s_roster[i].slotID == characterID)
            return s_roster[i].folder;
    return NULL;
}

/* -------------------------------------------------------------------------
 * File helpers
 * ------------------------------------------------------------------------- */

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

/* -------------------------------------------------------------------------
 * CTR container pointer relocation
 * ------------------------------------------------------------------------- */

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

/* -------------------------------------------------------------------------
 * Player slot offset for layouts
 *
 * The .ctr layouts store per-face texture coordinates and VRAM references:
 *     [0]    u0 (u8)
 *     [1]    v0 (u8)
 *     [2:4]  clut (u16 LE)
 *     [4]    u1 (u8)
 *     [5]    v1 (u8)
 *     [6:8]  page (u16 LE)
 *     [8]    u2 (u8)
 *     [9]    v2 (u8)
 *     [10]   u2 (u8)
 *     [11]   v2 (u8)
 *
 * To relocate a character to player slot N, shift the texture page and
 * CLUT reference. This lets the same .ctr file be used by any player.
 *
 *   page += N * NATIVE_SLOT_PAGES  (2 per slot)
 *   clut += N * NATIVE_SLOT_CLUTS  (8 per slot)
 *
 * Disabled for now (returns immediately). Enable once the segmentation
 * fault is confirmed to be elsewhere.
 * ------------------------------------------------------------------------- */

static void ApplyPlayerOffsetToLayouts(unsigned char *buf, long fileSize, int playerIndex)
{
    (void)buf;
    (void)fileSize;
    (void)playerIndex;
    /* Disabled for diagnostic run. */
    return;

#if 0
    if (playerIndex == 0)
        return;

    if (fileSize < 60)
        return;

    unsigned int dataSize = *(unsigned int *)buf;
    if ((long)(4 + dataSize) > fileSize)
        return;

    unsigned char *modelData = buf + 4;

    /* Header pointer at offset 20. */
    unsigned int headerPtr = *(unsigned int *)(modelData + 20);
    if (headerPtr == 0)
        return;

    unsigned int *header = (unsigned int *)headerPtr;
    unsigned int commandsPtr = header[8];   /* offset 32 = index 8 */
    unsigned int texArrayPtr = header[10];  /* offset 40 = index 10 */

    if (commandsPtr == 0 || texArrayPtr == 0)
        return;

    unsigned int *commands = (unsigned int *)commandsPtr;
    unsigned int *cmd = &commands[1];

    unsigned int maxLayout = 0;
    for (unsigned int i = 0; i < 4096; i++)
    {
        if (cmd[i] == 0xFFFFFFFF)
            break;
        unsigned int layout = cmd[i] & 0x1FF;
        if (layout > maxLayout)
            maxLayout = layout;
        if (maxLayout > 511)
        {
            maxLayout = 0;
            break;
        }
    }
    if (maxLayout == 0)
        return;

    unsigned int *texArray = (unsigned int *)texArrayPtr;

    unsigned int pageOffset = (unsigned int)playerIndex * NATIVE_SLOT_PAGES;
    unsigned int clutOffset = (unsigned int)playerIndex * NATIVE_SLOT_CLUTS;

    Log("[CustomRacer] layout relocate: player %d, maxLayout %u\n",
        playerIndex, maxLayout);

    for (unsigned int i = 1; i <= maxLayout; i++)
    {
        unsigned int layoutPtr = texArray[i - 1];
        if (layoutPtr == 0)
            continue;

        unsigned char *layout = (unsigned char *)layoutPtr;

        unsigned int page = layout[6] | (layout[7] << 8);
        page = (page + pageOffset) & 0x1F;
        layout[6] = page & 0xFF;
        layout[7] = (page >> 8) & 0xFF;

        unsigned int clut = layout[2] | (layout[3] << 8);
        clut = (clut + clutOffset) & 0xFFFF;
        layout[2] = clut & 0xFF;
        layout[3] = (clut >> 8) & 0xFF;
    }
#endif
}

/* -------------------------------------------------------------------------
 * Model loader
 * ------------------------------------------------------------------------- */

void *NativeCustomRacer_LoadModel(int playerIndex, int characterID)
{
    const char *folder = NativeCustomRacer_GetFolder(characterID);
    if (!folder)
        return NULL;

    char path[256];
    snprintf(path, sizeof(path),
             "assets/mods/racers/%s/model.ctr", folder);

    long sz = 0;
    unsigned char *buf = LoadFileToMemory(path, NATIVE_CTR_MAX_BYTES, &sz);
    if (!buf)
    {
        Log("[CustomRacer] model.ctr not found: %s\n", path);
        return NULL;
    }

    ApplyContainerPtrMap(buf, sz);
    ApplyPlayerOffsetToLayouts(buf, sz, playerIndex);

    Log("[CustomRacer] model.ctr loaded: %s (player %d, %ld bytes)\n",
        path, playerIndex, sz);
    return buf;
}

/* -------------------------------------------------------------------------
 * VRM (texture upload) loader
 * ------------------------------------------------------------------------- */

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

/* -------------------------------------------------------------------------
 * VRAM dump (debug)
 * ------------------------------------------------------------------------- */

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