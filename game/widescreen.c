#include <common.h>
#include <platform/native_renderer.h>

int Widescreen_GetFactor(void)
{
        return NativeRenderer_GetWidescreen() ? 750 : 1000; // 16:9 vs 4:3
}

int Widescreen_XShift(int width)
{
        const int factor = Widescreen_GetFactor();
        if (factor == 1000) return 0;
        return (width * (1000 - factor)) / 2000;
}

void Widescreen_CompressFT4(POLY_FT4 *p)
{
        int len = Widescreen_XShift(p->x1 - p->x0);
        p->x0 += len; p->x2 += len; p->x1 -= len; p->x3 -= len;
}

void Widescreen_CompressGT4(POLY_GT4 *p)
{
        int len = Widescreen_XShift(p->x1 - p->x0);
        p->x0 += len; p->x2 += len; p->x1 -= len; p->x3 -= len;
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
        int w = p->v[1].pos.x - p->v[0].pos.x;
        int len = Widescreen_XShift(w);
        p->v[0].pos.x += len; p->v[2].pos.x += len;
        p->v[1].pos.x -= len; p->v[3].pos.x -= len;
}

static int s_hudScope = 0;
void Widescreen_HudBegin(void) { s_hudScope++; }
void Widescreen_HudEnd(void)   { if (s_hudScope > 0) s_hudScope--; }
void Widescreen_HudReset(void) { s_hudScope = 0; }
int  Widescreen_HudActive(void){ return s_hudScope > 0 && Widescreen_GetFactor() != 1000; }
int  Widescreen_HudW(int w)    { return Widescreen_HudActive() ? (w * Widescreen_GetFactor() + 500) / 1000 : w; }

int Widescreen_ScaleAbout(int anchor, int x) {
        int f = Widescreen_GetFactor();
        if (f == 1000) return x;
        int d = x - anchor;
        return anchor + (d * f + (d >= 0 ? 500 : -500)) / 1000;
}
