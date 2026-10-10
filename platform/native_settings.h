#ifndef NS_H
#define NS_H
int  NativeSettings_GetDithering(void);
int  NativeSettings_GetResolution(void);
int  NativeSettings_GetBilinear(void);
int  NativeSettings_GetCharacterDetail(void);
int  NativeSettings_GetBotRandomizer(void);
int  NativeSettings_GetHighMp(void);
void NativeSettings_SetDithering(int);
void NativeSettings_SetResolution(int);
void NativeSettings_SetBilinear(int);
void NativeSettings_SetCharacterDetail(int);
void NativeSettings_SetBotRandomizer(int);
void NativeSettings_Load(void);
void NativeSettings_Save(void);
#endif