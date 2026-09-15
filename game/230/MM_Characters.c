#include <common.h>
#include <stdio.h>
#include <platform/native_custom_racer.h>

enum
{
	MM_CHARACTER_SELECT_SCREEN_W = 0x200,
	MM_CHARACTER_SELECT_SCREEN_H = 0xd8,
	MM_CHARACTER_SELECT_DISTANCE_TO_SCREEN = 0x100,
	MM_CHARACTER_SELECT_MODEL_MOVE_FP = 0x1000,
	MM_CHARACTER_SELECT_MODEL_MOVE_FP_SHIFT = 0xc,
	MM_CHARACTER_SELECT_MODEL_MOVE_NEXT = 1,
	MM_CHARACTER_SELECT_MODEL_MOVE_PREV = -1,
	MM_CHARACTER_SELECT_ICON_COUNT = 0xf,
	MM_CHARACTER_SELECT_EXPANSION_ICON_FIRST = 0xc,
	MM_CHARACTER_SELECT_DEFAULT_DRIVER_COUNT = 8,
	MM_CHARACTER_SELECT_MAX_PLAYERS = 4,
	MM_CHARACTER_SELECT_LIMITED_LAYOUT_OFFSET = 4,
	MM_CHARACTER_SELECT_FULL_LAYOUT_COUNT = 2,
	MM_CHARACTER_SELECT_TRANSITION_FRAMES = 0xc,
	MM_CHARACTER_SELECT_TRANSITION_STEP = 8,
	MM_CHARACTER_SELECT_ANGLE_STEP = 0x400,
	MM_CHARACTER_SELECT_ANGLE_OFFSET = 400,
	MM_CHARACTER_SELECT_SPIN_STEP = 0x40,
	MM_CHARACTER_SELECT_LAYOUT_3P = 2,
	MM_CHARACTER_SELECT_LAYOUT_4P = 3,
	MM_CHARACTER_SELECT_LAYOUT_1P_LIMITED = 4,
	MM_CHARACTER_SELECT_LAYOUT_2P_LIMITED = 5,
	MM_CHARACTER_SELECT_TITLE_TRANSITION_INDEX = 15,
	MM_CHARACTER_SELECT_DRIVER_WINDOW_TRANSITION_FIRST = 0x10,
	MM_CHARACTER_SELECT_3P_TITLE_X = 0x9c,
	MM_CHARACTER_SELECT_3P_SELECT_Y = 0x14,
	MM_CHARACTER_SELECT_3P_CHARACTER_Y = 0x26,
	MM_CHARACTER_SELECT_4P_TITLE_X = 0xfc,
	MM_CHARACTER_SELECT_4P_SELECT_Y = 8,
	MM_CHARACTER_SELECT_4P_CHARACTER_Y = 0x18,
	MM_CHARACTER_SELECT_LIMITED_TITLE_X = 0xfc,
	MM_CHARACTER_SELECT_LIMITED_TITLE_Y = 10,
	MM_CHARACTER_SELECT_INPUT_DPAD = BTN_RIGHT | BTN_LEFT | BTN_DOWN | BTN_UP,
	MM_CHARACTER_SELECT_INPUT_MENU = BTN_TRIANGLE | BTN_CIRCLE | BTN_SQUARE_one | BTN_CROSS_one,
	MM_CHARACTER_SELECT_INPUT_CONFIRM = BTN_CIRCLE | BTN_CROSS_one,
	MM_CHARACTER_SELECT_INPUT_BACK = BTN_TRIANGLE | BTN_SQUARE_one,
	MM_CHARACTER_SELECT_ICON_DECAL_OFFSET_X = 6,
	MM_CHARACTER_SELECT_ICON_DECAL_OFFSET_Y = 4,
	MM_CHARACTER_SELECT_ICON_RECT_W = 0x34,
	MM_CHARACTER_SELECT_ICON_RECT_H = 0x21,
	MM_CHARACTER_SELECT_CURSOR_LABEL_OFFSET_X = -6,
	MM_CHARACTER_SELECT_CURSOR_LABEL_OFFSET_Y = -3,
	MM_CHARACTER_SELECT_HIGHLIGHT_OFFSET_X = 3,
	MM_CHARACTER_SELECT_HIGHLIGHT_OFFSET_Y = 2,
	MM_CHARACTER_SELECT_HIGHLIGHT_W = 0x2e,
	MM_CHARACTER_SELECT_HIGHLIGHT_H = 0x1d,
	MM_CHARACTER_SELECT_SELECTED_BORDER_COUNT = 2,
	MM_CHARACTER_SELECT_SELECTED_BORDER_INSET_X = 3,
	MM_CHARACTER_SELECT_SELECTED_BORDER_INSET_Y = 2,
	MM_CHARACTER_SELECT_SELECTED_BORDER_SHRINK_W = 6,
	MM_CHARACTER_SELECT_SELECTED_BORDER_SHRINK_H = 4,
	MM_CHARACTER_SELECT_4P_NAME_BOTTOM_OFFSET = -6,
	MM_CHARACTER_SELECT_COLOR_PHASE_FRAME_STEP = 0x100,
	MM_CHARACTER_SELECT_COLOR_PHASE_PLAYER_STEP = 0x400,
	MM_CHARACTER_SELECT_COLOR_TRIG_MASK = 0x3ff,
	MM_CHARACTER_SELECT_COLOR_TRIG_HIGH_HALF_BIT = 0x400,
	MM_CHARACTER_SELECT_COLOR_TRIG_NEGATE_BIT = 0x800,
	MM_CHARACTER_SELECT_COLOR_PULSE_THRESHOLD = 0xc00,
	MM_CHARACTER_SELECT_COLOR_PULSE_SCALE_SHIFT = 7,
	MM_CHARACTER_SELECT_COLOR_PULSE_FP_SHIFT = 0xc,
};

void MM_Characters_AnimateColors(u8 *colorData, s16 playerID, s16 flag)
{
	u8 colorAdjustmentValue;
	u32 trigApproximationIndex;
	u32 trigApprox;

	u8 *ptrColor = (u8 *)data.ptrColor[playerID + PLAYER_BLUE];

	trigApprox = 0;

	if (flag == 0)
	{
		trigApproximationIndex = sdata->frameCounter * MM_CHARACTER_SELECT_COLOR_PHASE_FRAME_STEP + playerID * MM_CHARACTER_SELECT_COLOR_PHASE_PLAYER_STEP;
		trigApprox = CTR_ReadU32LE(&data.trigApprox[trigApproximationIndex & MM_CHARACTER_SELECT_COLOR_TRIG_MASK]);

		if ((trigApproximationIndex & MM_CHARACTER_SELECT_COLOR_TRIG_HIGH_HALF_BIT) == 0)
		{
			trigApprox = trigApprox << 0x10;
		}
		trigApprox = trigApprox >> 0x10;

		if ((trigApproximationIndex & MM_CHARACTER_SELECT_COLOR_TRIG_NEGATE_BIT) != 0)
		{
			trigApprox = -(int)trigApprox;
		}
	}

	colorAdjustmentValue = 0;
	if (MM_CHARACTER_SELECT_COLOR_PULSE_THRESHOLD < (int)trigApprox)
	{
		colorAdjustmentValue = ((trigApprox << MM_CHARACTER_SELECT_COLOR_PULSE_SCALE_SHIFT) >> MM_CHARACTER_SELECT_COLOR_PULSE_FP_SHIFT);
	}

	colorData[0] = ptrColor[0] | colorAdjustmentValue;
	colorData[1] = ptrColor[1] | colorAdjustmentValue;
	colorData[2] = ptrColor[2] | colorAdjustmentValue;
	colorData[3] = 0;

	return;
}

int MM_Characters_GetNextDriver(s16 direction, s16 characterID)
{
	u8 nextIcon = D230.activeCharacterSelectMeta[(s32)characterID].nextIconByDirection[direction];
	s16 unlocked = D230.activeCharacterSelectMeta[(s32)nextIcon].unlockFlags;

	s16 newDriver = nextIcon;

	if (
	    (unlocked != MM_CHARACTER_UNLOCK_ALWAYS) &&
	    !CHECK_ADV_BIT(sdata->gameProgress.unlocks, unlocked))
	{
		newDriver = characterID;
	}

	return newDriver;
}

/* === §8.1 Diff 1: shared helper to compare by characterID === */
static b32 MM_Characters_CharIDInUse(s16 candidateCharID, s16 excludePlayer)
{
	for (s32 p = 0; p < sdata->gGT->numPlyrNextGame; p++)
	{
		if ((p != excludePlayer) && (data.characterIDs[p] == candidateCharID))
			return 1;
	}
	return 0;
}

/* === §8.1 Diff 1b: find the first free icon for the player, starting at
 * their own index (P1 -> icon 0, P2 -> icon 1, ...) so that two auto-joins
 * in the same frame don't collide on the same icon. === */
static s16 MM_Characters_FindFreeIcon(s16 player)
{
	for (s32 i = 0; i < MM_CHARACTER_SELECT_ICON_COUNT; i++)
	{
		s32 tentative = ((s32)player + i) % MM_CHARACTER_SELECT_ICON_COUNT;
		s16 candidateCharID = D230.activeCharacterSelectMeta[tentative].characterID;
		if (!MM_Characters_CharIDInUse(candidateCharID, player))
			return (s16)tentative;
	}
	return 0;
}

/* === §8.1 Diff 2: boolIsInvalid by charID === */
b32 MM_Characters_boolIsInvalid(s16 *unused, s16 candidateIcon, s16 player)
{
	(void)unused;
	s16 candidateCharID = D230.activeCharacterSelectMeta[(s32)candidateIcon].characterID;
	return MM_Characters_CharIDInUse(candidateCharID, player);
}

struct Model *MM_Characters_GetModelByName(const char *name)
{
	struct Model **models;
	struct Model *model;
	struct Level *level1 = sdata->gGT->level1;

	if (level1 == NULL)
	{
		return NULL;
	}

	models = level1->ptrModelsPtrArray;
	if (models == NULL)
	{
		return NULL;
	}

	for (model = models[0]; model != NULL; models++, model = models[0])
	{
		if ((ModelName_ReadWord(model->name, 0) == ModelName_ReadWord(name, 0)) && (ModelName_ReadWord(model->name, 1) == ModelName_ReadWord(name, 1)) &&
		    (ModelName_ReadWord(model->name, 2) == ModelName_ReadWord(name, 2)) && (ModelName_ReadWord(model->name, 3) == ModelName_ReadWord(name, 3)))
		{
			return model;
		}
	}
	return NULL;
}

void MM_Characters_DrawWindows(b32 boolShowDrivers)
{
	struct GameTracker *gGT = sdata->gGT;
	SVec3 rot;

	if (boolShowDrivers != 0)
	{
		gGT->renderFlags |= RENDER_FLAG_TIRES;
	}

	for (s32 playerIndex = 0; playerIndex < gGT->numPlyrNextGame; playerIndex++)
	{
		SVec2 *windowPos = &D230.activeCharacterSelectWindowPos[playerIndex];
		struct TransitionMeta *tMeta = &D230.characterSelectTransitionMeta[playerIndex];

		struct PushBuffer *pb = &gGT->pushBuffer[playerIndex];
		pb->rect.x = windowPos->x + tMeta[MM_CHARACTER_SELECT_DRIVER_WINDOW_TRANSITION_FIRST].currX;
		pb->rect.y = windowPos->y + tMeta[MM_CHARACTER_SELECT_DRIVER_WINDOW_TRANSITION_FIRST].currY;
		pb->rect.w = D230.characterSelectWindowWidth;
		pb->rect.h = D230.characterSelectWindowHeight;

		if ((s16)pb->rect.x < 0)
		{
			pb->rect.w -= pb->rect.x;
			pb->rect.x = 0;
			if ((s16)pb->rect.w < 0)
			{
				pb->rect.w = 0;
			}
		}

		if ((s16)pb->rect.y < 0)
		{
			pb->rect.h -= pb->rect.y;
			pb->rect.y = 0;
			if ((s16)pb->rect.h < 0)
			{
				pb->rect.h = 0;
			}
		}

		if ((MM_CHARACTER_SELECT_SCREEN_W < pb->rect.x + pb->rect.w) && (pb->rect.w = MM_CHARACTER_SELECT_SCREEN_W - pb->rect.x, pb->rect.w < 0))
		{
			pb->rect.x = MM_CHARACTER_SELECT_SCREEN_W;
			pb->rect.w = 0;

#ifdef CTR_NATIVE
			pb->rect.w = 1;
#endif
		}

		if ((MM_CHARACTER_SELECT_SCREEN_H < pb->rect.y + pb->rect.h) && (pb->rect.h = MM_CHARACTER_SELECT_SCREEN_H - pb->rect.y, pb->rect.h < 0))
		{
			pb->rect.y = MM_CHARACTER_SELECT_SCREEN_H;
			pb->rect.h = 0;

#ifdef CTR_NATIVE
			pb->rect.h = 1;
#endif
		}

		pb->distanceToScreen_CURR = MM_CHARACTER_SELECT_DISTANCE_TO_SCREEN;
		pb->distanceToScreen_PREV = MM_CHARACTER_SELECT_DISTANCE_TO_SCREEN;

		pb->pos.x = 0;
		pb->pos.y = 0;
		pb->pos.z = 0;
		pb->rot.x = 0;
		pb->rot.y = 0;
		pb->rot.z = 0;

		struct Instance *driverInst = gGT->drivers[playerIndex]->instSelf;

		driverInst->flags &= ~HIDE_MODEL;

		if ((gGT->numPlyrNextGame <= playerIndex) || (boolShowDrivers == 0))
		{
			driverInst->flags |= HIDE_MODEL;
		}

		struct InstDrawPerPlayer *idpp = INST_GETIDPP(driverInst);

		idpp[0].pushBuffer = 0;
		idpp[1].pushBuffer = 0;
		idpp[2].pushBuffer = 0;
		idpp[3].pushBuffer = 0;

		idpp[playerIndex].pushBuffer = pb;

		s16 *currCharacterID = &D230.characterSelectPlayerState.currentCharacterID[playerIndex];

		driverInst->animFrame = 0;
		driverInst->animIndex = 0;

		s16 _cid = *currCharacterID;
		struct Model *model;
		if (_cid >= NATIVE_CUSTOM_ID_BASE)
			model = NativeCustomRacer_GetMenuModel((int)_cid, (int)playerIndex);
		else
			model = MM_Characters_GetModelByName(GET_METADATA((int)_cid)->name_Debug);

		driverInst->model = model;

		gGT->cameraDC[playerIndex].cameraMode = CAMERA_MODE_FREECAM;

		driverInst->matrix.t[0] = D230.characterSelectDriverModel.pos.x;
		driverInst->matrix.t[1] = D230.characterSelectDriverModel.pos.y;
		driverInst->matrix.t[2] = D230.characterSelectDriverModel.pos.z;

		s16 *moveTimer = &D230.characterSelectModelMoveTimer[playerIndex];
		s16 nextMoveTimer = *moveTimer + -1;

		if (*moveTimer == 0)
		{
			if (*currCharacterID != data.characterIDs[playerIndex])
			{
				*moveTimer = D230.characterSelectDriverModel.moveFrames << 1;
				D230.characterSelectPlayerState.desiredCharacterID[playerIndex] = data.characterIDs[playerIndex];
			}
		}
		else
		{
			*moveTimer = nextMoveTimer;

			s32 slideDirection;
			s32 slideOffset;

			if ((int)nextMoveTimer < (int)D230.characterSelectDriverModel.moveFrames)
			{
				*currCharacterID = D230.characterSelectPlayerState.desiredCharacterID[playerIndex];
				s32 moveFrameScale = RaceFlag_MoveModels((int)nextMoveTimer, (int)D230.characterSelectDriverModel.moveFrames);

				slideDirection = -D230.characterSelectPlayerState.modelMoveDir[playerIndex];
				slideOffset = moveFrameScale * D230.characterSelectDriverModel.slideDistance >> MM_CHARACTER_SELECT_MODEL_MOVE_FP_SHIFT;
			}
			else
			{
				s32 moveFrameScale =
				    RaceFlag_MoveModels((int)nextMoveTimer - (int)D230.characterSelectDriverModel.moveFrames, (int)D230.characterSelectDriverModel.moveFrames);

				slideDirection = D230.characterSelectPlayerState.modelMoveDir[playerIndex];
				slideOffset = (MM_CHARACTER_SELECT_MODEL_MOVE_FP - moveFrameScale) * (int)D230.characterSelectDriverModel.slideDistance >>
				              MM_CHARACTER_SELECT_MODEL_MOVE_FP_SHIFT;
			}

			driverInst->matrix.t[0] += slideDirection * slideOffset;
		}

		rot.x = D230.characterSelectDriverModel.rot.x;
		rot.y = D230.characterSelectDriverModel.rot.y + D230.characterSelectPlayerState.angle[playerIndex];
		rot.z = D230.characterSelectDriverModel.rot.z;

		ConvertRotToMatrix(&driverInst->matrix, &rot);
	}
	return;
}

void MM_Characters_SetMenuLayout(void)
{
	b32 expandRoster = false;

	D230.characterSelectRosterExpanded = 0;

	s32 numPlyrNextGame = sdata->gGT->numPlyrNextGame;
	s32 layoutIndex = numPlyrNextGame - 1;

	for (s32 iconIndex = MM_CHARACTER_SELECT_EXPANSION_ICON_FIRST; iconIndex < MM_CHARACTER_SELECT_ICON_COUNT; iconIndex++)
	{
		u16 unlocked = D230.characterSelectMeta1P2P[iconIndex].unlockFlags;

		if (CHECK_ADV_BIT(sdata->gameProgress.unlocks, unlocked))
		{
			expandRoster = true;
			break;
		}
	}

	if ((layoutIndex < MM_CHARACTER_SELECT_FULL_LAYOUT_COUNT) && (!expandRoster))
	{
		layoutIndex += MM_CHARACTER_SELECT_LIMITED_LAYOUT_OFFSET;
	}

	D230.characterSelectRosterExpanded = expandRoster;
	D230.characterSelectLayoutIndex = layoutIndex;
	D230.characterSelectDriverModel.pos.y = D230.characterSelectLayout.driverPosY[layoutIndex];
	D230.characterSelectDriverModel.pos.z = D230.characterSelectLayout.driverPosZ[layoutIndex];
	D230.characterSelectWindowWidth = D230.characterSelectLayout.windowW[layoutIndex];
	D230.characterSelectWindowHeight = D230.characterSelectLayout.windowH[layoutIndex];
	D230.activeCharacterSelectWindowPos = D230.characterSelectWindowPosByLayout[layoutIndex];
	D230.activeCharacterSelectMeta = D230.characterSelectMetaByLayout[layoutIndex];
	D230.characterSelectNameTextY = D230.characterSelectLayout.textY[layoutIndex];
	D230.characterSelectTransitionMeta = D230.characterSelectTransitionByPlayerCount[numPlyrNextGame - 1];

	return;
}

void MM_Characters_BackupIDs(void)
{
	for (s32 driverIndex = 0; driverIndex < MM_CHARACTER_SELECT_DEFAULT_DRIVER_COUNT; driverIndex++)
	{
		sdata->characterIDs_backup[driverIndex] = data.characterIDs[driverIndex];
	}
	return;
}

void MM_Characters_PreventOverlap(void)
{
	struct GameTracker *gGT = sdata->gGT;
	s8 availableDefaultCharacters[MM_CHARACTER_SELECT_DEFAULT_DRIVER_COUNT];

	CTR_WriteU32LE((u8 *)&availableDefaultCharacters[0], R230.packedDefaultCharacterIDWords[0]);
	CTR_WriteU32LE((u8 *)&availableDefaultCharacters[4], R230.packedDefaultCharacterIDWords[1]);

	for (s32 playerIndex = 0; playerIndex < gGT->numPlyrNextGame; playerIndex++)
	{
		s32 characterID = data.characterIDs[playerIndex];

		if (characterID < MM_CHARACTER_SELECT_DEFAULT_DRIVER_COUNT)
		{
			availableDefaultCharacters[characterID] = -1;
		}
	}

	for (s32 playerIndex = 1; playerIndex < gGT->numPlyrNextGame; playerIndex++)
	{
		for (s32 previousPlayer = 0; previousPlayer < playerIndex; previousPlayer++)
		{
			if (data.characterIDs[playerIndex] == data.characterIDs[previousPlayer])
			{
				for (s32 defaultIndex = 0; defaultIndex < MM_CHARACTER_SELECT_DEFAULT_DRIVER_COUNT; defaultIndex++)
				{
					s8 *defaultCharacter = &availableDefaultCharacters[defaultIndex];
					s8 freeCharacter = *defaultCharacter;

					if (-1 < freeCharacter)
					{
						data.characterIDs[playerIndex] = (s16)freeCharacter;
						*defaultCharacter = -1;
						break;
					}
				}
			}
		}
	}
	return;
}

void MM_Characters_RestoreIDs(void)
{
	struct GameTracker *gGT = sdata->gGT;

	sdata->characterSelectFlags = 0;
	D230.characterSelectTransitionFrame = MM_CHARACTER_SELECT_TRANSITION_FRAMES;
	D230.characterSelectMenuState = ENTERING_MENU;

  	/* Issue 4: intermediate screens (track select, etc.) clobber icon VRAM.
	 * Force a re-apply of our current page so the char-select window and
	 * icons render correctly on entry. */
	NativeCustomRacer_ForceReapply();

	/* Issue 4: intermediate screens (track select, etc.) clobber icon VRAM.
	 * Force a re-apply of our current page so the char-select window and
	 * icons render correctly on entry. */
	NativeCustomRacer_ForceReapply();

	for (s32 driverIndex = 0; driverIndex < MM_CHARACTER_SELECT_DEFAULT_DRIVER_COUNT; driverIndex++)
	{
		data.characterIDs[driverIndex] = sdata->characterIDs_backup[driverIndex];
	}

	MM_Characters_SetMenuLayout();

	/* === Phase 2: apply custom IDs to the active meta for this page === */
	D230.activeCharacterSelectMeta = NativeCustomRacer_GetPageMeta(
	    D230.activeCharacterSelectMeta, MM_CHARACTER_SELECT_ICON_COUNT);
	/* =================================================================== */

	for (s32 iconIndex = 0; iconIndex < MM_CHARACTER_SELECT_ICON_COUNT; iconIndex++)
	{
		s16 cid = D230.activeCharacterSelectMeta[iconIndex].characterID;
		if (cid >= NATIVE_CUSTOM_ID_BASE)
			s_customMenuID[cid - NATIVE_CUSTOM_ID_BASE] = (s16)iconIndex;
		else if (cid >= 0 && cid < 0x10)
			D230.characterMenuID[cid] = (s16)iconIndex;
	}

	for (s32 playerIndex = 0; playerIndex < gGT->numPlyrNextGame; playerIndex++)
	{
		s16 *currID = &data.characterIDs[playerIndex];

		/* === Phase 2: custom IDs (>= 16) are always "unlocked" === */
		if (*currID >= NATIVE_CUSTOM_ID_BASE)
			continue;
		/* ======================================================== */

		s16 unlocked = D230.activeCharacterSelectMeta[(s32)*currID].unlockFlags;

		if ((unlocked != MM_CHARACTER_UNLOCK_ALWAYS) &&
		    !CHECK_ADV_BIT(sdata->gameProgress.unlocks, unlocked))
		{
			*currID = CRASH_BANDICOOT;
		}
	}

	MM_Characters_PreventOverlap();

	for (s32 playerIndex = 0; playerIndex < gGT->numPlyrNextGame; playerIndex++)
	{
		D230.characterSelectPlayerState.currentCharacterID[playerIndex] = data.characterIDs[playerIndex];
		D230.characterSelectPlayerState.desiredCharacterID[playerIndex] = data.characterIDs[playerIndex];
		D230.characterSelectModelMoveTimer[playerIndex] = 0;
		D230.characterSelectPlayerState.angle[playerIndex] = (playerIndex * MM_CHARACTER_SELECT_ANGLE_STEP) + MM_CHARACTER_SELECT_ANGLE_OFFSET;
	}

	MM_Characters_DrawWindows(0);
	return;
}

void MM_Characters_HideDrivers(void)
{
	struct GameTracker *gGT = sdata->gGT;

	for (s32 playerIndex = 0; playerIndex < MM_CHARACTER_SELECT_MAX_PLAYERS; playerIndex++)
	{
		PushBuffer_Init(&gGT->pushBuffer[playerIndex], 0, 1);
		gGT->drivers[playerIndex]->instSelf->flags |= HIDE_MODEL;
	}

	return;
}

void MM_Characters_MenuProc(struct RectMenu *unused)
{
	(void)unused;
	b32 candidateInUseByOtherPlayer;
	b32 deadEndCandidateAvailable;
	s16 nextIcon;
	int intermediateIcon;
	s16 previousCandidateIcon;
	int nextIconCopy;
	s16 alternateIcon;
	s16 iconPerPlayer[4];

	RECT drawRect;

	s16 hitNavigationDeadEnd;

	int direction;

	struct GameTracker *gGT = sdata->gGT;

	u32 *ot = gGT->backBuffer->otMem.uiOT;

	/* === Custom racer pagination ===
	 * L1 / R1  = change page (player 1 only)
	 * L1+R1    = does NOT change page; the bits are left for the per-player
	 *            loop so that confirmed off-page players can rejoin. */
	if ((D230.characterSelectMenuState == IN_MENU) &&
	    (NativeCustomRacer_GetPageCount() > 1))
	{
		u32 taps = sdata->buttonTapPerPlayer[0];
		u32 lr = taps & (BTN_L1 | BTN_R1);

		if (lr == (BTN_L1 | BTN_R1))
		{
			/* Reserved for rejoin. Bits are NOT consumed here. */
		}
		else
		{
			if (taps & BTN_R1)
			{
				NativeCustomRacer_NextPage();
				taps &= ~BTN_R1;
			}
			if (taps & BTN_L1)
			{
				NativeCustomRacer_PrevPage();
				taps &= ~BTN_L1;
			}
		}
		sdata->buttonTapPerPlayer[0] = taps;
	}
	NativeCustomRacer_RefreshPage();
	/* ================================================================ */

	if (D230.characterSelectMenuState != IN_MENU)
	{
		MM_TransitionInOut(D230.characterSelectTransitionMeta, (int)D230.characterSelectTransitionFrame, MM_CHARACTER_SELECT_TRANSITION_STEP);
	}

	MM_Characters_SetMenuLayout();

	/* === Phase 2: swap the active meta for our page-patched copy === */
	D230.activeCharacterSelectMeta = NativeCustomRacer_GetPageMeta(
	    D230.activeCharacterSelectMeta, MM_CHARACTER_SELECT_ICON_COUNT);
	/* ============================================================= */

	/* === Phase 2: refresh ID <-> icon-index maps for the current layout === */
	for (s32 iconIndex = 0; iconIndex < MM_CHARACTER_SELECT_ICON_COUNT; iconIndex++)
	{
		s16 cid = D230.activeCharacterSelectMeta[iconIndex].characterID;
		if (cid >= NATIVE_CUSTOM_ID_BASE)
			s_customMenuID[cid - NATIVE_CUSTOM_ID_BASE] = (s16)iconIndex;
		else if (cid >= 0 && cid < 0x10)
			D230.characterMenuID[cid] = (s16)iconIndex;
	}
	/* =================================================================== */

	/* === §8.1 Diff 3: resolve iconPerPlayer[] by characterID.
	 * -1 = off-page (char not present in the current page's meta). === */
	for (s32 playerIndex = 0; playerIndex < MM_CHARACTER_SELECT_MAX_PLAYERS; playerIndex++)
	{
		s16 cid = data.characterIDs[playerIndex];
		iconPerPlayer[playerIndex] = -1;
		for (s32 iconIndex = 0; iconIndex < MM_CHARACTER_SELECT_ICON_COUNT; iconIndex++)
		{
			if (D230.activeCharacterSelectMeta[iconIndex].characterID == cid)
			{
				iconPerPlayer[playerIndex] = (s16)iconIndex;
				break;
			}
		}
	}
	/* ================================================================ */

	MM_Characters_DrawWindows(1);

	if (D230.characterSelectMenuState == ENTERING_MENU)
	{
		if (D230.characterSelectTransitionFrame == 0)
		{
			D230.characterSelectMenuState = IN_MENU;
		}
		else
		{
			D230.characterSelectTransitionFrame--;
		}
	}

	if (D230.characterSelectMenuState == EXITING_MENU)
	{
		D230.characterSelectTransitionFrame++;

		if (D230.characterSelectTransitionFrame > MM_CHARACTER_SELECT_TRANSITION_FRAMES)
		{
			MM_Characters_BackupIDs();

			if (D230.characterSelectExitsForward == 0)
			{
				MM_JumpTo_Title_Returning();
				MM_Characters_HideDrivers();
				return;
			}

			MM_Characters_HideDrivers();

			if ((gGT->gameMode2 & CUP_ANY_KIND) != 0)
			{
				sdata->ptrDesiredMenu = &D230.menuCupSelect;
				MM_CupSelect_Init();
				return;
			}

			sdata->ptrDesiredMenu = &D230.menuTrackSelect;
			MM_TrackSelect_Init();
			return;
		}
	}

	int posX = D230.characterSelectTransitionMeta[MM_CHARACTER_SELECT_TITLE_TRANSITION_INDEX].currX;
	int posY = D230.characterSelectTransitionMeta[MM_CHARACTER_SELECT_TITLE_TRANSITION_INDEX].currY;

	u32 characterSelectType;
	char *characterSelectString;
	switch (D230.characterSelectLayoutIndex)
	{
	case MM_CHARACTER_SELECT_LAYOUT_3P:
		if (D230.characterSelectRosterExpanded)
		{
			goto dontDrawSelectCharacter;
		}

		DecalFont_DrawLine(sdata->lngStrings[LNG_SELECT_CHARACTER_SELECT], posX + MM_CHARACTER_SELECT_3P_TITLE_X, posY + MM_CHARACTER_SELECT_3P_SELECT_Y,
		                   FONT_BIG, (JUSTIFY_CENTER | ORANGE));
		characterSelectType = FONT_BIG;
		characterSelectString = sdata->lngStrings[LNG_CHARACTER];
		posX = posX + MM_CHARACTER_SELECT_3P_TITLE_X;
		posY = posY + MM_CHARACTER_SELECT_3P_CHARACTER_Y;
		break;

	case MM_CHARACTER_SELECT_LAYOUT_4P:
		if (sdata->gameProgress.unlocks[0] & UNLOCK_FAKE_CRASH)
		{
			goto dontDrawSelectCharacter;
		}

		DecalFont_DrawLine(sdata->lngStrings[LNG_SELECT_CHARACTER_SELECT], posX + MM_CHARACTER_SELECT_4P_TITLE_X, posY + MM_CHARACTER_SELECT_4P_SELECT_Y,
		                   FONT_CREDITS, (JUSTIFY_CENTER | ORANGE));
		characterSelectType = FONT_CREDITS;
		characterSelectString = sdata->lngStrings[LNG_CHARACTER];
		posX = posX + MM_CHARACTER_SELECT_4P_TITLE_X;
		posY = posY + MM_CHARACTER_SELECT_4P_CHARACTER_Y;
		break;

	case MM_CHARACTER_SELECT_LAYOUT_1P_LIMITED:
	case MM_CHARACTER_SELECT_LAYOUT_2P_LIMITED:
		characterSelectType = FONT_BIG;
		characterSelectString = sdata->lngStrings[LNG_SELECT_CHARACTER];
		posX = posX + MM_CHARACTER_SELECT_LIMITED_TITLE_X;
		posY = posY + MM_CHARACTER_SELECT_LIMITED_TITLE_Y;
		break;

	default:
		goto dontDrawSelectCharacter;
	}

	DecalFont_DrawLine(characterSelectString, posX, posY, characterSelectType, (JUSTIFY_CENTER | ORANGE));

dontDrawSelectCharacter:

	/* Page indicator ("1 / 2") */
	if (NativeCustomRacer_GetPageCount() > 1)
	{
		char pageBuf[16];
		snprintf(pageBuf, sizeof(pageBuf), "%d / %d",
		         NativeCustomRacer_GetCurrentPage() + 1,
		         NativeCustomRacer_GetPageCount());
		DecalFont_DrawLine(pageBuf, 0x100, 0x0A, FONT_SMALL, (JUSTIFY_CENTER | ORANGE));
	}

	for (s32 playerIndex = 0; playerIndex < gGT->numPlyrNextGame; playerIndex++)
	{
		/* === §8.1 Fix B+ (Option 1 refined): off-page handling ===
		 * Not confirmed (bit clear):
		 *   -> auto-join to the first free icon (avoids collision between
		 *      players auto-joining on the same frame).
		 * Confirmed (bit set):
		 *   -> off-page. L1+R1 rejoins. Triangle/Square unconfirms and
		 *      adapts to the current page (auto-join on next frame). */
		if (iconPerPlayer[playerIndex] < 0)
		{
			u16 playerBit = (u16)(1 << playerIndex);

			if ((sdata->characterSelectFlags & playerBit) == 0)
			{
				/* Auto-join to a free icon. */
				s16 targetIcon = MM_Characters_FindFreeIcon((s16)playerIndex);
				iconPerPlayer[playerIndex] = targetIcon;
				data.characterIDs[playerIndex] = D230.activeCharacterSelectMeta[targetIcon].characterID;
				/* fall through to the normal body with targetIcon */
			}
			else
			{
				u32 btn = sdata->buttonTapPerPlayer[playerIndex];

				if (D230.characterSelectMenuState == IN_MENU &&
				    ((btn & (BTN_L1 | BTN_R1)) == (BTN_L1 | BTN_R1)))
				{
					s16 targetIcon = MM_Characters_FindFreeIcon((s16)playerIndex);
					iconPerPlayer[playerIndex] = targetIcon;
					data.characterIDs[playerIndex] = D230.activeCharacterSelectMeta[targetIcon].characterID;
					sdata->characterSelectFlags &= ~playerBit;
					sdata->buttonTapPerPlayer[playerIndex] &= ~(BTN_L1 | BTN_R1);
					/* fall through to the normal body with targetIcon */
				}
				else if (D230.characterSelectMenuState == IN_MENU &&
				         ((btn & MM_CHARACTER_SELECT_INPUT_BACK) != 0))
				{
					OtherFX_Play(2, 1);
					sdata->characterSelectFlags &= ~playerBit;
					sdata->buttonTapPerPlayer[playerIndex] = 0;
					continue;
				}
				else
				{
					continue;
				}
			}
		}
		/* ================================================ */

		u16 playerSelectFlag = (u16)(1 << playerIndex);
		s16 currentIcon = iconPerPlayer[playerIndex];
		s16 candidateIcon = currentIcon;
		b32 playerSelectedBeforeInput = (((int)(s16)sdata->characterSelectFlags >> playerIndex) & 1U) != 0;

		Color playerColor;
		MM_Characters_AnimateColors((u8 *)&playerColor, playerIndex, (int)(s16)(sdata->characterSelectFlags & playerSelectFlag));

		struct CharacterSelectMeta *preInputCharacterMeta = &D230.activeCharacterSelectMeta[currentIcon];
		u32 button = sdata->buttonTapPerPlayer[playerIndex];

		if ((D230.characterSelectMenuState == IN_MENU) &&
		    ((button & (MM_CHARACTER_SELECT_INPUT_DPAD | MM_CHARACTER_SELECT_INPUT_MENU)) != 0))
		{
			if (!playerSelectedBeforeInput)
			{
				if ((button & MM_CHARACTER_SELECT_INPUT_DPAD) != 0)
				{
					hitNavigationDeadEnd = 0;

					if ((button & BTN_UP) == 0)
					{
						if ((button & BTN_DOWN) == 0)
						{
							direction = CHARACTER_SELECT_DIR_LEFT;

							if ((button & BTN_LEFT) != 0)
							{
								goto LAB_800aec08;
							}

							direction = CHARACTER_SELECT_DIR_RIGHT;
							D230.characterSelectPlayerState.modelMoveDir[playerIndex] = MM_CHARACTER_SELECT_MODEL_MOVE_NEXT;
						}
						else
						{
							direction = CHARACTER_SELECT_DIR_DOWN;
							D230.characterSelectPlayerState.modelMoveDir[playerIndex] = MM_CHARACTER_SELECT_MODEL_MOVE_NEXT;
						}
					}
					else
					{
						direction = CHARACTER_SELECT_DIR_UP;
					LAB_800aec08:
						D230.characterSelectPlayerState.modelMoveDir[playerIndex] = MM_CHARACTER_SELECT_MODEL_MOVE_PREV;
					}

					previousCandidateIcon = candidateIcon;
					do
					{
						candidateIcon = MM_Characters_GetNextDriver(direction, previousCandidateIcon);
						alternateIcon = candidateIcon;

						if (candidateIcon == previousCandidateIcon)
						{
							hitNavigationDeadEnd = 1;
							nextIcon = MM_Characters_GetNextDriver(direction, (int)(s16)currentIcon);
							nextIconCopy = (int)nextIcon;
							candidateIcon = MM_Characters_GetNextDriver(D230.characterSelectFallbackDirection1[direction], nextIconCopy);
							intermediateIcon = (int)(s16)candidateIcon;

							if ((((intermediateIcon == alternateIcon) || (nextIconCopy == alternateIcon)) || (nextIconCopy == intermediateIcon)) ||
							    MM_Characters_boolIsInvalid(iconPerPlayer, intermediateIcon, playerIndex))
							{
								nextIcon = MM_Characters_GetNextDriver(D230.characterSelectFallbackDirection1[direction], (int)(s16)currentIcon);
								intermediateIcon = (int)nextIcon;
								candidateIcon = MM_Characters_GetNextDriver(direction, intermediateIcon);
								alternateIcon = (int)(s16)candidateIcon;

								if (((alternateIcon == previousCandidateIcon) || (intermediateIcon == previousCandidateIcon)) ||
								    ((intermediateIcon == alternateIcon || MM_Characters_boolIsInvalid(iconPerPlayer, alternateIcon, playerIndex))))
								{
									nextIcon = MM_Characters_GetNextDriver(direction, (int)(s16)currentIcon);
									intermediateIcon = (int)nextIcon;
									candidateIcon = MM_Characters_GetNextDriver(D230.characterSelectFallbackDirection2[direction], intermediateIcon);
									alternateIcon = (int)(s16)candidateIcon;

									if (((alternateIcon == previousCandidateIcon) || (intermediateIcon == previousCandidateIcon)) ||
									    ((intermediateIcon == alternateIcon || MM_Characters_boolIsInvalid(iconPerPlayer, alternateIcon, playerIndex))))
									{
										nextIcon = MM_Characters_GetNextDriver(D230.characterSelectFallbackDirection2[direction], (int)(s16)currentIcon);
										intermediateIcon = (int)nextIcon;
										candidateIcon = MM_Characters_GetNextDriver(direction, intermediateIcon);
										alternateIcon = (int)(s16)candidateIcon;

										if ((((alternateIcon == previousCandidateIcon) || (intermediateIcon == previousCandidateIcon)) ||
										     (intermediateIcon == alternateIcon)) ||
										    MM_Characters_boolIsInvalid(iconPerPlayer, alternateIcon, playerIndex))
										{
											candidateIcon = (u32)currentIcon;
										}
									}
								}
							}
						}
						/* === §8.1 Diff 5a: compare by characterID === */
						candidateInUseByOtherPlayer = MM_Characters_CharIDInUse(
						    D230.activeCharacterSelectMeta[(s32)candidateIcon].characterID, (s16)playerIndex);
						/* =========================================== */

						if (previousCandidateIcon << 0x10 != candidateIcon << 0x10)
						{
							OtherFX_Play(0, 1);
						}
						if (hitNavigationDeadEnd != 0)
						{
							deadEndCandidateAvailable = !candidateInUseByOtherPlayer;
							candidateInUseByOtherPlayer = false;
							if (deadEndCandidateAvailable)
							{
								break;
							}
							candidateIcon = (u32)currentIcon;
						}
						previousCandidateIcon = candidateIcon;
					} while (candidateInUseByOtherPlayer);
				}
				currentIcon = (u16)candidateIcon;

				/* === §8.1 Diff 5b: compare by characterID === */
				if (MM_Characters_CharIDInUse(
				        D230.activeCharacterSelectMeta[(s32)candidateIcon].characterID, (s16)playerIndex))
				{
					candidateIcon = (u32)(u16)iconPerPlayer[playerIndex];
				}
				currentIcon = (u16)candidateIcon;
				/* =========================================== */

				if (((sdata->buttonTapPerPlayer)[playerIndex] & MM_CHARACTER_SELECT_INPUT_CONFIRM) != 0)
				{
					sdata->characterSelectFlags = sdata->characterSelectFlags | (u16)(1 << playerIndex);

					u8 numPlyrNextGame = gGT->numPlyrNextGame;

					OtherFX_Play(1, 1);

					if ((int)(s16)sdata->characterSelectFlags == (1 << numPlyrNextGame) - 1)
					{
						D230.characterSelectExitsForward = 1;
						D230.characterSelectMenuState = EXITING_MENU;
					}
				}

				if (
				    ((playerIndex & 0xffff) == 0) &&
				    ((sdata->buttonTapPerPlayer[0] & MM_CHARACTER_SELECT_INPUT_BACK) != 0))
				{
					D230.characterSelectExitsForward = 0;
					D230.characterSelectMenuState = EXITING_MENU;

					OtherFX_Play(2, 1);
				}
			}
			else
			{
				if ((button & MM_CHARACTER_SELECT_INPUT_BACK) != 0)
				{
					OtherFX_Play(2, 1);

					sdata->characterSelectFlags = sdata->characterSelectFlags & ~playerSelectFlag;
				}
			}

			sdata->buttonTapPerPlayer[playerIndex] = 0;
		}

		iconPerPlayer[playerIndex] = currentIcon;

		struct TransitionMeta *currentIconTransition = &D230.characterSelectTransitionMeta[currentIcon];

		b32 playerSelectedAfterInput = ((sdata->characterSelectFlags >> playerIndex) & 1U) != 0;
		Color outlineColor;
		if (!playerSelectedAfterInput)
		{
			DecalFont_DrawLine(D230.playerNumberStrings[playerIndex], currentIconTransition->currX + (u32)preInputCharacterMeta->posX - 6,
			                   currentIconTransition->currY + (u32)preInputCharacterMeta->posY - 3, FONT_BIG, WHITE);
			outlineColor = playerColor;
		}
		else
		{
			outlineColor = D230.characterSelect_Outline;
		}

		drawRect.x = currentIconTransition->currX + preInputCharacterMeta->posX;
		drawRect.y = currentIconTransition->currY + preInputCharacterMeta->posY;
		drawRect.w = MM_CHARACTER_SELECT_ICON_RECT_W;
		drawRect.h = MM_CHARACTER_SELECT_ICON_RECT_H;

		RECTMENU_DrawOuterRect_HighLevel(&drawRect, outlineColor, 0, ot);
	}

	MM_Characters_PreventOverlap();

	struct CharacterSelectMeta *iconDrawMeta = D230.activeCharacterSelectMeta;

	for (s32 iconIndex = 0; iconIndex < MM_CHARACTER_SELECT_ICON_COUNT; iconIndex++)
	{
		s16 unlockRequirement = iconDrawMeta->unlockFlags;
		if (
		    (unlockRequirement == MM_CHARACTER_UNLOCK_ALWAYS) ||
		    CHECK_ADV_BIT(sdata->gameProgress.unlocks, unlockRequirement))
		{
			Color iconColor = D230.characterSelect_NeutralColor;

			for (s32 playerIndex = 0; playerIndex < gGT->numPlyrNextGame; playerIndex++)
			{
				b32 playerSelected = (((int)(s16)sdata->characterSelectFlags >> (playerIndex & 0x1fU)) & 1U) != 0;
				if (((s16)iconIndex == iconPerPlayer[playerIndex]) && playerSelected)
				{
					iconColor = D230.characterSelect_ChosenColor;
				}
			}

			struct TransitionMeta *iconTransition = &D230.characterSelectTransitionMeta[iconIndex];

			RECTMENU_DrawPolyGT4(gGT->ptrIcons[GET_METADATA(iconDrawMeta->characterID)->iconID],
			                     iconTransition->currX + iconDrawMeta->posX + MM_CHARACTER_SELECT_ICON_DECAL_OFFSET_X,
			                     iconTransition->currY + iconDrawMeta->posY + MM_CHARACTER_SELECT_ICON_DECAL_OFFSET_Y,

			                     &gGT->backBuffer->primMem, gGT->pushBuffer_UI.ptrOT,

			                     ColorCode_GetPacked(&iconColor), ColorCode_GetPacked(&iconColor), ColorCode_GetPacked(&iconColor),
			                     ColorCode_GetPacked(&iconColor), TRANS_50_DECAL, FP(1.0));
		}

		iconDrawMeta++;
	}

	struct CharacterSelectMeta *activeCharacterSelectMeta = D230.activeCharacterSelectMeta;

	/* === §8.1 Diff 6: do not overwrite off-page players' characterIDs === */
	for (s32 playerIndex = 0; playerIndex < MM_CHARACTER_SELECT_MAX_PLAYERS; playerIndex++)
	{
		if (iconPerPlayer[playerIndex] < 0)
			continue;
		data.characterIDs[playerIndex] = activeCharacterSelectMeta[(int)iconPerPlayer[playerIndex]].characterID;
	}
	/* ================================================================== */

	for (s32 playerIndex = 0; playerIndex < gGT->numPlyrNextGame; playerIndex++)
	{
		/* === §8.1 Fix A2: model rotation always advances, even when
		 * the player is off-page, so their window doesn't look
		 * "frozen" while waiting for L1+R1 or Triangle. === */
		D230.characterSelectPlayerState.angle[playerIndex] += MM_CHARACTER_SELECT_SPIN_STEP;
		/* ============================================================ */

		/* === §8.1 Fix A: off-page has no cursor === */
		if (iconPerPlayer[playerIndex] < 0)
			continue;
		/* ========================================= */

		s16 playerIcon = iconPerPlayer[playerIndex];
		activeCharacterSelectMeta = &D230.activeCharacterSelectMeta[playerIcon];
		b32 playerSelected = (((int)(s16)sdata->characterSelectFlags >> playerIndex) & 1U) != 0;

		if (!playerSelected)
		{
			Color animatedColor;
			u16 selectedPlayerFlag = (u16)(1 << playerIndex);
			MM_Characters_AnimateColors((u8 *)&animatedColor, playerIndex,
			                            (int)(s16)(sdata->characterSelectFlags & selectedPlayerFlag));

			animatedColor.r = (u8)((int)((u32)animatedColor.r << 2) / 5);
			animatedColor.g = (u8)((int)((u32)animatedColor.g << 2) / 5);
			animatedColor.b = (u8)((int)((u32)animatedColor.b << 2) / 5);

			struct TransitionMeta *selectedIconTransition = &D230.characterSelectTransitionMeta[playerIcon];

			drawRect.x = selectedIconTransition->currX + activeCharacterSelectMeta->posX + MM_CHARACTER_SELECT_HIGHLIGHT_OFFSET_X;
			drawRect.y = selectedIconTransition->currY + activeCharacterSelectMeta->posY + MM_CHARACTER_SELECT_HIGHLIGHT_OFFSET_Y;
			drawRect.w = MM_CHARACTER_SELECT_HIGHLIGHT_W;
			drawRect.h = MM_CHARACTER_SELECT_HIGHLIGHT_H;

			CTR_Box_DrawSolidBox(&drawRect, animatedColor, ot);
		}
		if ((D230.characterSelectModelMoveTimer[playerIndex] == 0) &&
		    (D230.characterSelectPlayerState.currentCharacterID[playerIndex] == data.characterIDs[playerIndex]))
		{
			u8 numPlyrNextGame = gGT->numPlyrNextGame;
			u32 fontType = FONT_CREDITS;

			if (numPlyrNextGame >= 3)
			{
				fontType = FONT_SMALL;
			}

			struct TransitionMeta *driverWindowTransition =
			    &D230.characterSelectTransitionMeta[playerIndex + MM_CHARACTER_SELECT_DRIVER_WINDOW_TRANSITION_FIRST];
			SVec2 *windowPos = &D230.activeCharacterSelectWindowPos[playerIndex];
			s16 nameBaseY = driverWindowTransition->currY + windowPos->y;
			s16 nameYOffset = (s16)((((u32)(numPlyrNextGame < 3) ^ 1) << 0x12) >> 0x10);
			s16 nameY;

			if ((numPlyrNextGame == 4) && (playerIndex > 1))
			{
				nameY = nameBaseY + nameYOffset + MM_CHARACTER_SELECT_4P_NAME_BOTTOM_OFFSET;
			}
			else
			{
				nameY = nameBaseY + D230.characterSelectNameTextY + nameYOffset;
			}

			/* === Phase 2: custom racers still have no LNG strings (Phase 5).
			 * Guard against reading lngStrings[-1]. === */
			s16 nameLNG = GET_METADATA(activeCharacterSelectMeta->characterID)->name_LNG_long;
			if (nameLNG >= 0)
			{
				DecalFont_DrawLine(sdata->lngStrings[nameLNG],
				                   (int)driverWindowTransition->currX + windowPos->x + (int)((u32)D230.characterSelectWindowWidth >> 1), (int)nameY, fontType,
				                   (JUSTIFY_CENTER | ORANGE));
			}
			/* ============================================================ */
		}
	}

	activeCharacterSelectMeta = D230.activeCharacterSelectMeta;

	for (s32 iconIndex = 0; iconIndex < MM_CHARACTER_SELECT_ICON_COUNT; iconIndex++)
	{
		s16 unlockRequirement = activeCharacterSelectMeta[iconIndex].unlockFlags;

		if (
		    (unlockRequirement == MM_CHARACTER_UNLOCK_ALWAYS) ||
		    CHECK_ADV_BIT(sdata->gameProgress.unlocks, unlockRequirement))
		{
			struct TransitionMeta *iconTransition = &D230.characterSelectTransitionMeta[iconIndex];

			drawRect.x = iconTransition->currX + activeCharacterSelectMeta[iconIndex].posX;
			drawRect.y = iconTransition->currY + activeCharacterSelectMeta[iconIndex].posY;
			drawRect.w = MM_CHARACTER_SELECT_ICON_RECT_W;
			drawRect.h = MM_CHARACTER_SELECT_ICON_RECT_H;

			RECTMENU_DrawInnerRect(&drawRect, 0, ot);
		}
	}

	SVec2 *windowPos = D230.activeCharacterSelectWindowPos;

	for (s32 playerIndex = 0; playerIndex < gGT->numPlyrNextGame; playerIndex++)
	{
		struct TransitionMeta *driverWindowTransition = &D230.characterSelectTransitionMeta[playerIndex + MM_CHARACTER_SELECT_DRIVER_WINDOW_TRANSITION_FIRST];
		b32 playerSelected = (((int)(s16)sdata->characterSelectFlags >> playerIndex) & 1U) != 0;
		Color animatedColor;

		drawRect.x = driverWindowTransition->currX + windowPos->x;
		drawRect.y = driverWindowTransition->currY + windowPos->y;
		drawRect.w = D230.characterSelectWindowWidth;
		drawRect.h = D230.characterSelectWindowHeight;

		MM_Characters_AnimateColors((u8 *)&animatedColor, playerIndex,
		                            playerSelected ^ 1);

		RECTMENU_DrawOuterRect_HighLevel(&drawRect, animatedColor, 0, ot);

		if (playerSelected)
		{
			RECT r58;
			r58.x = drawRect.x;
			r58.y = drawRect.y;
			r58.w = drawRect.w;
			r58.h = drawRect.h;

			for (s32 borderIndex = 0; borderIndex < MM_CHARACTER_SELECT_SELECTED_BORDER_COUNT; borderIndex++)
			{
				r58.x += MM_CHARACTER_SELECT_SELECTED_BORDER_INSET_X;
				r58.y += MM_CHARACTER_SELECT_SELECTED_BORDER_INSET_Y;
				r58.w -= MM_CHARACTER_SELECT_SELECTED_BORDER_SHRINK_W;
				r58.h -= MM_CHARACTER_SELECT_SELECTED_BORDER_SHRINK_H;

				animatedColor.r = (u8)((int)((u32)animatedColor.r << 2) / 5);
				animatedColor.g = (u8)((int)((u32)animatedColor.g << 2) / 5);
				animatedColor.b = (u8)((int)((u32)animatedColor.b << 2) / 5);

				RECTMENU_DrawOuterRect_HighLevel(&r58, animatedColor, 0, ot);
			}
		}
		windowPos++;

		RECTMENU_DrawInnerRect(&drawRect, 9, &ot[3]);

		drawRect.x = 0;
		drawRect.y = 0;

		RECTMENU_DrawRwdBlueRect(&drawRect, &D230.characterSelect_BlueRectColors[0], &gGT->pushBuffer[playerIndex].ptrOT[0x3ff], &gGT->backBuffer->primMem);
	}
	return;
}