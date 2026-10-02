#ifndef NG_H
#define NG_H
struct RectMenu;
void NativeGraphics_Open(void);
void NativeGraphics_Close(void);
int  NativeGraphics_IsOpen(void);
void NativeGraphics_MenuPtr(struct RectMenu *menu);
#endif
