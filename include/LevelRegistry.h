#ifndef LEVEL_REGISTRY_H
#define LEVEL_REGISTRY_H

#define LEVEL_REGISTRY_ID_LENGTH 64
#define LEVEL_REGISTRY_NAME_LENGTH 128
#define LEVEL_REGISTRY_PATH_LENGTH 256
#define LEVEL_REGISTRY_RACER_COUNT 8

struct LevelDef
{
	int replaceLevelID;
	int baseLevelID;
	char id[LEVEL_REGISTRY_ID_LENGTH];
	char name[LEVEL_REGISTRY_NAME_LENGTH];
	char assetName[LEVEL_REGISTRY_PATH_LENGTH];
	int primMemSize;
	char music[LEVEL_REGISTRY_PATH_LENGTH];
	int racerIDs[LEVEL_REGISTRY_RACER_COUNT];
	int racerCount;
	int logicalLevelID;
	int replacesRetailLevel;
	int forceHiLod;

	/* 1 if the custom is a battle arena (manifest "type": "battle", or
	 * baseLevelID in [NITRO_COURT, LAB_BASEMENT]). Arenas live in a
	 * separate logical ID range (LEVEL_REGISTRY_CUSTOM_BATTLE_BASE) so
	 * they don't consume the 16 high-score / ghost slots reserved for
	 * track additions. */
	int isBattle;
};

const char *LevelRegistry_GetMusic(int levelID);

/* Resolve the fully-qualified relative path to a custom level's
 * music file (e.g. "assets/mods/levels/my_track/music/music.ogg").
 * Returns NULL for retail levels, for replace customs whose base
 * doesn't match levelID, or for customs without a "music" field.
 * The returned pointer is a static buffer; valid until the next
 * call to either of these two functions. */
const char *LevelRegistry_GetActiveMusicPath(int levelID);
const char *LevelRegistry_GetActiveMusicFinalPath(int levelID);
const struct LevelDef *LevelRegistry_GetReplacement(int levelID);
int LevelRegistry_GetAdditionalCount(void);
const struct LevelDef *LevelRegistry_GetAdditional(int index);

/* Same as GetAdditional, but only returns additional battle arenas
 * (no-replace, isBattle = 1). Used by the Battle Track Select. */
int LevelRegistry_GetAdditionalBattleCount(void);
const struct LevelDef *LevelRegistry_GetAdditionalBattle(int index);
const struct LevelDef *LevelRegistry_GetAdditionalByLogicalID(int logicalLevelID);
const char *LevelRegistry_GetAdditionalName(int levelID);
void LevelRegistry_SetActive(const struct LevelDef *level);
const struct LevelDef *LevelRegistry_GetActive(void);
const int *LevelRegistry_GetRacers(int levelID, int *count);
int LevelRegistry_GetPrimMemSize(int levelID);
char *LevelRegistry_GetName(int levelID, char *retailName);
int LevelRegistry_ShouldForceHiLod(void);

const char *LevelRegistry_GetOverrideForBigfileEntry(
	int levelID,
	int levelLOD,
	int subfileIndex);

// Returns a parallel HighScoreTrack for the currently active additional
// (non-replace) custom level, or NULL if the active level is retail.
// Slots are indexed by (logicalLevelID - LEVEL_REGISTRY_CUSTOM_BASE).
// Used to keep custom track high scores / TT flags separate from the
// retail track they share a baseLevelID with.
struct HighScoreTrack *LevelRegistry_GetActiveCustomHighScoreTrack(void);
void LevelRegistry_LoadCustomHighScores(void);
void LevelRegistry_SaveCustomHighScores(void);

// Virtual memcard level IDs: retail filename packs only 5 bits for
// levelID (0-31). Customs get 25-31 (7 slots). The GhostHeader and
// the memcard filename both use these; the header wins on read.
#define LEVEL_REGISTRY_VIRTUAL_MEMCARD_BASE  25
#define LEVEL_REGISTRY_VIRTUAL_MEMCARD_COUNT 7

// Returns the virtual memcard ID for the active custom (set by Track
// Select), or -1 if the active level is retail.
int LevelRegistry_GetVirtualMemcardIDFromActive(void);
int LevelRegistry_GetVirtualMemcardIDFromBase(int baseLevelID);

// Maps a logicalLevelID (1000+) to its virtual memcard ID (25-31).
// Retail IDs (< 1000) pass through unchanged. Out-of-range customs
// (logicalID >= 1000 + COUNT) return the input unchanged.
int LevelRegistry_MapLogicalToVirtual(int logicalID);

#endif