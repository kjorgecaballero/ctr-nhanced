#include <common.h>
#include "native_options.h"
#include "native_graphics.h"
#include "native_cheats.h"

static const char *const s_opt_labels[2] = { "GRAPHICS", "CHEATS" };
static int s_opt_open = 0, s_opt_row = 0;

void NativeOptions_Open(void)   { s_opt_open = 1; s_opt_row = 0; }
void NativeOptions_Close(void)  { s_opt_open = 0; }
int  NativeOptions_IsOpen(void) { return s_opt_open; }

void NativeOptions_MenuPtr(struct RectMenu *menu) {
    u32 tap = sdata->AnyPlayerTap;

    if (tap != 0) {
        if (tap & BTN_UP)        { s_opt_row = (s_opt_row + 1) % 2; OtherFX_Play(0, 1); }
        else if (tap & BTN_DOWN) { s_opt_row = (s_opt_row + 1) % 2; OtherFX_Play(0, 1); }
        else if (tap & BTN_CROSS) {
            OtherFX_Play(1, 1);
            NativeOptions_Close();
            if (s_opt_row == 0) NativeGraphics_Open();
            else                NativeCheats_Open();
            RECTMENU_ClearInput();
            return;
        } else if (tap & (BTN_TRIANGLE | BTN_SQUARE_one)) {
            OtherFX_Play(1, 1);
            NativeOptions_Close();
            if (menu) menu->state &= ~ONLY_DRAW_TITLE;
            RECTMENU_ClearInput();
            return;
        }
        RECTMENU_ClearInput();
    }

    struct GameTracker *gGT = sdata->gGT;
    u32 *ot = gGT->backBuffer->otMem.uiOT;

    DecalFont_DrawLine("OPTIONS", 256, 26, FONT_BIG, JUSTIFY_CENTER | ORANGE);
    for (int r = 0; r < 2; r++) {
        int y = 58 + r * 18;
        DecalFont_DrawLine((char *)s_opt_labels[r], 76, y, FONT_SMALL, ORANGE);
    }
    RECT cur = {74, 58 + s_opt_row*18 - 3, 364, 14};
    CTR_Box_DrawClearBox(&cur, &sdata->menuRowHighlight_Normal, TRANS_50_DECAL, ot);
    RECT sep = {66, 43, 380, 2};
    Color c;
    ColorCode_SetPacked(&c, sdata->battleSetup_Color_UI_1);
    RECTMENU_DrawOuterRect_Edge(&sep, c, 0x20, ot);
    RECT bg = {56, 20, 400, 145};
    RECTMENU_DrawInnerRect(&bg, 4, ot);
}