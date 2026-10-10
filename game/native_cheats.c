#include <common.h>
#include "native_cheats.h"
#include "native_settings.h"

static const char *const s_cheat_labels[1] = { "BOT RANDOMIZER" };
static int s_cheat_open = 0, s_cheat_row = 0;

void NativeCheats_Open(void)   { s_cheat_open = 1; s_cheat_row = 0; }
void NativeCheats_Close(void)  { s_cheat_open = 0; }
int  NativeCheats_IsOpen(void) { return s_cheat_open; }

void NativeCheats_MenuPtr(struct RectMenu *menu) {
    u32 tap = sdata->AnyPlayerTap;

    if (tap != 0) {
        if (tap & (BTN_LEFT | BTN_RIGHT | BTN_CROSS)) {
            int v = NativeSettings_GetBotRandomizer();
            NativeSettings_SetBotRandomizer((tap & BTN_LEFT) ? (v + 2) % 3 : (v + 1) % 3);
            OtherFX_Play(1, 1);
        } else if (tap & (BTN_TRIANGLE | BTN_SQUARE_one)) {
            OtherFX_Play(1, 1);
            NativeCheats_Close();
            if (menu) menu->state &= ~ONLY_DRAW_TITLE;
            RECTMENU_ClearInput();
            return;
        }
        RECTMENU_ClearInput();
    }

    struct GameTracker *gGT = sdata->gGT;
    u32 *ot = gGT->backBuffer->otMem.uiOT;

    DecalFont_DrawLine("CHEATS", 256, 26, FONT_BIG, JUSTIFY_CENTER | ORANGE);
    DecalFont_DrawLine((char *)s_cheat_labels[0], 76, 58, FONT_SMALL, ORANGE);
    static const char *const s_brModes[3] = { "OFF", "RETAIL", "ALL" };
    DecalFont_DrawLine((char *)s_brModes[NativeSettings_GetBotRandomizer()], 436, 58, FONT_SMALL, JUSTIFY_RIGHT | WHITE);

    RECT cur = {74, 55, 364, 14};
    CTR_Box_DrawClearBox(&cur, &sdata->menuRowHighlight_Normal, TRANS_50_DECAL, ot);
    RECT sep = {66, 43, 380, 2};
    Color c;
    ColorCode_SetPacked(&c, sdata->battleSetup_Color_UI_1);
    RECTMENU_DrawOuterRect_Edge(&sep, c, 0x20, ot);
    RECT bg = {56, 20, 400, 145};
    RECTMENU_DrawInnerRect(&bg, 4, ot);
}