#ifndef NATIVE_CHEATS_H
#define NATIVE_CHEATS_H

struct RectMenu;

void NativeCheats_Open(void);
void NativeCheats_Close(void);
int  NativeCheats_IsOpen(void);
void NativeCheats_MenuPtr(struct RectMenu *menu);

#endif