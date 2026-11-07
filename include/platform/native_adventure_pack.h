#ifndef NATIVE_ADVENTURE_PACK_H
#define NATIVE_ADVENTURE_PACK_H

#include <common.h>

struct BigHeader;
struct GameTracker;

#define NATIVE_ADVENTURE_PACK_SLOTS 8

void NativeAdventurePack_OnGarageReset(void);
int  NativeAdventurePack_GetCharacterID(int slot);
int  NativeAdventurePack_IsActive(void);
void NativeAdventurePack_ActivateForLoad(void);

void NativeAdventurePack_StartLoadingModels(struct BigHeader *bigfile);
void NativeAdventurePack_OverrideModelPtrs(struct GameTracker *gGT);
void NativeAdventurePack_SpawnCharacters(struct GameTracker *gGT);

#endif
