#ifndef NATIVE_ADVENTURE_PACK_H
#define NATIVE_ADVENTURE_PACK_H

#include <common.h>

#define NATIVE_ADVENTURE_PACK_SLOTS 8

void NativeAdventurePack_OnGarageReset(void);
int  NativeAdventurePack_GetCharacterID(int slot);
int  NativeAdventurePack_IsActive(void);
void NativeAdventurePack_ActivateForLoad(void);

#endif