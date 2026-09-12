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
 * Model loader
 *
 * Each player index has its own .ctr file with the atlas already placed at
 * the player's VRAM region. No runtime pointer patching is required.
 * ------------------------------------------------------------------------- */

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

    Log("[CustomRacer] model_p%d.ctr loaded: %s (player %d, %ld bytes)\n",
        playerIndex, path, playerIndex, sz);
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

        /* Shift to the player's VRAM region so it matches the .ctr. */
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