#ifdef CTR_NATIVE

#include <SDL3/SDL_filesystem.h>
#include <ctype.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <LevelRegistry.h>
#include <platform/native_assets.h>

#define LEVEL_REGISTRY_MAX_LEVELS 32
#define LEVEL_REGISTRY_DEFAULT_PRIM_MEM 0x40000

// Virtual IDs for additional (non-replace) tracks. Chosen well above the
// retail range (0-24) so a custom's logicalLevelID can never collide with
// a real level ID or with another custom's baseLevelID.
#define LEVEL_REGISTRY_CUSTOM_BASE 1000

struct LevelJson
{
	const char *cursor;
	const char *end;
};

struct RetailLevelName
{
	const char *name;
	int id;
};

static const struct RetailLevelName s_retailLevelNames[] = {
	{"crash_cove", CRASH_COVE},
	{"mystery_caves", MYSTERY_CAVES},
	{"sewer_speedway", SEWER_SPEEDWAY},
	{"roo_tubes", ROO_TUBES},
	{"slide_coliseum", SLIDE_COLISEUM},
	{"turbo_track", TURBO_TRACK},
	{"coco_park", COCO_PARK},
	{"tiger_temple", TIGER_TEMPLE},
	{"papu_pyramid", PAPU_PYRAMID},
	{"dingo_canyon", DINGO_CANYON},
	{"polar_pass", POLAR_PASS},
	{"tiny_arena", TINY_ARENA},
	{"dragon_mines", DRAGON_MINES},
	{"blizzard_bluff", BLIZZARD_BLUFF},
	{"hot_air_skyway", HOT_AIR_SKYWAY},
	{"cortex_castle", CORTEX_CASTLE},
	{"n_gin_labs", N_GIN_LABS},
	{"oxide_station", OXIDE_STATION},
	{"main_menu", MAIN_MENU_LEVEL},
};

static const struct RetailLevelName s_characterEnumNames[] = {
	{"CRASH_BANDICOOT", CRASH_BANDICOOT},
	{"NEO_CORTEX", NEO_CORTEX},
	{"TINY_TIGER", TINY_TIGER},
	{"COCO_BANDICOOT", COCO_BANDICOOT},
	{"N_GIN", N_GIN},
	{"DINGODILE", DINGODILE},
	{"POLAR", POLAR},
	{"PURA", PURA},
	{"PINSTRIPE", PINSTRIPE},
	{"PAPU_PAPU", PAPU_PAPU},
	{"RIPPER_ROO", RIPPER_ROO},
	{"KOMODO_JOE", KOMODO_JOE},
	{"N_TROPY", N_TROPY},
	{"PENTA_PENGUIN", PENTA_PENGUIN},
	{"FAKE_CRASH", FAKE_CRASH},
	{"NITROS_OXIDE", NITROS_OXIDE},
};

static struct LevelDef s_levels[LEVEL_REGISTRY_MAX_LEVELS];
static int s_levelCount;
static int s_registryLoaded;
static const struct LevelDef *s_activeLevel;

#define LEVEL_REGISTRY_CUSTOM_HIGHSCORE_SLOTS 16
static struct HighScoreTrack s_customHighScoreTracks[LEVEL_REGISTRY_CUSTOM_HIGHSCORE_SLOTS];
static int s_customHighScoresInit;

static void LevelRegistry_InitCustomHighScoreTrack(struct HighScoreTrack *track)
{
	int i;
	memset(track, 0, sizeof(*track));
	for (i = 0; i < MEMCARD_HIGH_SCORE_ENTRIES_PER_TRACK; i++)
	{
		track->scoreEntry[i].time = MEMCARD_HIGH_SCORE_DEFAULT_TIME;
		track->scoreEntry[i].characterID = 0;
	}
}

struct HighScoreTrack *LevelRegistry_GetActiveCustomHighScoreTrack(void)
{
	const struct LevelDef *active = s_activeLevel;
	int slot;

	if (active == NULL || active->logicalLevelID < LEVEL_REGISTRY_CUSTOM_BASE)
		return NULL;

	slot = active->logicalLevelID - LEVEL_REGISTRY_CUSTOM_BASE;
	if (slot < 0 || slot >= LEVEL_REGISTRY_CUSTOM_HIGHSCORE_SLOTS)
		return NULL;

	if (!s_customHighScoresInit)
	{
		int i;
		for (i = 0; i < LEVEL_REGISTRY_CUSTOM_HIGHSCORE_SLOTS; i++)
			LevelRegistry_InitCustomHighScoreTrack(&s_customHighScoreTracks[i]);
		s_customHighScoresInit = 1;
	}

	return &s_customHighScoreTracks[slot];
}

int LevelRegistry_GetVirtualMemcardIDFromActive(void)
{
	const struct LevelDef *active = s_activeLevel;
	int slot;

	if (active == NULL || active->logicalLevelID < LEVEL_REGISTRY_CUSTOM_BASE)
		return -1;

	slot = active->logicalLevelID - LEVEL_REGISTRY_CUSTOM_BASE;
	if (slot < 0 || slot >= LEVEL_REGISTRY_VIRTUAL_MEMCARD_COUNT)
		return -1;

	return LEVEL_REGISTRY_VIRTUAL_MEMCARD_BASE + slot;
}

int LevelRegistry_MapLogicalToVirtual(int logicalID)
{
	int slot;

	if (logicalID < LEVEL_REGISTRY_CUSTOM_BASE)
		return logicalID;

	slot = logicalID - LEVEL_REGISTRY_CUSTOM_BASE;
	if (slot < 0 || slot >= LEVEL_REGISTRY_VIRTUAL_MEMCARD_COUNT)
		return logicalID;

	return LEVEL_REGISTRY_VIRTUAL_MEMCARD_BASE + slot;
}

static void LevelRegistry_Load(void);

const char *LevelRegistry_GetMusic(int levelID)
{
	const struct LevelDef *level;

	LevelRegistry_Load();
	level = ((s_activeLevel != NULL) &&
	         (s_activeLevel->baseLevelID == levelID)) ?
		s_activeLevel : LevelRegistry_GetReplacement(levelID);

	if ((level == NULL) || (level->music[0] == '\0'))
	{
		return NULL;
	}

	return level->music;
}

static void LevelJson_SkipWhitespace(struct LevelJson *json)
{
	while ((json->cursor < json->end) && isspace((unsigned char)*json->cursor))
		json->cursor++;
}

static int LevelJson_ReadString(struct LevelJson *json, char *dst, size_t dstSize)
{
	size_t length = 0;

	LevelJson_SkipWhitespace(json);
	if ((json->cursor >= json->end) || (*json->cursor++ != '"'))
		return 0;

	while (json->cursor < json->end)
	{
		char value = *json->cursor++;
		if (value == '"')
		{
			if (dstSize != 0)
				dst[length < dstSize ? length : dstSize - 1] = '\0';
			return length < dstSize;
		}
		if (value == '\\')
		{
			if (json->cursor >= json->end)
				return 0;
			value = *json->cursor++;
			switch (value)
			{
				case '"': case '\\': case '/': break;
				case 'b': value = '\b'; break;
				case 'f': value = '\f'; break;
				case 'n': value = '\n'; break;
				case 'r': value = '\r'; break;
				case 't': value = '\t'; break;
				default: return 0;
			}
		}
		if ((dstSize != 0) && (length + 1 < dstSize))
			dst[length] = value;
		length++;
	}

	return 0;
}

static int LevelJson_SkipValue(struct LevelJson *json);

static int LevelJson_SkipCollection(struct LevelJson *json, char open, char close)
{
	char key[LEVEL_REGISTRY_NAME_LENGTH];

	if ((json->cursor >= json->end) || (*json->cursor++ != open))
		return 0;
	LevelJson_SkipWhitespace(json);
	if ((json->cursor < json->end) && (*json->cursor == close))
	{
		json->cursor++;
		return 1;
	}

	while (json->cursor < json->end)
	{
		if (open == '{')
		{
			if (!LevelJson_ReadString(json, key, sizeof(key)))
				return 0;
			LevelJson_SkipWhitespace(json);
			if ((json->cursor >= json->end) || (*json->cursor++ != ':'))
				return 0;
		}
		if (!LevelJson_SkipValue(json))
			return 0;
		LevelJson_SkipWhitespace(json);
		if ((json->cursor < json->end) && (*json->cursor == close))
		{
			json->cursor++;
			return 1;
		}
		if ((json->cursor >= json->end) || (*json->cursor++ != ','))
			return 0;
	}

	return 0;
}

static int LevelJson_SkipValue(struct LevelJson *json)
{
	char ignored[LEVEL_REGISTRY_PATH_LENGTH];

	LevelJson_SkipWhitespace(json);
	if (json->cursor >= json->end)
		return 0;
	if (*json->cursor == '"')
		return LevelJson_ReadString(json, ignored, sizeof(ignored));
	if (*json->cursor == '{')
		return LevelJson_SkipCollection(json, '{', '}');
	if (*json->cursor == '[')
		return LevelJson_SkipCollection(json, '[', ']');

	while ((json->cursor < json->end) &&
	       (*json->cursor != ',') && (*json->cursor != '}') && (*json->cursor != ']') &&
	       !isspace((unsigned char)*json->cursor))
		json->cursor++;
	return 1;
}

static int LevelJson_ReadInt(struct LevelJson *json, int *value)
{
	char *numberEnd;
	long parsed;

	LevelJson_SkipWhitespace(json);
	parsed = strtol(json->cursor, &numberEnd, 10);
	if ((numberEnd == json->cursor) || (numberEnd > json->end) ||
	    (parsed < INT_MIN) || (parsed > INT_MAX))
		return 0;
	json->cursor = numberEnd;
	*value = (int)parsed;
	return 1;
}

static int LevelJson_ReadBool(struct LevelJson *json, int *value)
{
	LevelJson_SkipWhitespace(json);
	if (json->cursor >= json->end)
		return 0;

	// Accept both JSON native booleans (true/false) and quoted strings ("true"/"false")
	if (*json->cursor == '"')
	{
		char buf[8];
		if (!LevelJson_ReadString(json, buf, sizeof(buf)))
			return 0;
		if (strcmp(buf, "true") == 0) { *value = 1; return 1; }
		if (strcmp(buf, "false") == 0) { *value = 0; return 1; }
		return 0;
	}

	if ((json->end - json->cursor) >= 4 && memcmp(json->cursor, "true", 4) == 0)
	{
		*value = 1;
		json->cursor += 4;
		return 1;
	}
	if ((json->end - json->cursor) >= 5 && memcmp(json->cursor, "false", 5) == 0)
	{
		*value = 0;
		json->cursor += 5;
		return 1;
	}

	return 0;
}

static int LevelRegistry_FindRetailID(const char *name)
{
	size_t index;
	for (index = 0; index < sizeof(s_retailLevelNames) / sizeof(s_retailLevelNames[0]); index++)
	{
		if (strcmp(name, s_retailLevelNames[index].name) == 0)
			return s_retailLevelNames[index].id;
	}
	return -1;
}

static int LevelRegistry_FindCharacterID(const char *name)
{
	size_t index;
	for (index = 0; index < sizeof(s_characterEnumNames) / sizeof(s_characterEnumNames[0]); index++)
	{
		if (strcmp(name, s_characterEnumNames[index].name) == 0)
			return s_characterEnumNames[index].id;
	}
	return -1;
}

static int LevelJson_ReadRacers(struct LevelJson *json, struct LevelDef *level)
{
	char name[LEVEL_REGISTRY_NAME_LENGTH];
	int characterID;

	LevelJson_SkipWhitespace(json);
	if ((json->cursor >= json->end) || (*json->cursor++ != '['))
		return 0;

	LevelJson_SkipWhitespace(json);
	while ((json->cursor < json->end) && (*json->cursor != ']'))
	{
		if ((level->racerCount >= LEVEL_REGISTRY_RACER_COUNT) ||
		    !LevelJson_ReadString(json, name, sizeof(name)))
			return 0;
		characterID = LevelRegistry_FindCharacterID(name);
		if (characterID < 0)
			return 0;
		level->racerIDs[level->racerCount++] = characterID;

		LevelJson_SkipWhitespace(json);
		if ((json->cursor < json->end) && (*json->cursor == ','))
		{
			json->cursor++;
			LevelJson_SkipWhitespace(json);
		}
		else if ((json->cursor >= json->end) || (*json->cursor != ']'))
			return 0;
	}

	if ((json->cursor >= json->end) || (*json->cursor++ != ']'))
		return 0;
	return level->racerCount == LEVEL_REGISTRY_RACER_COUNT;
}

static int LevelRegistry_HasAsset(const char *assetName, const char *mode, const char *extension)
{
	char relativePath[LEVEL_REGISTRY_PATH_LENGTH];
	char resolvedPath[LEVEL_REGISTRY_PATH_LENGTH];
	int length;

	if ((mode != NULL) && (mode[0] != '\0'))
		length = snprintf(relativePath, sizeof(relativePath),
			"%s/%s/data.%s", assetName, mode, extension);
	else
		length = snprintf(relativePath, sizeof(relativePath),
			"%s/data.%s", assetName, extension);
	return (length > 0) && ((size_t)length < sizeof(relativePath)) &&
		NativeAssets_ResolvePath(relativePath, resolvedPath, sizeof(resolvedPath));
}

static int LevelRegistry_HasFile(const char *relativePath)
{
	char resolvedPath[LEVEL_REGISTRY_PATH_LENGTH];
	return NativeAssets_ResolvePath(relativePath, resolvedPath, sizeof(resolvedPath));
}

static int LevelRegistry_ParseManifest(const char *folder, const u8 *data, int size, struct LevelDef *level)
{
	struct LevelJson json;
	char key[LEVEL_REGISTRY_NAME_LENGTH];
	char replacement[LEVEL_REGISTRY_ID_LENGTH] = "";
	char base[LEVEL_REGISTRY_ID_LENGTH] = "";
	char musicFile[LEVEL_REGISTRY_PATH_LENGTH] = "";
	int hasID = 0;
	int hasName = 0;
	int hasMusic = 0;

	memset(level, 0, sizeof(*level));
	level->replaceLevelID = -1;
	level->baseLevelID = -1;
	level->primMemSize = LEVEL_REGISTRY_DEFAULT_PRIM_MEM;
	json.cursor = (const char *)data;
	json.end = json.cursor + size;

	LevelJson_SkipWhitespace(&json);
	if ((json.cursor >= json.end) || (*json.cursor++ != '{'))
	{
		fprintf(stderr, "[LevelRegistry] Parse fail: no opening brace\n");
		return 0;
	}
	LevelJson_SkipWhitespace(&json);
	while ((json.cursor < json.end) && (*json.cursor != '}'))
	{
		if (!LevelJson_ReadString(&json, key, sizeof(key)))
		{
			fprintf(stderr, "[LevelRegistry] Parse fail: bad key\n");
			return 0;
		}
		LevelJson_SkipWhitespace(&json);
		if ((json.cursor >= json.end) || (*json.cursor++ != ':'))
		{
			fprintf(stderr, "[LevelRegistry] Parse fail: no colon after key '%s'\n", key);
			return 0;
		}

		if (strcmp(key, "id") == 0)
			hasID = LevelJson_ReadString(&json, level->id, sizeof(level->id));
		else if (strcmp(key, "name") == 0)
			hasName = LevelJson_ReadString(&json, level->name, sizeof(level->name));
		else if (strcmp(key, "replace") == 0)
		{
			if (!LevelJson_ReadString(&json, replacement, sizeof(replacement)))
			{
				fprintf(stderr, "[LevelRegistry] Parse fail: bad 'replace' value\n");
				return 0;
			}
		}
		else if (strcmp(key, "base") == 0)
		{
			if (!LevelJson_ReadString(&json, base, sizeof(base)))
			{
				fprintf(stderr, "[LevelRegistry] Parse fail: bad 'base' value\n");
				return 0;
			}
		}
		else if (strcmp(key, "prim_mem") == 0)
		{
			if (!LevelJson_ReadInt(&json, &level->primMemSize))
			{
				fprintf(stderr, "[LevelRegistry] Parse fail: bad 'prim_mem' value\n");
				return 0;
			}
		}
		else if (strcmp(key, "force_hi_lod") == 0)
		{
			int boolValue = 0;
			if (!LevelJson_ReadBool(&json, &boolValue))
			{
				fprintf(stderr, "[LevelRegistry] Parse fail: bad 'force_hi_lod' value\n");
				return 0;
			}
			level->forceHiLod = boolValue;
		}
		else if (strcmp(key, "music") == 0)
		{
			hasMusic = LevelJson_ReadString(&json, musicFile, sizeof(musicFile));
			if (!hasMusic)
			{
				fprintf(stderr, "[LevelRegistry] Parse fail: bad 'music' value\n");
				return 0;
			}
		}
		else if (strcmp(key, "racers") == 0)
		{
			if (!LevelJson_ReadRacers(&json, level))
			{
				fprintf(stderr, "[LevelRegistry] Parse fail: bad 'racers' value\n");
				return 0;
			}
		}
		else if (!LevelJson_SkipValue(&json))
		{
			fprintf(stderr, "[LevelRegistry] Parse fail: bad value for key '%s'\n", key);
			return 0;
		}

		LevelJson_SkipWhitespace(&json);
		if ((json.cursor < json.end) && (*json.cursor == ','))
		{
			json.cursor++;
			LevelJson_SkipWhitespace(&json);
		}
		else if ((json.cursor >= json.end) || (*json.cursor != '}'))
		{
			fprintf(stderr, "[LevelRegistry] Parse fail: expected ',' or '}'\n");
			return 0;
		}
	}
	if ((json.cursor >= json.end) || (*json.cursor++ != '}'))
	{
		fprintf(stderr, "[LevelRegistry] Parse fail: no closing brace\n");
		return 0;
	}
	LevelJson_SkipWhitespace(&json);
	if (json.cursor != json.end)
	{
		fprintf(stderr, "[LevelRegistry] Parse fail: trailing bytes after closing brace\n");
		return 0;
	}

	level->replaceLevelID = LevelRegistry_FindRetailID(replacement);
	level->baseLevelID = LevelRegistry_FindRetailID(base);
	if (level->baseLevelID < 0)
		level->baseLevelID = level->replaceLevelID;
	if (snprintf(level->assetName, sizeof(level->assetName), "mods/levels/%s", folder) >= (int)sizeof(level->assetName))
	{
		fprintf(stderr, "[LevelRegistry] Parse fail: assetName too long\n");
		return 0;
	}
	if (hasMusic)
	{
		if ((musicFile[0] == '\0') || (strstr(musicFile, "..") != NULL) ||
		    (snprintf(level->music, sizeof(level->music), "%s/%s", level->assetName, musicFile) >= (int)sizeof(level->music)) ||
		    !LevelRegistry_HasFile(level->music))
		{
			fprintf(stderr, "[LevelRegistry] Parse fail: music '%s' not found\n", musicFile);
			return 0;
		}
	}
	if (!hasID || !hasName || (level->baseLevelID < 0) ||
	    (level->primMemSize < 0x10000) || (level->primMemSize > 0x400000))
	{
		fprintf(stderr, "[LevelRegistry] Parse fail: hasID=%d hasName=%d baseLevelID=%d primMem=%d\n",
			hasID, hasName, level->baseLevelID, level->primMemSize);
		return 0;
	}
	fprintf(stderr, "[LevelRegistry] primMemSize=%d (0x%x) forceHiLod=%d\n",
		level->primMemSize, level->primMemSize, level->forceHiLod);

	if (level->baseLevelID == MAIN_MENU_LEVEL)
	{
		if (!LevelRegistry_HasAsset(level->assetName, NULL, "lev") ||
		    !LevelRegistry_HasAsset(level->assetName, NULL, "vrm"))
		{
			fprintf(stderr, "[LevelRegistry] Parse fail: main_menu assets missing (need data.lev + data.vrm)\n");
			return 0;
		}
	}
	else if (!LevelRegistry_HasAsset(level->assetName, "1p", "lev") ||
	         !LevelRegistry_HasAsset(level->assetName, "1p", "vrm"))
	{
		fprintf(stderr, "[LevelRegistry] Parse fail: assets missing (need 1p/data.lev + 1p/data.vrm)\n");
		return 0;
	}

	fprintf(stderr, "[LevelRegistry] MANIFEST OK: id='%s' name='%s' replace=%d base=%d\n",
		level->id, level->name, level->replaceLevelID, level->baseLevelID);
	return 1;
}

static SDL_EnumerationResult SDLCALL LevelRegistry_Enumerate(void *userdata, const char *dirname, const char *fname)
{
	char manifestPath[LEVEL_REGISTRY_PATH_LENGTH];
	char fullPath[LEVEL_REGISTRY_PATH_LENGTH];
	struct NativeAssetsByteBuffer manifest;
	struct LevelDef level;
	SDL_PathInfo info;
	int index;
	int length;

	(void)userdata;
	if (s_levelCount >= LEVEL_REGISTRY_MAX_LEVELS)
	{
		fprintf(stderr, "[LevelRegistry] MAX_LEVELS reached, skipping '%s'\n", fname);
		return SDL_ENUM_SUCCESS;
	}
	length = snprintf(fullPath, sizeof(fullPath), "%s%s", dirname, fname);
	if ((length <= 0) || ((size_t)length >= sizeof(fullPath)) ||
	    !SDL_GetPathInfo(fullPath, &info) || (info.type != SDL_PATHTYPE_DIRECTORY))
	{
		return SDL_ENUM_CONTINUE;
	}

	fprintf(stderr, "[LevelRegistry] Found dir: %s\n", fname);

	length = snprintf(manifestPath, sizeof(manifestPath), "mods/levels/%s/level.json", fname);
	if ((length <= 0) || ((size_t)length >= sizeof(manifestPath)) ||
	    !NativeAssets_ReadBytes(manifestPath, NATIVE_ASSET_READ_DATA_FILE, &manifest))
	{
		fprintf(stderr, "[LevelRegistry] No level.json in '%s' (skipping)\n", fname);
		return SDL_ENUM_CONTINUE;
	}

	fprintf(stderr, "[LevelRegistry] Reading manifest: %s (%d bytes)\n", manifestPath, manifest.size);

	if (LevelRegistry_ParseManifest(fname, manifest.data, manifest.size, &level))
	{
		for (index = 0; index < s_levelCount; index++)
		{
			if (((level.replaceLevelID >= 0) &&
			     (s_levels[index].replaceLevelID == level.replaceLevelID)) ||
			    (strcmp(s_levels[index].id, level.id) == 0))
			{
				fprintf(stderr, "[LevelRegistry] Ignoring duplicate: %s\n", manifestPath);
				NativeAssets_FreeBytes(&manifest);
				return SDL_ENUM_CONTINUE;
			}
		}
		// Assign logicalLevelID. Replacements reuse the retail ID they
		// replace; additional tracks (no "replace") get a virtual ID in
		// a range disjoint from retail so GetRuntimeLevel can find them
		// by ID lookup.
		if (level.replaceLevelID < 0)
		{
			int additionalCount = 0;
			int addIndex;
			for (addIndex = 0; addIndex < s_levelCount; addIndex++)
			{
				if (s_levels[addIndex].replaceLevelID < 0)
					additionalCount++;
			}
			level.logicalLevelID = LEVEL_REGISTRY_CUSTOM_BASE + additionalCount;
		}
		else
		{
			level.logicalLevelID = level.replaceLevelID;
		}

		s_levels[s_levelCount++] = level;
		fprintf(stderr, "[LevelRegistry] Registered level #%d: '%s' (logicalID=%d)\n",
		        s_levelCount - 1, level.name, level.logicalLevelID);
	}
	else
	{
		fprintf(stderr, "[LevelRegistry] Ignoring invalid manifest: %s\n", manifestPath);
	}

	NativeAssets_FreeBytes(&manifest);
	return SDL_ENUM_CONTINUE;
}

static void LevelRegistry_Load(void)
{
	char levelsPath[LEVEL_REGISTRY_PATH_LENGTH];
	if (s_registryLoaded)
		return;
	s_registryLoaded = 1;

	fprintf(stderr, "[LevelRegistry] === Loading manifests ===\n");

	if (NativeAssets_BuildPath("mods/levels", levelsPath, sizeof(levelsPath)))
	{
		fprintf(stderr, "[LevelRegistry] Scan dir: %s\n", levelsPath);
		SDL_EnumerateDirectory(levelsPath, LevelRegistry_Enumerate, NULL);
	}
	else
	{
		fprintf(stderr, "[LevelRegistry] FAILED to build path 'mods/levels'\n");
	}

	fprintf(stderr, "[LevelRegistry] === Total levels loaded: %d ===\n", s_levelCount);
}

const struct LevelDef *LevelRegistry_GetReplacement(int levelID)
{
	int index;
	LevelRegistry_Load();
	for (index = 0; index < s_levelCount; index++)
	{
		if (s_levels[index].replaceLevelID == levelID)
			return &s_levels[index];
	}
	return NULL;
}

int LevelRegistry_GetAdditionalCount(void)
{
	int index;
	int count = 0;
	LevelRegistry_Load();
	for (index = 0; index < s_levelCount; index++)
	{
		if (s_levels[index].replaceLevelID < 0)
			count++;
	}
	return count;
}

const struct LevelDef *LevelRegistry_GetAdditional(int requestedIndex)
{
	int index;
	LevelRegistry_Load();
	for (index = 0; index < s_levelCount; index++)
	{
		if ((s_levels[index].replaceLevelID < 0) && (requestedIndex-- == 0))
			return &s_levels[index];
	}
	return NULL;
}

void LevelRegistry_SetActive(const struct LevelDef *level)
{
	s_activeLevel = level;
}

const struct LevelDef *LevelRegistry_GetActive(void)
{
	return s_activeLevel;
}

static const struct LevelDef *LevelRegistry_GetRuntimeLevel(int levelID)
{
	int index;
	LevelRegistry_Load();

	// Additional tracks (no replace): match by their virtual logicalLevelID.
	// Runs first so a virtual ID never falls through to a retail-ID lookup
	// that would read garbage.
	for (index = 0; index < s_levelCount; index++)
	{
		if ((s_levels[index].replaceLevelID < 0) &&
		    (s_levels[index].logicalLevelID == levelID))
			return &s_levels[index];
	}

	if ((s_activeLevel != NULL) && (s_activeLevel->baseLevelID == levelID))
		return s_activeLevel;
	return LevelRegistry_GetReplacement(levelID);
}

const int *LevelRegistry_GetRacers(int levelID, int *count)
{
	const struct LevelDef *level = LevelRegistry_GetRuntimeLevel(levelID);
	if (count != NULL)
		*count = level != NULL ? level->racerCount : 0;
	return (level != NULL) && (level->racerCount == LEVEL_REGISTRY_RACER_COUNT) ?
		level->racerIDs : NULL;
}

int LevelRegistry_GetPrimMemSize(int levelID)
{
	const struct LevelDef *level = LevelRegistry_GetRuntimeLevel(levelID);
	return level != NULL ? level->primMemSize : 0;
}

char *LevelRegistry_GetName(int levelID, char *retailName)   
{
	const struct LevelDef *level = LevelRegistry_GetRuntimeLevel(levelID);
	return level != NULL ? level->name : retailName;     
}

// Return the LevelDef of an additional track (no "replace") by its
// virtual logicalLevelID. Pure lookup, no side effects.
const struct LevelDef *LevelRegistry_GetAdditionalByLogicalID(int logicalLevelID)
{
	int index;
	LevelRegistry_Load();
	for (index = 0; index < s_levelCount; index++)
	{
		if ((s_levels[index].replaceLevelID < 0) &&
		    (s_levels[index].logicalLevelID == logicalLevelID))
			return &s_levels[index];
	}
	return NULL;
}

// Return the display name of an additional track by its virtual ID, or
// NULL if levelID does not belong to an additional track. Used by the
// Track Select menu to bypass data.metaDataLEV[], which is only sized
// for retail level IDs.
const char *LevelRegistry_GetAdditionalName(int levelID)
{
	int index;
	LevelRegistry_Load();
	for (index = 0; index < s_levelCount; index++)
	{
		if ((s_levels[index].replaceLevelID < 0) &&
		    (s_levels[index].logicalLevelID == levelID))
			return s_levels[index].name;
	}
	return NULL;
}

int LevelRegistry_ShouldForceHiLod(void)
{
	const struct LevelDef *level = LevelRegistry_GetRuntimeLevel(sdata->gGT->levelID);
	return (level != NULL) ? level->forceHiLod : 0;
}

const char *LevelRegistry_GetOverrideForBigfileEntry(int levelID, int levelLOD, int subfileIndex)
{
	static char path[LEVEL_REGISTRY_PATH_LENGTH];
	const struct LevelDef *level = LevelRegistry_GetRuntimeLevel(levelID);
	const char *mode;
	const char *extension;
	int firstEntry;

	if (level == NULL)
		return NULL;

	// EXPERIMENT: allow custom override in splitscreen. The 1P VRM is
	// loaded regardless of numPlyrCurrGame; we rely on the emulated VRAM
	// to not enforce the retail slot boundary. If this crashes or renders
	// wrong, revert and implement multi-LOD (Fase 3) instead.
	// (Nothing here for now -- removed the early return.)

	if (levelID == MAIN_MENU_LEVEL)
	{
		if (subfileIndex == BI_MAINMENUFILE + LVI_VRAM)
			extension = "vrm";
		else if (subfileIndex == BI_MAINMENUFILE + LVI_LEV)
			extension = "lev";
		else
			return NULL;

		if (snprintf(path, sizeof(path), "%s/data.%s", level->assetName, extension) >= (int)sizeof(path))
			return NULL;
		fprintf(stderr, "[LevelRegistry] OVERRIDE main_menu subfile=%d -> %s\n", subfileIndex, path);
		return path;
	}

	if ((levelLOD < LOAD_LEVEL_LOD_1P) || (levelLOD > LOAD_LEVEL_LOD_RELIC))
		return NULL;

	firstEntry = BI_ARCADETRACKS +
		(levelID * LOAD_TRACK_FILES_PER_LOD_GROUP) +
		sdata->levBigLodIndex[levelLOD - 1];
	if (subfileIndex == firstEntry + LVI_VRAM)
		extension = "vrm";
	else if (subfileIndex == firstEntry + LVI_LEV)
		extension = "lev";
	else
		return NULL;

	mode = levelLOD == LOAD_LEVEL_LOD_RELIC ? "relic" : "1p";
	if ((levelLOD == LOAD_LEVEL_LOD_RELIC) && !LevelRegistry_HasAsset(level->assetName, mode, extension))
		mode = "1p";
	if (snprintf(path, sizeof(path), "%s/%s/data.%s", level->assetName, mode, extension) >= (int)sizeof(path))
		return NULL;

	fprintf(stderr, "[LevelRegistry] OVERRIDE levelID=%d lod=%d subfile=%d -> %s\n",
		levelID, levelLOD, subfileIndex, path);
	return path;
}

#else

#include <LevelRegistry.h>

const struct LevelDef *LevelRegistry_GetAdditionalByLogicalID(int logicalLevelID) { (void)logicalLevelID; return 0; }
const char *LevelRegistry_GetAdditionalName(int levelID) { (void)levelID; return 0; }
const struct LevelDef *LevelRegistry_GetReplacement(int levelID) { (void)levelID; return 0; }
int LevelRegistry_GetAdditionalCount(void) { return 0; }
const struct LevelDef *LevelRegistry_GetAdditional(int index) { (void)index; return 0; }
void LevelRegistry_SetActive(const struct LevelDef *level) { (void)level; }
const struct LevelDef *LevelRegistry_GetActive(void) { return 0; }
const int *LevelRegistry_GetRacers(int levelID, int *count) { (void)levelID; if (count != 0) *count = 0; return 0; }
int LevelRegistry_GetPrimMemSize(int levelID) { (void)levelID; return 0; }
int LevelRegistry_ShouldForceHiLod(void) { return 0; }
const char *LevelRegistry_GetMusic(int levelID) { (void)levelID; return 0; }
char *LevelRegistry_GetName(int levelID, char *retailName) { (void)levelID; return retailName; }
const char *LevelRegistry_GetOverrideForBigfileEntry(int levelID, int levelLOD, int subfileIndex)
{
	(void)levelID; (void)levelLOD; (void)subfileIndex; return 0;
}

struct HighScoreTrack *LevelRegistry_GetActiveCustomHighScoreTrack(void) { return 0; }
int LevelRegistry_GetVirtualMemcardIDFromActive(void) { return -1; }
int LevelRegistry_MapLogicalToVirtual(int logicalID) { return logicalID; }

#endif