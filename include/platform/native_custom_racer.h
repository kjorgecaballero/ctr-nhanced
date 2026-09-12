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

/* Loads model.ctr for the given character into a malloc'ed buffer with
 * internal pointers relocated and layout VRAM coordinates shifted to the
 * specified player slot. Returns NULL on failure. The caller owns the buffer. */
void *NativeCustomRacer_LoadModel(int playerIndex, int characterID);

/* Applies textures.vrm for the given character to the player's VRAM region. */
void NativeCustomRacer_ApplySlot(int playerIndex, int characterID);

/* Dumps the current VRAM to a file if the environment variable
 * CTR_DUMP_VRAM is set to a non-empty path. No-op otherwise. */
void NativeCustomRacer_DumpVRAMIfRequested(void);

#ifdef __cplusplus
}
#endif

#endif