#include <common.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

#include <platform/native_custom_racer.h>
#include <platform/native_renderer.h>

#define NATIVE_ROSTER_MAX   64
#define NATIVE_VRM_MAX_BYTES (256 * 1024)
#define NATIVE_CTR_MAX_BYTES (256 * 1024)

/* Ancho en palabras VRAM por jugador. */
#define NATIVE_SLOT_WIDTH 128

#define NATIVE_MODELHEADER_SIZE  0x40
#define NATIVE_MODELHEADER_COUNT 4

/* Paginación */
#define NATIVE_PAGE_SIZE  16
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

/* Entrada del roster nuevo formato: page slot folder */
typedef struct
{
    int page;
    int slot;
    char folder[64];
} PageEntry;

static RosterEntry s_roster[NATIVE_ROSTER_MAX];
static int s_rosterCount = 0;
static int s_rosterLoaded = 0;

static PageEntry s_pageEntries[NATIVE_ROSTER_MAX];
static int s_pageEntryCount = 0;

static int s_page = 0;
static int s_pageCount = 1;
static int s_appliedPage = -1;

/* Backup de MetaDataCharacters[0..15] para restaurar entre páginas. */
static int s_metaBackupDone = 0;
static struct MetaDataCHAR s_metaBackup[16];


/* --------------------------------------------------------------------- */
/* Parser viejo (ext_id folder). Se conserva por compatibilidad.        */
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
/* Parser nuevo: "page slot folder [engine] ["name"]"                    */
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

        /* Compatibilidad: rellenamos s_roster[] con slotID = page*16+slot */
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
/* Búsqueda por página + slot                                            */
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

int NativeCustomRacer_HasSlot(int characterID)
{
    NativeCustomRacer_Init();
    return FindPageEntry(s_page, characterID) != NULL;
}

const char *NativeCustomRacer_GetFolder(int characterID)
{
    NativeCustomRacer_Init();
    const PageEntry *e = FindPageEntry(s_page, characterID);
    if (e)
        return e->folder;
    return NULL;
}

/* --------------------------------------------------------------------- */
/* Carga de archivos                                                     */
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
/* Reubicación de punteros del .ctr                                      */
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

/* Expansión de ModelHeader: duplica el único header 4 veces con
 * maxDistanceLOD=0xFFFF para forzar siempre LOD HI. */
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
/* Aplicación de .vrm a VRAM                                             */
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
/* Dump VRAM                                                             */
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

/* ===================================================================== */
/* PAGINACIÓN                                                            */
/* ===================================================================== */

static void EnsureMetaBackup(void)
{
    if (s_metaBackupDone)
        return;
    memcpy(s_metaBackup, data.MetaDataCharacters, sizeof(s_metaBackup));
    s_metaBackupDone = 1;
}

/* Sube page_N.vrm al atlas VRAM (0,216) 512x48.
 * Reutiliza VRM_ApplyBuffer con playerIndex=0 para no añadir offset. */
static void ApplyPageIcons(int page)
{
    char path[256];
    snprintf(path, sizeof(path), "assets/mods/racers/page_%d.vrm", page);

    long size = 0;
    unsigned char *buf = LoadFileToMemory(path, NATIVE_VRM_MAX_BYTES, &size);
    if (!buf)
    {
        Log("[CustomRacer] page_%d.vrm no encontrado: %s\n", page, path);
        return;
    }

    int blocks = VRM_ApplyBuffer(buf, (int)size, 0);
    free(buf);
    Log("[CustomRacer] page %d icons: %d blocks\n", page, blocks);
}

/* Reescribe MetaDataCharacters[0..15] para la página dada.
 * NO toca name_Debug (lo usa MM_Characters_GetModelByName para el modelo 3D). */
static void ApplyPageMeta(int page)
{
    EnsureMetaBackup();

    /* Restaurar originales primero */
    memcpy(data.MetaDataCharacters, s_metaBackup, sizeof(s_metaBackup));

    if (page == 0)
        return;

    /* Override slots que tengan entrada en esta página (0..14) */
    for (int i = 0; i < s_pageEntryCount; i++)
    {
        PageEntry *e = &s_pageEntries[i];
        if (e->page != page)
            continue;
        if (e->slot < 0 || e->slot >= 15)
            continue;

        struct MetaDataCHAR *md = &data.MetaDataCharacters[e->slot];
        md->iconID = NATIVE_ICON_BASE + e->slot;  /* 32..46 */
        /* name_LNG_* y engineID se dejan por ahora (TODO) */
    }
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
    s_appliedPage = -1;   /* forzar re-aplicación */
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

/* ===================================================================== */
/* DEBUG TEMPORAL: dump de ptrIcons[32..47]                              */
/* ===================================================================== */
void NativeCustomRacer_DebugDumpIcons(void)
{
    static int s_iconDbgDone = 0;
    if (s_iconDbgDone)
        return;
    if (!sdata || !sdata->gGT)
        return;
    if (sdata->gGT->ptrIcons[32] == NULL)
        return;

    s_iconDbgDone = 1;
    Log("--- ptrIcons[32..47] ---\n");
    for (int i = 32; i < 48; i++)
    {
        struct Icon *ic = sdata->gGT->ptrIcons[i];
        if (!ic)
        {
            Log("  [%02d] NULL\n", i);
            continue;
        }
        Log("  [%02d] name=%-12s u0=%3u v0=%3u u1=%3u v1=%3u u2=%3u v2=%3u u3=%3u v3=%3u tpage=0x%04X clut=0x%04X\n",
            i, ic->name,
            ic->texLayout.u0, ic->texLayout.v0,
            ic->texLayout.u1, ic->texLayout.v1,
            ic->texLayout.u2, ic->texLayout.v2,
            ic->texLayout.u3, ic->texLayout.v3,
            ic->texLayout.tpage, ic->texLayout.clut);
    }
    Log("--- fin ptrIcons ---\n");
}