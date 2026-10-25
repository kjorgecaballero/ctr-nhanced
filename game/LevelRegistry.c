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

// Parallel range for additional battle arenas. Disjoint from
// LEVEL_REGISTRY_CUSTOM_BASE so an arena doesn't consume a track
// high-score / ghost slot (LEVEL_REGISTRY_CUSTOM_HIGHSCORE_SLOTS = 16).
#define LEVEL_REGISTRY_CUSTOM_BATTLE_BASE 2000

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
	{"nitro_court", NITRO_COURT},
	{"rampage_ruins", RAMPAGE_RUINS},
	{"parking_lot", PARKING_LOT},
	{"skull_rock", SKULL_ROCK},
	{"the_north_bowl", THE_NORTH_BOWL},
	{"rocky_road", ROCKY_ROAD},
	{"lab_basement", LAB_BASEMENT},
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

/* Stable ghost keys (0x4000 | hash14 of manifest id). Built lazily. */
static int s_ghostKeys[LEVEL_REGISTRY_MAX_LEVELS];
static int s_ghostKeysBuilt;
static const struct LevelDef *s_ghostContext;
/* Last non-NULL active level. SetActive(NULL) is called on every retail load
 * and by menus, so at ghost-save time the active pointer can already be NULL.
 * Remembering the last custom level lets the base->virtual lookup pick the
 * track that was actually raced instead of the first one sharing the base. */
static const struct LevelDef *s_lastActiveLevel;

#define LEVEL_REGISTRY_LEGACY_HS_SLOTS 16
#define LEVEL_REGISTRY_HIGHSCORES_PATH "assets/mods/custom_highscores.bin"
#define LEVEL_REGISTRY_HIGHSCORES_MAGIC 0x48534843u /* "CHSH" */
#define LEVEL_REGISTRY_HIGHSCORES_VERSION 2u

struct LevelRegistryHighScoreHeader { u32 magic; u32 version; u32 slotCount; u32 reserved; };
struct LevelRegistryHighScoreEntry  { s32 key; struct HighScoreTrack track; };

static struct LevelRegistryHighScoreEntry s_customHS[LEVEL_REGISTRY_MAX_LEVELS];
static int s_customHSCount;
static struct HighScoreTrack s_legacyHS[LEVEL_REGISTRY_LEGACY_HS_SLOTS];
static int s_legacyHSCount;
static int s_customHSMigrated;
static int s_customHighScoresInit;

static void LevelRegistry_Load(void);

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

static int LevelRegistry_FindCustomHS(int key)
{
	int i;
	for (i = 0; i < s_customHSCount; i++)
		if (s_customHS[i].key == key) return i;
	return -1;
}

void LevelRegistry_LoadCustomHighScores(void)
{
	FILE *f;
	struct LevelRegistryHighScoreHeader h;
	int i, n;

	s_customHSCount = 0;
	s_legacyHSCount = 0;
	s_customHSMigrated = 0;
	s_customHighScoresInit = 1;

	f = fopen(LEVEL_REGISTRY_HIGHSCORES_PATH, "rb");
	if (f == NULL) return;

	if (fread(&h, sizeof(h), 1, f) != 1 || h.magic != LEVEL_REGISTRY_HIGHSCORES_MAGIC)
	{
		fprintf(stderr, "[LevelRegistry] custom_highscores.bin malformed, keeping defaults\n");
		fclose(f);
		return;
	}

	if (h.version == 1u)
	{
		n = (h.slotCount > LEVEL_REGISTRY_LEGACY_HS_SLOTS) ? LEVEL_REGISTRY_LEGACY_HS_SLOTS : (int)h.slotCount;
		if (fread(s_legacyHS, sizeof(struct HighScoreTrack), (size_t)n, f) == (size_t)n)
			s_legacyHSCount = n;
		fprintf(stderr, "[LevelRegistry] custom_highscores.bin v1 (%d slots) will be migrated\n", s_legacyHSCount);
	}
	else if (h.version == 2u)
	{
		n = (h.slotCount > LEVEL_REGISTRY_MAX_LEVELS) ? LEVEL_REGISTRY_MAX_LEVELS : (int)h.slotCount;
		for (i = 0; i < n; i++)
		{
			if (fread(&s_customHS[s_customHSCount], sizeof(s_customHS[0]), 1, f) != 1) break;
			if (s_customHS[s_customHSCount].key >= 0) s_customHSCount++;
		}
		fprintf(stderr, "[LevelRegistry] loaded custom_highscores.bin v2 (%d entries)\n", s_customHSCount);
	}
	else
		fprintf(stderr, "[LevelRegistry] custom_highscores.bin unknown version, keeping defaults\n");

	fclose(f);
}

static void LevelRegistry_MigrateLegacyHighScores(void)
{
	int i;
	LevelRegistry_Load();
	if (s_customHSMigrated) return;
	s_customHSMigrated = 1;

	for (i = 0; i < s_legacyHSCount; i++)
	{
		int key = LevelRegistry_GetGhostKey(LevelRegistry_GetAdditionalByLogicalID(LEVEL_REGISTRY_CUSTOM_BASE + i));
		if (key < 0 || LevelRegistry_FindCustomHS(key) >= 0 || s_customHSCount >= LEVEL_REGISTRY_MAX_LEVELS)
			continue;
		s_customHS[s_customHSCount].key = key;
		s_customHS[s_customHSCount].track = s_legacyHS[i];
		s_customHSCount++;
	}
}

void LevelRegistry_SaveCustomHighScores(void)
{
	FILE *f;
	struct LevelRegistryHighScoreHeader h;

	if (!s_customHighScoresInit) return;
	LevelRegistry_MigrateLegacyHighScores();

	memset(&h, 0, sizeof(h));
	h.magic = LEVEL_REGISTRY_HIGHSCORES_MAGIC;
	h.version = LEVEL_REGISTRY_HIGHSCORES_VERSION;
	h.slotCount = (u32)s_customHSCount;

	f = fopen(LEVEL_REGISTRY_HIGHSCORES_PATH, "wb");
	if (f == NULL)
	{
		fprintf(stderr, "[LevelRegistry] could not open custom_highscores.bin for writing\n");
		return;
	}
	if (fwrite(&h, sizeof(h), 1, f) != 1 ||
	    (s_customHSCount > 0 && fwrite(s_customHS, sizeof(s_customHS[0]), (size_t)s_customHSCount, f) != (size_t)s_customHSCount))
		fprintf(stderr, "[LevelRegistry] failed to write custom_highscores.bin\n");
	fclose(f);
}

struct HighScoreTrack *LevelRegistry_GetActiveCustomHighScoreTrack(void)
{
	const struct LevelDef *active = s_activeLevel;
	int key, idx;

	if (active == NULL || active->logicalLevelID < LEVEL_REGISTRY_CUSTOM_BASE)
		return NULL;
	key = LevelRegistry_GetGhostKey(active);
	if (key < 0)
		return NULL;

	LevelRegistry_MigrateLegacyHighScores();
	idx = LevelRegistry_FindCustomHS(key);
	if (idx < 0)
	{
		if (s_customHSCount >= LEVEL_REGISTRY_MAX_LEVELS) return NULL;
		idx = s_customHSCount++;
		s_customHS[idx].key = key;
		LevelRegistry_InitCustomHighScoreTrack(&s_customHS[idx].track);
	}
	return &s_customHS[idx].track;
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

/* Lookup by baseLevelID (which is what gGT->levelID holds for an
 * additional custom track). Works even when s_activeLevel is NULL,
 * which is the common case at ghost save/load time (the track select
 * menu has already cleared the active pointer). Without this, the save
 * path falls back to baseLevelID (3) which doesn't match the virtual
 * memcard ID that the load path expects, so the saved ghost shows up
 * as NOT AVAILABLE. */
int LevelRegistry_GetVirtualMemcardIDFromBase(int baseLevelID)
{
	const struct LevelDef *active = s_activeLevel;
	int index;
	int slot;

	if (active != NULL && active->baseLevelID == baseLevelID &&
	    active->logicalLevelID >= LEVEL_REGISTRY_CUSTOM_BASE)
	{
		slot = active->logicalLevelID - LEVEL_REGISTRY_CUSTOM_BASE;
		if (slot >= 0 && slot < LEVEL_REGISTRY_VIRTUAL_MEMCARD_COUNT)
			return LEVEL_REGISTRY_VIRTUAL_MEMCARD_BASE + slot;
	}

	/* Active is NULL here: prefer the last custom level that was raced, if it
	 * matches this base, before falling back to the first match. */
	if (s_lastActiveLevel != NULL && s_lastActiveLevel->baseLevelID == baseLevelID &&
	    s_lastActiveLevel->replaceLevelID < 0 &&
	    s_lastActiveLevel->logicalLevelID >= LEVEL_REGISTRY_CUSTOM_BASE)
	{
		slot = s_lastActiveLevel->logicalLevelID - LEVEL_REGISTRY_CUSTOM_BASE;
		if (slot >= 0 && slot < LEVEL_REGISTRY_VIRTUAL_MEMCARD_COUNT)
			return LEVEL_REGISTRY_VIRTUAL_MEMCARD_BASE + slot;
	}

	LevelRegistry_Load();
	for (index = 0; index < s_levelCount; index++)
	{
		if ((s_levels[index].replaceLevelID < 0) &&
		    (s_levels[index].baseLevelID == baseLevelID) &&
		    (s_levels[index].logicalLevelID >= LEVEL_REGISTRY_CUSTOM_BASE))
		{
			slot = s_levels[index].logicalLevelID - LEVEL_REGISTRY_CUSTOM_BASE;
			if (slot >= 0 && slot < LEVEL_REGISTRY_VIRTUAL_MEMCARD_COUNT)
				return LEVEL_REGISTRY_VIRTUAL_MEMCARD_BASE + slot;
		}
	}

	return -1;
}

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

static char s_musicPathBuf[512];
static char s_musicFinalPathBuf[512];

static const struct LevelDef *LevelRegistry_ResolveForMusic(int levelID)
{
        LevelRegistry_Load();
        if ((s_activeLevel != NULL) && (s_activeLevel->baseLevelID == levelID))
                return s_activeLevel;
        return LevelRegistry_GetReplacement(levelID);
}

const char *LevelRegistry_GetActiveMusicPath(int levelID)
{
        const struct LevelDef *level = LevelRegistry_ResolveForMusic(levelID);

        if (level == NULL || level->music[0] == '\0' || level->assetName[0] == '\0')
                return NULL;

        snprintf(s_musicPathBuf, sizeof(s_musicPathBuf),
                 "assets/%s", level->music);
        return s_musicPathBuf;
}

const char *LevelRegistry_GetActiveMusicFinalPath(int levelID)
{
        const struct LevelDef *level = LevelRegistry_ResolveForMusic(levelID);
        size_t len;

        if (level == NULL || level->music[0] == '\0' || level->assetName[0] == '\0')
                return NULL;

        len = strlen(level->music);
        if (len < 5 || strcmp(level->music + len - 4, ".ogg") != 0)
                return NULL;

        snprintf(s_musicFinalPathBuf, sizeof(s_musicFinalPathBuf),
                 "assets/%.*s_final.ogg",
                 (int)(len - 4), level->music);
        return s_musicFinalPathBuf;
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
	char type[16] = "";
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
		else if (strcmp(key, "type") == 0)
		{
			if (!LevelJson_ReadString(&json, type, sizeof(type)))
			{
				fprintf(stderr, "[LevelRegistry] Parse fail: bad 'type' value\n");
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

	// isBattle: explicit via "type", or inferred from the retail arena ID range.
	{
		int inferredBattle = (level->baseLevelID >= NITRO_COURT &&
		                      level->baseLevelID <= LAB_BASEMENT);

		if (strcmp(type, "battle") == 0)
			level->isBattle = 1;
		else if (strcmp(type, "track") == 0)
			level->isBattle = 0;
		else
			level->isBattle = inferredBattle;

		if (level->isBattle &&
		    (level->baseLevelID < NITRO_COURT || level->baseLevelID > LAB_BASEMENT))
		{
			fprintf(stderr, "[LevelRegistry] Parse fail: battle arena base must be one of the 7 retail arenas (got %d)\n",
			        level->baseLevelID);
			return 0;
		}
	}

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

	fprintf(stderr, "[LevelRegistry] MANIFEST OK: id='%s' name='%s' replace=%d base=%d isBattle=%d\n",
		level->id, level->name, level->replaceLevelID, level->baseLevelID, level->isBattle);
	return 1;
}

/* Phase 2 + 3: read the LEV once, validate the header, compute per-track
 * memory needs and store them in LevelDef. Returns 1 if the LEV is
 * structurally valid and measured, 0 if it must be rejected.
 *
 * This is not Rld_CheckLev: it catches the gross cases (truncated file,
 * ptrmap outside the body, absurd quad count, pointer past EOF) so a
 * corrupt custom can't crash the load. Deeper validation (spawn table,
 * checkpoints, restart points) is a follow-up. */
static u32 LevelRegistry_ToFileOffset(u32 val, u32 bodyBase)
{
	if (val == 0)
		return 0xFFFFFFFFu;
	if (val >= 0x80000000u)
		return bodyBase + (val & 0x7FFFFFFFu);
	return bodyBase + val;
}

static int LevelRegistry_ValidateAndMeasure(struct LevelDef *level)
{
	char path[LEVEL_REGISTRY_PATH_LENGTH];
	struct NativeAssetsByteBuffer lev;
	const u8 *buf;
	u32 bodySize, ptrMapOffset, ptrMapBytes, ptrMapEntries, ptrMapStart;
	u32 meshInfoOff, meshInfoPtr, numQuadBlock, qbArrayOff, qbArrayPtr;
	u32 i;
	int len;

	if (level == NULL)
		return 0;

	len = snprintf(path, sizeof(path), "%s/1p/data.lev", level->assetName);
	if ((len <= 0) || ((size_t)len >= sizeof(path)))
		return 0;

	if (!NativeAssets_ReadBytes(path, NATIVE_ASSET_READ_DATA_FILE, &lev))
	{
		fprintf(stderr, "[LevelRegistry] VALIDATE FAIL '%s': cannot read %s\n",
			level->id, path);
		return 0;
	}

	buf = lev.data;
	bodySize = (u32)lev.size - 4u;

	if (lev.size < 4 + 0x1F4 + 4)
	{
		fprintf(stderr, "[LevelRegistry] VALIDATE FAIL '%s': file too small (%d bytes)\n",
			level->id, lev.size);
		goto fail;
	}

	ptrMapOffset = *(const u32 *)(const void *)buf;
	if (ptrMapOffset >= bodySize)
	{
		fprintf(stderr, "[LevelRegistry] VALIDATE FAIL '%s': ptrMapOffset=%u >= bodySize=%u\n",
			level->id, ptrMapOffset, bodySize);
		goto fail;
	}

	ptrMapBytes = *(const u32 *)(const void *)(buf + 4 + ptrMapOffset);
	if ((ptrMapBytes == 0) || ((ptrMapBytes & 3u) != 0))
	{
		fprintf(stderr, "[LevelRegistry] VALIDATE FAIL '%s': ptrMapBytes=%u not multiple of 4\n",
			level->id, ptrMapBytes);
		goto fail;
	}

	ptrMapEntries = ptrMapBytes >> 2;
	ptrMapStart = 4 + ptrMapOffset + 4;
	if (ptrMapStart + ptrMapBytes > (u32)lev.size)
	{
		fprintf(stderr, "[LevelRegistry] VALIDATE FAIL '%s': ptrMap truncated\n",
			level->id);
		goto fail;
	}

	for (i = 0; i < ptrMapEntries; i++)
	{
		u32 off = *(const u32 *)(const void *)(buf + ptrMapStart + i * 4);
		if (off >= ptrMapOffset)
		{
			fprintf(stderr, "[LevelRegistry] VALIDATE FAIL '%s': ptrMap[%u]=%u out of body\n",
				level->id, i, off);
			goto fail;
		}
	}

	/* ptr_mesh_info at body offset 0x0. Raw file -> offset, patched -> PS1 ptr. */
	meshInfoPtr = *(const u32 *)(const void *)(buf + 4 + 0x0);
	meshInfoOff = LevelRegistry_ToFileOffset(meshInfoPtr, 4);
	if ((meshInfoOff == 0xFFFFFFFFu) || (meshInfoOff + 0x20 > (u32)lev.size))
	{
		fprintf(stderr, "[LevelRegistry] VALIDATE FAIL '%s': ptr_mesh_info=%08x out of file\n",
			level->id, meshInfoPtr);
		goto fail;
	}

	numQuadBlock = *(const u32 *)(const void *)(buf + meshInfoOff + 0x0);
	qbArrayPtr   = *(const u32 *)(const void *)(buf + meshInfoOff + 0xC);
	qbArrayOff   = LevelRegistry_ToFileOffset(qbArrayPtr, 4);

	if ((numQuadBlock == 0) || (numQuadBlock > 0x10000u))
	{
		fprintf(stderr, "[LevelRegistry] VALIDATE FAIL '%s': numQuadBlock=%u out of [1, 0x10000]\n",
			level->id, numQuadBlock);
		goto fail;
	}
	if ((qbArrayOff == 0xFFFFFFFFu) || (qbArrayOff + numQuadBlock * 0x5C > (u32)lev.size))
	{
		fprintf(stderr, "[LevelRegistry] VALIDATE FAIL '%s': ptrQuadBlockArray=%08x past EOF\n",
			level->id, qbArrayPtr);
		goto fail;
	}

	/* Reload-style sky budget: read Skybox.numFaces[8], sort
	 * descending, sum the 4 largest, multiply by sizeof(POLY_G3)=28.
	 * That is exactly how many bytes the 4 drawn segments need. */
	level->skyPrimBytes = 0;
	{
		u32 skyPtr = *(const u32 *)(const void *)(buf + 4 + 0x4);
		u32 skyOff = LevelRegistry_ToFileOffset(skyPtr, 4);
		if ((skyOff != 0xFFFFFFFFu) && (skyOff + 0x18 <= (u32)lev.size))
		{
			u32 nf[8]; u32 top[4]; int i, j;
			for (i = 0; i < 8; i++)
				nf[i] = *(const u16 *)(const void *)(buf + skyOff + 0x08 + (u32)i * 2u);
			for (i = 0; i < 4; i++) top[i] = 0;
			for (i = 0; i < 8; i++)
			{
				for (j = 3; j >= 0; j--)
				{
					if (nf[i] > top[j])
					{
						int k;
						for (k = 0; k < j; k++) top[k] = top[k + 1];
						top[j] = nf[i];
						break;
					}
				}
			}
			level->skyPrimBytes = (int)((top[0] + top[1] + top[2] + top[3]) * 28u);
			fprintf(stderr, "[LevelRegistry] SKY '%s': faces=%u,%u,%u,%u,%u,%u,%u,%u top4=%u,%u,%u,%u bytes=%d\n",
				level->id, nf[0], nf[1], nf[2], nf[3], nf[4], nf[5], nf[6], nf[7],
				top[0], top[1], top[2], top[3], level->skyPrimBytes);
		}
	}

	/* Phase 3: measure. Approximations from rldpack build on Matsuri:
	 *   draw 1,474,512 / 7089 quads = ~208 B/quad
	 *   sky    382,592 / 7089 quads = ~54  B/quad (track specific)
	 * Use 288 B/quad which covers draw + sky with ~10% slack. Honor the
	 * manifest prim_mem if it already asks for more. */
	level->needPrimBytes = (int)numQuadBlock * 288;
	if (level->primMemSize > level->needPrimBytes)
		level->needPrimBytes = level->primMemSize;

	/* Clip buffer: same 60 words per quad as MainDB_GetClipSize. */
	level->needClipBytes = (int)numQuadBlock * 60 * 4;

	/* Rough total: 2 primMem + 2 OT + 2 swapchain + clip + LEV + rough
	 * VRM + MPK block + slack. Used only for the 'will it fit?' log. */
	level->needTotalBytes =
		level->needPrimBytes * 2 +
		(int)lev.size * 2 +
		level->needClipBytes +
		0x60000;

	fprintf(stderr,
		"[LevelRegistry] MEASURED '%s': quads=%u needPrim=%d needClip=%d needTotal=%d\n",
		level->id, numQuadBlock, level->needPrimBytes,
		level->needClipBytes, level->needTotalBytes);

	NativeAssets_FreeBytes(&lev);
	return 1;

fail:
	NativeAssets_FreeBytes(&lev);
	return 0;
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
		/* Phase 2+3: validate the LEV and measure memory. Reject on failure
		 * using the same path as a duplicate (free manifest, continue). */
		if (!LevelRegistry_ValidateAndMeasure(&level))
		{
			fprintf(stderr, "[LevelRegistry] Rejecting '%s' (validation failed)\n",
				level.id);
			NativeAssets_FreeBytes(&manifest);
			return SDL_ENUM_CONTINUE;
		}

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
		// by ID lookup. Battle arenas get a SEPARATE range (2000+) so
		// they don't consume the 16 high score / ghost slots reserved
		// for track additions (1000-1015).
		if (level.replaceLevelID < 0)
		{
			int additionalCount = 0;
			int battleCount = 0;
			int addIndex;
			for (addIndex = 0; addIndex < s_levelCount; addIndex++)
			{
				if (s_levels[addIndex].replaceLevelID < 0)
				{
					if (s_levels[addIndex].isBattle)
						battleCount++;
					else
						additionalCount++;
				}
			}
			if (level.isBattle)
				level.logicalLevelID = LEVEL_REGISTRY_CUSTOM_BATTLE_BASE + battleCount;
			else
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

	/* Custom level high scores: load the sidecar once per process. */
	LevelRegistry_LoadCustomHighScores();

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
	s_ghostKeysBuilt = 0;
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
		if ((s_levels[index].replaceLevelID < 0) && !s_levels[index].isBattle)
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
		if ((s_levels[index].replaceLevelID < 0) && !s_levels[index].isBattle &&
		    (requestedIndex-- == 0))
			return &s_levels[index];
	}
	return NULL;
}

int LevelRegistry_GetAdditionalBattleCount(void)
{
	int index;
	int count = 0;
	LevelRegistry_Load();
	for (index = 0; index < s_levelCount; index++)
	{
		if ((s_levels[index].replaceLevelID < 0) && s_levels[index].isBattle)
			count++;
	}
	return count;
}

const struct LevelDef *LevelRegistry_GetAdditionalBattle(int requestedIndex)
{
	int index;
	LevelRegistry_Load();
	for (index = 0; index < s_levelCount; index++)
	{
		if ((s_levels[index].replaceLevelID < 0) && s_levels[index].isBattle &&
		    (requestedIndex-- == 0))
			return &s_levels[index];
	}
	return NULL;
}

void LevelRegistry_SetActive(const struct LevelDef *level)
{
	s_activeLevel = level;
	if (level != NULL)
		s_lastActiveLevel = level;
}

const struct LevelDef *LevelRegistry_GetActive(void)
{
	return s_activeLevel;
}

/* === Stable ghost keys === */
static unsigned LevelRegistry_HashId(const char *s)
{
	unsigned h = 2166136261u;
	while (*s) { h ^= (unsigned char)*s++; h *= 16777619u; }
	return h;
}

static void LevelRegistry_BuildGhostKeys(void)
{
	int i, j;
	LevelRegistry_Load();
	for (i = 0; i < s_levelCount; i++)
	{
		const struct LevelDef *d = &s_levels[i];
		int key, clash;
		s_ghostKeys[i] = -1;
		if (d->replaceLevelID >= 0 || d->isBattle || d->id[0] == '\0')
			continue;
		key = (int)(LevelRegistry_HashId(d->id) & 0x3FFF);
		do {
			clash = 0;
			for (j = 0; j < i; j++)
				if (s_ghostKeys[j] == (LEVEL_REGISTRY_GHOST_KEY_BASE | key)) { clash = 1; break; }
			if (clash) key = (key + 1) & 0x3FFF;
		} while (clash);
		s_ghostKeys[i] = LEVEL_REGISTRY_GHOST_KEY_BASE | key;
	}
	s_ghostKeysBuilt = 1;
}

int LevelRegistry_IsGhostKey(int v) { return v >= 0x4000 && v <= 0x7FFF; }

int LevelRegistry_GetGhostKey(const struct LevelDef *def)
{
	if (def == NULL) return -1;
	if (!s_ghostKeysBuilt) LevelRegistry_BuildGhostKeys();
	if (def < s_levels || def >= s_levels + s_levelCount) return -1;
	return s_ghostKeys[def - s_levels];
}

const struct LevelDef *LevelRegistry_GetByGhostKey(int key)
{
	int i;
	if (!LevelRegistry_IsGhostKey(key)) return NULL;
	if (!s_ghostKeysBuilt) LevelRegistry_BuildGhostKeys();
	for (i = 0; i < s_levelCount; i++)
		if (s_ghostKeys[i] == key) return &s_levels[i];
	return NULL;
}

int LevelRegistry_GhostIDFromLogical(int logicalID)
{
	int key = LevelRegistry_GetGhostKey(LevelRegistry_GetAdditionalByLogicalID(logicalID));
	return key >= 0 ? key : logicalID;
}

void LevelRegistry_SetGhostContext(const struct LevelDef *def) { s_ghostContext = def; }

int LevelRegistry_ResolveGhostLevelID(int retailID)
{
	if (s_ghostContext != NULL && s_ghostContext->baseLevelID == retailID)
	{
		int key = LevelRegistry_GetGhostKey(s_ghostContext);
		if (key >= 0) return key;
	}
	return retailID;
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
	// wrong, revert and implement multi-LOD (Phase 3) instead.
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
int LevelRegistry_GetAdditionalBattleCount(void) { return 0; }
const struct LevelDef *LevelRegistry_GetAdditionalBattle(int index) { (void)index; return 0; }
void LevelRegistry_SetActive(const struct LevelDef *level) { (void)level; }
const struct LevelDef *LevelRegistry_GetActive(void) { return 0; }
const int *LevelRegistry_GetRacers(int levelID, int *count) { (void)levelID; if (count != 0) *count = 0; return 0; }
int LevelRegistry_GetPrimMemSize(int levelID) { (void)levelID; return 0; }
int LevelRegistry_ShouldForceHiLod(void) { return 0; }
const char *LevelRegistry_GetMusic(int levelID) { (void)levelID; return 0; }
const char *LevelRegistry_GetActiveMusicPath(int levelID) { (void)levelID; return 0; }
const char *LevelRegistry_GetActiveMusicFinalPath(int levelID) { (void)levelID; return 0; }
char *LevelRegistry_GetName(int levelID, char *retailName) { (void)levelID; return retailName; }
const char *LevelRegistry_GetOverrideForBigfileEntry(int levelID, int levelLOD, int subfileIndex)
{
	(void)levelID; (void)levelLOD; (void)subfileIndex; return 0;
}

struct HighScoreTrack *LevelRegistry_GetActiveCustomHighScoreTrack(void) { return 0; }
int LevelRegistry_GetVirtualMemcardIDFromActive(void) { return -1; }
int LevelRegistry_GetVirtualMemcardIDFromBase(int baseLevelID) { (void)baseLevelID; return -1; }
int LevelRegistry_MapLogicalToVirtual(int logicalID) { return logicalID; }
int LevelRegistry_IsGhostKey(int v) { (void)v; return 0; }
int LevelRegistry_GetGhostKey(const struct LevelDef *def) { (void)def; return -1; }
const struct LevelDef *LevelRegistry_GetByGhostKey(int key) { (void)key; return 0; }
int LevelRegistry_GhostIDFromLogical(int logicalID) { return logicalID; }
void LevelRegistry_SetGhostContext(const struct LevelDef *def) { (void)def; }
int LevelRegistry_ResolveGhostLevelID(int retailID) { return retailID; }

#endif