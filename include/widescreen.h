#ifndef WIDESCREEN_H
#define WIDESCREEN_H

int Widescreen_GetFactor(void);
int Widescreen_XShift(int width);

void Widescreen_CompressFT4(POLY_FT4 *p);
void Widescreen_CompressGT4(POLY_GT4 *p);
void Widescreen_CompressGT4Scaled(POLY_GT4 *p, int unscaledWidth, int scale);
void Widescreen_CompressNative(PolyFT4 *p);

void Widescreen_HudBegin(void);
void Widescreen_HudEnd(void);
void Widescreen_HudReset(void);
int  Widescreen_HudActive(void);
int  Widescreen_HudW(int w);
int  Widescreen_ScaleAbout(int anchor, int x);
#endif
