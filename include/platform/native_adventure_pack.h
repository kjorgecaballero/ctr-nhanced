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
void NativeAdventurePack_LoadCameras(void);
void NativeAdventurePack_GetCamera(s16 *pos, s16 *rot);
void NativeAdventurePack_GetSlotPos(int slot, s16 *pos, s16 *rot);
u16 NativeAdventurePack_GetAnimFrames(struct Model *m);

void NativeAdventurePack_StartLoadingModels(struct BigHeader *bigfile);
void NativeAdventurePack_StartLoadingModelsLate(struct BigHeader *bigfile);
int  NativeAdventurePack_ModelsReady(struct BigHeader *bigfile);
void NativeAdventurePack_OverrideModelPtrs(struct GameTracker *gGT);
void NativeAdventurePack_SpawnCharacters(struct GameTracker *gGT);

#endif
