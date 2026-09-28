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
};

const char *LevelRegistry_GetMusic(int levelID);
const struct LevelDef *LevelRegistry_GetReplacement(int levelID);
int LevelRegistry_GetAdditionalCount(void);
const struct LevelDef *LevelRegistry_GetAdditional(int index);
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

// Virtual memcard level IDs: retail filename packs only 5 bits for
// levelID (0-31). Customs get 25-31 (7 slots). The GhostHeader and
// the memcard filename both use these; the header wins on read.
#define LEVEL_REGISTRY_VIRTUAL_MEMCARD_BASE  25
#define LEVEL_REGISTRY_VIRTUAL_MEMCARD_COUNT 7

// Returns the virtual memcard ID for the active custom (set by Track
// Select), or -1 if the active level is retail.
int LevelRegistry_GetVirtualMemcardIDFromActive(void);

// Maps a logicalLevelID (1000+) to its virtual memcard ID (25-31).
// Retail IDs (< 1000) pass through unchanged. Out-of-range customs
// (logicalID >= 1000 + COUNT) return the input unchanged.
int LevelRegistry_MapLogicalToVirtual(int logicalID);

#endif