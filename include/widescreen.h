#ifndef WIDESCREEN_H
#define WIDESCREEN_H

/* Factor en milésimas: 1000 = 4:3 (no-op), 750 = 16:9, 833 = 16:10, 563 = 21:9 */
int Widescreen_GetFactor(void);

int Widescreen_ScaleX(int value);
int Widescreen_ExpandX(int value);
int Widescreen_ScaleAboutX(int x, int anchorX);
int Widescreen_QuadCenterX(int x0, int x1, int x2, int x3);

int Widescreen_XShift(int width);

void Widescreen_CompressFT4(POLY_FT4 *p);
void Widescreen_CompressGT4(POLY_GT4 *p);
void Widescreen_CompressGT4Scaled(POLY_GT4 *p, int unscaledWidth, int scale);
void Widescreen_CompressNative(PolyFT4 *p);

#ifndef CTR_NATIVE_WIDESCREEN
#define CTR_NATIVE_WIDESCREEN           1
#define CTR_WIDESCREEN_SCALE_X(value)   Widescreen_ScaleX((int)(value))
#define CTR_WIDESCREEN_EXPAND_X(value)  Widescreen_ExpandX((int)(value))
#endif

#endif
