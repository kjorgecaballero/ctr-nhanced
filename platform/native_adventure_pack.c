#include <common.h>
#include <platform/native_adventure_pack.h>
#include <platform/native_custom_racer.h>
#include <LevelRegistry.h>

static int s_packCharIDs[NATIVE_ADVENTURE_PACK_SLOTS];
static int s_packActive = 0;
static s16 s_cam_pos[3] = {0, 100, 500};
static s16 s_cam_rot[2] = {0, 0};
static s16 s_slot_pos[8][4] = {
    {-700, 0, -200, 0}, {-500, 0, -100, 0}, {-300, 0, -50, 0}, {-100, 0, 0, 0},
    { 100, 0, 0, 0}, { 300, 0, -50, 0}, { 500, 0, -100, 0}, { 700, 0, -200, 0},
};

static void ResolvePack(void)
{
    s_packActive = 0;
    for (int i = 0; i < NATIVE_ADVENTURE_PACK_SLOTS; i++)
        s_packCharIDs[i] = -1;

    const struct LevelDef *pack = LevelRegistry_GetReplacement(ADVENTURE_GARAGE);
    if (pack == NULL || !pack->isAdventureGarage)
        return;
    if (pack->adventureCharCount != NATIVE_ADVENTURE_PACK_SLOTS)
        return;

    s_packActive = 1;
    NativeAdventurePack_LoadCameras();
    for (int i = 0; i < NATIVE_ADVENTURE_PACK_SLOTS; i++)
        s_packCharIDs[i] = NativeCustomRacer_GetCharacterIDFromFolder(
                               pack->adventureCharSlugs[i]);

    fprintf(stderr, "[AdventurePack] active: id='%s' name='%s'\n",
            pack->id, pack->name);
    for (int i = 0; i < NATIVE_ADVENTURE_PACK_SLOTS; i++)
        fprintf(stderr, "[AdventurePack] slot %d: slug='%s' -> charID=%d\n",
                i, pack->adventureCharSlugs[i], s_packCharIDs[i]);
}

void NativeAdventurePack_OnGarageReset(void) { ResolvePack(); }

int NativeAdventurePack_GetCharacterID(int slot)
{
    if (!s_packActive || slot < 0 || slot >= NATIVE_ADVENTURE_PACK_SLOTS)
        return -1;
    return s_packCharIDs[slot];
}

int NativeAdventurePack_IsActive(void) { return s_packActive; }

void NativeAdventurePack_ActivateForLoad(void)
{
    ResolvePack();
    const struct LevelDef *pack = LevelRegistry_GetReplacement(ADVENTURE_GARAGE);
    LevelRegistry_SetActive((pack != NULL && pack->isAdventureGarage) ? pack : NULL);
}

/* === Fase 2a: model override + spawn === */
static void        *s_packModelRaw[8];
static struct Model *s_packModels[8];

static void (*const s_LOAD_SetPointer)(struct LoadQueueSlot *) = LOAD_QUEUE_CALLBACK_SET_POINTER;

/* Load-queue notes (from LOAD_Queue.c / LOAD_TenStages.c):
 *  - the queue has LOAD_QUEUE_SLOT_COUNT (8) entries; LOAD_AppendQueue
 *    silently returns when it is full (the model is just dropped);
 *  - the queue is drained in the background and the stage dispatcher is
 *    released by the *callbacks* (e.g. the LEV one), not when the queue
 *    is empty. Anything queued after the LEV can therefore still be in
 *    flight when case 7 runs -> raw == NULL.
 * So: queue in two batches (case 4 / case 6) and make case 7 WAIT until
 * every queued model has arrived (NativeAdventurePack_ModelsReady),
 * re-queueing any that were dropped once the queue is empty. */
#define ADV_PACK_FIRST_BATCH 6
#define ADV_PACK_WAIT_TIMEOUT_FRAMES 900

static int s_packQueued[8];
static int s_packWaitFrames = 0;
static int s_packRetries = 0;

static void QueueOne(struct BigHeader *bigfile, int i)
{
    int charID = s_packCharIDs[i];
    if (charID < 0) return;
    if (charID >= NATIVE_CUSTOM_ID_BASE) return;   /* custom: Fase 2b */

    int mpk = GET_MPK_ID(charID);
    int qlenBefore = (int)sdata->queueLength;
    LOAD_AppendQueue(bigfile, LT_GETADDR,
                     BI_ADVENTUREPACK + mpk,
                     &s_packModelRaw[i],
                     s_LOAD_SetPointer);
    s_packQueued[i] = 1;
    fprintf(stderr, "[AdventurePack] queued slot %d charID=%d mpk=%d bigfile=%d qlen %d->%d%s\n",
            i, charID, mpk, BI_ADVENTUREPACK + mpk,
            qlenBefore, (int)sdata->queueLength,
            ((int)sdata->queueLength == qlenBefore) ? "  (DROPPED: queue full)" : "");
}

static void QueueSlots(struct BigHeader *bigfile, int from, int to)
{
    for (int i = from; i < to; i++)
        QueueOne(bigfile, i);
}

void NativeAdventurePack_StartLoadingModels(struct BigHeader *bigfile)
{
    if (!s_packActive || bigfile == NULL) return;
    memset(s_packModelRaw, 0, sizeof(s_packModelRaw));
    memset(s_packModels,   0, sizeof(s_packModels));
    memset(s_packQueued,   0, sizeof(s_packQueued));
    s_packWaitFrames = 0;
    s_packRetries = 0;
    QueueSlots(bigfile, 0, ADV_PACK_FIRST_BATCH);
}

void NativeAdventurePack_StartLoadingModelsLate(struct BigHeader *bigfile)
{
    if (!s_packActive || bigfile == NULL) return;
    QueueSlots(bigfile, ADV_PACK_FIRST_BATCH, NATIVE_ADVENTURE_PACK_SLOTS);
}

/* Called every frame from case 7 until it returns 1. */
int NativeAdventurePack_ModelsReady(struct BigHeader *bigfile)
{
    if (!s_packActive) return 1;

    int missing = 0;
    for (int i = 0; i < NATIVE_ADVENTURE_PACK_SLOTS; i++)
        if (s_packQueued[i] && s_packModelRaw[i] == NULL) missing++;

    if (missing == 0)
    {
        if (s_packWaitFrames > 0)
            fprintf(stderr, "[AdventurePack] all models arrived after waiting %d frames (retries=%d)\n",
                    s_packWaitFrames, s_packRetries);
        return 1;
    }

    s_packWaitFrames++;

    /* Queue empty but models still missing -> they were dropped. */
    if (s_packWaitFrames >= 10 && sdata->queueLength == 0 && s_packRetries < 2 && bigfile != NULL)
    {
        s_packRetries++;
        fprintf(stderr, "[AdventurePack] %d model(s) missing with empty queue, re-queueing (try %d)\n",
                missing, s_packRetries);
        for (int i = 0; i < NATIVE_ADVENTURE_PACK_SLOTS; i++)
            if (s_packQueued[i] && s_packModelRaw[i] == NULL)
                QueueOne(bigfile, i);
    }

    if (s_packWaitFrames > ADV_PACK_WAIT_TIMEOUT_FRAMES)
    {
        fprintf(stderr, "[AdventurePack] TIMEOUT waiting for %d model(s), continuing without them\n", missing);
        return 1;
    }
    return 0;
}


/* Fuerza maxDistanceLOD=0xFFFF en TODOS los modelos del .lev (karts y
 * personajes). Sin esto, los selectkart* (nhdr=1) se descartan por LOD
 * al no tener header con maxDistanceLOD alto. */

/* Reemplaza el modelo de cada InstDef de personaje del garaje (IDs 0xCE-0xD5)
 * por el modelo custom del roster, si el slot tiene un custom.
 * Los modelos custom usan Sentinel (texturas OpenGL), no VRAM. PatchLev
 * skipea correctamente los layouts con CLUT Sentinel.
 */
void NativeAdventurePack_ApplyCustomRacers(struct Level *lev)
{
    if (lev == NULL || lev->ptrInstDefs == NULL) return;
    int applied = 0;
    for (int i = 0; i < NATIVE_ADVENTURE_PACK_SLOTS; i++)
    {
        int charID = s_packCharIDs[i];
        if (charID < 0) continue;
        if (charID < NATIVE_CUSTOM_ID_BASE) continue;  // retail, dejar como esta

        void *raw = NativeCustomRacer_LoadModel(0, charID);
        if (raw == NULL) {
            fprintf(stderr, "[AdventurePack] custom slot %d charID=%d FAILED to load\n", i, charID);
            continue;
        }
        struct Model *custom = (struct Model *)((u8 *)raw + LOAD_MODEL_FILE_HEADER_BYTES);
        custom->id = STATIC_CRASHSELECT + i;  // forzar ID para el PVS bypass
        NativeCustomRacer_RegisterGarageModel(i, custom);

        // Reemplazar en gGT->modelPtr[]
        sdata->gGT->modelPtr[STATIC_CRASHSELECT + i] = custom;

        // Reemplazar en el InstDef correspondiente
        for (u32 j = 0; j < lev->numInstances; j++) {
            struct InstDef *def = &lev->ptrInstDefs[j];
            if (def->model != NULL && def->model->id == STATIC_CRASHSELECT + i) {
                def->model = custom;
                break;
            }
        }
        fprintf(stderr, "[AdventurePack] custom racer slot %d charID=%d applied (model=%p)\n",
                i, charID, (void *)custom);
        applied++;
    }
    fprintf(stderr, "[AdventurePack] ApplyCustomRacers: %d custom models applied\n", applied);
}

void NativeAdventurePack_ForceGarageLOD(struct Level *lev)
{
    if (lev == NULL || lev->ptrModelsPtrArray == NULL) return;
    int count = 0;
    for (u32 i = 0; i < lev->numModels; i++) {
        struct Model *m = lev->ptrModelsPtrArray[i];
        if (m == NULL) break;
        for (int h = 0; h < m->numHeaders; h++) {
            m->headers[h].maxDistanceLOD = (s16)0xFFFF;
        }
        count++;
    }
    fprintf(stderr, "[AdventurePack] ForceGarageLOD: %d models maxDistanceLOD=0xFFFF\n", count);
}

void NativeAdventurePack_OverrideModelPtrs(struct GameTracker *gGT)
{
    if (!s_packActive || gGT == NULL) return;
    for (int i = 0; i < NATIVE_ADVENTURE_PACK_SLOTS; i++)
    {
        if (s_packModelRaw[i] == NULL) {
            fprintf(stderr, "[AdventurePack] slot %d raw=NULL\n", i);
            continue;
        }
        u8 *raw = (u8 *)s_packModelRaw[i];
        u32 fileSize = *(u32 *)raw;
        struct Model **list = (struct Model **)(raw + 8);
        struct Model *charModel = list[18];
        if ((uintptr_t)charModel < (uintptr_t)(raw + 8) ||
            (uintptr_t)charModel >= (uintptr_t)(raw + 4 + fileSize)) {
            fprintf(stderr, "[AdventurePack] slot %d list[18]=%p out of range\n", i, (void*)charModel);
            continue;
        }
        charModel->id = STATIC_CRASHSELECT + i;
        gGT->modelPtr[STATIC_CRASHSELECT + i] = charModel;
        s_packModels[i] = charModel;

        extern int NativeLevelTextures_PatchModel(struct Model *);
        NativeLevelTextures_PatchModel(charModel);

        fprintf(stderr, "[AdventurePack] model override slot %d m=%p name='%.16s' id=%d\n",
                i, (void *)charModel, charModel->name, (int)charModel->id);
    }
}

void NativeAdventurePack_SpawnCharacters(struct GameTracker *gGT)
{
    (void)gGT;
    if (!s_packActive) return;

    for (int i = 0; i < NATIVE_ADVENTURE_PACK_SLOTS; i++)
    {
        if (s_packModels[i] == NULL) continue;

        struct CsThreadInitData initData;
        memset(&initData, 0, sizeof(initData));
        initData.podiumPos.x = s_slot_pos[i][0];
        initData.podiumPos.y = s_slot_pos[i][1];
        initData.podiumPos.z = s_slot_pos[i][2];
        initData.rot.y = s_slot_pos[i][3];   /* mira hacia la cámara */

        struct Thread *t = CS_Thread_Init(STATIC_CRASHSELECT + i, "advpack",
                                          &initData, 0, 0);
        if (t != NULL && t->inst != NULL) {
            t->inst->scale.x = 0x1000;
            t->inst->scale.y = 0x1000;
            t->inst->scale.z = 0x1000;
        }
        fprintf(stderr, "[AdventurePack] spawned slot %d at (%d,%d,%d) t=%p\n",
                i, s_slot_pos[i][0], s_slot_pos[i][1], s_slot_pos[i][2], (void *)t);
    }
}

void NativeAdventurePack_LoadCameras(void) {
    if (!s_packActive) return;
    const struct LevelDef *pack = LevelRegistry_GetReplacement(ADVENTURE_GARAGE);
    if (!pack) return;

    char path[256];
    snprintf(path, sizeof(path), "assets/mods/levels/%s/cameras.json", pack->id);
    FILE *f = fopen(path, "r");
    if (!f) return;

    int vals[64]; int n = 0; char buf[512];
    while (fgets(buf, sizeof(buf), f) && n < 64) {
        char *p = buf;
        while (*p) {
            if ((*p >= '0' && *p <= '9') || *p == '-') {
                vals[n++] = atoi(p);
                while (*p && ((*p >= '0' && *p <= '9') || *p == '-')) p++;
            } else p++;
        }
    }
    fclose(f);

    fprintf(stderr, "[DIAG-Adv] LoadCameras leyo %d valores del JSON\n", n);
    if (n >= 5) {
        s_cam_pos[0] = vals[0]; s_cam_pos[1] = vals[1]; s_cam_pos[2] = vals[2];
        s_cam_rot[0] = vals[3]; s_cam_rot[1] = vals[4];
        fprintf(stderr, "[DIAG-Adv] Camara JSON: X=%d Y=%d Z=%d\n", s_cam_pos[0], s_cam_pos[1], s_cam_pos[2]);
    }
    for (int i = 0; i < 8; i++) {
        int off = 5 + i*4;
        if (off + 3 < n) {
            s_slot_pos[i][0] = vals[off];
            s_slot_pos[i][1] = vals[off+1];
            s_slot_pos[i][2] = vals[off+2];
            s_slot_pos[i][3] = vals[off+3];
            if (i == 0) fprintf(stderr, "[DIAG-Adv] Slot 0 JSON: X=%d Y=%d Z=%d\n", s_slot_pos[0][0], s_slot_pos[0][1], s_slot_pos[0][2]);
        }
    }
}

void NativeAdventurePack_GetCamera(s16 *pos, s16 *rot) {
    pos[0] = s_cam_pos[0]; pos[1] = s_cam_pos[1]; pos[2] = s_cam_pos[2];
    rot[0] = s_cam_rot[0]; rot[1] = s_cam_rot[1];
}

void NativeAdventurePack_GetSlotPos(int slot, s16 *pos, s16 *rot) {
    if (slot < 0 || slot >= 8) return;
    pos[0] = s_slot_pos[slot][0]; pos[1] = s_slot_pos[slot][1]; pos[2] = s_slot_pos[slot][2];
    rot[0] = 0; rot[1] = s_slot_pos[slot][3];
}

u16 NativeAdventurePack_GetAnimFrames(struct Model *m) {
    if (!s_packActive || !m) return 0;
    for (int i = 0; i < 8; i++) {
        if (s_packModels[i] == m) {
            if (m->headers && m->headers[0].ptrAnimations && m->headers[0].ptrAnimations[0])
                return (u16)(m->headers[0].ptrAnimations[0]->numFrames & 0x7FFF);
        }
    }
    return 0;
}
