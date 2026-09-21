#include <common.h>
#include <platform/native_custom_racer.h>
#include <platform/native_audio.h>

/* === Custom voiceline routing (mirrors Ziggy's VoiceGroup) ============
 * Maps retail voiceID (0..23) to one of 8 semantic groups. voiceIDs
 * not in the table are ignored. Mirrors Ziggy's ziggy_voice.c.
 * group: 0=boost, 1=hurt, 2=spin, 3=jump, 4=trap, 5=protected,
 *        6=overtake, 7=attack. */
static int CustomVoiceGroup(u32 voiceID)
{
	switch (voiceID)
	{
	case 16: return 0;             /* turbo */
	case 1: case 4: case 5: case 6: return 1;  /* hit / squashed / crash */
	case 3: return 2;              /* spin */
	case 7: return 3;              /* native big-air meter */
	case 15: return 4;             /* potion / TNT / crate */
	case 2: case 13: return 5;     /* blocked hit / shield */
	case 8: return 6;              /* passes a human racer */
	case 10: case 11: case 12: case 14: return 7;
	default: return -1;
	}
}

/* Per-custom voice state: seen mask, last-frame stamp, RNG gate.
 * Indexed by (characterID - NATIVE_CUSTOM_ID_BASE) so multiple customs
 * in the same race (2P VS) don't share RNG / guard state. The custom
 * branch filters characterID < NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT
 * before writing, so idx is always in [0, NATIVE_CUSTOM_COUNT).
 * static → zero-init. */
static u32 s_customVoiceSeen[NATIVE_CUSTOM_COUNT];
static u32 s_customVoiceLastFrame[NATIVE_CUSTOM_COUNT];
static u8  s_customVoiceHasSpoken[NATIVE_CUSTOM_COUNT];

// does not really touch voiceline
void Voiceline_PoolInit(void)
{
	s32 index;

	sdata->criticalSectionCount = 0;

	sdata->numBackup_ChannelStats = 0;

	sdata->ptrCseqHeader = 0;

	Bank_ResetAllocator();

	Audio_SetDefaults();

	LIST_Clear(&sdata->channelFree);
	LIST_Clear(&sdata->channelTaken);

	LIST_Init(&sdata->channelFree, &sdata->channelStatsPrev[0].link.item, 0x20, 0x18);

	SpuSetReverbVoice(0, 0xffffff);

	// initialize all members in sound list
	for (index = 0; index < 24; index++)
	{
		struct ChannelStats *stats = &sdata->channelStatsPrev[index];
		sdata->ChannelUpdateFlags[index] = 0;

		SpuSetVoiceADSRAttr(index, 0, 0xf, 0x7f, 2, 0xf, 5, 1, 3);

		stats->flags = 0;
		stats->channelID = index;

		stats->ad = 0x80ff;
		stats->sr = 0x1fc2;

		struct ChannelAttr *curr = &sdata->channelAttrCur[index];

		curr->spuStartAddr = (void *)-1;

		curr->ad = 0x80ff;
		curr->sr = 0x1fc2;

		curr->pitch = -1;
		curr->reverb = -1;
		curr->audioL = -1;
		curr->audioR = -1;
	}

	for (index = 0; index < 2; index++)
	{
		struct Song *pool = &sdata->songPool[index];

		// not playing
		pool->flags = 0;

		pool->songPoolIndex = index;
	}

	for (index = 0; index < 24; index++)
	{
		struct SongSeq *seq = &sdata->songSeq[index];

		// not playing
		seq->flags = 0;

		seq->soundID = index;
	}
}

void Voiceline_ClearTimeStamp(void)
{
	for (s32 i = 0; i < 16; i++)
	{
		// Clear audio timestamps arrays
		sdata->timeSet1[i] = 0;
		sdata->timeSet2[i] = 0;
	}
}

void Voiceline_PoolClear(void)
{
	sdata->boolCanPlayWrongWaySFX = false;

	sdata->voicelineCooldown = 0;

	sdata->boolCanPlayVoicelines = false;

	LIST_Clear(&sdata->Voiceline1);

	LIST_Clear(&sdata->Voiceline2);

	// put them all on free list
	LIST_Init(&sdata->Voiceline1, &sdata->voicelinePool[0].item, sizeof(struct VoicelineItem), 8);

	Voiceline_ClearTimeStamp();
}

void Voiceline_StopAll(void)
{
	while (sdata->Voiceline2.last != 0)
	{
		struct Item *voiceLine = sdata->Voiceline2.last;

		LIST_RemoveMember(&sdata->Voiceline2, voiceLine);
		LIST_AddFront(&sdata->Voiceline1, voiceLine);
	}
}

void Voiceline_ToggleEnable(int toggle)
{
	// if this is disabling
	if (toggle == 0)
	{
		sdata->voicelineCooldown = 0;

		Voiceline_StopAll();
	}
	sdata->boolCanPlayVoicelines = toggle;
}

static u32 Voiceline_RequestPlay_NextAudioRNG(void)
{
	sdata->audioRNG = ((sdata->audioRNG >> 3) + sdata->audioRNG * 0x20000000) * 5 + 1;
	return sdata->audioRNG;
}

void Voiceline_RequestPlay(u32 voiceID, u32 characterID, u32 characterID2)
{
	u8 voiceType;
	u32 elapsedFrames;
	u32 canImmediate;
	u32 canQueue;



	if (voiceID >= 0x18)
	{
		return;
	}

	/* === Custom voicelines (Ziggy-style) ===
	 * Customs (characterID >= NATIVE_CUSTOM_ID_BASE) enqueue in the
	 * retail Voiceline2 list; Voiceline_StartPlay then routes the
	 * custom xaID via NativeCustomRacer_GetVoiceTrackBase. Mirrors
	 * Ziggy's ziggy_voice.c: group filter, 60-frame guard, 1/4 & 1/8
	 * RNG. Retail engine handles cooldown, XA_State, streaming. */
	if (characterID >= NATIVE_CUSTOM_ID_BASE)
	{
		int group;
		u32 frame;
		int idx;

		if (characterID >= NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT)
			return;
		if ((sdata->gGT->gameMode1 & END_OF_RACE) != 0)
			return;
		if (sdata->boolCanPlayVoicelines == 0)
			return;

		idx = (int)characterID - NATIVE_CUSTOM_ID_BASE;

		group = CustomVoiceGroup(voiceID);
		if (group < 0)
			return;

		/* 60-frame (1 second) minimum between any two custom voicelines. */
		frame = sdata->gGT->frameTimer_MainFrame_ResetDB;
		if (s_customVoiceHasSpoken[idx] && (frame - s_customVoiceLastFrame[idx]) < 60)
			return;

		if (sdata->voicelineCooldown != 0)
			return;

		/* Same 1/4 first-use and 1/8 repeat odds as retail for
		 * voluntary quips (voiceID > 7), matching Ziggy. */
		if (voiceID > 7)
		{
			u32 rng;
			sdata->audioRNG = ((sdata->audioRNG >> 3) + sdata->audioRNG * 0x20000000) * 5 + 1;
			rng = sdata->audioRNG;
			if (rng & ((s_customVoiceSeen[idx] & (1u << voiceID)) ? 7 : 3))
				return;
		}

		/* Dedup: don't enqueue the same (character, voiceID) twice. */
		for (struct Item *it = sdata->Voiceline2.first; it != NULL; it = it->next)
		{
			struct VoicelineItem *vl = (struct VoicelineItem *)it;
			if ((voiceID == (u32)vl->voiceID) &&
			    (characterID == vl->characterID))
				return;
		}

		struct Item *item = sdata->Voiceline1.first;
		if (item != NULL)
		{
			LIST_RemoveMember(&sdata->Voiceline1, item);
		}
		else
		{
			item = sdata->Voiceline2.last;
			if (item != NULL)
				LIST_RemoveMember(&sdata->Voiceline2, item);
		}
		if (item == NULL)
			return;

		LIST_AddFront(&sdata->Voiceline2, item);

		{
			struct VoicelineItem *vl = (struct VoicelineItem *)item;
			vl->characterID          = characterID;
			vl->secondaryCharacterID = characterID2;
			vl->voiceID              = voiceID;
			vl->startFrame           = sdata->gGT->timer;
		}
		s_customVoiceSeen[idx] |= 1u << voiceID;
		s_customVoiceLastFrame[idx] = frame;
		s_customVoiceHasSpoken[idx] = 1;
		return;
	}

	if (characterID >= 0x10)
	{
		return;
	}

	if (characterID2 >= 0x11)
	{
		return;
	}

	if ((sdata->gGT->gameMode1 & END_OF_RACE) != 0)
	{
		return;
	}

	voiceType = data.voiceID[voiceID];

	if ((s32)voiceID >= 8)
	{
		u32 alreadyPlayed = sdata->timeSet1[characterID] & (1 << (voiceID & 0x1f));
		u32 rng = Voiceline_RequestPlay_NextAudioRNG();

		if (alreadyPlayed != 0)
		{
			rng &= 7;
		}
		else
		{
			rng &= 3;
		}

		if (rng != 0)
		{
			return;
		}
	}

	elapsedFrames = (u32)CTR_MipsSubLo(sdata->gGT->frameTimer_MainFrame_ResetDB, sdata->timeSet2[characterID]);
	canImmediate = 0;
	if (elapsedFrames >= 0x3d)
	{
		canImmediate = voiceType < 2;
	}

	canQueue = 1;
	if (sdata->boolCanPlayVoicelines == 0)
	{
		canQueue = 0;
	}
	else if ((sdata->voicelineCooldown != 0) && (((u8 *)sdata->backupParams_FUN_8002cf28)[0xa] == characterID))
	{
		canQueue = 0;
	}
	else if (elapsedFrames < 0x3c)
	{
		canQueue = 0;
	}

	if (canQueue != 0)
	{
		if (canImmediate != 0)
		{
			u32 rng = Voiceline_RequestPlay_NextAudioRNG();

			canImmediate = 0;
			if ((rng & 1) != 0)
			{
				canQueue = 0;
				goto playImmediate;
			}
		}
	}
	else
	{
		if (canImmediate == 0)
		{
			return;
		}
	}

	if (canImmediate == 0)
	{
		goto queueVoiceline;
	}

playImmediate:
	if (voiceType == 0)
	{
		OtherFX_Play((characterID + 0x1c) & 0xffff, 2);
	}
	else if (voiceType == 1)
	{
		OtherFX_Play((characterID + 0x2c) & 0xffff, 2);
	}

	sdata->timeSet2[characterID] = sdata->gGT->frameTimer_MainFrame_ResetDB;
	return;

queueVoiceline:
	if (canQueue == 0)
	{
		return;
	}

	sdata->timeSet1[characterID] |= 1 << (voiceID & 0x1f);

	for (struct Item *item = sdata->Voiceline2.first; item != NULL; item = item->next)
	{
		struct VoicelineItem *voiceLine = (struct VoicelineItem *)item;

		if ((voiceID == (u32)voiceLine->voiceID) && (characterID == voiceLine->characterID))
		{
			return;
		}
	}

	struct Item *item = sdata->Voiceline1.first;
	if (item != NULL)
	{
		LIST_RemoveMember(&sdata->Voiceline1, item);
	}
	else
	{
		item = sdata->Voiceline2.last;
		if (item != NULL)
		{
			LIST_RemoveMember(&sdata->Voiceline2, item);
		}
	}

	LIST_AddFront(&sdata->Voiceline2, item);

	{
		struct VoicelineItem *voiceLine = (struct VoicelineItem *)item;

		voiceLine->characterID = characterID;
		voiceLine->secondaryCharacterID = characterID2;
		voiceLine->voiceID = voiceID;
		voiceLine->startFrame = sdata->gGT->timer;
	}
}

void Voiceline_StartPlay(struct Item *voiceLine)
{
	struct VoicelineItem *voiceLineItem = (struct VoicelineItem *)voiceLine;
	u32 voiceID = (u16)voiceLineItem->voiceID;
	u32 characterID = voiceLineItem->characterID;
	u32 voiceSetIndex;

	/* Custom branch: route through the retail CDSYS_XAPlay with an
	 * extended xaID. The XNF has been patched by
	 * build_voice_pipeline.py to map 314+ to the custom banks.
	 * Uses CustomVoiceGroup() for the semantic group index (mirrors
	 * Ziggy's ziggy_voice.c). */
	if (characterID >= NATIVE_CUSTOM_ID_BASE)
	{
		int idx;
		int base;
		int group;

		if (characterID >= NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT)
		{
			sdata->voicelineCooldown = 0x1e;
			return;
		}

		idx = (int)characterID - NATIVE_CUSTOM_ID_BASE;
		base = NativeCustomRacer_GetVoiceTrackBase((int)characterID);
		group = CustomVoiceGroup(voiceID);
		if (base == 0 || group < 0)
		{
			sdata->voicelineCooldown = 0x1e;
			return;
		}
		int trackId = base + group;
		if (CDSYS_XAPlay(CDSYS_XA_TYPE_GAME, trackId) == 0)
		{
			sdata->voicelineCooldown = 0x1e;
			return;
		}
		sdata->voicelineCooldown =
			(s16)(CDSYS_XAGetTrackLength(CDSYS_XA_TYPE_GAME, trackId) / 5) + 0x1e;
		s_customVoiceLastFrame[idx] = sdata->gGT->frameTimer_MainFrame_ResetDB;
		s_customVoiceHasSpoken[idx] = 1;
		return;
	}

	CTR_WriteU32LE(&sdata->backupParams_FUN_8002cf28[0], CTR_ReadU32LE((u8 *)voiceLineItem + 0x0));
	CTR_WriteU32LE(&sdata->backupParams_FUN_8002cf28[1], CTR_ReadU32LE((u8 *)voiceLineItem + 0x4));
	CTR_WriteU32LE(&sdata->backupParams_FUN_8002cf28[2], CTR_ReadU32LE((u8 *)voiceLineItem + 0x8));
	CTR_WriteU32LE(&sdata->backupParams_FUN_8002cf28[3], CTR_ReadU32LE((u8 *)voiceLineItem + 0xc));

	if ((IS_BOSS_RACE(sdata->gGT->gameMode1)) && ((u32)(voiceID - 10) < 6) && (((u32)(characterID - 8) < 4) || (characterID == 0xf)))
	{
		u32 rng = Voiceline_RequestPlay_NextAudioRNG();
		voiceSetIndex = (rng & 3) + 4;
	}
	else
	{
		voiceSetIndex = data.voiceID[(s16)voiceID];
	}

	s16 *voiceIDs = data.voiceData[characterID].voiceSet[voiceSetIndex].ptr;
	u16 numVoiceIDs = data.voiceData[characterID].voiceSet[voiceSetIndex].num;

	if (numVoiceIDs == 0)
	{
		Voiceline_StopAll();
		return;
	}

	u32 rng = Voiceline_RequestPlay_NextAudioRNG();
	u32 voiceIndex = rng % numVoiceIDs;
	u32 xaID = (u16)voiceIDs[voiceIndex];

	if (CDSYS_XAPlay(CDSYS_XA_TYPE_GAME, xaID) == 0)
	{
		sdata->voicelineCooldown = 0x1e;
		return;
	}

	sdata->voicelineCooldown = (s16)(CDSYS_XAGetTrackLength(CDSYS_XA_TYPE_GAME, xaID) / 5) + 0x1e;
}

void Voiceline_Update(void)
{
	struct GameTracker *gGT = sdata->gGT;

	if (sdata->boolCanPlayVoicelines == 0)
	{
		return;
	}

	if (sdata->voicelineCooldown != 0)
	{
		sdata->voicelineCooldown = (s16)CTR_MipsSubLo((u16)sdata->voicelineCooldown, 1);
		if (sdata->voicelineCooldown != 0)
		{
			return;
		}
	}

	if (sdata->XA_State != 0)
	{
		return;
	}

	if (sdata->boolCanPlayWrongWaySFX != 0)
	{
		if ((sdata->WrongWayDirection_bool != 0) && (sdata->framesDrivingSameDirection > 0x1e))
		{
			u32 voiceID;

			sdata->boolCanPlayWrongWaySFX = false;

			if (gGT->numPlyrCurrGame == 1)
			{
				if (!VehPickupItem_MaskBoolGoodGuy(gGT->drivers[0]))
				{
					voiceID = 0x3d;
				}
				else
				{
					voiceID = 0x1e;
				}

				if (CDSYS_XAPlay(CDSYS_XA_TYPE_EXTRA, voiceID) == 0)
				{
					sdata->voicelineCooldown = 0x1e;
					return;
				}

				sdata->voicelineCooldown = (s16)(CDSYS_XAGetTrackLength(CDSYS_XA_TYPE_EXTRA, voiceID) / 5) + 0x1e;
				return;
			}
		}

		if (sdata->boolCanPlayWrongWaySFX != 0)
		{
			goto playQueuedVoice;
		}
	}

	if ((sdata->WrongWayDirection_bool == 0) && (sdata->framesDrivingSameDirection > 0x1e))
	{
		sdata->boolCanPlayWrongWaySFX = true;
	}

playQueuedVoice:
	if (sdata->Voiceline2.first != NULL)
	{
		struct Item *first = sdata->Voiceline2.first;

		LIST_RemoveMember(&sdata->Voiceline2, first);
		LIST_AddBack(&sdata->Voiceline1, first);
		Voiceline_StartPlay(first);
	}
}

void Voiceline_EmptyFunc(void)
{
}

void Voiceline_SetDefaults(void)
{
	sdata->audioState = AUDIO_NONE;
	sdata->desiredXA_FinalLapIndex = 0;
	sdata->desiredXA_RaceIntroIndex = 0;

	sdata->WrongWayDirection_bool = false;

	sdata->framesDrivingSameDirection = 0;
	sdata->nTropyVoiceCount = 0;
	sdata->boolNeedXASeek = 0;

	Music_SetDefaults();
}
