#include <common.h>
#include "native_graphics.h"
#include "native_settings.h"

extern int  Platform_IsFullscreen(void);
extern void Platform_GraphicsSetFullscreen(int on);
extern int  gNativeDitheringEnabled;

/* 4 rows. HISTORICAL:
 *   - ASPECT RATIO was removed because it only stretched the 4:3
 *     framebuffer to a 16:9 viewport (Hor-stretch, karts looked fat).
 *     Replaced by WIDESCREEN, which also compresses matrix_ViewProj X
 *     in PushBuffer_SetMatrixVP for true Hor+ widescreen.
 *   - ANTI-ALIASING: placeholder, never reached the renderer.
 *   - CHARACTER DETAIL: forced HIGH via NativeSettings. */
static const char *const s_labels[4] = {
    "DISPLAY MODE", "RESOLUTION", "DITHERING", "WIDESCREEN"
};

#define NGFX_ROW_COUNT  4

static int s_open = 0, s_row = 0, s_res = 2;

void NativeGraphics_Open(void)  {
    s_open = 1;
    s_row = 0;
    s_res = NativeSettings_GetResolution();
    MM_Title_KillThread();
}
void NativeGraphics_Close(void) { s_open = 0; }
int  NativeGraphics_IsOpen(void) { return s_open; }

static const char *ng_val(int r, char *b, int n) {
    switch (r) {
    case 0: return Platform_IsFullscreen() ? "FULLSCREEN" : "WINDOWED";
    case 1: if (s_res < 0) return "NATIVE"; snprintf(b, n, "%dX", s_res); return b;
    case 2: return gNativeDitheringEnabled ? "ON" : "OFF";
    default: return NativeSettings_GetWidescreen() ? "16:9" : "4:3";
    }
}

static int ng_chg(int r, int d) {
    switch (r) {
    case 0: { int w = (d < 0) ? 1 : 0;
              if (w == Platform_IsFullscreen()) return 0;
              Platform_GraphicsSetFullscreen(w); return 1; }
    case 1: if (d < 0) { if (s_res <= 1) return 0; s_res--; }
            else      { if (s_res >= 8) return 0; s_res++; }
            NativeSettings_SetResolution(s_res);
            return 1;
    case 2: NativeSettings_SetDithering(!NativeSettings_GetDithering()); return 1;
    default: NativeSettings_SetWidescreen(!NativeSettings_GetWidescreen()); return 1;
    }
}

void NativeGraphics_MenuPtr(struct RectMenu *menu) {
    if (menu) menu->state |= ONLY_DRAW_TITLE | INVISIBLE;

    u32 tap = sdata->AnyPlayerTap;

    if (tap != 0) {
        if (tap & BTN_UP)        { s_row = (s_row + NGFX_ROW_COUNT - 1) % NGFX_ROW_COUNT; OtherFX_Play(0,1); }
        else if (tap & BTN_DOWN) { s_row = (s_row + 1) % NGFX_ROW_COUNT; OtherFX_Play(0,1); }
        else if (tap & (BTN_LEFT | BTN_RIGHT)) {
            int ok = ng_chg(s_row, (tap & BTN_LEFT) ? -1 : 1);
            OtherFX_Play(ok ? 0 : 5, 1);
        } else if (tap & (BTN_TRIANGLE | BTN_SQUARE_one)) {
            OtherFX_Play(1, 1);
            NativeGraphics_Close();
            if (menu) menu->state &= ~(ONLY_DRAW_TITLE | INVISIBLE);
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
    for (r = 0; r < NGFX_ROW_COUNT; r++) {
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
    RECT bg = {56, 20, 400, 163};
    RECTMENU_DrawInnerRect(&bg, 4, ot);
}
