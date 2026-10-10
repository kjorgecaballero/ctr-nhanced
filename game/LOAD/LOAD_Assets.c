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
	/* BOT-RANDOMIZATION: shuffle the 4 bots locally so the global set
	 * table (data.characterIDs_2P_AIs) stays pristine across races.
	 * Restricted to retail IDs so every bot has valid AI data. */
	if (NativeSettings_GetBotRandomizer() != 0)
	{
		int pool[16];
		int poolSize = 0;
		for (int c = 0; c < 16; c++)
		{
			if (c != p1 && c != p2) pool[poolSize++] = c;
		}
		for (int k = 0; k < 4; k++)
		{
			int j = rand() % poolSize;
			data.characterIDs[2 + k] = pool[j];
			pool[j] = pool[--poolSize];
		}
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
	/* Fase 2: keep the original ID at [0] (may be 16+), but the AI slots
	 * must use slots 0..15 so they can index into BI_RACERMODELHI and
	 * MetaDataCharacters without going out of bounds. */
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

#ifdef CTR_NATIVE
	/* BOT-RANDOMIZATION: draw 7 bot IDs from the full retail pool (0..15)
	 * excluding the player's own mpkID, without replacement. Only runs
	 * when the cheat is enabled. */
	if (NativeSettings_GetBotRandomizer() != 0)
	{
		int pool[16];
		int poolSize = 0;
		for (int c = 0; c < 16; c++)
		{
			if (c != mpkID) pool[poolSize++] = c;
		}
		for (int i = 1; i < LOAD_CHARACTER_ID_COUNT; i++)
		{
			int j = rand() % poolSize;
			data.characterIDs[i] = pool[j];
			pool[j] = pool[--poolSize];
		}
	}
#endif
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
	/* Seed the PRNG per race so bot randomization varies between races. */
	if (NativeSettings_GetBotRandomizer() != 0)
		srand((unsigned int)Platform_GetVBlankCount());
#endif

	// 3P/4P
	if ((u32)(levelLOD - LOAD_LEVEL_LOD_3P) < LOAD_LEVEL_LOD_3P4P_COUNT)
	{
		// NOTE: The 3P/4P LOW LOD path in this port has a distance-based
		// deformation bug that affects both custom and original models.
		// Custom racers load normally here; the deformation is a separate
		// engine issue, not caused by the custom .ctr files.
		int playerCount = gGT->numPlyrCurrGame;
		if (playerCount < 3) playerCount = 3;
		if (playerCount > 4) playerCount = 4;

		/* BUG-MENU-04 (4P OOB): driverModelExtras[] has only
		 * LOAD_DRIVER_MODEL_EXTRA_COUNT (=3) slots. Writing to index 3
		 * aliases podiumModel_firstPlace and corrupts it, which later
		 * crashes the menu on exit. Keep the loop inside the array and
		 * stash the 4th player's custom model in our BSS side table. */
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
				// high lod CTR model
				LOAD_AppendQueue(bigfile, LT_GETADDR, BI_RACERMODELHI + data.characterIDs[i], &data.driverModelExtras[i].fileBase, LOAD_DriverMPK_SetPointer);
			}
		}

		/* 4th player (index >= LOAD_DRIVER_MODEL_EXTRA_COUNT): no slot in
		 * driverModelExtras. If custom, keep the loaded buffer in our BSS
		 * table with the file-header offset already applied. */
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

		        /* Bots HI LOD (CUSTOM-LEVELS-BOTS-LOD). Load BI_RACERMODELHI for
         * each bot slot (index >= numPlyrCurrGame). Custom bots are skipped
         * (already loaded via NativeCustomRacer_LoadModel). The arcade MPK
         * still loads below for game logic. */
        /* Bot HI LOD load disabled: in 3P/4P the bot characterIDs are not
         * assigned yet when LOAD_DriverMPK runs, so we would queue Crash for
         * every slot. Needs a different hook (after char assignment). */

        // The 4P arcade MPK always loads; bots and game logic depend on its data.
        lastFileIndexMPK = BI_4PARCADEPACK + GET_MPK_ID(data.characterIDs[3]);
	}

	else if (levelLOD == LOAD_LEVEL_LOD_1P)
	{
		if ((gameMode1 & (TIME_TRIAL | MAIN_MENU)) == TIME_TRIAL)
		{
			goto LoadHighAndPack;
		}

		if (
		    // adv/cutscene mpk when we just need text from MPK
		    ((gameMode1 & (GAME_CUTSCENE | ADVENTURE_ARENA)) != 0) ||

		    // credits
		    ((gGT->gameMode2 & CREDITS) != 0) ||

		    // adventure character select
		    (gGT->levelID == ADVENTURE_GARAGE))
		{
			lastFileIndexMPK = BI_ADVENTUREPACK + GET_MPK_ID(data.characterIDs[0]);
			goto QueueLastPack;
		}

		if ((gameMode1 & ADVENTURE_BOSS) != 0)
		{
			goto LoadHighAndPack;
		}

		if (
		    // If you are in Adventure cup
		    ((gameMode1 & (ADVENTURE_CUP)) != 0) &&

		    // purple gem cup
		    (gGT->cup.cupID == 4))
		{
			// high lod model
			if (NativeCustomRacer_HasSlot(data.characterIDs[0]))
			{
				void *customModel = NativeCustomRacer_LoadModel(0, data.characterIDs[0]);
				data.driverModelExtras[0].fileBase = customModel;
			}
			else
			{
				LOAD_AppendQueue(bigfile, LT_GETADDR, BI_RACERMODELHI + data.characterIDs[0], &data.driverModelExtras[0].fileBase, LOAD_DriverMPK_SetPointer);
			}

			// pack of four AIs with bosses
			LOAD_AppendQueue(bigfile, LT_GETADDR, BI_2PARCADEPACK + LOAD_PURPLE_GEM_CUP_AI_SET_INDEX, NULL, callback);

			data.characterIDs[1] = RIPPER_ROO;
			data.characterIDs[2] = PAPU_PAPU;
			data.characterIDs[3] = KOMODO_JOE;
			data.characterIDs[4] = PINSTRIPE;

			return sdata->ptrMPK;
		}

		if ((gameMode1 & (TIME_TRIAL | MAIN_MENU)) != MAIN_MENU)
		{
			LOAD_Robots1P(data.characterIDs[0]);

#ifdef CTR_NATIVE
			/* BOT-RANDOMIZATION: load HI model per shuffled bot ID, but
			 * only if there's room in the fixed-size load queue. Reserve
			 * 2 slots for the player HI + arcade pack below; the pack's
			 * callback is what ends the loading stage, so if it drops,
			 * the game hangs on the checkered screen. Bots that don't
			 * fit fall back to the arcade pack name lookup in VehBirth. */
			if (NativeSettings_GetBotRandomizer() != 0)
			{
				int room = LOAD_QUEUE_SLOT_COUNT - (int)sdata->queueLength - 2;
				for (i = 1; i < LOAD_CHARACTER_ID_COUNT && room > 0; i++, room--)
				{
					int cid = data.characterIDs[i];
					if (cid >= 0 && cid < 16)
					{
						void **rawSlot = NativeCustomRacer_GetBotModelRawSlot(i);
						if (rawSlot != NULL)
						{
							LOAD_AppendQueue(bigfile, LT_GETADDR,
							    BI_RACERMODELHI + cid,
							    rawSlot, LOAD_DriverMPK_SetPointer);
						}
					}
				}
			}
#endif
		}

		// arcade 1P. Replace the player's model with the custom one, but keep
		// loading the original MPK: the bots depend on its internal data.
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
		// Do NOT switch the order to optimize Relic,
		// if HI+IDs[1] and PACK+IDs[0] is loaded,
		// then mask-grab breaks for all characters
		// on Hot Air Skyway (except Crash Bandicoot)

		// Load Player 1 [0]. Replace the model if it has a custom racer.
		if (NativeCustomRacer_HasSlot(data.characterIDs[0]))
		{
			void *customModel = NativeCustomRacer_LoadModel(0, data.characterIDs[0]);
			data.driverModelExtras[0].fileBase = customModel;
		}
		else
		{
			LOAD_AppendQueue(bigfile, LT_GETADDR, BI_RACERMODELHI + data.characterIDs[0], &data.driverModelExtras[0].fileBase, LOAD_DriverMPK_SetPointer);
		}

		// Load boss or ghost [1]. Always load the ghost MPK: the game relies
		// on its data during the race.
		lastFileIndexMPK = BI_TIMETRIALPACK + GET_MPK_ID(data.characterIDs[1]);
	}

	// else if (levelLOD == LOAD_LEVEL_LOD_2P)
	else
	{
		// HI models for P1/P2 humans (matches 1P/3P/4P; also pinned at
		// stage 6 via maxDistanceLOD so they stay HI at any distance).
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

		/* Bots HI LOD for 2P. Inline of LOAD_Robots2P so we can queue the
		 * bot HI models BEFORE the arcade-pack callback fires. The callback
		 * is attached to the last item queued; if bot HI came after it,
		 * stage 6 would run FinalizeBotModels before they loaded and we
		 * would fall back to the arcade MED pack. */
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
				/* BOT-RANDOMIZATION: draw 4 bots from the 16-retail pool,
				 * excluding P1 and P2's mpkIDs. Same pattern as 1P. */
				if (NativeSettings_GetBotRandomizer() != 0)
				{
					int pool[16];
					int poolSize = 0;
					for (int c = 0; c < 16; c++)
					{
						if (c != p1 && c != p2) pool[poolSize++] = c;
					}
					for (int k = 0; k < 4; k++)
					{
						int j = rand() % poolSize;
						data.characterIDs[2 + k] = pool[j];
						pool[j] = pool[--poolSize];
					}
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

// param_1 - Pointer to "cd position of bigfile"
// param_2 - language index - 0 ja, 1 en, 2 en2, 3 fr, 4 de, 5 it, 6 es, 7 ne
void LOAD_LangFile(int bigfilePtr, int lang)
{
	struct LngFile *lngFile;
	u32 size;

	int i;
	int numStrings;
	char **strArray;


	if (sdata->lngFile == 0)
	{
		sdata->lngFile = MEMPACK_AllocMem(sdata->langBufferSize /* "lang buffer" */);
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