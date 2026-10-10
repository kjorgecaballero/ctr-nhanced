#ifndef NATIVE_OPTIONS_H
#define NATIVE_OPTIONS_H

struct RectMenu;

void NativeOptions_Open(void);
void NativeOptions_Close(void);
int  NativeOptions_IsOpen(void);
void NativeOptions_MenuPtr(struct RectMenu *menu);

#endif