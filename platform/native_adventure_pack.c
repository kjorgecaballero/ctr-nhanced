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