#include <common.h>
#include <native_settings.h>
#include <widescreen.h>

int Widescreen_GetFactor(void)
{
        switch (NativeSettings_GetAspectRatio())
        {
                case 1:  return 756;  // 16:9 (34/45 exacto de Vita)
                case 2:  return 833;  // 16:10
                case 3:  return 563;  // 21:9
                default: return 1000; // 4:3 (no-op)
        }
}

int Widescreen_ScaleX(int value)
{
        const int factor = Widescreen_GetFactor();
        if (factor == 1000) return value;
        return (int)(((s64)value * factor) / 1000);
}

int Widescreen_ExpandX(int value)
{
        const int factor = Widescreen_GetFactor();
        if (factor == 1000) return value;
        return (int)(((s64)value * 1000) / factor);
}

int Widescreen_ScaleAboutX(int x, int anchorX)
{
        return anchorX + Widescreen_ScaleX(x - anchorX);
}

int Widescreen_QuadCenterX(int x0, int x1, int x2, int x3)
{
        int mn = x0, mx = x0;
        if (x1 < mn) mn = x1;
        if (x2 < mn) mn = x2;
        if (x3 < mn) mn = x3;
        if (x1 > mx) mx = x1;
        if (x2 > mx) mx = x2;
        if (x3 > mx) mx = x3;
        return (mn + mx) / 2;
}

int Widescreen_XShift(int width)
{
        const int factor = Widescreen_GetFactor();
        if (factor == 1000) return 0;
        return (width * (1000 - factor)) / 2000;
}

void Widescreen_CompressFT4(POLY_FT4 *p)
{
        if (Widescreen_GetFactor() == 1000) return;
        const int cx = Widescreen_QuadCenterX(p->x0, p->x1, p->x2, p->x3);
        p->x0 = (s16)Widescreen_ScaleAboutX(p->x0, cx);
        p->x1 = (s16)Widescreen_ScaleAboutX(p->x1, cx);
        p->x2 = (s16)Widescreen_ScaleAboutX(p->x2, cx);
        p->x3 = (s16)Widescreen_ScaleAboutX(p->x3, cx);
}

void Widescreen_CompressGT4(POLY_GT4 *p)
{
        if (Widescreen_GetFactor() == 1000) return;
        const int cx = Widescreen_QuadCenterX(p->x0, p->x1, p->x2, p->x3);
        p->x0 = (s16)Widescreen_ScaleAboutX(p->x0, cx);
        p->x1 = (s16)Widescreen_ScaleAboutX(p->x1, cx);
        p->x2 = (s16)Widescreen_ScaleAboutX(p->x2, cx);
        p->x3 = (s16)Widescreen_ScaleAboutX(p->x3, cx);
}

void Widescreen_CompressGT4Scaled(POLY_GT4 *p, int unscaledWidth, int scale)
{
        const int factor = Widescreen_GetFactor();
        if (scale <= 0 || scale >= FP(1.0) || factor == 1000) {
                Widescreen_CompressGT4(p); return;
        }
        const s64 divisor = (s64)FP(1.0) * 1000;
        const int width = ((s64)unscaledWidth * scale * factor + divisor / 2) / divisor;
        const int left = p->x0 + (p->x1 - p->x0 - width) / 2;
        p->x0 = p->x2 = left;
        p->x1 = p->x3 = left + width;
}

void Widescreen_CompressNative(PolyFT4 *p)
{
        if (Widescreen_GetFactor() == 1000) return;
        const int cx = Widescreen_QuadCenterX(p->v[0].pos.x, p->v[1].pos.x, p->v[2].pos.x, p->v[3].pos.x);
        for (int i = 0; i < 4; i++)
                p->v[i].pos.x = (s16)Widescreen_ScaleAboutX(p->v[i].pos.x, cx);
}
