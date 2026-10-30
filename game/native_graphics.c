#include <common.h>
#include <widescreen.h>
#include "native_graphics.h"
#include "native_settings.h"
#include "native_options.h"

extern int  Platform_IsFullscreen(void);
extern void Platform_GraphicsSetFullscreen(int on);
extern int  gNativeDitheringEnabled;

/* 4 rows. ASPECT RATIO reinstated with persistence fix.
 *   - ANTI-ALIASING: local-only menu placeholder, never reached
 *     the renderer. No MSAA in native_renderer.c.
 *   - CHARACTER DETAIL: LOW is a joke (box LOD), SMART is
 *     indistinguishable from HIGH on modern hardware. Forced HIGH
 *     via NativeSettings (see native_settings.c). */
static const char *const s_labels[4] = {
    "DISPLAY MODE", "RESOLUTION", "DITHERING", "ASPECT RATIO"
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
    case 3: {
        int a = NativeSettings_GetAspectRatio();
        if (a == 1) return "16:9";
        if (a == 2) return "16:10";
        if (a == 3) return "21:9";
        return "4:3";
    }
    default: return gNativeDitheringEnabled ? "ON" : "OFF";
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
    case 3: {
        int a = NativeSettings_GetAspectRatio();
        if (d < 0) { if (a <= 0) return 0; a--; }
        else       { if (a >= 3) return 0; a++; }
        NativeSettings_SetAspectRatio(a);
        NativeRenderer_UpdatePresentationViewport();
        return 1;
    }
    default: NativeSettings_SetDithering(!NativeSettings_GetDithering()); return 1;
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
            NativeOptions_Open();
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
        DecalFont_DrawLine((char *)s_labels[r], Widescreen_ScaleAboutX(76, 256), y, FONT_SMALL, ORANGE);
        DecalFont_DrawLine((char *)ng_val(r, buf, sizeof(buf)), Widescreen_ScaleAboutX(436, 256), y,
                           FONT_SMALL, JUSTIFY_RIGHT | WHITE);
    }
    int origW_cur = 364;
        int compW_cur = CTR_WIDESCREEN_SCALE_X(origW_cur);
        RECT cur = {74 + (origW_cur - compW_cur) / 2, 58 + s_row*18 - 3, compW_cur, 14};
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