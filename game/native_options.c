#include <common.h>
#include "native_options.h"
#include "native_graphics.h"
#include "native_cheats.h"
#include <widescreen.h>

static const char *const s_opt_labels[2] = { "GRAPHICS", "CHEATS" };
static int s_opt_open = 0, s_opt_row = 0;

void NativeOptions_Open(void)   { s_opt_open = 1; s_opt_row = 0; MM_Title_KillThread(); }
void NativeOptions_Close(void)  { s_opt_open = 0; }
int  NativeOptions_IsOpen(void) { return s_opt_open; }

void NativeOptions_MenuPtr(struct RectMenu *menu) {
    if (!s_opt_open) return;
    if (menu) menu->state |= ONLY_DRAW_TITLE | INVISIBLE;

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
            if (menu) menu->state &= ~(ONLY_DRAW_TITLE | INVISIBLE);
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
        DecalFont_DrawLine((char *)s_opt_labels[r], Widescreen_ScaleAboutX(76, 256), y, FONT_SMALL, ORANGE);
    }
    int origW_cur = 364;
    int compW_cur = CTR_WIDESCREEN_SCALE_X(origW_cur);
    RECT cur = {74 + (origW_cur - compW_cur) / 2, 58 + s_opt_row*18 - 3, compW_cur, 14};
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