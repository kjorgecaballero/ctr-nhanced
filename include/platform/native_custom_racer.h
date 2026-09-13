#ifndef NATIVE_CUSTOM_RACER_H
#define NATIVE_CUSTOM_RACER_H

#include <common.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Inicializa el subsistema. Lee roster.txt en la primera llamada. */
void NativeCustomRacer_Init(void);

/* Fuerza recarga de roster.txt (útil para hot-reload). */
void NativeCustomRacer_ReloadRoster(void);

/* Devuelve 1 si el characterID tiene racer custom en la página actual. */
int NativeCustomRacer_HasSlot(int characterID);

/* Devuelve el folder del racer para characterID, o NULL. */
const char *NativeCustomRacer_GetFolder(int characterID);

/* Carga model_p{playerIndex}.ctr para el characterID, con punteros
 * reubicados y UVs desplazadas al slot VRAM del jugador.
 * Devuelve buffer malloc'ed (caller owns) o NULL. */
void *NativeCustomRacer_LoadModel(int playerIndex, int characterID);

/* Sube textures.vrm a la región VRAM del jugador. */
void NativeCustomRacer_ApplySlot(int playerIndex, int characterID);

/* Dump VRAM si CTR_DUMP_VRAM está seteado. No-op si no. */
void NativeCustomRacer_DumpVRAMIfRequested(void);

/* === Paginación de racers === */
int  NativeCustomRacer_GetPageCount(void);
int  NativeCustomRacer_GetCurrentPage(void);
void NativeCustomRacer_SetCurrentPage(int page);
void NativeCustomRacer_NextPage(void);
void NativeCustomRacer_PrevPage(void);

/* Reaplica atlas VRAM + metadata de la página actual. Idempotente. */
void NativeCustomRacer_RefreshPage(void);

/* TEMPORAL: dump de ptrIcons[32..47] la primera vez que existan. */
void NativeCustomRacer_DebugDumpIcons(void);

#ifdef __cplusplus
}
#endif

#endif