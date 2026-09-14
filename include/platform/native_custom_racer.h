#ifndef NATIVE_CUSTOM_RACER_H
#define NATIVE_CUSTOM_RACER_H

#include <common.h>
#include <namespace_Vehicle.h>

#ifdef __cplusplus
extern "C" {
#endif

/* === Fase 1: IDs custom 16..63 ============================================
 * No extendemos data.MetaDataCharacters[0x10] (rompería ~30 CTR_STATIC_ASSERT
 * de struct sData). En su lugar, tabla paralela en BSS + macro de redirección.
 *   IDs 0..15 -> data.MetaDataCharacters (comportamiento original intacto).
 *   IDs 16+   -> s_customMeta.
 * ========================================================================== */
#define NATIVE_CUSTOM_ID_BASE 16
#define NATIVE_CUSTOM_COUNT   48

extern struct MetaDataCHAR s_customMeta[NATIVE_CUSTOM_COUNT];
extern s16                 s_customMenuID[NATIVE_CUSTOM_COUNT];

#define GET_METADATA(id)                                                      \
    ((((id) >= NATIVE_CUSTOM_ID_BASE) &&                                      \
      ((id) <  (NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT)))                \
        ? &s_customMeta[(id) - NATIVE_CUSTOM_ID_BASE]                         \
        : &data.MetaDataCharacters[(id)])

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

/* === Racer pagination === */
int  NativeCustomRacer_GetPageCount(void);
int  NativeCustomRacer_GetCurrentPage(void);
void NativeCustomRacer_SetCurrentPage(int page);
void NativeCustomRacer_NextPage(void);
void NativeCustomRacer_PrevPage(void);

/* Re-applies the current page's VRAM atlas + metadata. Idempotent. */
void NativeCustomRacer_RefreshPage(void);

#ifdef __cplusplus
}
#endif

#endif