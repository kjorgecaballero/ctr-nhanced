#ifndef NATIVE_CUSTOM_RACER_H
#define NATIVE_CUSTOM_RACER_H

#include <common.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Initializes the custom racer subsystem. Reads roster.txt on first call. */
void NativeCustomRacer_Init(void);

/* Forces a reload of roster.txt. Use if the file changes at runtime. */
void NativeCustomRacer_ReloadRoster(void);

/* Returns 1 if the given character ID has a custom racer entry. */
int NativeCustomRacer_HasSlot(int characterID);

/* Returns the folder name for the given character ID, or NULL. */
const char *NativeCustomRacer_GetFolder(int characterID);

/* Loads model.ctr for the given character into a malloc'ed buffer.
 * Returns NULL on failure. The caller owns the buffer. */
void *NativeCustomRacer_LoadModel(int characterID);

/* Applies the textures.vrm for the given character to VRAM. */
void NativeCustomRacer_ApplySlot(int characterID);

#ifdef __cplusplus
}
#endif

#endif