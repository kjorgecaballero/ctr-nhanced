#include <common.h>
#include <platform/native_custom_racer.h>
#include "native_settings.h"
#include <stdlib.h>

#if defined(CTR_NATIVE) && defined(CTR_INTERNAL)
#include <platform/native_checkpoint.h>
#endif

void LOAD_RunPtrMap(char *origin, int *patchArr, int numPtrs)
{
	int *ptrCurrOffset = patchArr;

	for (ptrCurrOffset = &patchArr[0]; ptrCurrOffset < &patchArr[numPtrs]; ptrCurrOffset++)
	{
		int offset = (*ptrCurrOffset >> 2) << 2;
		*(int *)&origin[offset] = *(int *)&origin[offset] + (int)origin;
#if defined(CTR_NATIVE) && defined(CTR_INTERNAL)
		NativeCheckpoint_RegisterPointerSlot(&origin[offset]);
#endif
	}
}

#ifdef CTR_NATIVE
static void LOAD_PickBots(int firstSlot, int count, int numHumans, int allowCustom,
                          u32 packMask, int hiBudget)
{
	int pool[16 + NATIVE_CUSTOM_COUNT];
	int poolSize = 0;

	for (int c = 0; c < 16; c++)
	{
		int taken = 0;
		for (int h = 0; h < numHumans; h++)
			if (GET_MPK_ID(data.characterIDs[h]) == c) taken = 1;
		if (!taken) pool[poolSize++] = c;
	}

	if (allowCustom)
	{
		int tmp[NATIVE_CUSTOM_COUNT];
		int n = NativeCustomRacer_GetCustomPool(tmp, NATIVE_CUSTOM_COUNT);
		for (int k = 0; k < n; k++)
		{
			int taken = 0;
			for (int h = 0; h < numHumans; h++)
				if (data.characterIDs[h] == tmp[k]) taken = 1;
			if (!taken) pool[poolSize++] = tmp[k];
		}
	}

	for (int k = 0; k < count; k++)
	{
		int slot = firstSlot + k;
		int chosen = -1;

		while (poolSize > 0 && chosen < 0)
		{
			int j = rand() % poolSize;
			int id = pool[j];
			pool[j] = pool[--poolSize];

			if (id < NATIVE_CUSTOM_ID_BASE)
			{
				if (!((packMask >> id) & 1))
				{
					if (hiBudget <= 0) continue;
					hiBudget--;
				}
				chosen = id;
			}
			else if (NativeCustomRacer_LoadBotModel(slot, id))
				chosen = id;
		}

		if (chosen >= 0)
			data.characterIDs[slot] = chosen;
	}
}
#endif

void LOAD_Robots2P(struct BigHeader *bigfile, int p1, int p2, void (*callback)(struct LoadQueueSlot *))
{
	int setIndex;
	u8 *robotSet;
	b32 boolFoundRepeat = false;

	for (setIndex = 0; setIndex < LOAD_2P_AI_SET_COUNT; setIndex++)
	{
		robotSet = data.characterIDs_2P_AIs[setIndex];

		boolFoundRepeat = false;
		for (int racerIndex = 0; racerIndex < LOAD_2P_AI_SET_RACER_COUNT; racerIndex++)
		{
			if ((robotSet[racerIndex] == p1) || (robotSet[racerIndex] == p2))
			{
				boolFoundRepeat = true;
				break;
			}
		}

		if (!boolFoundRepeat)
		{
			break;
		}
	}

	if (setIndex >= LOAD_2P_AI_SET_COUNT)
	{
		return;
	}

#ifdef CTR_NATIVE
	if (NativeSettings_GetBotRandomizer() != 0)
	{
		LOAD_PickBots(2, 4, 2, 0, 0u, 4);
	}
	else
#endif
	{
		data.characterIDs[2] = robotSet[0];
		data.characterIDs[3] = robotSet[1];
		data.characterIDs[4] = robotSet[2];
		data.characterIDs[5] = robotSet[3];
	}

	LOAD_AppendQueue(bigfile, LT_GETADDR, BI_2PARCADEPACK + setIndex, NULL, callback);
}

void LOAD_Robots1P(int characterID)
{
	int mpkID = GET_MPK_ID(characterID);
	int newCharacterID = 0;

	data.characterIDs[0] = characterID;

	for (int i = 1; i < LOAD_CHARACTER_ID_COUNT; i++, newCharacterID++)
	{
		if (newCharacterID == mpkID)
		{
			newCharacterID++;
		}

		data.characterIDs[i] = newCharacterID;
	}
}

static void (*const LOAD_DriverMPK_SetPointer)(struct LoadQueueSlot *) = LOAD_QUEUE_CALLBACK_SET_POINTER;

int LOAD_DriverMPK(struct BigHeader *bigfile, int levelLOD, void (*callback)(struct LoadQueueSlot *))
{
	int i;
	int gameMode1;

	struct GameTracker *gGT = sdata->gGT;
	gameMode1 = gGT->gameMode1;

	int lastFileIndexMPK;

#ifdef CTR_NATIVE
	NativeCustomRacer_ResetBotSlots(gGT->numPlyrCurrGame);

	if (NativeSettings_GetBotRandomizer() != 0)
		srand((unsigned int)Platform_GetVBlankCount());
#endif

	// 3P/4P
	if ((u32)(levelLOD - LOAD_LEVEL_LOD_3P) < LOAD_LEVEL_LOD_3P4P_COUNT)
	{
		int playerCount = gGT->numPlyrCurrGame;
		if (playerCount < 3) playerCount = 3;
		if (playerCount > 4) playerCount = 4;

		int driverExtraCount = playerCount;
		if (driverExtraCount > LOAD_DRIVER_MODEL_EXTRA_COUNT)
			driverExtraCount = LOAD_DRIVER_MODEL_EXTRA_COUNT;

		for (i = 0; i < driverExtraCount; i++)
		{
			if (NativeCustomRacer_HasSlot(data.characterIDs[i]))
			{
				void *customModel = NativeCustomRacer_LoadModel(i, data.characterIDs[i]);
				data.driverModelExtras[i].fileBase = customModel;
			}
			else
			{
				LOAD_AppendQueue(bigfile, LT_GETADDR, BI_RACERMODELHI + data.characterIDs[i], &data.driverModelExtras[i].fileBase, LOAD_DriverMPK_SetPointer);
			}
		}

		for (i = LOAD_DRIVER_MODEL_EXTRA_COUNT; i < playerCount; i++)
		{
			if (NativeCustomRacer_HasSlot(data.characterIDs[i]))
			{
				unsigned char *buf = (unsigned char *)NativeCustomRacer_LoadModel(i, data.characterIDs[i]);
				if (buf != NULL)
					buf += LOAD_MODEL_FILE_HEADER_BYTES;
				NativeCustomRacer_SetPlayerModelPtr(i, buf);
			}
			else
			{
				void **rawSlot = NativeCustomRacer_GetP4RetailHiLodSlot();
				LOAD_AppendQueue(bigfile, LT_GETADDR, BI_RACERMODELHI + data.characterIDs[i], rawSlot, LOAD_DriverMPK_SetPointer);
			}
		}

		lastFileIndexMPK = BI_4PARCADEPACK + GET_MPK_ID(data.characterIDs[3]);
	}

	else if (levelLOD == LOAD_LEVEL_LOD_1P)
	{
		if ((gameMode1 & (TIME_TRIAL | MAIN_MENU)) == TIME_TRIAL)
		{
			goto LoadHighAndPack;
		}

		if (
		    ((gameMode1 & (GAME_CUTSCENE | ADVENTURE_ARENA)) != 0) ||
		    ((gGT->gameMode2 & CREDITS) != 0) ||
		    (gGT->levelID == ADVENTURE_GARAGE))
		{
			lastFileIndexMPK = BI_ADVENTUREPACK + GET_MPK_ID(data.characterIDs[0]);
			goto QueueLastPack;
		}

		if ((gameMode1 & ADVENTURE_BOSS) != 0)
		{
			goto LoadHighAndPack;
		}

		if (((gameMode1 & (ADVENTURE_CUP)) != 0) && (gGT->cup.cupID == 4))
		{
			if (NativeCustomRacer_HasSlot(data.characterIDs[0]))
			{
				void *customModel = NativeCustomRacer_LoadModel(0, data.characterIDs[0]);
				data.driverModelExtras[0].fileBase = customModel;
			}
			else
			{
				LOAD_AppendQueue(bigfile, LT_GETADDR, BI_RACERMODELHI + data.characterIDs[0], &data.driverModelExtras[0].fileBase, LOAD_DriverMPK_SetPointer);
			}

			LOAD_AppendQueue(bigfile, LT_GETADDR, BI_2PARCADEPACK + LOAD_PURPLE_GEM_CUP_AI_SET_INDEX, NULL, callback);

			data.characterIDs[1] = RIPPER_ROO;
			data.characterIDs[2] = PAPU_PAPU;
			data.characterIDs[3] = KOMODO_JOE;
			data.characterIDs[4] = PINSTRIPE;

			return sdata->ptrMPK;
		}

		if ((gameMode1 & (TIME_TRIAL | MAIN_MENU)) != MAIN_MENU)
		{
#ifdef CTR_NATIVE
			LOAD_Robots1P(data.characterIDs[0]);

			if (NativeSettings_GetBotRandomizer() != 0)
			{
				u32 packMask = 0;
				for (i = 1; i < LOAD_CHARACTER_ID_COUNT; i++)
					packMask |= 1u << data.characterIDs[i];

				int reserve = NativeCustomRacer_HasSlot(data.characterIDs[0]) ? 1 : 2;
				int hiBudget = LOAD_QUEUE_SLOT_COUNT - (int)sdata->queueLength - reserve;
				if (hiBudget < 0) hiBudget = 0;

				LOAD_PickBots(1, LOAD_CHARACTER_ID_COUNT - 1, 1,
				              NativeSettings_GetBotRandomizer() == 2,
				              packMask, hiBudget);

				for (i = 1; i < LOAD_CHARACTER_ID_COUNT; i++)
				{
					int cid = data.characterIDs[i];
					if (cid >= 0 && cid < 16 && !((packMask >> cid) & 1))
					{
						void **rawSlot = NativeCustomRacer_GetBotModelRawSlot(i);
						if (rawSlot != NULL)
							LOAD_AppendQueue(bigfile, LT_GETADDR,
							    BI_RACERMODELHI + cid,
							    rawSlot, LOAD_DriverMPK_SetPointer);
					}
				}
			}
#else
			LOAD_Robots1P(data.characterIDs[0]);
#endif
		}

		if (NativeCustomRacer_HasSlot(data.characterIDs[0]))
		{
			void *customModel = NativeCustomRacer_LoadModel(0, data.characterIDs[0]);
			data.driverModelExtras[0].fileBase = customModel;
		}
		else
		{
			LOAD_AppendQueue(bigfile, LT_GETADDR, BI_RACERMODELHI + data.characterIDs[0], &data.driverModelExtras[0].fileBase, LOAD_DriverMPK_SetPointer);
		}

		lastFileIndexMPK = BI_1PARCADEPACK + GET_MPK_ID(data.characterIDs[0]);
	}

	else if ((levelLOD == LOAD_LEVEL_LOD_RELIC) || ((gameMode1 & TIME_TRIAL) != 0))
	{
	LoadHighAndPack:
		if (NativeCustomRacer_HasSlot(data.characterIDs[0]))
		{
			void *customModel = NativeCustomRacer_LoadModel(0, data.characterIDs[0]);
			data.driverModelExtras[0].fileBase = customModel;
		}
		else
		{
			LOAD_AppendQueue(bigfile, LT_GETADDR, BI_RACERMODELHI + data.characterIDs[0], &data.driverModelExtras[0].fileBase, LOAD_DriverMPK_SetPointer);
		}

		lastFileIndexMPK = BI_TIMETRIALPACK + GET_MPK_ID(data.characterIDs[1]);
	}

	else
	{
		for (i = 0; i < LOAD_MED_LOD_DRIVER_MODEL_EXTRA_COUNT; i++)
		{
			if (NativeCustomRacer_HasSlot(data.characterIDs[i]))
			{
				void *customModel = NativeCustomRacer_LoadModel(i, data.characterIDs[i]);
				data.driverModelExtras[i].fileBase = customModel;
			}
			else
			{
				LOAD_AppendQueue(bigfile, LT_GETADDR, BI_RACERMODELHI + data.characterIDs[i], &data.driverModelExtras[i].fileBase, LOAD_DriverMPK_SetPointer);
			}
		}

		{
			int setIndex;
			u8 *robotSet = NULL;
			int p1 = GET_MPK_ID(data.characterIDs[0]);
			int p2 = GET_MPK_ID(data.characterIDs[1]);

			for (setIndex = 0; setIndex < LOAD_2P_AI_SET_COUNT; setIndex++)
			{
				robotSet = data.characterIDs_2P_AIs[setIndex];
				b32 foundRepeat = false;
				for (int ri = 0; ri < LOAD_2P_AI_SET_RACER_COUNT; ri++)
				{
					if ((robotSet[ri] == p1) || (robotSet[ri] == p2))
					{
						foundRepeat = true;
						break;
					}
				}
				if (!foundRepeat) break;
			}

			if (setIndex < LOAD_2P_AI_SET_COUNT)
			{
#ifdef CTR_NATIVE
				if (NativeSettings_GetBotRandomizer() != 0)
				{
					LOAD_PickBots(2, 4, 2,
					              NativeSettings_GetBotRandomizer() == 2,
					              0u, 4);
				}
				else
#endif
				{
					data.characterIDs[2] = robotSet[0];
					data.characterIDs[3] = robotSet[1];
					data.characterIDs[4] = robotSet[2];
					data.characterIDs[5] = robotSet[3];
				}

				for (i = 2; i < 6; i++)
				{
					if (data.characterIDs[i] < NATIVE_CUSTOM_ID_BASE)
					{
						void **rawSlot = NativeCustomRacer_GetBotModelRawSlot(i);
						if (rawSlot != NULL)
							LOAD_AppendQueue(bigfile, LT_GETADDR, BI_RACERMODELHI + data.characterIDs[i], rawSlot, LOAD_DriverMPK_SetPointer);
					}
				}

				LOAD_AppendQueue(bigfile, LT_GETADDR, BI_2PARCADEPACK + setIndex, NULL, callback);
			}
		}

		return sdata->ptrMPK;
	}

QueueLastPack:
	LOAD_AppendQueue(bigfile, LT_GETADDR, lastFileIndexMPK, NULL, callback);
	return sdata->ptrMPK;
}

struct LngFile
{
	int numStrings;
	int offsetToPtrArr;
	char strings[1];
};

void LOAD_LangFile(int bigfilePtr, int lang)
{
	struct LngFile *lngFile;
	u32 size;

	int i;
	int numStrings;
	char **strArray;

	if (sdata->lngFile == 0)
	{
		sdata->lngFile = MEMPACK_AllocMem(sdata->langBufferSize);
	}

	lngFile = sdata->lngFile;

	lngFile = LOAD_ReadFile_ex((struct BigHeader *)bigfilePtr, LT_SETADDR, BI_LANGUAGEFILE + lang, lngFile, &size, NULL);
	if (lngFile == NULL)
	{
		return;
	}

	numStrings = lngFile->numStrings;
	strArray = (char **)((u32)lngFile + lngFile->offsetToPtrArr);

	sdata->numLngStrings = numStrings;
	sdata->lngStrings = strArray;

	for (i = 0; i < numStrings; i++)
	{
		strArray[i] = (char *)((u32)strArray[i] + (u32)lngFile);
	}
}

int LOAD_GetBigfileIndex(u32 levelID, int lod, int fileIndexInGroup)
{
	if (levelID < NITRO_COURT)
	{
		return BI_ARCADETRACKS + levelID * LOAD_TRACK_FILES_PER_LOD_GROUP + sdata->levBigLodIndex[lod - 1] + fileIndexInGroup;
	}

	if ((u32)(levelID - NITRO_COURT) < LOAD_BATTLE_TRACK_COUNT)
	{
		return BI_BATTLETRACKS + (levelID - NITRO_COURT) * LOAD_TRACK_FILES_PER_LOD_GROUP + sdata->levBigLodIndex[lod - 1] + fileIndexInGroup;
	}

	if ((u32)(levelID - INTRO_RACE_TODAY) < LOAD_INTRO_CUTSCENE_COUNT)
	{
		return BI_CUTSCENES_INTRO + (levelID - INTRO_RACE_TODAY) * LOAD_CUTSCENE_FILES_PER_LEVEL + fileIndexInGroup;
	}

	if ((u32)(levelID - OXIDE_ENDING) < LOAD_OUTRO_CUTSCENE_COUNT)
	{
		return BI_CUTSCENES_OUTRO + (levelID - OXIDE_ENDING) * LOAD_OUTRO_FILES_PER_LEVEL + fileIndexInGroup;
	}

	if (levelID == ADVENTURE_GARAGE)
	{
		return BI_MAINMENUFILE + LOAD_MAIN_MENU_GARAGE_FILE_OFFSET + fileIndexInGroup;
	}

	if (levelID == NAUGHTY_DOG_CRATE)
	{
		return BI_NDBOX + fileIndexInGroup;
	}

	if ((u32)(levelID - CREDITS_CRASH) < LOAD_CREDIT_LEVEL_COUNT)
	{
		return BI_CREDITS + (levelID - CREDITS_CRASH) * LOAD_CUTSCENE_FILES_PER_LEVEL + fileIndexInGroup;
	}

	if (levelID == MAIN_MENU_LEVEL)
	{
		return BI_MAINMENUFILE + fileIndexInGroup;
	}

	if (levelID == SCRAPBOOK)
	{
		return BI_SCRAPBOOK + fileIndexInGroup;
	}

	return BI_ADVENTUREHUB + (levelID - GEM_STONE_VALLEY) * LOAD_CUTSCENE_FILES_PER_LEVEL + fileIndexInGroup;
}