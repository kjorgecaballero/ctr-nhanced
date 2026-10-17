#include <common.h>
#include "platform/native_debug.h"

static int s_dbgGhostReplay = -1;
static int ReplayDbg(void) { return NativeDbg_Enabled(&s_dbgGhostReplay, "CTR_DBG_GHOST"); }

#include <platform/native_custom_racer.h>
#include <LevelRegistry.h>

/* BUG-GHOST-01
 *
 * Time Trial ghost with a custom racer is invisible.
 *
 * GhostReplay_Init1/Init2 used to resolve the ghost model via
 *   VehBirth_GetModelByName(GET_METADATA(charID)->name_Debug)
 * For custom IDs (>= 16) this fails for two reasons:
 *   1) The folder slug ("nash") may not match the .ctr internal name.
 *   2) The ghost's custom model was never loaded into
 *      driverModelExtras[1] either. In that case, at that point
 *      data.characterIDs[1] is still 0 (the ghost's real character ID
 *      is written later).
 *
 * Fix: for custom IDs, load model_p1.ctr directly (its UVs are baked
 * for VRAM slot 1, matching the texture upload that LOAD_TenStages
 * already performs for the ghost), upload the matching textures once,
 * and cache the result per (ghostSlot, charID). Originals keep the
 * name-based lookup.
 *
 * Same pattern as VehBirth_NonGhost: custom IDs use their loaded model
 * directly, never the name lookup. */
#ifndef LOAD_MODEL_FILE_HEADER_BYTES
#define LOAD_MODEL_FILE_HEADER_BYTES 4
#endif

/* NativePointerIsReadable — true if [p, p+size) is mapped and readable.
 * Used to reject garbage pointers coming out of ptrSpawnType1 tables
 * whose layout differs between the arcade and relic LODs (e.g. Turbo
 * Track in Time Trial returns 0x2D002A00 from pointers[ST1_NTROPY]). */
#if defined(_WIN32)
#include <windows.h>
static int NativePointerIsReadable(const void *p, size_t size)
{
	MEMORY_BASIC_INFORMATION mbi;
	uintptr_t start, end, regionEnd;

	if (p == NULL || size == 0) return 0;
	if (VirtualQuery(p, &mbi, sizeof(mbi)) == 0) return 0;
	if (mbi.State != MEM_COMMIT) return 0;
	if (mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)) return 0;

	start = (uintptr_t)p;
	end = start + size;
	regionEnd = (uintptr_t)mbi.BaseAddress + mbi.RegionSize;
	if (end > regionEnd) return 0;

	return 1;
}
#else
static int NativePointerIsReadable(const void *p, size_t size)
{
	(void)p; (void)size;
	return 1; /* non-Windows: don't reject */
}
#endif

static struct Model *s_ghostCustomModel [2] = { NULL, NULL };
static s32           s_ghostCustomCharID[2] = { -1,   -1 };
static int s_dbgF = 0;

/* Invalidate the custom ghost cache. Same problem as the menu
 * cache: points to the mempack and PopToState leaves it dangling. */
void GhostReplay_ResetCache(void)
{
    s_ghostCustomModel[0]  = NULL;
    s_ghostCustomModel[1]  = NULL;
    s_ghostCustomCharID[0] = -1;
    s_ghostCustomCharID[1] = -1;
}
/* Custom level check based on levelLOD: in Time Trial, retail forces
 * LOAD_LEVEL_LOD_RELIC, and only custom levels fall to LOD_1P. This is
 * the same info LOAD_IsCustomLevel uses internally, but read from the
 * already-computed sdata->levelLOD instead of re-querying the registry. */
static int Ghost_IsCustomLevel(struct GameTracker *gGT)
{
	return gGT->levelID != MAIN_MENU_LEVEL &&
	       sdata->levelLOD == LOAD_LEVEL_LOD_1P;
}

static struct Model *GhostReplay_ResolveModel(s32 charID, s32 ghostSlot)
{
	/* Only IDs in the valid custom range use the custom model path.
	 * Anything below NATIVE_CUSTOM_ID_BASE falls to the retail name
	 * lookup, and anything above the max is invalid (probably a
	 * truncated charID that spilled into the levelID bits). */
	if (charID >= NATIVE_CUSTOM_ID_BASE &&
	    charID < NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT)
	{
		if (s_ghostCustomModel[ghostSlot] == NULL ||
		    s_ghostCustomCharID[ghostSlot] != charID)
		{
			void *buf = NativeCustomRacer_LoadModel(1, charID);
			if (buf != NULL)
			{
				s_ghostCustomModel[ghostSlot]  =
				    (struct Model *)((u8 *)buf + LOAD_MODEL_FILE_HEADER_BYTES);
				s_ghostCustomCharID[ghostSlot] = charID;
				NativeCustomRacer_ApplySlot(1, charID);
			}
		}
		return s_ghostCustomModel[ghostSlot];
	}

	return VehBirth_GetModelByName(GET_METADATA(charID)->name_Debug);
}

/* Wrapper around BOTS_Driver_Convert + BOTS_ThTick_Drive.
 * On custom levels without nav paths (CTR Editor exports may omit them),
 * BOTS_Driver_Convert returns early without setting botData.botNavFrame,
 * and BOTS_ThTick_Drive crashes on NULL navFrameCurr. In that case we
 * skip the drive tick, hide the ghost instance, and finish the ghost. */
static void Ghost_ConvertToBotAndDrive(struct Thread *t, struct Driver *d)
{
	BOTS_Driver_Convert(d);

	if (d->botData.botNavFrame == NULL)
	{
		/* No nav path (custom level without nav data). Leave the ghost
		 * parked at its last position. Do NOT kill the thread — killing
		 * it mid-race leaves downstream state inconsistent (ghost tape
		 * selection hangs). The next frame will hit this same path and
		 * return cleanly. */
		return;
	}

	BOTS_ThTick_Drive(t);
}

internal s16 Ghost_LerpRot12(s16 curr, s16 next, u16 t)
{
	s32 delta = ((s32)next - (s32)curr) & 0xFFF;
	if (delta > 0x7FF)
	{
		delta -= 0x1000;
	}
	return (curr + ((delta * t) >> 0xC)) & 0xFFF;
}

void GhostReplay_ThTick(struct Thread *t)
{
	struct GameTracker *gGT = sdata->gGT;

	/* Total defense: in custom levels, any of these can become
	 * stale after MEMPACK_PopToState. We verify with
	 * VirtualQuery before touching anything. */
	if (t == NULL || !NativePointerIsReadable(t, sizeof(struct Thread)))
	{
		return;
	}

	struct Driver *d = t->object;
	if (d == NULL || !NativePointerIsReadable(d, sizeof(struct Driver)))
	{
		return;
	}

	struct Instance *inst = d->instSelf;
	if (inst == NULL || !NativePointerIsReadable(inst, sizeof(struct Instance)))
	{
		return;
	}

	struct GhostTape *tape = d->ghostTape;
	if (tape == NULL || !NativePointerIsReadable(tape, sizeof(struct GhostTape)))
	{
		return;
	}

	inst->scale = (SVec3){.x = 0xccc, .y = 0xccc, .z = 0xccc};

	// 6-second timer != 0, and ghost made by human
	if ((sdata->ghostOverflowTextTimer != 0) && (d->ghostID == 0))
	{
		s32 color = 0xFFFF8004;
		if (sdata->ghostOverflowTextTimer & 1)
		{
			color = 0xFFFF8003;
		}

		DecalFont_DrawLine(sdata->lngStrings[LNG_GHOST_DATA_OVERFLOW], 0x100, 0x28, 2, color);
		DecalFont_DrawLine(sdata->lngStrings[LNG_CAN_NOT_SAVE_GHOST_DATA], 0x100, 0x32, 2, color);

		sdata->ghostOverflowTextTimer--;
	}

	if ((sdata->boolGhostsDrawing == 0) || ((gGT->gameMode1 & DEBUG_MENU) != 0) || (tape->ptrEnd == tape->ptrStart) || (d->ghostBoolInit == 0))
	{
		inst->flags |= HIDE_MODEL;
		return;
	}

	d->reserves = (s16)CTR_MipsSubLo((u16)d->reserves, gGT->elapsedTimeMS);
	if (d->reserves < 0)
	{
		d->reserves = 0;
	}

	if ((gGT->trafficLightsTimer < 1) && (d->ghostBoolStarted == 0))
	{
		d->ghostBoolStarted = 1;
		tape->packetID = -1;
	}

	inst->alphaScale = 0xa00;

	inst->flags &= ~(HIDE_MODEL | DRAW_TRANSPARENT);
	inst->flags |= GHOST_DRAW_TRANSPARENT;

	s32 timeInRace = tape->timeElapsedInRace >= 0 ? tape->timeElapsedInRace : 0;

	struct GhostPacket *packet = &tape->packets[0];

	// flush and rewrite cached GhostPackets array
	if (tape->timeInPacket32 <= timeInRace)
	{
		s16 opcodePos = 0;
		u8 *packetPtr = tape->ptrCurr;
		u8 *packetEndChain = tape->ptrCurr;
		SVec3 tmpPos = {0};

		tape->packetID = -1;
		tape->timeInPacket01 = tape->timeInPacket32_backup;

		// advance two POSITION opcodes, combining
		// with velocity data to build the packet cache
		while (opcodePos < 2)
		{
			// Reject packetPtr outside the tape's [start, end) range
			// OR pointing to unmapped memory. ptrEnd only catches the
			// "past the end" case; a corrupted ptrCurr can drop below
			// ptrStart and slip through the old single-sided check.
			// See BUG-GHOST-02: TT ghost recorded with a custom racer
			// fell, was saved, and on replay ptrCurr became 0x1F1777.
			if ((void *)packetPtr < (void *)tape->ptrStart ||
			    (void *)packetPtr >= (void *)tape->ptrEnd ||
			    !NativePointerIsReadable(packetPtr, 16))
			{
				struct GhostHeader *gh = tape->gh;

				if (gh != NULL && NativePointerIsReadable(gh, sizeof(struct GhostHeader)))
				{
					d->ySpeed = gh->ySpeed;
					d->actionsFlagSet &= ~ACTION_BOT;
					d->speedApprox = gh->speedApprox;
				}

				Ghost_ConvertToBotAndDrive(t, d);

				d->actionsFlagSet |= ACTION_RACE_FINISHED;
				t->flags |= THREAD_FLAG_DISABLE_COLLISION;
				return;
			}

			// reached end of tape
			if (tape->ptrEnd <= (void *)packetPtr)
			{
				struct GhostHeader *gh = tape->gh;

				if (gh != NULL && NativePointerIsReadable(gh, sizeof(struct GhostHeader)))
				{
					d->ySpeed = gh->ySpeed;
					d->actionsFlagSet &= ~ACTION_BOT;
					d->speedApprox = gh->speedApprox;
				}

				Ghost_ConvertToBotAndDrive(t, d);

				d->actionsFlagSet |= ACTION_RACE_FINISHED;
				t->flags |= THREAD_FLAG_DISABLE_COLLISION;
				return;
			}

			u8 opcode = packetPtr[0];
			if (GHOST_IS_OPCODE(opcode))
			{
				switch (opcode)
				{
				case GHOST_OP_POSITION:
					for (s32 i = 0; i < 3; ++i)
					{
						u16 rawValue = Ghost_ReadBE16(&packetPtr[1 + i * 2]);
						CTR_VECTOR_DATA(&(tmpPos))[i] = (s16)(((s32)((u32)rawValue << 0x10)) >> 0xd);
					}
					packet->pos = tmpPos;

					packet->rot.x = 0;
					packet->rot.y = (u16)packetPtr[9] << 4;
					packet->rot.z = (u16)packetPtr[10] << 4;

					if (opcodePos == 1)
					{
						s32 bigEndianTime = Ghost_ReadBE16(&packetPtr[7]);
						tape->ptrCurr = packetPtr;

						tape->timeInPacket32_backup += bigEndianTime;
						tape->timeInPacket32 += bigEndianTime;
					}

					opcodePos++;

					packet->bufferPacket = packetEndChain;
					packetPtr += GHOST_SIZE_POSITION;
					packetEndChain = packetPtr;

					packet++;

					break;

				case GHOST_OP_ANIMATION:
					packetPtr += GHOST_SIZE_ANIMATION;
					break;

				case GHOST_OP_BOOST:
					packetPtr += GHOST_SIZE_BOOST;
					break;

				case GHOST_OP_INSTANCE:
					packetPtr += GHOST_SIZE_INSTANCE;
					break;

				case GHOST_OP_IDLE:
					packet->pos = tmpPos;
					packet[0].rot = packet[-1].rot;

					packet->bufferPacket = packetEndChain;
					packetPtr += GHOST_SIZE_IDLE;
					packetEndChain = packetPtr;

					packet++;
					break;
				}
			}

			// velocity data (no opcode byte)
			else
			{
				for (s32 i = 0; i < 3; ++i)
				{
					CTR_VECTOR_DATA(&(tmpPos))[i] += (s16)((s8)packetPtr[i]) * 8;
				}
				packet->pos = tmpPos;

				packet->rot.x = 0;
				packet->rot.y = packetPtr[3] << 4;
				packet->rot.z = packetPtr[4] << 4;

				packet->bufferPacket = packetEndChain;
				packetPtr += GHOST_SIZE_VELOCITY;
				packetEndChain = packetPtr;

				packet++;
			}
		}

		tape->numPacketsInArray = ((u32)packet - (u32)&tape->packets[0]) >> 4;

		tape->numPacketsInArray -= 1;

		if (tape->numPacketsInArray < 0)
		{
			tape->numPacketsInArray = 1;
		}

		tape->timeBetweenPackets = tape->timeInPacket32 - tape->timeInPacket01;
		if (tape->timeBetweenPackets == 0)
		{
			tape->timeBetweenPackets = 1;
		}
	}

	s32 scaledNum = (timeInRace - tape->timeInPacket01) * tape->numPacketsInArray * 0x1000;

	// 0% = 0, 100% = 0x1000
	s32 scaledPacketIdx = scaledNum / tape->timeBetweenPackets;
	s32 packetIdx = scaledPacketIdx >> 0xc;
	u16 lerp4096 = (u16)(scaledPacketIdx & 0xfff);

	if (tape->numPacketsInArray <= packetIdx)
	{
		packetIdx = tape->numPacketsInArray - 1;
		lerp4096 = 0;
	}

	// Ptrs to current and next packets for better readability
	struct GhostPacket *currPacket = &tape->packets[packetIdx];
	struct GhostPacket *nextPacket = &tape->packets[packetIdx + 1];

	s32 vel[3];
	vel[0] = (s32)nextPacket->pos.x - (s32)currPacket->pos.x;
	vel[1] = (s32)nextPacket->pos.y - (s32)currPacket->pos.y;
	vel[2] = (s32)nextPacket->pos.z - (s32)currPacket->pos.z;

	inst->matrix.t[0] = currPacket->pos.x + ((vel[0] * lerp4096) >> 0xC);
	inst->matrix.t[1] = currPacket->pos.y + ((vel[1] * lerp4096) >> 0xC);
	inst->matrix.t[2] = currPacket->pos.z + ((vel[2] * lerp4096) >> 0xC);

	SVec3 local_rot = {
	    .x = Ghost_LerpRot12(currPacket->rot.x, nextPacket->rot.x, lerp4096),
	    .y = Ghost_LerpRot12(currPacket->rot.y, nextPacket->rot.y, lerp4096),
	    .z = Ghost_LerpRot12(currPacket->rot.z, nextPacket->rot.z, lerp4096),
	};

	ConvertRotToMatrix(&inst->matrix, &local_rot);

	d->posCurr.x = inst->matrix.t[0] << 8;
	d->posCurr.y = inst->matrix.t[1] << 8;
	d->posCurr.z = inst->matrix.t[2] << 8;

	d->rotCurr.x = local_rot.x;
	d->rotCurr.y = local_rot.y;
	d->rotCurr.z = local_rot.z;

	u8 *buffer = tape->packets[packetIdx].bufferPacket;

	while (tape->packetID < packetIdx)
	{
		if (tape->ptrEnd <= (void *)buffer)
		{
			break;
		}

		u8 opcode = buffer[0];

		if (!GHOST_IS_OPCODE(opcode))
		{
			buffer += GHOST_SIZE_VELOCITY;
			tape->packetID++;
		}

		else
		{
			switch (opcode)
			{
			case GHOST_OP_POSITION:
				buffer += GHOST_SIZE_POSITION;
				tape->packetID++;
				break;

			case GHOST_OP_ANIMATION:
			{
				s32 numAnimFrames = INSTANCE_GetNumAnimFrames(inst, buffer[1]);
				inst->animIndex = (numAnimFrames < 1) ? 0 : buffer[1];

				s32 maxFrame = INSTANCE_GetNumAnimFrames(inst, inst->animIndex) - 1;
				if (buffer[2] != 0)
				{
					if (buffer[2] < maxFrame)
					{
						inst->animFrame = buffer[2];
					}
					else
					{
						inst->animFrame = maxFrame;
					}
				}
				else if (maxFrame > 0)
				{
					inst->animFrame = 0;
				}
				else
				{
					inst->animFrame = maxFrame;
				}

				buffer += GHOST_SIZE_ANIMATION;
			}
			break;

			case GHOST_OP_BOOST:
				if (gGT->trafficLightsTimer < 1 && ((gGT->gameMode1 & START_OF_RACE) == 0) && !RaceFlag_IsFullyOnScreen())
				{
					VehFire_Increment(d, Ghost_ReadBE16(&buffer[1]), buffer[3], Ghost_ReadBE16(&buffer[4]));
				}
				buffer += GHOST_SIZE_BOOST;
				break;

			case GHOST_OP_INSTANCE:
				inst->flags &= ~SPLIT_LINE;
				if (buffer[1] != 0)
				{
					inst->flags |= SPLIT_LINE;
				}
				buffer += GHOST_SIZE_INSTANCE;
				break;

			case GHOST_OP_IDLE:
				buffer += GHOST_SIZE_IDLE;
				tape->packetID++;
				break;
			}
		}
	}

	if (gGT->trafficLightsTimer < 1)
	{
		tape->timeElapsedInRace += gGT->elapsedTimeMS;
	}

	if (ReplayDbg() && d->ghostID == 0 && s_dbgF < 120)
	{
		fprintf(stderr, "[GDBG-E] f=%d tl=%d ms=%d tir=%d t01=%d t32=%d pid=%d n=%d t=(%d,%d,%d)\n",
			s_dbgF, (int)gGT->trafficLightsTimer, (int)gGT->elapsedTimeMS,
			(int)tape->timeElapsedInRace, (int)tape->timeInPacket01, (int)tape->timeInPacket32,
			(int)tape->packetID, (int)tape->numPacketsInArray,
			(int)inst->matrix.t[0], (int)inst->matrix.t[1], (int)inst->matrix.t[2]);
		s_dbgF++;
	}
}


void GhostReplay_Init1(void)
{
	struct GameTracker *gGT = sdata->gGT;

	sdata->boolCanSaveGhost = 0;
	sdata->boolGhostsDrawing = 0;

	// only continue if you're in time trial, not main menu, and not cutscene
	if ((gGT->gameMode1 & GAME_MODE_TIME_TRIAL_GAMEPLAY_MASK) != TIME_TRIAL)
	{
		return;
	}

	struct GhostHeader *gh = MEMPACK_AllocMem(0x3e00);
	char *recordBuffer = GHOSTHEADER_GETRECORDBUFFER(gh);
	sdata->GhostRecording.ptrGhost = gh;
	sdata->GhostRecording.ptrStartOffset = &recordBuffer[0];
	if (ReplayDbg())
		fprintf(stderr, "[GDBG-G] Init1 gh=%p end=%p size=0x3e00\n", (void*)gh, (void*)((u8*)gh + 0x3e00));
	sdata->GhostRecording.ptrEndOffset = &recordBuffer[0x3DD4];
if (ReplayDbg())
	fprintf(stderr, "[GDBG-T] Init1 gh=%p start=%p cur=%p end=%p start-gh=%d\n",
        (void*)sdata->GhostRecording.ptrGhost,
        (void*)sdata->GhostRecording.ptrStartOffset,
        (void*)sdata->GhostRecording.ptrCurrOffset,
        (void*)sdata->GhostRecording.ptrEndOffset,
        (int)((char*)sdata->GhostRecording.ptrStartOffset - (char*)sdata->GhostRecording.ptrGhost));


	// ALWAYS initialize ghost threads, even if gh == 0,
	// or else the "Ghost Too Big" text will never play.
	// 0: human ghost, 1: N Tropy / Oxide ghost
	for (s32 i = 0; i < 2; i++)
	{
		struct GhostTape *tape = MEMPACK_AllocMem(0x268);
		memset(tape, 0, 0x268);
		sdata->ptrGhostTape[i] = tape;

		/* Ensure tape fields are clean before any path assigns them.
		 * If the slot 1 branch is skipped (custom N.Tropy guard) or
		 * the readable check fails, these stay zero and Init2 skips
		 * the tape (ptrEnd == ptrStart). Without this, fields from the
		 * memset may be inconsistent with the actual assignment path. */
		tape->gh = NULL;
		tape->gh_again = NULL;
		tape->ptrStart = NULL;
		tape->ptrEnd = NULL;

		if (i == 0)
		{
			gh = sdata->ptrGhostTapePlaying;
		}
		else
		{
			if (Ghost_IsCustomLevel(gGT))
			{
				fprintf(stderr, "[GHOST] Init1 guard: lod=%d active=%p repl=%p\n",
				        (int)sdata->levelLOD, (void*)LevelRegistry_GetActive(),
				        (void*)LevelRegistry_GetReplacement(gGT->levelID));
				continue;
			}

			s32 timeTrialFlags = sdata->gameProgress.highScoreTracks[gGT->levelID].timeTrialFlags;
			void **pointers = ST1_GETPOINTERS(gGT->level1->ptrSpawnType1);

			gh = ((timeTrialFlags & TT_NTROPY_BEATEN) != 0) ? pointers[ST1_NOXIDE] : pointers[ST1_NTROPY];
		}

		// CTR_NATIVE: custom tracks exported by CTR Editor may not include
		// ST1_NTROPY / ST1_NOXIDE spawn entries, and retail Turbo Track in
		// Time Trial loads LOAD_LEVEL_LOD_RELIC whose ST1 table is shorter
		// than the arcade one. In both cases pointers[ST1_NTROPY] can
		// return garbage that is not NULL (observed 0x2D002A00). Reject
		// anything that isn't a readable mapped region. The tape was
		// memset to 0, so GhostReplay_Init2 / ThTick will skip it
		// (ptrEnd == ptrStart).
		/* Custom levels ship no N. Tropy / Oxide ghost: ST1_NTROPY and
		 * ST1_NOXIDE read past the end of the LEV's ST1 table. The value
		 * can be a readable host address (e.g. 0x1F1468), so
		 * NativePointerIsReadable cannot reject it. */
		if (!NativePointerIsReadable(gh, sizeof(struct GhostHeader)))
		{
			continue;
		}

		recordBuffer = GHOSTHEADER_GETRECORDBUFFER(gh);

		tape->gh = gh;
		tape->gh_again = gh;
		tape->ptrStart = &recordBuffer[0];
		tape->constDEADC0ED = 0xDEADC0ED;
		tape->ptrEnd = &recordBuffer[gh->size];

		if (i == 1)
		{
			gGT->timeToBeatInTimeTrial_ForCurrentEvent = gh->timeElapsedInRace;
		}
	}

	for (s32 i = 0; i < 2; i++)
	{
		struct Thread *t = PROC_BirthWithObject(SIZE_RELATIVE_POOL_BUCKET(4, NONE, LARGE, GHOST), GhostReplay_ThTick, sdata->s_ghost, 0);

		t->modelIndex = DYNAMIC_GHOST;
		t->flags |= THREAD_FLAG_DISABLE_COLLISION;

		struct Driver *ghostDriver = t->object;
		memset(ghostDriver, 0, 0x638);
		ghostDriver->ghostID = i;
		ghostDriver->driverID = i + 1;
		ghostDriver->ghostBoolInit = 0;
		ghostDriver->ghostTape = sdata->ptrGhostTape[i];

			s32 charID = data.characterIDs[i + 1];
			if (charID < 0 || charID >= NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT)
			{
				fprintf(stderr, "[SANITY] Init1 thread i=%d charID=%d invalid, forcing 0\n", (int)i, charID);
				charID = 0;
				data.characterIDs[i + 1] = 0;
			}
			struct Model *model = GhostReplay_ResolveModel(charID, i);

		/* A ghost recorded with a custom racer that has since been
		 * removed from the roster (or a corrupted charID) makes
		 * ResolveModel return NULL. Skip the ghost slot instead of
		 * crashing on model->name below. */
		if (model == NULL)
		{
			/* Kill the thread completely: no tick, no bucket, no
			 * instance. GhostReplay_Init2 will skip it because
			 * instSelf is NULL and we'll never render it. */
			t->funcThTick = NULL;
			t->flags |= THREAD_FLAG_DEAD;
			continue;
		}

		struct Instance *inst = INSTANCE_Birth3D(model, model->name, t);
		t->inst = inst;

		struct Model *wake = gGT->modelPtr[STATIC_WAKE];
		if (wake)
		{
			struct Instance *wakeInst = INSTANCE_Birth3D(wake, wake->name, 0);
			ghostDriver->wakeInst = wakeInst;

			if (wakeInst != 0)
			{
				wakeInst->flags |= HIDE_MODEL | ANIM_LOOP;
			}
		}

		inst->depthBiasSecondary = 0xc;
		inst->flags |= OWNER_PUSHBUFFER_GATE;
		ghostDriver->instSelf = inst;
		VehBirth_TireSprites(t);
		VehBirth_SetConsts(ghostDriver);

		ghostDriver->actionsFlagSet |= ACTION_BOT; // AI driver
		ghostDriver->wheelSprites = ICONGROUP_GETICONS(gGT->iconGroup[0xc]);

		// NOTE(aalhendi): GhostReplay_Init2 owns retail activation/tick.
	}
}


void GhostReplay_Init2(void)
{
	struct GameTracker *gGT = sdata->gGT;

	for (struct Thread *thread = gGT->threadBuckets[GHOST].thread; thread != NULL; thread = thread->siblingThread)
	{
		struct Driver *driver = thread->object;
		if (driver == NULL)
		{
			continue;
		}

		if (driver->instSelf == NULL)
		{
			continue;
		}

		struct GhostTape *tape = driver->ghostTape;
		if (tape->ptrEnd == tape->ptrStart)
		{
			continue;
		}

		// Reject tapes whose [start, end) range isn't fully readable.
		// A truncated or corrupted ghost file can produce ptrEnd far
		// past the real allocation (gh->size wrong) or a wildly invalid
		// ptrStart. Skip the ghost entirely instead of crashing inside
		// GhostReplay_ThTick.
		{
			size_t tapeBytes = (size_t)((u8 *)tape->ptrEnd - (u8 *)tape->ptrStart);
			if (tapeBytes == 0 || tapeBytes > 0x4000 ||
			    !NativePointerIsReadable(tape->ptrStart, tapeBytes))
			{
				continue;
			}
		}

		s32 ghostID = driver->ghostID;
		if (ghostID == 0)
		{
			if (sdata->boolReplayHumanGhost == 0)
			{
				continue;
			}
		}
		else
		{
			if (ghostID != 1)
			{
				continue;
			}

			if (Ghost_IsCustomLevel(gGT))
			{
				fprintf(stderr, "[GHOST] Init2 guard: lod=%d active=%p repl=%p\n",
				        (int)sdata->levelLOD, (void*)LevelRegistry_GetActive(),
				        (void*)LevelRegistry_GetReplacement(gGT->levelID));
				continue;
			}

			s32 timeTrialFlags = sdata->gameProgress.highScoreTracks[gGT->levelID].timeTrialFlags;
			if ((timeTrialFlags & TT_NTROPY_OPEN) == 0)
			{
				continue;
			}
		}

		if (driver->instSelf == NULL)
		{
			continue;
		}

		if (ghostID == 0 && ReplayDbg())
		{
			u8 *rb = (u8 *)tape->ptrStart;
			fprintf(stderr, "[GDBG-D] tape=%p gh=%p ptrStart=%p size=%d ptrPlaying=%p rb=%02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X\n",
				(void*)tape, (void*)tape->gh, (void*)tape->ptrStart,
				(int)((u8*)tape->ptrEnd - (u8*)tape->ptrStart),
				(void*)sdata->ptrGhostTapePlaying,
				rb[0], rb[1], rb[2], rb[3], rb[4], rb[5], rb[6], rb[7],
				rb[8], rb[9], rb[10], rb[11], rb[12], rb[13], rb[14], rb[15]);
		}

		tape->timeElapsedInRace = 0;
		s_dbgF = 0;
		tape->timeInPacket32_backup = 0;
		tape->unk20 = 0;
		tape->timeInPacket32 = 0;
		tape->timeInPacket01 = 0;
		tape->ptrCurr = tape->ptrStart;

		sdata->boolGhostsDrawing = 1;
		driver->ghostBoolInit = 1;
		driver->ghostBoolStarted = 0;

		s32 characterIndex = ghostID + 1;
		if (ghostID != 0)
		{
			s32 timeTrialFlags = sdata->gameProgress.highScoreTracks[gGT->levelID].timeTrialFlags;
			if ((timeTrialFlags & TT_NTROPY_BEATEN) != 0)
			{
				characterIndex = ghostID + 2;
			}
		}

		s32 characterID = data.characterIDs[characterIndex];
		struct Model *model = GhostReplay_ResolveModel(characterID, ghostID);

		/* Same NULL guard as Init1: a ghost whose custom racer is no
		 * longer in the roster must not crash the replay. */
		if (model == NULL)
		{
			continue;
		}

		{
			int customWheels = NativeCustomRacer_HasWheels(characterID);
			if (customWheels >= 0)
				driver->wheelSize = customWheels ? 0xccc : 0;
			else
				driver->wheelSize = (characterID != NITROS_OXIDE) ? 0xccc : 0;
		}
		struct Instance *inst = driver->instSelf;
		char *name = (ghostID != 0) ? sdata->s_ghost1 : sdata->s_ghost0;

		INSTANCE_Birth(inst, model, name, inst->thread, 7);
		if (ghostID == 0 && ReplayDbg())
		{
			fprintf(stderr, "[GDBG-I] size=%d char=%d start=%p len=%d first32=",
				(int)tape->gh->size, (int)tape->gh->characterID,
				(void *)tape->ptrStart,
				(int)((char *)tape->ptrEnd - (char *)tape->ptrStart));
			for (int i = 0; i < 32; i++)
			{
				fprintf(stderr, "%02X ", ((unsigned char *)tape->ptrStart)[i]);
			}
			fprintf(stderr, "\n");
		}
		GhostReplay_ThTick(thread);

		// NOTE(aalhendi): written in retail. never read?
		tape->unk2 = tape->unk1;
		tape->unk4 = tape->unk3;
		tape->unk20 = 0;
	}
}
