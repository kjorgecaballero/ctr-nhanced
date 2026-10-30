#include <common.h>
#include "native_cheats.h"
#include "native_settings.h"
#include "native_options.h"
#include <widescreen.h>

static const char *const s_cheat_labels[1] = { "BOT RANDOMIZER" };
static int s_cheat_open = 0, s_cheat_row = 0;

void NativeCheats_Open(void)   { s_cheat_open = 1; s_cheat_row = 0; MM_Title_KillThread(); }
void NativeCheats_Close(void)  { s_cheat_open = 0; }
int  NativeCheats_IsOpen(void) { return s_cheat_open; }

void NativeCheats_MenuPtr(struct RectMenu *menu) {
    if (menu) menu->state |= ONLY_DRAW_TITLE | INVISIBLE;

    u32 tap = sdata->AnyPlayerTap;

    if (tap != 0) {
        if (tap & (BTN_LEFT | BTN_RIGHT | BTN_CROSS)) {
            int v = NativeSettings_GetBotRandomizer();
            NativeSettings_SetBotRandomizer((tap & BTN_LEFT) ? (v + 2) % 3 : (v + 1) % 3);
            OtherFX_Play(1, 1);
        } else if (tap & (BTN_TRIANGLE | BTN_SQUARE_one)) {
            OtherFX_Play(1, 1);
            NativeCheats_Close();
            NativeOptions_Open();
            RECTMENU_ClearInput();
            return;
        }
        RECTMENU_ClearInput();
    }

    struct GameTracker *gGT = sdata->gGT;
    u32 *ot = gGT->backBuffer->otMem.uiOT;

    DecalFont_DrawLine("CHEATS", 256, 26, FONT_BIG, JUSTIFY_CENTER | ORANGE);
    DecalFont_DrawLine((char *)s_cheat_labels[0], Widescreen_ScaleAboutX(76, 256), 58, FONT_SMALL, ORANGE);
    static const char *const s_brModes[3] = { "OFF", "RETAIL", "ALL" };
    DecalFont_DrawLine((char *)s_brModes[NativeSettings_GetBotRandomizer()], Widescreen_ScaleAboutX(436, 256), 58, FONT_SMALL, JUSTIFY_RIGHT | WHITE);

    int origW_cur = 364;
    int compW_cur = CTR_WIDESCREEN_SCALE_X(origW_cur);
    RECT cur = {74 + (origW_cur - compW_cur) / 2, 55, compW_cur, 14};
    CTR_Box_DrawClearBox(&cur, &sdata->menuRowHighlight_Normal, TRANS_50_DECAL, ot);
    int origW_sep = 380;
    int compW_sep = CTR_WIDESCREEN_SCALE_X(origW_sep);
    RECT sep = {66 + (origW_sep - compW_sep) / 2, 43, compW_sep, 2};
    Color c;
    ColorCode_SetPacked(&c, sdata->battleSetup_Color_UI_1);
    RECTMENU_DrawOuterRect_Edge(&sep, c, 0x20, ot);
    int origW_bg = 400;
    int compW_bg = CTR_WIDESCREEN_SCALE_X(origW_bg);
    RECT bg = {56 + (origW_bg - compW_bg) / 2, 20, compW_bg, 145};
    RECTMENU_DrawInnerRect(&bg, 4, ot);
}