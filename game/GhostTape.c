#include <common.h>
#ifdef CTR_NATIVE
#include <LevelRegistry.h>
#endif

static int s_ghostDbgN = 0;
static int s_ghostDbgStartCount = 0;
static int s_ghostDbgEndCount = 0;
static int s_ghostDbgFrame = 0;
static int s_ghostDbgPaddingWarned = 0;

/* (vacío) */

void GhostTape_Start(void)
{
	fprintf(stderr, "[GDBG-PM] prim start=%p cap=%u cursor=%p ghost=%p\n",
		(void *)sdata->gGT->backBuffer->primMem.start, (unsigned)sdata->gGT->backBuffer->primMem.capacityBytes,
		(void *)sdata->gGT->backBuffer->primMem.cursor, (void *)sdata->GhostRecording.ptrGhost);
	struct GhostHeader *gh;
	struct Driver *d;
	struct GameTracker *gGT = sdata->gGT;

	d = gGT->drivers[0];

	gh = sdata->GhostRecording.ptrGhost;

	/* Limpia el header entero antes de escribir los campos. El campo
	 * emptyPadding[0x14] (bytes 0x14-0x27) nunca se inicializa y
	 * queda con basura del mempack si esa zona no era cero. Esa basura
	 * se serializa a memcard y en algunos casos pisa el inicio del
	 * record buffer, corrompiendo el primer paquete del tape. */
	memset(gh, 0, sizeof(struct GhostHeader));

	gh->version = GHOST_TAPE_VERSION_RETAIL;
	gh->levelID = gGT->levelID;
#ifdef CTR_NATIVE
	{
		// Customs get a virtual memcard ID (25-31) so their ghosts do not
		// share the retail baseLevelID slot in the memcard filename.
		int virtualID = LevelRegistry_GetVirtualMemcardIDFromBase(gGT->levelID);
		if (virtualID >= 0)
			gh->levelID = (u16)virtualID;
	}
#endif
	gh->characterID = data.characterIDs[d->driverID];       


	sdata->GhostRecording.VelX = 0;
	sdata->GhostRecording.VelY = 0;
	sdata->GhostRecording.VelZ = 0;

	sdata->GhostRecording.timeElapsedInRace = 0;
	sdata->boolGhostTooBigToSave = 0;
	sdata->ghostOverflowTextTimer = 0;
	sdata->boolCanSaveGhost = 1;
	s_ghostDbgFrame = 0;
	s_ghostDbgPaddingWarned = 0;

	fprintf(stderr, "[GDBG-S] Start called tl=%d timer=%d cur-start=%d\n",
		(int)gGT->trafficLightsTimer, (int)gGT->timer,
		(int)((char*)sdata->GhostRecording.ptrCurrOffset - (char*)sdata->GhostRecording.ptrStartOffset));
	sdata->GhostRecording.ptrCurrOffset = sdata->GhostRecording.ptrStartOffset;

	/* Zero the record buffer so stale mempack data can't be interpreted
	 * as packets by the replay parser before the first real write. */
	{
		u8 *rb = (u8 *)sdata->GhostRecording.ptrStartOffset;
		u8 *re = (u8 *)sdata->GhostRecording.ptrEndOffset;
		if (re > rb)
			memset(rb, 0, (u32)(re - rb));
	}



	{
		u8 *h14 = (u8 *)gh + 0x14;
		u8 *rb = (u8 *)sdata->GhostRecording.ptrStartOffset;
		fprintf(stderr, "[GDBG-A] gh=%p ptrStart=%p h14=%02X %02X %02X %02X %02X %02X %02X %02X rb=%02X %02X %02X %02X %02X %02X %02X %02X\n",
			(void*)gh, (void*)rb,
			h14[0], h14[1], h14[2], h14[3], h14[4], h14[5], h14[6], h14[7],
			rb[0], rb[1], rb[2], rb[3], rb[4], rb[5], rb[6], rb[7]);
	}

	sdata->GhostRecording.countEightFrames = 0;
	sdata->GhostRecording.countSixteenFrames = 0;
	sdata->GhostRecording.timeOfLast80buffer = 0;
	sdata->GhostRecording.boostCooldown1E = 0;

	sdata->GhostRecording.animFrame = -1;
	sdata->GhostRecording.animIndex = -1;
	sdata->GhostRecording.instanceFlags = 0;

	s_ghostDbgN = 0;
	fprintf(stderr, "[GDBG-T] Start gh=%p start=%p cur=%p end=%p start-gh=%d\n",
        (void*)sdata->GhostRecording.ptrGhost,
        (void*)sdata->GhostRecording.ptrStartOffset,
        (void*)sdata->GhostRecording.ptrCurrOffset,
        (void*)sdata->GhostRecording.ptrEndOffset,
        (int)((char*)sdata->GhostRecording.ptrStartOffset - (char*)sdata->GhostRecording.ptrGhost));

fprintf(stderr, "[GDBG] Start#%d tl=%d canSave=%d Vel=(%d,%d,%d) cur=%p start=%p b0..3=%02X %02X %02X %02X\n",
	    ++s_ghostDbgStartCount, (int)gGT->trafficLightsTimer, (int)sdata->boolCanSaveGhost,
	    (int)sdata->GhostRecording.VelX, (int)sdata->GhostRecording.VelY, (int)sdata->GhostRecording.VelZ,
	    (void*)sdata->GhostRecording.ptrCurrOffset, (void*)sdata->GhostRecording.ptrStartOffset,
	    ((u8*)sdata->GhostRecording.ptrStartOffset)[0], ((u8*)sdata->GhostRecording.ptrStartOffset)[1],
	    ((u8*)sdata->GhostRecording.ptrStartOffset)[2], ((u8*)sdata->GhostRecording.ptrStartOffset)[3]);

	return;
}


void GhostTape_End(void)
{
	struct Driver *d;
	struct GhostHeader *gh;
	struct GameTracker *gGT = sdata->gGT;

	// quit, if ghost cant be saved
	if (sdata->boolCanSaveGhost == 0)
	{
		return;
	}

	// dont save ghost twice
	sdata->boolCanSaveGhost = 0;

	fprintf(stderr, "[GDBG] End#%d off=%d\n", ++s_ghostDbgEndCount,
	    (int)((char*)sdata->GhostRecording.ptrCurrOffset - (char*)sdata->GhostRecording.ptrStartOffset));

	// Write the last chunk of ghost data
	fprintf(stderr, "[GDBG-T] End gh=%p start=%p cur=%p end=%p start-gh=%d\n",
        (void*)sdata->GhostRecording.ptrGhost,
        (void*)sdata->GhostRecording.ptrStartOffset,
        (void*)sdata->GhostRecording.ptrCurrOffset,
        (void*)sdata->GhostRecording.ptrEndOffset,
        (int)((char*)sdata->GhostRecording.ptrStartOffset - (char*)sdata->GhostRecording.ptrGhost));

GhostTape_WriteMoves(1);

	d = gGT->drivers[0];
	gh = sdata->GhostRecording.ptrGhost;

	/* Defensivo: entre GhostTape_Start y GhostTape_End algo pisa los
	 * primeros 8 bytes del buffer (levelID y characterID llegan al End
	 * con basura: 15444/477). Reescribir los campos inmutables para
	 * que la memcard guarde el header correcto. */
	gh->version = GHOST_TAPE_VERSION_RETAIL;
	gh->levelID = gGT->levelID;
	{
		int virtualID = LevelRegistry_GetVirtualMemcardIDFromBase(gGT->levelID);
		if (virtualID >= 0)
			gh->levelID = (u16)virtualID;
	}
	gh->characterID = data.characterIDs[d->driverID];

	gh->ySpeed = d->ySpeed;
	gh->speedApprox = d->speedApprox;
	gh->timeElapsedInRace = d->timeElapsedInRace;
	gh->size = (u32)sdata->GhostRecording.ptrCurrOffset - (u32)sdata->GhostRecording.ptrStartOffset;

	{
		unsigned char *b = (unsigned char *)sdata->GhostRecording.ptrStartOffset;
		fprintf(stderr, "[GDBG] End: size=%d first40:", (int)gh->size);
		for (int i = 0; i < 40; i++) fprintf(stderr, " %02X", b[i]);
		fprintf(stderr, "\n");
	}

	fprintf(stderr, "[GHOST-DBG] End:   ptr=%p charID=%d lvlID=%d size=%d\n",
	        (void *)gh, (int)gh->characterID,
	        (int)gh->levelID, (int)gh->size);

	{
		u8 *h14 = (u8 *)gh + 0x14;
		u8 *rb = (u8 *)sdata->GhostRecording.ptrStartOffset;
		fprintf(stderr, "[GDBG-B] gh=%p ptrStart=%p ptrCurr=%p size=%d h14=%02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X rb=%02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X\n",
			(void*)gh, (void*)rb, (void*)sdata->GhostRecording.ptrCurrOffset, (int)gh->size,
			h14[0], h14[1], h14[2], h14[3], h14[4], h14[5], h14[6], h14[7],
			h14[8], h14[9], h14[10], h14[11], h14[12], h14[13], h14[14], h14[15],
			rb[0], rb[1], rb[2], rb[3], rb[4], rb[5], rb[6], rb[7],
			rb[8], rb[9], rb[10], rb[11], rb[12], rb[13], rb[14], rb[15]);
	}

	fprintf(stderr, "[GHOST-DBG] EndBuf: %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x\n",
	        ((u8 *)sdata->GhostRecording.ptrStartOffset)[0],
	        ((u8 *)sdata->GhostRecording.ptrStartOffset)[1],
	        ((u8 *)sdata->GhostRecording.ptrStartOffset)[2],
	        ((u8 *)sdata->GhostRecording.ptrStartOffset)[3],
	        ((u8 *)sdata->GhostRecording.ptrStartOffset)[4],
	        ((u8 *)sdata->GhostRecording.ptrStartOffset)[5],
	        ((u8 *)sdata->GhostRecording.ptrStartOffset)[6],
	        ((u8 *)sdata->GhostRecording.ptrStartOffset)[7],
	        ((u8 *)sdata->GhostRecording.ptrStartOffset)[8],
	        ((u8 *)sdata->GhostRecording.ptrStartOffset)[9],
	        ((u8 *)sdata->GhostRecording.ptrStartOffset)[10]);
}


void GhostTape_WriteMoves(s16 raceFinished)
{
	struct GameTracker *gGT = sdata->gGT;
	u32 gameMode = gGT->gameMode1;

	if (raceFinished == 0)
	{
		// if you can not save ghost
		if (sdata->boolCanSaveGhost == 0)
		{
			return;
		}

		// if paused or [race ended while not yet in end-of-race menu]???
		if ((gameMode & GAME_MODE_GHOST_RECORD_BLOCK_MASK) != 0)
		{
			return;
		}

		// if traffic lights are not done counting down
		if (0 < gGT->trafficLightsTimer)
		{
			return;
		}

		// If you're in End-Of-Race menu
		if ((gameMode & END_OF_RACE) != 0)
		{
			GhostTape_End();
			return;
		}
	}
	if (sdata->GhostRecording.boostCooldown1E != 0)
	{
		sdata->GhostRecording.boostCooldown1E--;
	}

	{
	static int s_wdFired = 0;
	unsigned char *p = (unsigned char *)sdata->GhostRecording.ptrGhost + 0x14;
	int dirty = 0;
	for (int i = 0; i < 20; i++) dirty |= p[i];
	if (dirty && !s_wdFired)
	{
		s_wdFired = 1;
		fprintf(stderr, "[GDBG-W2] DIRTY timer=%d tl=%d frame=%d cur-start=%d first20=",
			(int)gGT->timer, (int)gGT->trafficLightsTimer, (int)sdata->frameCounter,
			(int)((char *)sdata->GhostRecording.ptrCurrOffset - (char *)sdata->GhostRecording.ptrStartOffset));
		for (int i = 0; i < 20; i++) fprintf(stderr, "%02X ", p[i]);
		fprintf(stderr, "\n");
	}
	if (sdata->GhostRecording.ptrCurrOffset == sdata->GhostRecording.ptrStartOffset) s_wdFired = 0;
}

s_ghostDbgFrame++;
	if (!s_ghostDbgPaddingWarned && sdata->GhostRecording.ptrGhost != NULL)
	{
		u8 *pad = (u8 *)sdata->GhostRecording.ptrGhost + 0x14;
		int sum = 0;
		for (int i = 0; i < 0x14; i++) sum += pad[i];
		if (sum != 0)
		{
			u8 *rb = (u8 *)sdata->GhostRecording.ptrStartOffset;
			fprintf(stderr, "[GDBG-W] padding dirty: frame=%d tl=%d off=%d\n", s_ghostDbgFrame, (int)gGT->trafficLightsTimer, (int)((char*)sdata->GhostRecording.ptrCurrOffset - (char*)sdata->GhostRecording.ptrStartOffset));
			s_ghostDbgPaddingWarned = 1;
		}
	}

	if (

	    // If race is just finished
	    (raceFinished != 0) ||

	    // This is true every 8 frames
	    ((sdata->GhostRecording.countEightFrames & GHOST_RECORD_INTERVAL_MASK_8) == 0))
	{
		struct Driver *driver = gGT->threadBuckets[0].thread->object;

		// player instance
		struct Instance *inst = driver->instSelf;     

		if (s_ghostDbgN < 4)
		{
			fprintf(stderr, "[GDBG] WM#%d tl=%d cur=%p same=%d Vel=(%d,%d,%d) c16=%d off=%d\n",
				s_ghostDbgN, (int)gGT->trafficLightsTimer,
				(void*)sdata->GhostRecording.ptrCurrOffset, (int)(driver == gGT->drivers[0]),
				(int)sdata->GhostRecording.VelX, (int)sdata->GhostRecording.VelY, (int)sdata->GhostRecording.VelZ,
				(int)sdata->GhostRecording.countSixteenFrames,
				(int)((char*)sdata->GhostRecording.ptrCurrOffset - (char*)sdata->GhostRecording.ptrStartOffset));
		}

		// compress position (x, y, z) with bitshifting
		int posX = inst->matrix.t[0] >> GHOST_RECORD_POSITION_SHIFT;
		int posY = inst->matrix.t[1] >> GHOST_RECORD_POSITION_SHIFT;
		int posZ = inst->matrix.t[2] >> GHOST_RECORD_POSITION_SHIFT;

		// get change in position (x, y, z)
		sdata->GhostRecording.VelX = (s16)posX - sdata->GhostRecording.VelX;
		sdata->GhostRecording.VelY = (s16)posY - sdata->GhostRecording.VelY;
		sdata->GhostRecording.VelZ = (s16)posZ - sdata->GhostRecording.VelZ;

		// Time elapsed since last 0x80 buffer
		int timeSincePositionPacket = sdata->GhostRecording.timeElapsedInRace - sdata->GhostRecording.timeOfLast80buffer;

		// get pointer to current recording char in buffer
		char *writeCursor = sdata->GhostRecording.ptrCurrOffset;

		if (
		    // if animation frame changed
		    (sdata->GhostRecording.animFrame != inst->animFrame) ||

		    // if animation changed
		    (sdata->GhostRecording.animIndex != inst->animIndex))
		{
			sdata->GhostRecording.animFrame = inst->animFrame;
			sdata->GhostRecording.animIndex = inst->animIndex;

			writeCursor[0] = GHOST_OP_ANIMATION;
			writeCursor[1] = inst->animIndex;
			writeCursor[2] = inst->animFrame;
			writeCursor += GHOST_SIZE_ANIMATION;
		}

		// If there is a change in instance flags,
		// determine if driver is split by water or mud
		if ((inst->flags & GHOST_RECORD_INSTANCE_SPLIT_FLAG) != (sdata->GhostRecording.instanceFlags & GHOST_RECORD_INSTANCE_SPLIT_FLAG))
		{
			// Record the instance flags
			// determine if driver is split by water or mud

			writeCursor[0] = GHOST_OP_INSTANCE;
			writeCursor[1] = (char)(inst->flags >> GHOST_RECORD_INSTANCE_SPLIT_SHIFT) & 1;
			writeCursor += GHOST_SIZE_INSTANCE;
		}

		// If velocity is small enough for a compressed 5-char message
		if (
		    // If the race is not over
		    (raceFinished == 0) &&

		    // false once every 32 counts, despite the retail field name
		    ((sdata->GhostRecording.countSixteenFrames & GHOST_RECORD_INTERVAL_MASK_32) != 0) &&

		    // If velX is small enough for one char
		    (sdata->GhostRecording.VelX < GHOST_RECORD_VELOCITY_MAX) && (GHOST_RECORD_VELOCITY_MIN_EXCLUSIVE < sdata->GhostRecording.VelX) &&

		    // If velY is small enough for one char
		    (sdata->GhostRecording.VelY < GHOST_RECORD_VELOCITY_MAX) && (GHOST_RECORD_VELOCITY_MIN_EXCLUSIVE < sdata->GhostRecording.VelY) &&

		    // If velZ is small enough for one char
		    (sdata->GhostRecording.VelZ < GHOST_RECORD_VELOCITY_MAX) && (GHOST_RECORD_VELOCITY_MIN_EXCLUSIVE < sdata->GhostRecording.VelZ) &&

		    // if not a lot of time has passed
		    // since the last 0x80 buffer
		    (timeSincePositionPacket < GHOST_RECORD_TIME_DELTA_MAX_EXCLUSIVE))
		{
			// If there is no change in position
			if (((sdata->GhostRecording.VelX == 0) && (sdata->GhostRecording.VelY == 0)) && (sdata->GhostRecording.VelZ == 0))
			{
				// Record that you are doing nothing
				writeCursor[0] = GHOST_OP_IDLE;
				writeCursor += GHOST_SIZE_IDLE;
			}

			// If you are moving
			else
			{
				// dont write opcode,
				// "no opcode" means "assume velocity"

				// Write velX to buffer
				writeCursor[0] = (char)sdata->GhostRecording.VelX;
				writeCursor[1] = (char)sdata->GhostRecording.VelY;
				writeCursor[2] = (char)sdata->GhostRecording.VelZ;
				writeCursor[3] = (char)(driver->rotCurr.y >> GHOST_RECORD_ROTATION_SHIFT);
				writeCursor[4] = (char)(driver->rotCurr.z >> GHOST_RECORD_ROTATION_SHIFT);
				writeCursor += GHOST_SIZE_VELOCITY;
			}
		}

		// If velocity is too large,
		// If the race just ended
		// If you're in a forced full-position interval
		// write a longer message
		else
		{
			// 0x80-style chunks are 11 chars long (including 0x80)

			// Write to ghost recording buffer
			writeCursor[0] = GHOST_OP_POSITION;

			// flipping endians

			// Write 2-char X position
			writeCursor[1] = (char)(posX >> 8);
			writeCursor[2] = (char)posX;

			// Write 2-char Y position
			writeCursor[3] = (char)(posY >> 8);
			writeCursor[4] = (char)posY;

			// Write 2-char Z position
			writeCursor[5] = (char)(posZ >> 8);
			writeCursor[6] = (char)posZ;

			// Write 2-char ???
			// related to time
			writeCursor[7] = (char)(timeSincePositionPacket >> 8);
			writeCursor[8] = (char)timeSincePositionPacket;

			// Write 2-char rotation
			writeCursor[9] = (char)(driver->rotCurr.y >> GHOST_RECORD_ROTATION_SHIFT);
			writeCursor[10] = (char)(driver->rotCurr.z >> GHOST_RECORD_ROTATION_SHIFT);

			writeCursor += GHOST_SIZE_POSITION;

			// Time of last 0x80 buffer
			sdata->GhostRecording.timeOfLast80buffer = sdata->GhostRecording.timeElapsedInRace;
		}

		// Make a copy of instance flags
		sdata->GhostRecording.instanceFlags = inst->flags;

		if (
		    // if offset of ghost-recording buffer exceeds
		    // the maximum size of a ghost that can be recorded
		    // (if you're one frame away from max capacity)
		    ((u32)sdata->GhostRecording.ptrEndOffset < (u32)writeCursor + GHOST_RECORD_BUFFER_END_GUARD) &&

		    (sdata->boolCanSaveGhost = 0,

		     // If you're not in End-Of-Race menu
		     // (if you were, you'd be just in time to save the ghost)
		     (gameMode & END_OF_RACE) == 0))
		{
			sdata->boolGhostTooBigToSave = 1;

			// set ghostOverflowTextTimer
			// to 180 frames (6 seconds 30fps)
			sdata->ghostOverflowTextTimer = GHOST_RECORD_OVERFLOW_TEXT_FRAMES;
		}

		// Increment frame counter
		sdata->GhostRecording.countSixteenFrames++;

		// Save this frame's X, Y, Z positions,
		// so that they can be used next frame to
		// calculate velocity
		sdata->GhostRecording.VelX = (s16)posX;
		sdata->GhostRecording.VelY = (s16)posY;
		sdata->GhostRecording.VelZ = (s16)posZ;

		if (s_ghostDbgN < 4)
		{
			fprintf(stderr, "[GDBG]   wrote %d bytes, first=%02X\n",
				(int)(writeCursor - (char*)sdata->GhostRecording.ptrCurrOffset),
				(u8)((char*)sdata->GhostRecording.ptrCurrOffset)[0]);
			s_ghostDbgN++;
		}

		// save incremeneted pointer
		sdata->GhostRecording.ptrCurrOffset = writeCursor;
	}

	// Increment frame counter
	sdata->GhostRecording.countEightFrames++;

	// Increment race timer by elapsed milliseconds per frame, ~32
	sdata->GhostRecording.timeElapsedInRace += gGT->elapsedTimeMS;

	if (s_ghostDbgFrame % 300 == 0) {
		fprintf(stderr, "[GDBG-PM] frame=%d cursor-start=%d cap=%u\n", s_ghostDbgFrame, 
			(int)((u8*)sdata->gGT->backBuffer->primMem.cursor - (u8*)sdata->gGT->backBuffer->primMem.start), 
			(unsigned)sdata->gGT->backBuffer->primMem.capacityBytes);
	}

	return;
}


void GhostTape_WriteBoosts(int addReserve, u8 type, int speedCap)
{
	char *writeCursor;

	// quit, if ghost cant be saved
	if (sdata->boolCanSaveGhost == 0)
	{
		return;
	}

	writeCursor = sdata->GhostRecording.ptrCurrOffset;

	fprintf(stderr, "[GHOST-DBG] WriteBoosts: ptr=%p off=%d\n",
	        (void *)writeCursor,
	        (int)(writeCursor - (char *)sdata->GhostRecording.ptrStartOffset));

	if ((type & TURBO_PAD) != 0)
	{
		if (sdata->GhostRecording.boostCooldown1E != 0)
		{
			return;
		}
		sdata->GhostRecording.boostCooldown1E = GHOST_RECORD_BOOST_COOLDOWN_FRAMES;
	}

	// 0x82-style chunks are 6 bytes long (including 0x82)

	// Write to recording buffer
	writeCursor[0] = GHOST_OP_BOOST;

	// big endian reserve
	writeCursor[1] = (char)((u32)addReserve >> 8);
	writeCursor[2] = (char)addReserve;

	// char, add type (increment or set)
	writeCursor[3] = type;

	// big endian speedCcap
	writeCursor[4] = (char)((u32)speedCap >> 8);
	writeCursor[5] = (char)speedCap;

	sdata->GhostRecording.ptrCurrOffset += GHOST_SIZE_BOOST;
}


void GhostTape_Destroy()
{
	if (sdata->ptrGhostTapePlaying != 0)
	{
		MEMPACK_ClearHighMem();
		sdata->ptrGhostTapePlaying = 0;
	}
}
