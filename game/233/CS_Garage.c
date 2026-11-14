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

/* Adventure-pack camera calibration knobs (ANG units: 0x1000 = 360 deg).
 * Tune empirically: if the view is mirrored/inverted, flip the sign of
 * the corresponding bias or negate the ratan2 result. */
#ifndef ADV_CAM_AIM_HEIGHT
#define ADV_CAM_AIM_HEIGHT  0   /* raise aim point above the slot origin (feet) */
#endif
#define ADV_CAM_YAW_BIAS    0
#define ADV_CAM_PITCH_BIAS  0

/* Set by CS_Garage_Init(), consumed by MenuProc on the next frame.
 * Forces the custom camera interp to snap to currSelectIndex instead
 * of sliding from the previous garage's slot. See CS_Garage_Init. */
static int s_garageForceSnap = 0;

/* Deferred ambient start: set by CS_Garage_Init, consumed on
 * the first MenuProc tick (Audio_SetState_Safe from ZoomOut
 * would otherwise kill the voices at the next audio tick). */
static int s_pendingAmbientStart = 0;
static int s_garagePackTimer = 0;
static char s_garagePackName[64] = "";
static int s_packSelectOpen = 0;
static int s_packSelectCur = 0;
static int s_packSelectScroll = 0;

extern const char *NativeSettings_GetGaragePack(void);
extern void NativeSettings_SetGaragePack(const char *id);
extern int LevelRegistry_GetAdventureGarageCount(void);
extern const struct LevelDef *LevelRegistry_GetAdventureGarageByIndex(int index);
extern void MainRaceTrack_RequestLoad(int levelID);


void CS_Garage_ZoomOut(s16 zoomState)
{
	if (zoomState != 0)
	{
		// number of frames to zoom in, or out,
		// when selecting or cancelling OSK
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

	// if just entered garage
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

    if (sdata->AnyPlayerTap & BTN_START) {
        s_packSelectOpen = !s_packSelectOpen;
        fprintf(stderr, "[MENU-TOGGLE] open=%d\n", s_packSelectOpen);
        s_packSelectCur = 0;
    }

        if (s_packSelectOpen) {
            fprintf(stderr, "[MENU-DRAW] open=%d total=%d\n", s_packSelectOpen, LevelRegistry_GetAdventureGarageCount()+1);
            
            struct GameTracker *gGT = sdata->gGT;
            u32 *ot = gGT->backBuffer->otMem.uiOT;
            int total = LevelRegistry_GetAdventureGarageCount() + 1;
            
            // Title
            DecalFont_DrawLine("SELECT GARAGE", 256, 26, FONT_BIG, JUSTIFY_CENTER | ORANGE);
            
            // List of packs
            int max_visible = 6;
            // Ajustar scroll
            if (s_packSelectCur < s_packSelectScroll) s_packSelectScroll = s_packSelectCur;
            if (s_packSelectCur >= s_packSelectScroll + max_visible) s_packSelectScroll = s_packSelectCur - max_visible + 1;
            
            int start_r = s_packSelectScroll;
            int end_r = start_r + max_visible;
            if (end_r > total) end_r = total;

            for (int r = start_r; r < end_r; r++) {
                int y = 58 + (r - start_r) * 18;
                const char *name = (r < total - 1) ? LevelRegistry_GetAdventureGarageByIndex(r)->name : "RETAIL";
                DecalFont_DrawLine(name, Widescreen_ScaleAboutX(76, 256), y, FONT_SMALL, ORANGE);
            }
            
            // Indicadores de scroll
            if (s_packSelectScroll > 0) {
                DecalFont_DrawLine("^", 46, 58, FONT_SMALL, ORANGE);
            }
            if (s_packSelectScroll + max_visible < total) {
                DecalFont_DrawLine("v", 46, 58 + (max_visible-1)*18, FONT_SMALL, ORANGE);
            }
            
            // Highlight
            int origW_cur = 364;
            int compW_cur = CTR_WIDESCREEN_SCALE_X(origW_cur);
            int real_y = 58 + (s_packSelectCur - s_packSelectScroll) * 18;
            RECT cur = {74 + (origW_cur - compW_cur) / 2, real_y - 3, compW_cur, 14};
            CTR_Box_DrawClearBox(&cur, &sdata->menuRowHighlight_Normal, TRANS_50_DECAL, ot);
            
            // Separator
            int origW_sep = 380;
            int compW_sep = CTR_WIDESCREEN_SCALE_X(origW_sep);
            RECT sep = {66 + (origW_sep - compW_sep) / 2, 43, compW_sep, 2};
            Color c;
            ColorCode_SetPacked(&c, sdata->battleSetup_Color_UI_1);
            RECTMENU_DrawOuterRect_Edge(&sep, c, 0x20, ot);
            
            // Background box
            int origW_bg = 400;
            int compW_bg = CTR_WIDESCREEN_SCALE_X(origW_bg);
            int bgHeight = 20 + (total > 6 ? 6 : total) * 18 + 20;
            RECT bg = {56 + (origW_bg - compW_bg) / 2, 20, compW_bg, bgHeight};
            RECTMENU_DrawInnerRect(&bg, 4, ot);
        }
    if (s_packSelectOpen) {
            fprintf(stderr, "[MENU-INPUT] open=%d\n", s_packSelectOpen);
        int total = LevelRegistry_GetAdventureGarageCount() + 1;
        if (sdata->AnyPlayerTap & BTN_DOWN) { s_packSelectCur++; if (s_packSelectCur >= total) s_packSelectCur = 0; }
        if (sdata->AnyPlayerTap & BTN_UP)   { s_packSelectCur--; if (s_packSelectCur < 0) s_packSelectCur = total - 1; }
        if (sdata->AnyPlayerTap & BTN_TRIANGLE) { s_packSelectOpen = 0; }
        if (sdata->AnyPlayerTap & BTN_CROSS) {
            if (s_packSelectCur == total - 1) NativeSettings_SetGaragePack("");
            else NativeSettings_SetGaragePack(LevelRegistry_GetAdventureGarageByIndex(s_packSelectCur)->id);
            extern void NativeAdventurePack_ActivateForLoad(void);
            NativeAdventurePack_ActivateForLoad();
            MainRaceTrack_RequestLoad(ADVENTURE_GARAGE);
            s_packSelectOpen = 0;
        }
        return;
    }

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

	// CameraDC, freecam mode
	gGT->cameraDC[0].cameraMode = CAMERA_MODE_FREECAM;


	// subtract transition timer by one frame
	garageFrames = gGarage.numFramesCurr_GarageMove - 1;

	// if mid-transition, skip some code
	if (gGarage.numFramesCurr_GarageMove != 0)
	{
		goto update_garage_camera;
	}

	// At this point, there must not be a transition
	// between drivers, so start drawing the UI

	// count frames in garage?
	gGarage.unusedFrameCount++;

	// animate growth of all three stat bars
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

	// Stats side: 0 = Right, 1 = Left
	// Force left for Tiny/Pura (retail behavior) or if custom slot says so
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
        if (s_garagePackTimer > 0) {
            s_garagePackTimer--;
            DecalFont_DrawLine(s_garagePackName, 256, 160, FONT_BIG, JUSTIFY_CENTER | WHITE);
        }
	DecalFont_DrawLine(sdata->lngStrings[LNG_ACCEL], Widescreen_ScaleAboutX(statNamePosX, 256), GARAGE_STAT_NAME_ACCEL_Y, FONT_BIG, JUSTIFY_RIGHT | LIME_GREEN);
	DecalFont_DrawLine(sdata->lngStrings[LNG_TURN], Widescreen_ScaleAboutX(statNamePosX, 256), GARAGE_STAT_NAME_TURN_Y, FONT_BIG, JUSTIFY_RIGHT | BLUE);


	int engineID = MDC->engineID;

	// 0x248 - Beginner
	// EngineID == 3
	int classStringIndex = 0;

	// 0x24A - Advanced
	if (engineID == SPEED)
	{
		classStringIndex = 2;
	}

	// 0x249 - Intermediate
	if (engineID < SPEED)
	{
		classStringIndex = 1;
	}

	// 7 pixels tall
	u16 statBarStart_Y = GARAGE_STAT_BAR_START_Y;
	u16 statBarEnd_Y = GARAGE_STAT_BAR_END_Y;

	u16 statBarShadows_Y = GARAGE_STAT_BAR_SHADOW_Y;

	// Draw class name
	DecalFont_DrawLine(sdata->lngStrings[gGarage.classStringIDs[classStringIndex]], Widescreen_ScaleAboutX(classNamePosX, 256), GARAGE_CLASS_NAME_Y, FONT_BIG, (JUSTIFY_CENTER | ORANGE));

	// bar length (animated)

	for (int i = 0; i < 3; i++)
	{
		statBarLength = &gGarage.statBarLengths[i];

		// bar outline
		r.x = Widescreen_ScaleAboutX(statBarPosX, 256);
		r.y = statBarStart_Y;
		r.w = CTR_WIDESCREEN_SCALE_X(*statBarLength);
		r.h = GARAGE_STAT_BAR_HEIGHT;

		// outline color white at 0x800b7780
		CTR_Box_DrawWireBox(&r, &white, gGT->pushBuffer_UI.ptrOT, primMem);

		// bar shadows
		r.x = Widescreen_ScaleAboutX(statBarPosX, 256) + CTR_WIDESCREEN_SCALE_X(1);
		r.y = statBarShadows_Y;
		r.w = CTR_WIDESCREEN_SCALE_X(*statBarLength) - CTR_WIDESCREEN_SCALE_X(2);
		r.h = GARAGE_STAT_BAR_SHADOW_HEIGHT;

		// outline color black (shadows)
		CTR_Box_DrawWireBox(&r, &black, gGT->pushBuffer_UI.ptrOT, primMem);

		int segmentLen = GARAGE_STAT_BAR_SEGMENT_WIDTH;
		int segmentStart = 0;
		int segmentEnd = segmentLen;

		for (int segmentIndex = 0; segmentIndex < GARAGE_STAT_BAR_SEGMENT_COUNT; segmentIndex++)
		{
			// color data of bars (blue green yellow red)
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
				// primMem curr
				POLY_G4 *p = primMem->cursor;

				// quit if prim mem runs out
				if (primMem->end < (void *)p)
				{
					return;
				}

				primMem->cursor = p + 1;

				// color data
				CtrGpu_WriteColorCode(&p->r0, barColor[0] | GARAGE_STAT_BAR_POLY_G4_COLOR_CODE);
				CtrGpu_WriteColorCode(&p->r1, barColor[1] | GARAGE_STAT_BAR_POLY_G4_COLOR_CODE);
				CtrGpu_WriteColorCode(&p->r2, barColor[0] | GARAGE_STAT_BAR_POLY_G4_COLOR_CODE);
				CtrGpu_WriteColorCode(&p->r3, barColor[1] | GARAGE_STAT_BAR_POLY_G4_COLOR_CODE);

				s16 segmentX = statBarPosX + segmentStart;
				s16 segmentX_comp = Widescreen_ScaleAboutX(segmentX, 256);
				s16 segmentX2_comp = Widescreen_ScaleAboutX(segmentX + currSegmentLen, 256);

				// top left
				p->x0 = segmentX_comp;
				p->y0 = statBarStart_Y;

				// top right
				p->x1 = segmentX2_comp;
				p->y1 = statBarStart_Y;

				// bottom left
				p->x2 = segmentX_comp;
				p->y2 = statBarEnd_Y;

				// bottom right
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

	// Stats box
	r.x = Widescreen_ScaleAboutX(classNamePosX, 256) - (classMaxLen >> 1) - CTR_WIDESCREEN_SCALE_X(GARAGE_STAT_BOX_PADDING_X);
	r.y = GARAGE_STAT_BOX_Y;
	r.w = classMaxLen + CTR_WIDESCREEN_SCALE_X(GARAGE_STAT_BOX_PADDING_X * 2);
	r.h = GARAGE_STAT_BOX_HEIGHT;

	// Draw 2D Menu rectangle background
	RECTMENU_DrawInnerRect(&r, 4, gGT->backBuffer->otMem.uiOT);

	char *name = sdata->lngStrings[nameIndex];
        {
                const char *customName = NativeCustomRacer_GetDisplayName(currCharacterID);
                if (customName != NULL) name = (char *)customName;
        }

	// Draw character name
	DecalFont_DrawLine(name, GARAGE_CHARACTER_NAME_X, GARAGE_CHARACTER_NAME_Y, FONT_BIG, JUSTIFY_CENTER | ORANGE);

	int arrowColor = ORANGE;

	// blink arrows
	if ((sdata->frameCounter & 4) == 0)
	{
		arrowColor = RED;
	}

	// Color data
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

	// If you dont press D-pad
	if ((sdata->AnyPlayerHold & GARAGE_INPUT_HORIZONTAL) == 0)
	{
		// If you do not press Cross or Circle
		if ((sdata->AnyPlayerTap & GARAGE_INPUT_CONFIRM) == 0)
		{
			// If you press Triangle or Square
			if ((sdata->AnyPlayerTap & GARAGE_INPUT_BACK) != 0)
			{
				// Play Sound
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
					// return to main menu
					sdata->mainMenuState = MAIN_MENU_TITLE;

					Garage_Leave();

					// load main menu LEV
					MainRaceTrack_RequestLoad(MAIN_MENU_LEVEL);
				}
			}
		}

		// If you press Cross or Circle
		else
		{
			// "Have you selected character?"
			// If true, it will show an animation, and then show the
			// OSK (keyboard) screen. If set to 0 after in that screen,
			// the screen does not disappear

			// if false
			if (gGarage.boolSelected == 0)
			{
				// make it true
				gGarage.boolSelected = 1;
			}

			// if true
			else
			{
				// if pressed X twice quickly
				if (gGarage.boolSelected == 1)
				{
					// set desiredMenu to OSK (on-screen keyboard)
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

	// if using D-pad
	else
	{
		// erase animated bars
		for (int i = 2; i > -1; i--)
		{
			statBarLength = &gGarage.statBarLengths[i];
			*statBarLength = 0;
		}
		// Play Sound
		OtherFX_Play(0, 1);

		// If you dont press Left
		if ((sdata->AnyPlayerHold & BTN_LEFT) == 0)
		{
			// If you dont press Right
			if ((sdata->AnyPlayerHold & BTN_RIGHT) != 0)
			{
				currSelectIndex++;
				goto LAB_800b8084;
			}
		}

		// If you press Left
		else
		{
			currSelectIndex--;

		LAB_800b8084:

			// previous equals current
			sdata->advCharSelectIndex_prev = sdata->advCharSelectIndex_curr;

			// clamp 0-7
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

		// reset frame counter to max number of frames
		gGarage.numFramesCurr_GarageMove = gGarage.numFramesMax_GarageMove;

		if (gGarage.numFramesCurr_ZoomIn < gGarage.numFramesMax_Zoom)
		{
			gGarage.numFramesCurr_ZoomOut = gGarage.numFramesMax_Zoom - gGarage.numFramesCurr_ZoomIn;
		}

		gGarage.boolSelected = 0;
		gGT->gameMode2 &= ~GARAGE_OSK;
	}

	// clear gamepad input (for menus)
	RECTMENU_ClearInput();

	garageFrames = gGarage.numFramesCurr_GarageMove;
update_garage_camera:
	gGarage.numFramesCurr_GarageMove = garageFrames;

	// if frames remaing for zoom camera
	if (0 < gGarage.numFramesCurr_ZoomIn)
	{
		// decrease zoom frame timer
		gGarage.numFramesCurr_ZoomIn--;
	}

	// if pressed X once, and waited for countdown clock
	if ((gGarage.boolSelected == 1) && (gGarage.numFramesCurr_ZoomIn == 0))
	{
		if (
		    // frames remaining for animation
		    (GARAGE_OSK_DELAY_FRAMES <= gGarage.delayOneSecond) || ((gGT->gameMode2 & GARAGE_OSK) != 0))
		{
			// set desiredMenu to OSK (on-screen keyboard)
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
		// NOTE(aalhendi): PC-only keyboard shim; retail gamepad flow above stays unchanged.
		// flush async key state buffer. If not, tapping Enter "before" picking a garage character,
		//  then picking character, will immediately warp you to the adv hub, with no time to type the name
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

	// Pura->Crash
	if ((currSelectIndex == 0) && (prevSelectIndex == 7))
	{
		garageFrames = GARAGE_CAMERA_WRAP_RIGHT_FRAME - gGarage.numFramesCurr_GarageMove;
	}
	// Crash->Pura
	else if ((currSelectIndex == 7) && (prevSelectIndex == 0))
	{
		garageFrames = gGarage.numFramesCurr_GarageMove + GARAGE_CAMERA_WRAP_LEFT_FRAME;
	}
	// Move Right
	else if (prevSelectIndex < currSelectIndex)
	{
		garageFrames = currSelectIndex * GARAGE_CAMERA_FRAME_STEP - gGarage.numFramesCurr_GarageMove;
	}
	// Move Left
	else
	{
		garageFrames = currSelectIndex * GARAGE_CAMERA_FRAME_STEP + gGarage.numFramesCurr_GarageMove;
	}

	// animation frame index,
	// pointer to position,
	// pointer to rotation

	s16 pathFlags;
	SVec3 camPos;
	SVec3 camRot;

	        /* CUSTOM-CAMERA-INTERP: estado de interpolación entre slots.
         * Antes el path custom asignaba camPos/camRot directamente desde el
         * JSON (use_rot=1) o desde el look-at (use_rot=0). Al cambiar de
         * slot, la cámara saltaba bruscamente de A a B. Ahora interpola con
         * ease-in-out cúbico en ~15 frames (0.25s a 60 fps). */
        static s16 s_camFrom[3]    = {0, 0, 0};
        static s16 s_camTo[3]      = {0, 0, 0};
        static s16 s_camCur[3]     = {0, 0, 0};
        static s16 s_camRotFrom[2] = {0, 0};
        static s16 s_camRotTo[2]   = {0, 0};
        static s16 s_camRotCur[2]  = {0, 0};
        static s16 s_camInterpT    = 0x1000;   /* 0 = inicio, 0x1000 = terminado */
        static int s_camLastSelectIdx = -1;
        if (s_garageForceSnap) {
                /* Garage just (re)entered: drop the previous garage's
                 * slot so the first frame snaps to currSelectIndex. */
                s_garageForceSnap = 0;
                s_camLastSelectIdx = -1;
        }

        if (NativeAdventurePack_IsActive()) {
                s16 cam_p[3];
                s16 cam_r[2];   /* [0]=pitch (+ = arriba), [1]=yaw; solo valido si CameraHasRot */
                extern int NativeAdventurePack_CameraHasRot(void);
                s16 char_p[3];
                s16 char_r[2];
                NativeAdventurePack_GetCameraForSlot(currSelectIndex, cam_p, cam_r);
                NativeAdventurePack_GetSlotPos(currSelectIndex, char_p, char_r);

                /* === CUSTOM-CAMERA-INTERP: calcular target por slot === */
                s16 camTarget[3];
                s16 rotTarget[2];

                camTarget[0] = cam_p[0];
                camTarget[1] = cam_p[1];
                camTarget[2] = cam_p[2];

                if (NativeAdventurePack_CameraHasRot()) {
                        /* Camara capturada en Blender: pitch/yaw ya vienen en
                         * espacio motor (ANG 0x1000 = 360). */
                        rotTarget[0] = (s16)((-cam_r[0] + ADV_CAM_PITCH_BIAS) & 0xFFF);
                        rotTarget[1] = (s16)(( cam_r[1] + ADV_CAM_YAW_BIAS) & 0xFFF);
                } else {
                        /* look-at: objetivo - camara */
                        int dx = char_p[0] - cam_p[0];
                        int dy = (char_p[1] + ADV_CAM_AIM_HEIGHT) - cam_p[1];
                        int dz = char_p[2] - cam_p[2];
                        int horiz_dist = SquareRoot0((u32)(dx * dx + dz * dz));
                        int pitch = ratan2(dy, horiz_dist);

                        rotTarget[0] = (s16)((-pitch + ADV_CAM_PITCH_BIAS) & 0xFFF);
                        rotTarget[1] = (s16)(( ratan2(dx, dz) + ADV_CAM_YAW_BIAS) & 0xFFF);
                }

                /* Detectar cambio de slot. */
                if (s_camLastSelectIdx == -1) {
                        /* Primera entrada al garaje custom: sin pan. */
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
                        /* Same slot but target changed (LoadCameras ran after
                         * the first frame). Snap direct to the correct target
                         * without a visible pan. */
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
                        /* Cambio de slot: pan desde el estado actual. */
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

                /* Avanzar interpolación (15 frames). */
                if (s_camInterpT < 0x1000) {
                        s_camInterpT += 0x1000 / 15;
                        if (s_camInterpT > 0x1000) s_camInterpT = 0x1000;
                }

                /* Ease-in-out cúbico: w = t*t*(3-2t) en punto fijo 12 bits.
                 * Rotación con shortest-angle (maneja wrap 0xFFF->0x001). */
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
                camRot.z = (s16)0x800;   /* roll 180 grados, verificado visualmente */
        } else {
                CAM_Path_Move((int)garageFrames, CTR_VECTOR_DATA(&(camPos)), CTR_VECTOR_DATA(&(camRot)), &pathFlags);
                /* Al volver a retail, resetear el estado de interpolación
                 * para que la próxima entrada al garaje custom no panee. */
                s_camLastSelectIdx = -1;
                s_camInterpT = 0x1000;
        }

	// set position and rotation to pushBuffer
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

	// --- FIX: Reconstruir la matriz de vista con la nueva cámara ---
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
	// go to 3D character selection
	sdata->ptrActiveMenu = &gGarage.menuGarage;

	gGarage.menuGarage.state &= ~(ONLY_DRAW_TITLE);

	// Ensure cameras.json is parsed BEFORE the first rendered frame.
	// Without this, s_cam_per_slot[] is BSS {0,0,0} on frame 1 and the
	// camera pops to the correct target on a later frame.
	{
		extern void NativeAdventurePack_LoadCameras(void);
		NativeAdventurePack_LoadCameras();
	}

	/* Reset selection to slot 0 on every garage entry. Without this,
 * sdata->advCharSelectIndex_curr/_prev persist across garages
 * (retail -> custom -> retail), and the camera enters on the
 * previous garage's slot. s_garageForceSnap makes MenuProc skip
 * the first-frame interpolation so the camera snaps to slot 0
 * without sliding from the stale slot. */
        sdata->advCharSelectIndex_curr = 0;
        sdata->advCharSelectIndex_prev = 0;
        s_garageForceSnap = 1;
        s_pendingAmbientStart = 1;   /* defer ambient to first MenuProc tick */

        // 0 = just entered garage
	CS_Garage_ZoomOut(0);

}
