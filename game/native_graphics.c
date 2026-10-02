#include <common.h>
#include "native_graphics.h"

extern int  Platform_IsFullscreen(void);
extern void Platform_GraphicsSetFullscreen(int on);
extern void NativeRenderer_SetInternalScale(int scale);
extern int  NativeRenderer_GetInternalScale(void);

static const char *const s_labels[4] = {
    "DISPLAY MODE", "ASPECT RATIO", "RESOLUTION", "ANTI-ALIASING"
};
static const char *const s_aspects[4] = {"AUTO","4:3","16:9","21:9"};

static int s_open = 0, s_row = 0, s_aspect = 0, s_res = 2, s_msaa = 1;

void NativeGraphics_Open(void)  { s_open = 1; s_row = 0; s_res = NativeRenderer_GetInternalScale(); }
void NativeGraphics_Close(void) { s_open = 0; }
int  NativeGraphics_IsOpen(void) { return s_open; }

static const char *ng_val(int r, char *b, int n) {
    switch (r) {
    case 0: return Platform_IsFullscreen() ? "FULLSCREEN" : "WINDOWED";
    case 1: return s_aspects[s_aspect];
    case 2: if (s_res < 0) return "NATIVE"; snprintf(b, n, "%dX", s_res); return b;
    default: if (s_msaa >= 4) return "4X"; if (s_msaa >= 2) return "2X"; return "OFF";
    }
}

static int ng_chg(int r, int d) {
    switch (r) {
    case 0: { int w = (d < 0) ? 1 : 0;
              if (w == Platform_IsFullscreen()) return 0;
              Platform_GraphicsSetFullscreen(w); return 1; }
    case 1: {
        int v = s_aspect + d; if (v < 0 || v > 3) return 0; s_aspect = v;
        static const int AW[4] = {4, 4, 16, 21};
        static const int AH[4] = {3, 3, 9, 9};
        extern void NativeRenderer_SetPresentationAspect(int, int);
        NativeRenderer_SetPresentationAspect(AW[v], AH[v]);
        return 1;
    }
    case 2: if (d < 0) { if (s_res <= 1) return 0; s_res--; }
            else { if (s_res >= 4) return 0; s_res++; }
            NativeRenderer_SetInternalScale(s_res);
            return 1;
    default: { static const int lv[3] = {1,2,4}; int i = 0;
               while (i < 2 && lv[i] < s_msaa) i++; i += d;
               if (i < 0 || i > 2) return 0; s_msaa = lv[i]; return 1; }
    }
}

void NativeGraphics_MenuPtr(struct RectMenu *menu) {
    u32 tap = sdata->AnyPlayerTap;

    if (tap != 0) {
        if (tap & BTN_UP) { s_row = (s_row + 3) % 4; OtherFX_Play(0,1); }
        else if (tap & BTN_DOWN) { s_row = (s_row + 1) % 4; OtherFX_Play(0,1); }
        else if (tap & (BTN_LEFT | BTN_RIGHT)) {
            int ok = ng_chg(s_row, (tap & BTN_LEFT) ? -1 : 1);
            OtherFX_Play(ok ? 0 : 5, 1);
        } else if (tap & (BTN_TRIANGLE | BTN_SQUARE_one)) {
            OtherFX_Play(1, 1);
            NativeGraphics_Close();
            if (menu) menu->state &= ~ONLY_DRAW_TITLE;
            RECTMENU_ClearInput();
            return;
        }
        RECTMENU_ClearInput();
    }

    struct GameTracker *gGT = sdata->gGT;
    u32 *ot = gGT->backBuffer->otMem.uiOT;
    char buf[16];
    int r;

    DecalFont_DrawLine("GRAPHICS", 256, 26, FONT_BIG, JUSTIFY_CENTER | ORANGE);
    for (r = 0; r < 4; r++) {
        int y = 58 + r * 18;
        DecalFont_DrawLine((char *)s_labels[r], 76, y, FONT_SMALL, ORANGE);
        DecalFont_DrawLine((char *)ng_val(r, buf, sizeof(buf)), 436, y,
                           FONT_SMALL, JUSTIFY_RIGHT | WHITE);
    }
    RECT cur = {74, 58 + s_row*18 - 3, 364, 14};
    CTR_Box_DrawClearBox(&cur, &sdata->menuRowHighlight_Normal, TRANS_50_DECAL, ot);
    RECT sep = {66, 43, 380, 2};
    Color c;
    ColorCode_SetPacked(&c, sdata->battleSetup_Color_UI_1);
    RECTMENU_DrawOuterRect_Edge(&sep, c, 0x20, ot);
    RECT bg = {56, 20, 400, 145};
    RECTMENU_DrawInnerRect(&bg, 4, ot);
}
