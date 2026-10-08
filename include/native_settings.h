#ifndef NATIVE_SETTINGS_H
#define NATIVE_SETTINGS_H

int  NativeSettings_GetDithering(void);
void NativeSettings_SetDithering(int enabled);
int  NativeSettings_GetResolution(void);
void NativeSettings_SetResolution(int scale);
int  NativeSettings_GetBilinear(void);
void NativeSettings_SetBilinear(int enabled);
int  NativeSettings_GetCharacterDetail(void);
void NativeSettings_SetCharacterDetail(int mode);

void NativeSettings_Load(void);
void NativeSettings_Save(void);

#endif