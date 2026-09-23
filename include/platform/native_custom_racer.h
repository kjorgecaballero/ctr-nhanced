#ifndef NATIVE_CUSTOM_RACER_H
#define NATIVE_CUSTOM_RACER_H

#include <common.h>
#include <namespace_Vehicle.h>

#ifdef __cplusplus
extern "C" {
#endif

/* === Phase 1: custom IDs 16..63 ===========================================
 * We do NOT extend data.MetaDataCharacters[0x10] (that would break ~30
 * CTR_STATIC_ASSERTs on struct sData). Instead: a parallel table in BSS
 * plus a redirection macro.
 *   IDs 0..15 -> data.MetaDataCharacters (original behavior, untouched).
 *   IDs 16+   -> s_customMeta.
 * ========================================================================= */
#define NATIVE_CUSTOM_ID_BASE 16
#define NATIVE_CUSTOM_COUNT   146   /* 128 (pages 1-8, slots 0-15)
                                     * + 2 (page 0, slots 16-17)
                                     * + 16 (pages 1-8, slots 16-17) */

/* Page 0 grid slots 16 and 17 are custom. Their customIDs are the
 * last two of the custom ID space (see GET_MPK_ID). */
#define NATIVE_PAGE0_CUSTOM_BASE  144
#define NATIVE_PAGE0_CUSTOM_COUNT 2

/* Pages 1-8 grid slots 16-17. IDs 146-161 (8 pages x 2 slots). */
#define NATIVE_EXT_CUSTOM_BASE   146
#define NATIVE_EXT_CUSTOM_COUNT  16

#define NATIVE_PAGE_SIZE      16

extern struct MetaDataCHAR s_customMeta[NATIVE_CUSTOM_COUNT];
extern s16                 s_customMenuID[NATIVE_CUSTOM_COUNT];

#define GET_METADATA(id)                                                      \
    ((((id) >= NATIVE_CUSTOM_ID_BASE) &&                                      \
      ((id) <  (NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT)))                \
        ? &s_customMeta[(id) - NATIVE_CUSTOM_ID_BASE]                         \
        : &data.MetaDataCharacters[(id)])

/* Grid slot (0..15) -> enum Characters. Must match the permutation in
 * game/230/D230.c characterSelectMeta1P2P, which is how the game maps
 * character-select cells to the enum-ordered arrays (voice banks,
 * dance models, kart colors, TNT height, BI_*PACK ranges). */
extern const u8 s_gridToCharID[NATIVE_PAGE_SIZE + NATIVE_PAGE0_CUSTOM_COUNT];


/* Maps a character ID to an enum Characters index (0..15) for use as an
 * index into the BI_*PACK / BI_RACERMODELHI bigfile ranges, which only
 * have 16 entries. Custom IDs wrap to their page slot, then through
 * s_gridToCharID. Originals pass through unchanged.
 *
 * ID ranges:
 *   16..143   pages 1-8, slots 0-15
 *   144..145  page 0, slots 16-17
 *   146..161  pages 1-8, slots 16-17
 *
 * Was a macro; converted to static inline to (a) keep the 3-way branch
 * readable and (b) avoid evaluating the argument multiple times. */
static inline int GET_MPK_ID(int id)
{
    if (id < NATIVE_CUSTOM_ID_BASE)
        return id;
    if (id < NATIVE_PAGE0_CUSTOM_BASE)
        return s_gridToCharID[(id - NATIVE_CUSTOM_ID_BASE) % NATIVE_PAGE_SIZE];
    if (id < NATIVE_EXT_CUSTOM_BASE)
        return s_gridToCharID[NATIVE_PAGE_SIZE + (id - NATIVE_PAGE0_CUSTOM_BASE)];
    if (id < NATIVE_EXT_CUSTOM_BASE + NATIVE_EXT_CUSTOM_COUNT)
        return s_gridToCharID[NATIVE_PAGE_SIZE
                            + ((id - NATIVE_EXT_CUSTOM_BASE) % NATIVE_PAGE0_CUSTOM_COUNT)];
    return id;
}

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

/* === Custom podium dance (v1) =========================================
 * Podium model index is `mpkID + STATIC_CRASHDANCE`; CS_Podium_Init
 * resolves it via gGT->modelPtr[]. This hook overrides that slot
 * with a custom `dance.ctr` loaded from the racer's folder, right
 * before the podium threads spawn. Retail path untouched. */
void  NativeCustomRacer_ResetPodiumDance(void);
int   NativeCustomRacer_HasDanceModel(int characterID);

/* Snapshot of the rank->charID mapping taken while gGT->drivers[] is
 * still populated. Podium_InitModels calls this BEFORE the driver array
 * gets cleared by the end-of-race flow. Preload/Apply must use this
 * cache instead of reading drivers[] directly: by the time
 * CS_Podium_FullScene_Init runs, only drivers[0] is guaranteed alive. */
void  NativeCustomRacer_CachePodiumCharIDs(struct GameTracker *gGT);

/* Preloads custom podium dance models for rank 0..2 drivers into an
 * internal per-charID table. Does NOT touch gGT->modelPtr[]. Call from
 * CS_Podium_FullScene_Init before the CS_Thread_Init calls. Uses the
 * rank->charID cache populated by NativeCustomRacer_CachePodiumCharIDs. */
void  NativeCustomRacer_PreloadPodiumDanceModels(struct GameTracker *gGT);

/* Attaches the preloaded custom dance model to a specific podium thread,
 * based on the driver whose driverRank == rank. Call from
 * CS_Podium_FullScene_Init immediately after each CS_Thread_Init. */
struct Thread;
void  NativeCustomRacer_ApplyPodiumDanceToThread(struct Thread *t, int rank);

/* Forces the thread's instance model to the correct retail podium model
 * for the given rank (0 = First, 1 = Second, 2 = Third). Needed when two
 * podiums share an mpkID (custom + original): LOAD_TenStages case 8 writes
 * both into gGT->modelPtr[mpkID] and the last one wins, so both threads
 * would read the same retail Model*. Call right after CS_Thread_Init and
 * before NativeCustomRacer_ApplyPodiumDanceToThread. */
void  NativeCustomRacer_FixPodiumModel(struct Thread *t, int rank);

/* Returns the custom frame count for a model installed by
 * PreloadPodiumDanceModels, or 0 if the model is not a custom dance.
 * CS_Thread.c uses this to make a custom dance with N frames play
 * 0..N-1 instead of the retail script's hardcoded range. */
struct Model;
u16 NativeCustomRacer_GetPodiumDanceFramesForModel(struct Model *model);


/* === Custom podium music (v1) ==========================================
 * One track per custom. xaID = 13 + roster_index (retail MUSIC occupies
 * 0..12). The pipeline inserts custom music entries right after the
 * retail MUSIC block and bumps firstSongEXTRA/GAME accordingly.
 * Returns 0 if the rank-0 driver has no custom, or the roster entry has
 * no music/podium.wav (the pipeline writes a null entry -> CDSYS_XAPlay
 * returns 0 -> caller falls back to the retail switch). */
#define NATIVE_MUSIC_TRACK_BASE 13

int NativeCustomRacer_GetPodiumMusicTrackForFirstPlace(void);

/* Applies textures.vrm for the given character to the player's VRAM region. */
void NativeCustomRacer_ApplySlot(int playerIndex, int characterID);

/* Dumps the current VRAM to a file if the environment variable
 * CTR_DUMP_VRAM is set to a non-empty path. No-op otherwise. */
void NativeCustomRacer_DumpVRAMIfRequested(void);

/* === Phase 2.5: BUG-MENU-04 side table ====================================
 * data.driverModelExtras[] has only LOAD_DRIVER_MODEL_EXTRA_COUNT (=3)
 * slots, so index 3 (P4 in 4P) aliases podiumModel_firstPlace. Writing
 * there corrupts the podium model pointers and crashes the menu on exit.
 * We keep the 4th player's custom model in a BSS side table, keyed by
 * playerIndex, so we never touch the struct Data layout.
 * The stored pointer is already offset by LOAD_MODEL_FILE_HEADER_BYTES,
 * i.e. it points to a valid `struct Model`. */
void  NativeCustomRacer_SetPlayerModelPtr(int playerIndex, void *model);
void *NativeCustomRacer_GetPlayerModelPtr(int playerIndex);

/* Menu preview: real Oxide model (see native_custom_racer.c). */
void  NativeCustomRacer_ResetOxideMenuModel(void);
void **NativeCustomRacer_GetOxideMenuModelSlot(void);
struct Model *NativeCustomRacer_GetOxideMenuModel(void);

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

/* === Phase 2: menu integration ===
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

/* === Mask good/bad (Aku Aku / Uka Uka) ===
 * Returns 1 = good (Aku Aku), 0 = bad (Uka Uka), -1 = not a custom.
 * Default for customs without a mask= field in roster.txt is good. */
int NativeCustomRacer_GetMaskIsGoodGuy(int characterID);

/* === Wheels visible flag ===
 * Returns 1 = wheels visible, 0 = wheels hidden (Oxide-style), -1 = not a custom.
 * Default for customs without a wheels= field in roster.txt is 1. */
int NativeCustomRacer_HasWheels(int characterID);

/* === Custom voicelines (v2) ============================================
 * Customs deliver XA files under
 *   assets/mods/racers/<slug>/voices/<set>_<var>.xa
 * <set> = 0..10 (data.voiceID[voiceID], same index as retail)
 * <var> = 0..7 (variants; RNG picks one per call).
 * Returns 1 if a custom voice was played. */

/* Event indices within a custom's voice bank. Must match the EVENTS
 * list in tools/custom_racers/build_voice_pipeline.py: reordering here
 * without rebuilding the XNF will route every event to the wrong track. */
#define NATIVE_VOICE_TRACK_BASE           314
#define NATIVE_VOICE_VARIANTS_PER_GROUP   2
#define NATIVE_VOICE_GAMEPLAY_GROUP_COUNT 8
#define NATIVE_VOICE_MENU_BASE            (NATIVE_VOICE_GAMEPLAY_GROUP_COUNT * NATIVE_VOICE_VARIANTS_PER_GROUP)

#define NATIVE_VOICE_EVENT_BOOST_01      0
#define NATIVE_VOICE_EVENT_BOOST_02      1
#define NATIVE_VOICE_EVENT_HURT_01       2
#define NATIVE_VOICE_EVENT_HURT_02       3
#define NATIVE_VOICE_EVENT_SPIN_01       4
#define NATIVE_VOICE_EVENT_SPIN_02       5
#define NATIVE_VOICE_EVENT_JUMP_01       6
#define NATIVE_VOICE_EVENT_JUMP_02       7
#define NATIVE_VOICE_EVENT_TRAP_01       8
#define NATIVE_VOICE_EVENT_TRAP_02       9
#define NATIVE_VOICE_EVENT_PROTECTED_01  10
#define NATIVE_VOICE_EVENT_PROTECTED_02  11
#define NATIVE_VOICE_EVENT_OVERTAKE_01   12
#define NATIVE_VOICE_EVENT_OVERTAKE_02   13
#define NATIVE_VOICE_EVENT_ATTACK_01     14
#define NATIVE_VOICE_EVENT_ATTACK_02     15
#define NATIVE_VOICE_EVENT_MENU_YES      16
#define NATIVE_VOICE_EVENT_MENU_OUCH     17
#define NATIVE_VOICE_EVENT_COUNT         18

/* Returns the base xaID for the custom's voice tracks
 * (314 + roster_index * NATIVE_VOICE_EVENT_COUNT), or 0 if the
 * character has no custom voice assigned.
 * Slot layout (gameplay groups use group*2+variant):
 *   base+0=boost_01, +1=boost_02, +2=hurt_01, ..., +15=attack_02,
 *   +16=menu_yes, +17=menu_ouch. */
int NativeCustomRacer_GetVoiceTrackBase(int characterID);

/* Returns the duration of the last custom voiceline played, in
 * 60Hz frames (capped at 600 = 10s). 0 if nothing played or the
 * call failed. HOWL_Voiceline.c uses this to size the custom
 * cooldown so a queued retail voiceline cannot cut the custom
 * mid-playback. */

/* === Debug-only rank forcer ============================================
 * Set via L2 + D-pad en MainFrame_GameLogic (CTR_INTERNAL only).
 * -1 = off, 0/1/2 = 1°/2°/3°. Consumido por Podium_InitModels. */
#if defined(CTR_DEBUG_PODIUM_JUMP)
extern s32 g_debugForcedPodiumRank;
void NativeDebug_ForcePodium(s32 targetRank);
#endif

/* Wrapper for Voiceline_RequestPlay call sites. Originals map to their
 * grid enum (retail path); customs (>= NATIVE_CUSTOM_ID_BASE) pass
 * through raw so the custom voice table is used. */
static inline int GET_VOICE_CHAR_ID(int id)
{
    if (id >= NATIVE_CUSTOM_ID_BASE)
        return id;
    return GET_MPK_ID(id);
}

#ifdef __cplusplus
}
#endif

#endif