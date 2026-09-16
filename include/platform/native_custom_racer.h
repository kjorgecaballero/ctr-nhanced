#ifndef NATIVE_CUSTOM_RACER_H
#define NATIVE_CUSTOM_RACER_H

#include <common.h>
#include <namespace_Vehicle.h>

#ifdef __cplusplus
extern "C" {
#endif

/* === Fase 1: custom IDs 16..63 ===========================================
 * We do NOT extend data.MetaDataCharacters[0x10] (that would break ~30
 * CTR_STATIC_ASSERTs on struct sData). Instead: a parallel table in BSS
 * plus a redirection macro.
 *   IDs 0..15 -> data.MetaDataCharacters (original behavior, untouched).
 *   IDs 16+   -> s_customMeta.
 * ========================================================================= */
#define NATIVE_CUSTOM_ID_BASE 16
#define NATIVE_CUSTOM_COUNT   128
#define NATIVE_PAGE_SIZE      16

extern struct MetaDataCHAR s_customMeta[NATIVE_CUSTOM_COUNT];
extern s16                 s_customMenuID[NATIVE_CUSTOM_COUNT];

#define GET_METADATA(id)                                                      \
    ((((id) >= NATIVE_CUSTOM_ID_BASE) &&                                      \
      ((id) <  (NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT)))                \
        ? &s_customMeta[(id) - NATIVE_CUSTOM_ID_BASE]                         \
        : &data.MetaDataCharacters[(id)])

/* Maps a character ID to a valid slot index (0..15) for use as an index
 * into the BI_*PACK / BI_RACERMODELHI bigfile ranges, which only have 16
 * entries. Custom IDs 16..63 wrap back to their original character slot. */
#define GET_MPK_ID(id)                                                        \
    (((id) >= NATIVE_CUSTOM_ID_BASE)                                          \
        ? (((id) - NATIVE_CUSTOM_ID_BASE) % NATIVE_PAGE_SIZE)                 \
        : (id))

/* Initializes the custom racer subsystem. Reads roster.txt on first call. */
void NativeCustomRacer_Init(void);

/* Forces a reload of roster.txt. Use if the file changes at runtime. */
void NativeCustomRacer_ReloadRoster(void);

/* Returns 1 if the given character ID has a custom racer entry. */
int NativeCustomRacer_HasSlot(int characterID);

/* Returns the folder name for the given character ID, or NULL. */
const char *NativeCustomRacer_GetFolder(int characterID);

/* Returns a pointer to the custom's packed vertex-color code array
 * (same format as data.ptrColor[][0..3]), or NULL if the custom has
 * no #RRGGBB field in roster.txt. */
const u32 *NativeCustomRacer_GetColorPtr(int characterID);

/* Returns the "Display Name" for the given custom character ID (>= 16),
 * read from roster.txt during ReloadRoster. Falls back to the folder slug
 * if the quoted field is empty. Returns NULL for original IDs and for
 * unknown customs, so callers can keep their existing LNG fallback. */
const char *NativeCustomRacer_GetDisplayName(int characterID);

/* Loads model.ctr for the given character into a malloc'ed buffer with
 * internal pointers relocated and layout VRAM coordinates shifted to the
 * specified player slot. Returns NULL on failure. The caller owns the buffer. */
void *NativeCustomRacer_LoadModel(int playerIndex, int characterID);

/* Applies textures.vrm for the given character to the player's VRAM region. */
void NativeCustomRacer_ApplySlot(int playerIndex, int characterID);

/* Dumps the current VRAM to a file if the environment variable
 * CTR_DUMP_VRAM is set to a non-empty path. No-op otherwise. */
void NativeCustomRacer_DumpVRAMIfRequested(void);

/* === Fase 2.5: BUG-MENU-04 side table ====================================
 * data.driverModelExtras[] has only LOAD_DRIVER_MODEL_EXTRA_COUNT (=3)
 * slots, so index 3 (P4 in 4P) aliases podiumModel_firstPlace. Writing
 * there corrupts the podium model pointers and crashes the menu on exit.
 * We keep the 4th player's custom model in a BSS side table, keyed by
 * playerIndex, so we never touch the struct Data layout.
 * The stored pointer is already offset by LOAD_MODEL_FILE_HEADER_BYTES,
 * i.e. it points to a valid `struct Model`. */
void  NativeCustomRacer_SetPlayerModelPtr(int playerIndex, void *model);
void *NativeCustomRacer_GetPlayerModelPtr(int playerIndex);

/* === Menu preview ===
 * Returns a struct Model* ready for the character-select 3D window.
 * Loads model_p0.ctr on first call and caches it per characterID.
 * Only meaningful for IDs >= NATIVE_CUSTOM_ID_BASE; returns NULL otherwise. */
struct Model;
struct Model *NativeCustomRacer_GetMenuModel(int characterID, int playerIndex);

/* === Racer pagination === */
int  NativeCustomRacer_GetPageCount(void);
int  NativeCustomRacer_GetCurrentPage(void);
void NativeCustomRacer_SetCurrentPage(int page);
void NativeCustomRacer_NextPage(void);
void NativeCustomRacer_PrevPage(void);

/* Re-applies the current page's VRAM atlas + metadata. Idempotent. */
void NativeCustomRacer_RefreshPage(void);

/* === Fase 2: menu integration ===
 * Returns the CharacterSelectMeta array the character-select menu should
 * use for the current page.
 * If page == 0, returns `base` untouched.
 * If page > 0, returns a BSS copy of `base` with custom slots patched so
 * their characterID is 16+ (so the engine treats them as first-class racers).
 * Call from MM_Characters.c right after SetMenuLayout. */
struct CharacterSelectMeta *NativeCustomRacer_GetPageMeta(
    struct CharacterSelectMeta *base, int count);

/* === BUG-ICON-01: on-demand icon VRAM ====================================
 * Customs use iconID 32+slot, sharing the same VRAM slots as originals
 * (Crash=32, Cortex=33, ...). A page-level bulk upload (ApplyPageIcons)
 * clobbers the other side, so screens that draw driver icons without
 * re-touching the atlas (ghost list, race results, minimap) show stale
 * content. EnsureIconForChar uploads just the slot needed:
 *   - for originals: slices the slot's sub-rect from a cached page_0 atlas
 *   - for customs: uploads only that slot's blocks from page_N.vrm
 * Safe to call every frame; no-op if the slot already has the right icon. */
void NativeCustomRacer_EnsureIconForChar(int characterID);

/* === BUG-ICON-01 / Issue 4: force a full re-apply ========================
 * Intermediate screens (track select, etc.) load their own VRAM content
 * and clobber the icon atlas. s_appliedPage made RefreshPage a no-op on
 * re-entry, so the char select showed page 0 even when s_page was 1.
 * Call this when entering a screen that depends on our icons being
 * correct (e.g. MM_Characters_RestoreIDs). */
void NativeCustomRacer_ForceReapply(void);

/* === Sentinel CLUT (BUG-ICON-02) ===
 * Returns a struct Icon* suitable for Decal / RECTMENU draw calls.
 * For customs (ID >= 16): a BSS Icon with texLayout.clut carrying the
 * Sentinel bit (0x8000 | idx); the renderer samples a dedicated GL
 * texture instead of the shared VRAM slot.
 * For originals (0..15): gGT->ptrIcons[iconID] with EnsureIconForChar. */
struct Icon;
struct Icon *NativeCustomRacer_GetIconPtr(int characterID);

/* === High-score name color override ===
 * Draws a string with DecalFont_DrawLine, but for custom IDs (>= 16)
 * that have a #RRGGBB in roster.txt, temporarily swaps in the roster
 * color instead of the DecalFontStyle index passed by the caller.
 * Originals (0..15) and customs without a roster color fall through
 * unchanged, so existing call sites keep their behavior. */
void NativeCustomRacer_DrawLineForRacer(char *str, s16 posX, s16 posY,
                                        s16 fontType, s16 colorFlags,
                                        int characterID);

#ifdef __cplusplus
}
#endif

#endif