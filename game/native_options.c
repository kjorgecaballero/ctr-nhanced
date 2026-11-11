#include <common.h>
#include "native_options.h"
#include "native_graphics.h"
#include "native_cheats.h"
#include <widescreen.h>
#include <native_settings.h>
#include <LevelRegistry.h>

static const char *const s_opt_labels[3] = { "GRAPHICS", "CHEATS", "GARAGE PACK" };
static int s_opt_open = 0, s_opt_row = 0;

/* Row 2 (GARAGE PACK) only appears when 2+ packs are installed.
 * With 1 pack, ResolvePackFromSetting() auto-uses it (compat), so
 * a selector would be confusing (both choices point to the same). */
static int NativeOptions_GetRowCount(void)
{
    return (LevelRegistry_GetAdventureGarageCount() >= 2) ? 3 : 2;
}

static const char *NativeOptions_GetGaragePackLabel(void)
{
    const char *id = NativeSettings_GetGaragePack();
    if (id == NULL || id[0] == '\0') return "RETAIL";
    const struct LevelDef *pack = LevelRegistry_GetAdventureGarageByID(id);
    return (pack != NULL) ? pack->name : "RETAIL";
}

static void NativeOptions_CycleGaragePack(int dir)
{
    int count = LevelRegistry_GetAdventureGarageCount();
    if (count < 1) return;

    const char *curID = NativeSettings_GetGaragePack();
    int curIdx = 0;  /* 0 = RETAIL */
    if (curID != NULL && curID[0] != '\0') {
        for (int i = 0; i < count; i++) {
            const struct LevelDef *p = LevelRegistry_GetAdventureGarageByIndex(i);
            if (p != NULL && strcmp(p->id, curID) == 0) { curIdx = i + 1; break; }
        }
    }

    int total = count + 1;  /* RETAIL + packs */
    int next = (curIdx + dir + total) % total;
    if (next == 0) {
        NativeSettings_SetGaragePack("");
    } else {
        const struct LevelDef *p = LevelRegistry_GetAdventureGarageByIndex(next - 1);
        NativeSettings_SetGaragePack((p != NULL) ? p->id : "");
    }
}

void NativeOptions_Open(void)   { s_opt_open = 1; s_opt_row = 0; MM_Title_KillThread(); }
void NativeOptions_Close(void)  { s_opt_open = 0; }
int  NativeOptions_IsOpen(void) { return s_opt_open; }

void NativeOptions_MenuPtr(struct RectMenu *menu) {
    if (!s_opt_open) return;
    if (menu) menu->state |= ONLY_DRAW_TITLE | INVISIBLE;

    u32 tap = sdata->AnyPlayerTap;
    int N = NativeOptions_GetRowCount();
    if (s_opt_row >= N) s_opt_row = N - 1;

    if (tap != 0) {
        if (tap & BTN_UP)        { s_opt_row = (s_opt_row + N - 1) % N; OtherFX_Play(0, 1); }
        else if (tap & BTN_DOWN) { s_opt_row = (s_opt_row + 1) % N; OtherFX_Play(0, 1); }
        else if (s_opt_row == 2 && (tap & BTN_LEFT))  { NativeOptions_CycleGaragePack(-1); OtherFX_Play(0, 1); }
        else if (s_opt_row == 2 && (tap & BTN_RIGHT)) { NativeOptions_CycleGaragePack(+1); OtherFX_Play(0, 1); }
        else if (tap & BTN_CROSS) {
            if (s_opt_row == 2) {
                /* GARAGE PACK: only cycles with LEFT/RIGHT, no sub-menu */
                RECTMENU_ClearInput();
                return;
            }
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
    for (int r = 0; r < N; r++) {
        int y = 58 + r * 18;
        char buf[128];
        if (r == 2) {
            snprintf(buf, sizeof(buf), "%s: %s", s_opt_labels[2],
                     NativeOptions_GetGaragePackLabel());
        } else {
            snprintf(buf, sizeof(buf), "%s", s_opt_labels[r]);
        }
        DecalFont_DrawLine(buf, Widescreen_ScaleAboutX(76, 256), y, FONT_SMALL, ORANGE);
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
    int bgHeight = (N == 3) ? 163 : 145;  /* extra row = +18 */
    RECT bg = {56 + (origW_bg - compW_bg) / 2, 20, compW_bg, bgHeight};
    RECTMENU_DrawInnerRect(&bg, 4, ot);
}