#include <common.h>
#include <platform/native_custom_racer.h>
#include <platform/native_adventure_pack.h>
#include <widescreen.h>

enum GarageInputMask
{
	GARAGE_INPUT_HORIZONTAL = BTN_LEFT | BTN_RIGHT,
	GARAGE_INPUT_MENU = BTN_TRIANGLE | BTN_CROSS_one | BTN_CIRCLE | BTN_SQUARE_one,
	GARAGE_INPUT_CONFIRM = BTN_CROSS_one | BTN_CIRCLE,
	GARAGE_INPUT_BACK = BTN_TRIANGLE | BTN_SQUARE_one,
};

enum
{
	GARAGE_STAT_BAR_RATE = 3,
	GARAGE_STAT_BAR_SEGMENT_COUNT = 6,
	GARAGE_STAT_BAR_SEGMENT_WIDTH = 13,
	GARAGE_STAT_BAR_ROW_STEP = 15,
	GARAGE_STAT_BAR_POLY_G4_CODE = 0x38,
	GARAGE_STAT_BAR_POLY_G4_COLOR_CODE = GARAGE_STAT_BAR_POLY_G4_CODE << 24,
	GARAGE_STAT_NAME_SPEED_Y = 30,
	GARAGE_STAT_NAME_ACCEL_Y = 0x2d,
	GARAGE_STAT_NAME_TURN_Y = 60,
	GARAGE_CLASS_NAME_Y = 15,
	GARAGE_STAT_BAR_START_Y = 33,
	GARAGE_STAT_BAR_END_Y = 40,
	GARAGE_STAT_BAR_SHADOW_Y = 34,
	GARAGE_STAT_BAR_HEIGHT = 7,
	GARAGE_STAT_BAR_SHADOW_HEIGHT = 5,
	GARAGE_STAT_BOX_Y = 11,
	GARAGE_STAT_BOX_HEIGHT = 68,
	GARAGE_STAT_BOX_PADDING_X = 6,
	GARAGE_OSK_DELAY_FRAMES = 60,
	GARAGE_CAMERA_FRAME_STEP = 30,
	GARAGE_CAMERA_WRAP_RIGHT_FRAME = 240,
	GARAGE_CAMERA_WRAP_LEFT_FRAME = 210,
	GARAGE_CHARACTER_NAME_X = 0x100,
	GARAGE_CHARACTER_NAME_Y = 0xb4,
	GARAGE_CHARACTER_ARROW_Y = 187,
	GARAGE_CHARACTER_ARROW_LEFT_BASE_X = 236,
	GARAGE_CHARACTER_ARROW_RIGHT_BASE_X = 274,
	GARAGE_CHARACTER_ARROW_ICON_INDEX = 0x38,
	GARAGE_CHARACTER_ARROW_SCALE = 0x1000,
	GARAGE_CHARACTER_ARROW_ROT_LEFT = 0x800,
};

#ifndef ADV_CAM_AIM_HEIGHT
#define ADV_CAM_AIM_HEIGHT  0
#endif
#define ADV_CAM_YAW_BIAS    0
#define ADV_CAM_PITCH_BIAS  0

static int s_garageForceSnap = 0;
static int s_pendingAmbientStart = 0;
static int s_garagePackTimer = 0;
static char s_garagePackName[64] = "";
static int s_targetGarageSlot = -1;

extern const char *NativeSettings_GetGaragePack(void);
extern void NativeSettings_SetGaragePack(const char *id);
extern int LevelRegistry_GetAdventureGarageCount(void);
extern const struct LevelDef *LevelRegistry_GetAdventureGarageByIndex(int index);
extern void MainRaceTrack_RequestLoad(int levelID);


void CS_Garage_ZoomOut(s16 zoomState)
{
	if (zoomState != 0)
	{
		gGarage.numFramesCurr_ZoomIn = gGarage.numFramesMax_Zoom;
		gGarage.numFramesCurr_ZoomOut = gGarage.numFramesMax_Zoom;
	}
	else
	{
		gGarage.numFramesCurr_ZoomIn = 0;
		gGarage.numFramesCurr_ZoomOut = 0;
	}

	gGarage.numFramesCurr_GarageMove = 0;
	gGarage.boolSelected = 0;
	gGarage.delayOneSecond = 0;

	sdata->gGT->gameMode2 &= ~(GARAGE_OSK);

	if (zoomState == 0)
	{
		Garage_Init();
		Garage_Enter(sdata->advCharSelectIndex_curr);
		Audio_SetState_Safe(AUDIO_GARAGE);
	}
}

void CS_Garage_MenuProc(struct RectMenu *menu)
{
	if (s_pendingAmbientStart) {
	    s_pendingAmbientStart = 0;
	    { extern void NativeCustomRacer_UpdateGarageAmbients(int);
	      NativeCustomRacer_UpdateGarageAmbients((int)sdata->advCharSelectIndex_curr); }
	    fprintf(stderr, "[AmbientDiag] MenuProc: deferred ambient start\n");
	}
	(void)menu;
	s16 garageFrames;
	s16 *statBarLength;
	u16 classNamePosX;
	u32 statNamePosX;
	u32 statBarPosX;

    static u32 s_dbg_lastTap = 0;
    if (sdata->AnyPlayerTap != s_dbg_lastTap) {
        fprintf(stderr, "[BTN] tap=0x%08X hold=0x%08X", sdata->AnyPlayerTap, sdata->AnyPlayerHold);
        fprintf(stderr, " L1=0x%X R1=0x%X", BTN_L1, BTN_R1);
        fprintf(stderr, "\n");
        s_dbg_lastTap = sdata->AnyPlayerTap;
    }
    
    u32 currSelectIndex = sdata->advCharSelectIndex_curr;

    // --- GARAGE MENU ---
    static int s_menu_open = 0;
    static int s_menu_sel_row = 0;
    static int s_menu_sel_col = 0;
    static int s_menu_scroll = 0;

    if (!s_menu_open && (sdata->AnyPlayerTap & BTN_START)) {
        s_menu_open = 1;
        s_menu_sel_row = 0;
        s_menu_sel_col = 0;
        s_menu_scroll = 0;
        extern void NativeCustomRacer_ForceReapply(void); 
        NativeCustomRacer_ForceReapply(); 
    }

    if (s_menu_open) {
        struct GameTracker *gGT = sdata->gGT;
        u32 *ot = gGT->backBuffer->otMem.uiOT;
        int count = LevelRegistry_GetAdventureGarageCount();
        int total = count + 1; 

        // Caja centrada (460 de ancho)
        int origW_bg = 460;
        int compW_bg = CTR_WIDESCREEN_SCALE_X(origW_bg);
        int bgX = (512 - compW_bg) / 2;
        int bgHeight = 20 + (total > 5 ? 5 : total) * 28 + 20;
        int bgY = (240 - bgHeight) / 2;

        RECT bg = {bgX, bgY, compW_bg, bgHeight};

        DecalFont_DrawLine("SELECT GARAGE", 256, bgY + 6, FONT_BIG, JUSTIFY_CENTER | ORANGE);

        if (s_menu_sel_row < s_menu_scroll) s_menu_scroll = s_menu_sel_row;
        if (s_menu_sel_row >= s_menu_scroll + 5) s_menu_scroll = s_menu_sel_row - 4;

        for (int i = s_menu_scroll; i < total && i < s_menu_scroll + 5; i++) {
            int y = bgY + 30 + (i - s_menu_scroll) * 28;
            const char *name = (i < count) ? LevelRegistry_GetAdventureGarageByIndex(i)->name : "RETAIL";
            char short_name[16];
            if (strlen(name) > 12) {
                strncpy(short_name, name, 11); short_name[11] = '\0'; strcat(short_name, "..");
            } else {
                strcpy(short_name, name);
            }

            DecalFont_DrawLine(short_name, Widescreen_ScaleAboutX(60, 256), y, FONT_SMALL, ORANGE);

            for (int j = 0; j < 8; j++) {
                int charID = -1;
                if (i < count) {
                    const struct LevelDef *p = LevelRegistry_GetAdventureGarageByIndex(i);
                    const char *slug = p->adventureCharSlugs[j][0] ? p->adventureCharSlugs[j] : p->garageOnlySlugs[j];
                    if (slug[0]) charID = NativeCustomRacer_GetCharacterIDFromFolder(slug);
                } else {
                    charID = j;
                }

                if (charID >= 0) {
                    struct Icon *icon = NativeCustomRacer_GetIconPtr(charID);
                    if (icon) {
                        int ix = 200 + j * 32;
                        RECTMENU_DrawPolyGT4(icon, Widescreen_ScaleAboutX(ix, 256), y - 6,
                            &gGT->backBuffer->primMem, gGT->pushBuffer_UI.ptrOT,
                            0x80808080, 0x80808080, 0x80808080, 0x80808080,
                            TRANS_50_DECAL, FP(0.75));

                        if (i == s_menu_sel_row && s_menu_sel_col == j + 1) {
                            RECT drawRect;
                            drawRect.x = Widescreen_ScaleAboutX(ix - 3, 256);
                            drawRect.y = y - 9;
                            drawRect.w = 34;
                            drawRect.h = 23;

                            int oOldW = drawRect.w;
                            drawRect.w = CTR_WIDESCREEN_SCALE_X(oOldW);
                            drawRect.x += ((oOldW - drawRect.w) / 2) + 1;

                            RECTMENU_DrawOuterRect_HighLevel(&drawRect, sdata->menuRowHighlight_Normal, 0, ot);
                        }
                    }
                }
            }

            if (i == s_menu_sel_row && s_menu_sel_col == 0) {
                int origW_cur = 130;
                int compW_cur = CTR_WIDESCREEN_SCALE_X(origW_cur);
                RECT cur = {Widescreen_ScaleAboutX(55, 256), y - 4, compW_cur, 16};
                CTR_Box_DrawClearBox(&cur, &sdata->menuRowHighlight_Normal, TRANS_50_DECAL, ot);
            }
        }

        // Dibujar la caja de fondo AL FINAL para que los textos no se oscurezcan
        RECTMENU_DrawInnerRect(&bg, 4, ot);

        int max_col = 0;
        if (s_menu_sel_row < count) {
            const struct LevelDef *p = LevelRegistry_GetAdventureGarageByIndex(s_menu_sel_row);
            for (int j = 0; j < 8; j++) {
                if (p->adventureCharSlugs[j][0] || p->garageOnlySlugs[j][0]) max_col = j + 1;
            }
        } else {
            max_col = 8;
        }

        if (sdata->AnyPlayerTap & BTN_DOWN) { s_menu_sel_row++; if (s_menu_sel_row >= total) s_menu_sel_row = 0; s_menu_sel_col = 0; }
        if (sdata->AnyPlayerTap & BTN_UP)   { s_menu_sel_row--; if (s_menu_sel_row < 0) s_menu_sel_row = total - 1; s_menu_sel_col = 0; }

        if (sdata->AnyPlayerTap & BTN_RIGHT) { s_menu_sel_col++; if (s_menu_sel_col > max_col) s_menu_sel_col = 0; }
        if (sdata->AnyPlayerTap & BTN_LEFT)  { s_menu_sel_col--; if (s_menu_sel_col < 0) s_menu_sel_col = max_col; }

        if (sdata->AnyPlayerTap & (BTN_TRIANGLE | BTN_SQUARE_one)) { s_menu_open = 0; }

        if (sdata->AnyPlayerTap & BTN_CROSS) {
            if (s_menu_sel_row == count) {
                NativeSettings_SetGaragePack("");
                s_targetGarageSlot = (s_menu_sel_col == 0) ? -1 : s_menu_sel_col - 1;
            } else {
                NativeSettings_SetGaragePack(LevelRegistry_GetAdventureGarageByIndex(s_menu_sel_row)->id);
                s_targetGarageSlot = (s_menu_sel_col == 0) ? 0 : s_menu_sel_col - 1;
            }
            extern void NativeAdventurePack_ActivateForLoad(void);
            NativeAdventurePack_ActivateForLoad();
            MainRaceTrack_RequestLoad(ADVENTURE_GARAGE);
            s_menu_open = 0;
        }
        return;
    }

    // --- L1/R1 SWITCHER ---
    if ((sdata->AnyPlayerTap & BTN_L1) || (sdata->AnyPlayerTap & BTN_R1))
    {
        fprintf(stderr, "[L1R1] Detectado!\n");
        int count = LevelRegistry_GetAdventureGarageCount();
        int total = count + 1; // +1 para Retail
        const char *curr = NativeSettings_GetGaragePack();
        int idx = -1;

        if (curr[0] == '\0') {
            idx = count; // Estamos en Retail
        } else {
            for (int i = 0; i < count; i++) {
                if (strcmp(LevelRegistry_GetAdventureGarageByIndex(i)->id, curr) == 0) {
                    idx = i;
                    break;
                }
            }
        }

        if (idx == -1) idx = 0; // Fallback

        if (sdata->AnyPlayerTap & BTN_R1) idx++; else idx--;
        if (idx < 0) idx = total - 1;
        if (idx >= total) idx = 0;

        if (idx == count) {
            fprintf(stderr, "[L1R1] Cambiando a: RETAIL\n");
            NativeSettings_SetGaragePack("");
            strncpy(s_garagePackName, "RETAIL", 63);
        } else {
            const struct LevelDef *n = LevelRegistry_GetAdventureGarageByIndex(idx);
            fprintf(stderr, "[L1R1] Cambiando a: %s\n", n->name);
            NativeSettings_SetGaragePack(n->id);
            strncpy(s_garagePackName, n->name, 63);
        }

        s_garagePackTimer = 120;
        extern void NativeAdventurePack_ActivateForLoad(void);
        NativeAdventurePack_ActivateForLoad(); // Crucial: avisa al LevelRegistry
        MainRaceTrack_RequestLoad(ADVENTURE_GARAGE);
        return;
    }

    // --- LOGICA RETAIL ORIGINAL ---
	struct GameTracker *gGT = sdata->gGT;
	struct PrimMem *primMem = &gGT->backBuffer->primMem;
	s16 currCharacterID = gGarage.garageCharacterIDs[currSelectIndex];
        {
                int packID = NativeAdventurePack_GetCharacterID(currSelectIndex);
                if (packID >= 0) currCharacterID = (s16)packID;
        }
	struct MetaDataCHAR *MDC = GET_METADATA(currCharacterID);
	int nameIndex = MDC->name_LNG_long;
	RECT r;
	Color white = MakeColor(0xFF, 0xFF, 0xFF);
	Color black = MakeColor(0, 0, 0);

	gGT->cameraDC[0].cameraMode = CAMERA_MODE_FREECAM;

	garageFrames = gGarage.numFramesCurr_GarageMove - 1;

	if (gGarage.numFramesCurr_GarageMove != 0)
	{
		goto update_garage_camera;
	}

	gGarage.unusedFrameCount++;

	for (int i = 0; i < 3; i++)
	{
		statBarLength = &gGarage.statBarLengths[i];
		s16 stat = gGarage.statBarTargetLengths[MDC->engineID * 3 + i];

		if (*statBarLength < stat)
		{
			*statBarLength = *statBarLength + GARAGE_STAT_BAR_RATE;
		}
		if (stat < *statBarLength)
		{
			*statBarLength = stat;
		}
	}

	int statsSide = NativeAdventurePack_GetStatsSide(currSelectIndex);
	if (statsSide == 1 || nameIndex == LNG_TINY_TIGER || nameIndex == LNG_PURA_FULL)
	{
		statNamePosX = 129;
		classNamePosX = 128;
		statBarPosX = 139;
	}
	else
	{
		statNamePosX = 383;
		classNamePosX = 384;
		statBarPosX = 393;
	}

	DecalFont_DrawLine(sdata->lngStrings[LNG_SPEED], Widescreen_ScaleAboutX(statNamePosX, 256), GARAGE_STAT_NAME_SPEED_Y, FONT_BIG, JUSTIFY_RIGHT | ORANGE_RED);
    
    // Timer para mostrar el nombre del pack (opcional)
    if (s_garagePackTimer > 0) {
        s_garagePackTimer--;
        DecalFont_DrawLine(s_garagePackName, 256, 160, FONT_BIG, JUSTIFY_CENTER | WHITE);
    }

	DecalFont_DrawLine(sdata->lngStrings[LNG_ACCEL], Widescreen_ScaleAboutX(statNamePosX, 256), GARAGE_STAT_NAME_ACCEL_Y, FONT_BIG, JUSTIFY_RIGHT | LIME_GREEN);
	DecalFont_DrawLine(sdata->lngStrings[LNG_TURN], Widescreen_ScaleAboutX(statNamePosX, 256), GARAGE_STAT_NAME_TURN_Y, FONT_BIG, JUSTIFY_RIGHT | BLUE);

	int engineID = MDC->engineID;

	int classStringIndex = 0;

	if (engineID == SPEED)
	{
		classStringIndex = 2;
	}

	if (engineID < SPEED)
	{
		classStringIndex = 1;
	}

	u16 statBarStart_Y = GARAGE_STAT_BAR_START_Y;
	u16 statBarEnd_Y = GARAGE_STAT_BAR_END_Y;
	u16 statBarShadows_Y = GARAGE_STAT_BAR_SHADOW_Y;

	DecalFont_DrawLine(sdata->lngStrings[gGarage.classStringIDs[classStringIndex]], Widescreen_ScaleAboutX(classNamePosX, 256), GARAGE_CLASS_NAME_Y, FONT_BIG, (JUSTIFY_CENTER | ORANGE));

	for (int i = 0; i < 3; i++)
	{
		statBarLength = &gGarage.statBarLengths[i];

		r.x = Widescreen_ScaleAboutX(statBarPosX, 256);
		r.y = statBarStart_Y;
		r.w = CTR_WIDESCREEN_SCALE_X(*statBarLength);
		r.h = GARAGE_STAT_BAR_HEIGHT;
		CTR_Box_DrawWireBox(&r, &white, gGT->pushBuffer_UI.ptrOT, primMem);

		r.x = Widescreen_ScaleAboutX(statBarPosX, 256) + CTR_WIDESCREEN_SCALE_X(1);
		r.y = statBarShadows_Y;
		r.w = CTR_WIDESCREEN_SCALE_X(*statBarLength) - CTR_WIDESCREEN_SCALE_X(2);
		r.h = GARAGE_STAT_BAR_SHADOW_HEIGHT;
		CTR_Box_DrawWireBox(&r, &black, gGT->pushBuffer_UI.ptrOT, primMem);

		int segmentLen = GARAGE_STAT_BAR_SEGMENT_WIDTH;
		int segmentStart = 0;
		int segmentEnd = segmentLen;

		for (int segmentIndex = 0; segmentIndex < GARAGE_STAT_BAR_SEGMENT_COUNT; segmentIndex++)
		{
			u32 *barColor = &gGarage.statBarSegmentColors[segmentIndex];
			s16 currSegmentLen = (s16)segmentLen;

			if (*statBarLength <= segmentEnd)
			{
				currSegmentLen = *statBarLength - segmentStart;
			}

			if ((int)currSegmentLen << 0x10 < 0)
			{
				currSegmentLen = 0;
			}

			if (segmentStart + currSegmentLen <= *statBarLength)
			{
				POLY_G4 *p = primMem->cursor;

				if (primMem->end < (void *)p)
				{
					return;
				}

				primMem->cursor = p + 1;

				CtrGpu_WriteColorCode(&p->r0, barColor[0] | GARAGE_STAT_BAR_POLY_G4_COLOR_CODE);
				CtrGpu_WriteColorCode(&p->r1, barColor[1] | GARAGE_STAT_BAR_POLY_G4_COLOR_CODE);
				CtrGpu_WriteColorCode(&p->r2, barColor[0] | GARAGE_STAT_BAR_POLY_G4_COLOR_CODE);
				CtrGpu_WriteColorCode(&p->r3, barColor[1] | GARAGE_STAT_BAR_POLY_G4_COLOR_CODE);

				s16 segmentX = statBarPosX + segmentStart;
				s16 segmentX_comp = Widescreen_ScaleAboutX(segmentX, 256);
				s16 segmentX2_comp = Widescreen_ScaleAboutX(segmentX + currSegmentLen, 256);

				p->x0 = segmentX_comp;
				p->y0 = statBarStart_Y;
				p->x1 = segmentX2_comp;
				p->y1 = statBarStart_Y;
				p->x2 = segmentX_comp;
				p->y2 = statBarEnd_Y;
				p->x3 = segmentX2_comp;
				p->y3 = statBarEnd_Y;

				addPolyG4(gGT->pushBuffer_UI.ptrOT, p);
			}

			segmentStart += segmentLen;
			segmentEnd += segmentLen;
		}

		statBarStart_Y += GARAGE_STAT_BAR_ROW_STEP;
		statBarEnd_Y += GARAGE_STAT_BAR_ROW_STEP;
		statBarShadows_Y += GARAGE_STAT_BAR_ROW_STEP;
	}

	s16 classMaxLen = DecalFont_GetLineWidth(sdata->lngStrings[LNG_INTERMEDIATE], FONT_BIG);

	r.x = Widescreen_ScaleAboutX(classNamePosX, 256) - (classMaxLen >> 1) - CTR_WIDESCREEN_SCALE_X(GARAGE_STAT_BOX_PADDING_X);
	r.y = GARAGE_STAT_BOX_Y;
	r.w = classMaxLen + CTR_WIDESCREEN_SCALE_X(GARAGE_STAT_BOX_PADDING_X * 2);
	r.h = GARAGE_STAT_BOX_HEIGHT;

	RECTMENU_DrawInnerRect(&r, 4, gGT->backBuffer->otMem.uiOT);

	char *name = sdata->lngStrings[nameIndex];
        {
                const char *customName = NativeCustomRacer_GetDisplayName(currCharacterID);
                if (customName != NULL) name = (char *)customName;
        }

	DecalFont_DrawLine(name, GARAGE_CHARACTER_NAME_X, GARAGE_CHARACTER_NAME_Y, FONT_BIG, JUSTIFY_CENTER | ORANGE);

	int arrowColor = ORANGE;

	if ((sdata->frameCounter & 4) == 0)
	{
		arrowColor = RED;
	}

	u32 *arrowColors = data.ptrColor[(s32)arrowColor];
	int nameLen = DecalFont_GetLineWidth(name, FONT_BIG) >> 1;

	int arrowPos[2] = {Widescreen_ScaleAboutX(GARAGE_CHARACTER_ARROW_LEFT_BASE_X, 256) - nameLen, Widescreen_ScaleAboutX(GARAGE_CHARACTER_ARROW_RIGHT_BASE_X, 256) + nameLen};
	int arrowRot[2] = {GARAGE_CHARACTER_ARROW_ROT_LEFT, 0};

	struct Icon **iconPtrArray = ICONGROUP_GETICONS(gGT->iconGroup[4]);

	for (int i = 0; i < 2; i++)
	{
		DecalHUD_Arrow2D(iconPtrArray[GARAGE_CHARACTER_ARROW_ICON_INDEX], arrowPos[i], GARAGE_CHARACTER_ARROW_Y,
		                 primMem, gGT->pushBuffer_UI.ptrOT,
		                 arrowColors[0], arrowColors[1], arrowColors[2], arrowColors[3],
		                 0, GARAGE_CHARACTER_ARROW_SCALE, arrowRot[i]);
	}

	garageFrames = gGarage.numFramesCurr_GarageMove;

	if (((gGT->renderFlags & RENDER_FLAG_CHECKERED_FLAG) != 0) ||
	    (((sdata->AnyPlayerTap & GARAGE_INPUT_MENU) == 0) && ((sdata->AnyPlayerHold & GARAGE_INPUT_HORIZONTAL) == 0)))
	{
		goto update_garage_camera;
	}

	if ((sdata->AnyPlayerHold & GARAGE_INPUT_HORIZONTAL) == 0)
	{
		if ((sdata->AnyPlayerTap & GARAGE_INPUT_CONFIRM) == 0)
		{
			if ((sdata->AnyPlayerTap & GARAGE_INPUT_BACK) != 0)
			{
				OtherFX_Play(2, 1);
				garageFrames = gGarage.numFramesCurr_ZoomIn;
				if (gGarage.boolSelected == 1)
				{
					gGarage.boolSelected = 0;
					gGT->gameMode2 &= ~GARAGE_OSK;

					if (garageFrames < gGarage.numFramesMax_Zoom)
					{
						gGarage.numFramesCurr_ZoomOut = gGarage.numFramesMax_Zoom - garageFrames;
					}
				}
				else
				{
					sdata->mainMenuState = MAIN_MENU_TITLE;
					Garage_Leave();
					MainRaceTrack_RequestLoad(MAIN_MENU_LEVEL);
				}
			}
		}
		else
		{
			if (gGarage.boolSelected == 0)
			{
				gGarage.boolSelected = 1;
			}
			else
			{
				if (gGarage.boolSelected == 1)
				{
					sdata->ptrDesiredMenu = &data.menuSubmitName;

					data.characterIDs[0] = gGarage.garageCharacterIDs[currSelectIndex];
                {
                        int packID = NativeAdventurePack_GetCharacterID(currSelectIndex);
                        if (packID >= 0) {
                            if (IS_NATIVE_GARAGE_ONLY_ID(packID))
                                data.characterIDs[0] = NativeCustomRacer_GetGarageOnlyRetailID(packID);
                            else
                                data.characterIDs[0] = (s16)packID;
                        }
                }
					sdata->advProgress.characterID = data.characterIDs[0];
					SubmitName_RestoreName(0);
					OtherFX_Play(1, 1);
				}
			}
		}
	}
	else
	{
		for (int i = 2; i > -1; i--)
		{
			statBarLength = &gGarage.statBarLengths[i];
			*statBarLength = 0;
		}
		OtherFX_Play(0, 1);

		if ((sdata->AnyPlayerHold & BTN_LEFT) == 0)
		{
			if ((sdata->AnyPlayerHold & BTN_RIGHT) != 0)
			{
				currSelectIndex++;
				goto LAB_800b8084;
			}
		}
		else
		{
			currSelectIndex--;

		LAB_800b8084:
			sdata->advCharSelectIndex_prev = sdata->advCharSelectIndex_curr;
			currSelectIndex &= 7;
			sdata->advCharSelectIndex_curr = currSelectIndex;

			Garage_MoveLR(currSelectIndex);

                        {
                            extern void NativeCustomRacer_SwitchGarageCharacter(int);
                            int newID = (int)gGarage.garageCharacterIDs[currSelectIndex];
                            {
                                extern int NativeAdventurePack_GetCharacterID(int);
                                int packID = NativeAdventurePack_GetCharacterID(currSelectIndex);
                                if (packID >= 0) newID = packID;
                            }
                            NativeCustomRacer_UpdateGarageAmbients((int)currSelectIndex);
                        }
		}

		gGarage.numFramesCurr_GarageMove = gGarage.numFramesMax_GarageMove;

		if (gGarage.numFramesCurr_ZoomIn < gGarage.numFramesMax_Zoom)
		{
			gGarage.numFramesCurr_ZoomOut = gGarage.numFramesMax_Zoom - gGarage.numFramesCurr_ZoomIn;
		}

		gGarage.boolSelected = 0;
		gGT->gameMode2 &= ~GARAGE_OSK;
	}

	RECTMENU_ClearInput();

	garageFrames = gGarage.numFramesCurr_GarageMove;

update_garage_camera:
	gGarage.numFramesCurr_GarageMove = garageFrames;

	if (0 < gGarage.numFramesCurr_ZoomIn)
	{
		gGarage.numFramesCurr_ZoomIn--;
	}

	if ((gGarage.boolSelected == 1) && (gGarage.numFramesCurr_ZoomIn == 0))
	{
		if ((GARAGE_OSK_DELAY_FRAMES <= gGarage.delayOneSecond) || ((gGT->gameMode2 & GARAGE_OSK) != 0))
		{
			sdata->ptrDesiredMenu = &data.menuSubmitName;

			data.characterIDs[0] = gGarage.garageCharacterIDs[currSelectIndex];
                {
                        int packID = NativeAdventurePack_GetCharacterID(currSelectIndex);
                        if (packID >= 0) {
                            if (IS_NATIVE_GARAGE_ONLY_ID(packID))
                                data.characterIDs[0] = NativeCustomRacer_GetGarageOnlyRetailID(packID);
                            else
                                data.characterIDs[0] = (s16)packID;
                        }
                }
			sdata->advProgress.characterID = data.characterIDs[0];

			SubmitName_RestoreName(0);
			OtherFX_Play(1, 1);
		}
		else
		{
			gGarage.delayOneSecond++;
		}
	}

#ifdef CTR_NATIVE
	if (sdata->ptrDesiredMenu == &data.menuSubmitName)
	{
		NikoGetEnterKey();
	}
#endif

	if (gGarage.boolSelected == 0)
	{
		gGarage.numFramesCurr_ZoomIn = gGarage.numFramesMax_Zoom;
	}

	if (gGarage.numFramesCurr_ZoomOut != 0)
	{
		gGarage.numFramesCurr_ZoomOut--;
	}

	u32 prevSelectIndex = sdata->advCharSelectIndex_prev;

	if ((currSelectIndex == 0) && (prevSelectIndex == 7))
	{
		garageFrames = GARAGE_CAMERA_WRAP_RIGHT_FRAME - gGarage.numFramesCurr_GarageMove;
	}
	else if ((currSelectIndex == 7) && (prevSelectIndex == 0))
	{
		garageFrames = gGarage.numFramesCurr_GarageMove + GARAGE_CAMERA_WRAP_LEFT_FRAME;
	}
	else if (prevSelectIndex < currSelectIndex)
	{
		garageFrames = currSelectIndex * GARAGE_CAMERA_FRAME_STEP - gGarage.numFramesCurr_GarageMove;
	}
	else
	{
		garageFrames = currSelectIndex * GARAGE_CAMERA_FRAME_STEP + gGarage.numFramesCurr_GarageMove;
	}

	s16 pathFlags;
	SVec3 camPos;
	SVec3 camRot;

    static s16 s_camFrom[3]    = {0, 0, 0};
    static s16 s_camTo[3]      = {0, 0, 0};
    static s16 s_camCur[3]     = {0, 0, 0};
    static s16 s_camRotFrom[2] = {0, 0};
    static s16 s_camRotTo[2]   = {0, 0};
    static s16 s_camRotCur[2]  = {0, 0};
    static s16 s_camInterpT    = 0x1000;
    static int s_camLastSelectIdx = -1;
    if (s_garageForceSnap) {
            s_garageForceSnap = 0;
            s_camLastSelectIdx = -1;
    }

    if (NativeAdventurePack_IsActive()) {
            s16 cam_p[3];
            s16 cam_r[2];
            extern int NativeAdventurePack_CameraHasRot(void);
            s16 char_p[3];
            s16 char_r[2];
            NativeAdventurePack_GetCameraForSlot(currSelectIndex, cam_p, cam_r);
            NativeAdventurePack_GetSlotPos(currSelectIndex, char_p, char_r);

            s16 camTarget[3];
            s16 rotTarget[2];

            camTarget[0] = cam_p[0];
            camTarget[1] = cam_p[1];
            camTarget[2] = cam_p[2];

            if (NativeAdventurePack_CameraHasRot()) {
                    rotTarget[0] = (s16)((-cam_r[0] + ADV_CAM_PITCH_BIAS) & 0xFFF);
                    rotTarget[1] = (s16)(( cam_r[1] + ADV_CAM_YAW_BIAS) & 0xFFF);
            } else {
                    int dx = char_p[0] - cam_p[0];
                    int dy = (char_p[1] + ADV_CAM_AIM_HEIGHT) - cam_p[1];
                    int dz = char_p[2] - cam_p[2];
                    int horiz_dist = SquareRoot0((u32)(dx * dx + dz * dz));
                    int pitch = ratan2(dy, horiz_dist);

                    rotTarget[0] = (s16)((-pitch + ADV_CAM_PITCH_BIAS) & 0xFFF);
                    rotTarget[1] = (s16)(( ratan2(dx, dz) + ADV_CAM_YAW_BIAS) & 0xFFF);
            }

            if (s_camLastSelectIdx == -1) {
                    for (int i = 0; i < 3; i++) s_camCur[i] = s_camFrom[i] = s_camTo[i] = camTarget[i];
                    for (int i = 0; i < 2; i++) s_camRotCur[i] = s_camRotFrom[i] = s_camRotTo[i] = rotTarget[i];
                    s_camLastSelectIdx = currSelectIndex;
                    s_camInterpT = 0x1000;
            } else if (s_camLastSelectIdx == currSelectIndex
            && (s_camTo[0] != camTarget[0]
             || s_camTo[1] != camTarget[1]
             || s_camTo[2] != camTarget[2]
             || s_camRotTo[0] != rotTarget[0]
             || s_camRotTo[1] != rotTarget[1])) {
                    s_camCur[0] = camTarget[0];
                    s_camCur[1] = camTarget[1];
                    s_camCur[2] = camTarget[2];
                    s_camRotCur[0] = rotTarget[0];
                    s_camRotCur[1] = rotTarget[1];
                    s_camTo[0] = camTarget[0];
                    s_camTo[1] = camTarget[1];
                    s_camTo[2] = camTarget[2];
                    s_camRotTo[0] = rotTarget[0];
                    s_camRotTo[1] = rotTarget[1];
                    s_camInterpT = 0x1000;
            } else if (s_camLastSelectIdx != currSelectIndex) {
                    s_camFrom[0] = s_camCur[0];
                    s_camFrom[1] = s_camCur[1];
                    s_camFrom[2] = s_camCur[2];
                    s_camRotFrom[0] = s_camRotCur[0];
                    s_camRotFrom[1] = s_camRotCur[1];

                    s_camTo[0] = camTarget[0];
                    s_camTo[1] = camTarget[1];
                    s_camTo[2] = camTarget[2];
                    s_camRotTo[0] = rotTarget[0];
                    s_camRotTo[1] = rotTarget[1];

                    s_camLastSelectIdx = currSelectIndex;
                    s_camInterpT = 0;
            }

            if (s_camInterpT < 0x1000) {
                    s_camInterpT += 0x1000 / 15;
                    if (s_camInterpT > 0x1000) s_camInterpT = 0x1000;
            }

            {
                    int t  = s_camInterpT;
                    int t2 = (t * t) >> 12;
                    int t3 = (t2 * t) >> 12;
                    int w  = t2 * 3 - t3 * 2;

                    for (int i = 0; i < 3; i++)
                            s_camCur[i] = (s16)(s_camFrom[i] + (((s_camTo[i] - s_camFrom[i]) * w) >> 12));
                    for (int i = 0; i < 2; i++) {
                            int d = ((int)s_camRotTo[i] - (int)s_camRotFrom[i]) & 0xFFF;
                            if (d > 0x800) d -= 0x1000;
                            s_camRotCur[i] = (s16)(((int)s_camRotFrom[i] + ((d * w) >> 12)) & 0xFFF);
                    }
            }

            camPos.x = s_camCur[0];
            camPos.y = s_camCur[1];
            camPos.z = s_camCur[2];
            camRot.x = s_camRotCur[0];
            camRot.y = s_camRotCur[1];
            camRot.z = (s16)0x800;
    } else {
            CAM_Path_Move((int)garageFrames, CTR_VECTOR_DATA(&(camPos)), CTR_VECTOR_DATA(&(camRot)), &pathFlags);
            s_camLastSelectIdx = -1;
            s_camInterpT = 0x1000;
    }

	gGT->pushBuffer[0].pos = camPos;
	gGT->pushBuffer[0].rot = camRot;

	int zoom = gGarage.numFramesCurr_ZoomOut;
	if (zoom == 0)
	{
		zoom = (gGarage.numFramesMax_Zoom - gGarage.numFramesCurr_ZoomIn) * (gGarage.fovMax - gGarage.fovMin);
	}
	else
	{
		zoom = zoom * (gGarage.fovMax - gGarage.fovMin);
	}

	zoom = gGarage.fovMin + zoom / gGarage.numFramesMax_Zoom;

	gGT->pushBuffer[0].distanceToScreen_CURR = zoom;
	gGT->pushBuffer[0].distanceToScreen_PREV = zoom;

	{
		extern void PushBuffer_SetMatrixVP(struct PushBuffer *pb);
		PushBuffer_SetMatrixVP(&gGT->pushBuffer[0]);
	}
}

struct RectMenu *CS_Garage_GetMenuPtr(void)
{
	return &gGarage.menuGarage;
}

void CS_Garage_Init(void)
{
	sdata->ptrActiveMenu = &gGarage.menuGarage;

	gGarage.menuGarage.state &= ~(ONLY_DRAW_TITLE);

	{
		extern void NativeAdventurePack_LoadCameras(void);
		NativeAdventurePack_LoadCameras();
	}

    if (s_targetGarageSlot >= 0) {
        sdata->advCharSelectIndex_curr = s_targetGarageSlot;
        s_targetGarageSlot = -1;
    } else {
        sdata->advCharSelectIndex_curr = 0;
    }
    
    sdata->advCharSelectIndex_prev = 0;
    s_garageForceSnap = 1;
    s_pendingAmbientStart = 1;

	CS_Garage_ZoomOut(0);
}