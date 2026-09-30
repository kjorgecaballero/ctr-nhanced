#ifndef PLATFORM_NATIVE_CUSTOM_MUSIC_H
#define PLATFORM_NATIVE_CUSTOM_MUSIC_H

#include <macros.h>

/* === Custom level music (OGG streaming) ===
 * Music per-level streamed from assets/MUSIC_CUSTOM/level_XX.ogg,
 * where XX is the level ID. Mixed into the SPU output every frame.
 * Does NOT consume SPU RAM or voices. */

int  NativeCustomMusic_TryStartLevel(int levelID);
void NativeCustomMusic_BeginHubClock(void);
int  NativeCustomMusic_TrySwapHub(int levelID);
int  NativeCustomMusic_ShouldMuteLevelCseq(void);
int  NativeCustomMusic_IsActive(void);
void NativeCustomMusic_Stop(void);
void NativeCustomMusic_SetPaused(int paused);
void NativeCustomMusic_SetMaskMuted(int muted);
void NativeCustomMusic_SetVolume(int volume);
void NativeCustomMusic_Restart(void);
void NativeCustomMusic_EnableFinalLap(void);
void NativeCustomMusic_EndRace(void);
void NativeCustomMusic_MixFrameNoLock(int *mixLeft, int *mixRight, s16 masterLeft, s16 masterRight);

#endif