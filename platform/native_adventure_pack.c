#include <common.h>
#include <platform/native_adventure_pack.h>
#include <platform/native_custom_racer.h>
#include <LevelRegistry.h>

static int s_packCharIDs[NATIVE_ADVENTURE_PACK_SLOTS];
static int s_packActive = 0;

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

void NativeAdventurePack_StartLoadingModels(struct BigHeader *bigfile)
{
    if (!s_packActive || bigfile == NULL) return;
    memset(s_packModelRaw, 0, sizeof(s_packModelRaw));
    memset(s_packModels,   0, sizeof(s_packModels));

    for (int i = 0; i < NATIVE_ADVENTURE_PACK_SLOTS; i++)
    {
        int charID = s_packCharIDs[i];
        if (charID < 0) continue;
        if (charID >= NATIVE_CUSTOM_ID_BASE) continue;   /* custom: Fase 2b */

        int mpk = GET_MPK_ID(charID);
        LOAD_AppendQueue(bigfile, LT_GETADDR,
                         BI_ADVENTUREPACK + mpk,
                         &s_packModelRaw[i],
                         s_LOAD_SetPointer);
        fprintf(stderr, "[AdventurePack] queued slot %d charID=%d mpk=%d bigfile=%d\n",
                i, charID, mpk, BI_ADVENTUREPACK + mpk);
    }
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
        struct Model *m = (struct Model *)((u8 *)s_packModelRaw[i] + LOAD_MODEL_FILE_HEADER_BYTES);
        m->id = STATIC_CRASHSELECT + i;
        gGT->modelPtr[STATIC_CRASHSELECT + i] = m;
        s_packModels[i] = m;
        fprintf(stderr, "[AdventurePack] model override slot %d m=%p\n",
                i, (void *)m);
    }
}

void NativeAdventurePack_SpawnCharacters(struct GameTracker *gGT)
{
    (void)gGT;
    if (!s_packActive) return;

    static const s16 s_positions[8][3] = {
        {-700, 0, -200}, {-500, 0, -100}, {-300, 0, -50}, {-100, 0, 0},
        { 100, 0, 0}, { 300, 0, -50}, { 500, 0, -100}, { 700, 0, -200},
    };

    for (int i = 0; i < NATIVE_ADVENTURE_PACK_SLOTS; i++)
    {
        if (s_packModels[i] == NULL) continue;

        struct CsThreadInitData initData;
        memset(&initData, 0, sizeof(initData));
        initData.podiumPos.x = s_positions[i][0];
        initData.podiumPos.y = s_positions[i][1];
        initData.podiumPos.z = s_positions[i][2];
        initData.rot.y = ANG_PI;   /* mira hacia la cámara */

        struct Thread *t = CS_Thread_Init(STATIC_CRASHSELECT + i, "advpack",
                                          &initData, 0, 0);
        if (t != NULL && t->inst != NULL) {
            t->inst->scale.x = 0x1000;
            t->inst->scale.y = 0x1000;
            t->inst->scale.z = 0x1000;
        }
        fprintf(stderr, "[AdventurePack] spawned slot %d at (%d,%d,%d) t=%p\n",
                i, s_positions[i][0], s_positions[i][1], s_positions[i][2], (void *)t);
    }
}
