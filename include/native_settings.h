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

int  NativeSettings_GetBotRandomizer(void);
int  NativeSettings_GetHighMp(void);
int  NativeSettings_GetAspectRatio(void);
void NativeSettings_SetAspectRatio(int mode);
void NativeSettings_SetBotRandomizer(int enabled);

/* Adventure garage pack selector.
 * Empty string = RETAIL (use the retail garage, no custom override).
 * Non-empty = manifest "id" of the pack to use.
 * Persisted in ctr_native.cfg as garage_pack=<id>. */
const char *NativeSettings_GetGaragePack(void);
void        NativeSettings_SetGaragePack(const char *id);

#endif