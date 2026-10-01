#include <common.h>
#include <platform/native_custom_music.h>
#include <LevelRegistry.h>
#include <platform/native_audio.h>

/* stb_vorbis es un solo archivo. Con STB_VORBIS_HEADER_ONLY solo
 * traemos los prototypes; la implementación se compila una sola vez
 * desde externals/stb_vorbis.c (ver CMakeLists.txt). */
#define STB_VORBIS_HEADER_ONLY
#include <stb_vorbis.c>
#undef STB_VORBIS_HEADER_ONLY

#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CUSTOM_MUSIC_OUTPUT_RATE 44100
#define CUSTOM_MUSIC_FP_SHIFT 16
#define CUSTOM_MUSIC_FP_ONE (1u << CUSTOM_MUSIC_FP_SHIFT)

struct NativeCustomMusicState
{
        s16 *pcm;
        int frameCount;

        s16 *finalPcm;
        int finalFrameCount;
        int finalLapActive;
        int finalLapRequested;

        int channels;
        int sampleRate;
        u64 positionFp;
        u64 timelineOutputFrames;
        u32 stepFp;
        int active;
        int paused;
        int maskMuted;
        int raceEndSeen;
        int hubFallback;
        int volume;
        int levelID;
        char cachedPath[512];
};

static struct NativeCustomMusicState s_customMusic = {0};
static u64 s_hubClockFrames = 0;
static int s_hubClockActive = 0;
static int s_hubClockPaused = 0;

static void NativeCustomMusic_StopNoLock(int freePcm)
{
        if (freePcm)
        {
                if (s_customMusic.pcm != NULL)
                        free(s_customMusic.pcm);
                if (s_customMusic.finalPcm != NULL)
                        free(s_customMusic.finalPcm);

                memset(&s_customMusic, 0, sizeof(s_customMusic));
                s_customMusic.levelID = -1;
                s_customMusic.volume = 70;
        }
        else
        {
                /* Soft stop: keep PCM cached so a later TryStartLevel
                 * for the same level does not re-decode. */
                s_customMusic.active = 0;
                s_customMusic.paused = 1;
        }
}

void NativeCustomMusic_BeginHubClock(void)
{
        NativeAudio_LockOutput();
        if (!s_hubClockActive)
        {
                s_hubClockFrames = 0;
                s_hubClockPaused = 0;
                s_hubClockActive = 1;
        }
        NativeAudio_UnlockOutput();
}

static void NativeCustomMusic_StopTrackKeepHub(void)
{
        NativeAudio_LockOutput();
        NativeCustomMusic_StopNoLock(0);
        NativeAudio_UnlockOutput();
}

/* Decode the whole OGG into an s16 PCM buffer. Returns 1 on success. */
static int NativeCustomMusic_LoadOgg(const char *path, s16 **pcmOut,
                                     int *frameCountOut, int *channelsOut,
                                     int *sampleRateOut)
{
        int error = 0;
        stb_vorbis *vf;
        stb_vorbis_info info;
        int totalFrames;
        size_t totalSamples;
        s16 *pcm;
        int samplesRead;
        int framesRead;

        *pcmOut = NULL;
        *frameCountOut = 0;
        *channelsOut = 0;
        *sampleRateOut = 0;

        vf = stb_vorbis_open_filename(path, &error, NULL);
        if (vf == NULL)
        {
                fprintf(stderr,
                        "[CustomMusic] stb_vorbis_open_filename failed: %d (%s)\n",
                        error, path);
                return 0;
        }

        info = stb_vorbis_get_info(vf);
        if ((info.channels != 1) && (info.channels != 2))
        {
                fprintf(stderr, "[CustomMusic] OGG invalido: se requiere mono o stereo.\n");
                stb_vorbis_close(vf);
                return 0;
        }

        totalFrames = (int)stb_vorbis_stream_length_in_samples(vf);
        if (totalFrames <= 0)
        {
                fprintf(stderr, "[CustomMusic] OGG sin frames validos.\n");
                stb_vorbis_close(vf);
                return 0;
        }

        totalSamples = (size_t)totalFrames * (size_t)info.channels;
        if (totalSamples > (SIZE_MAX / sizeof(s16)))
        {
                stb_vorbis_close(vf);
                return 0;
        }

        pcm = (s16 *)malloc(totalSamples * sizeof(s16));
        if (pcm == NULL)
        {
                fprintf(stderr, "[CustomMusic] Sin memoria para decodificar OGG.\n");
                stb_vorbis_close(vf);
                return 0;
        }

        samplesRead = stb_vorbis_get_samples_short_interleaved(
                vf, info.channels, pcm, (int)totalSamples);
        stb_vorbis_close(vf);

        /* stb ya devuelve per-channel (frames), no shorts totales. */
        framesRead = samplesRead;
        if (framesRead <= 0)
        {
                free(pcm);
                return 0;
        }

        *pcmOut = pcm;
        *frameCountOut = framesRead;
        *channelsOut = info.channels;
        *sampleRateOut = (int)info.sample_rate;
        return 1;
}

static int NativeCustomMusic_FileExists(const char *path)
{
        FILE *f = fopen(path, "rb");
        if (f == NULL)
                return 0;
        fclose(f);
        return 1;
}

static int NativeCustomMusic_TryStartLevelEx(int levelID, int preservePosition)
{
        char relativePath[512];
        char finalRelativePath[512];
        s16 *newPcm = NULL;
        s16 *newFinalPcm = NULL;

        int newFrameCount = 0;
        int newFinalFrameCount = 0;
        int newChannels = 0;
        int newSampleRate = 0;

        int finalChannels = 0;
        int finalSampleRate = 0;
        u64 startPositionFp = 0;
        u64 startTimeline = 0;

        static int bannerPrinted = 0;

        if (!bannerPrinted)
        {
                printf("[CustomMusic] CTR Native OGG music core (stb_vorbis)\n");
                fflush(stdout);
                bannerPrinted = 1;
        }

        /* --- RESOLVE PATHS (custom level or retail) ----------------- */
        {
                const char *customPath      = LevelRegistry_GetActiveMusicPath(levelID);
                const char *customFinalPath = LevelRegistry_GetActiveMusicFinalPath(levelID);

                if (customPath != NULL)
                {
                        snprintf(relativePath, sizeof(relativePath), "%s", customPath);
                        if (customFinalPath != NULL)
                                snprintf(finalRelativePath, sizeof(finalRelativePath),
                                         "%s", customFinalPath);
                        else
                                finalRelativePath[0] = '\0';
                }
                else
                {
                        snprintf(relativePath, sizeof(relativePath),
                                 "assets/MUSIC_CUSTOM/level_%02d.ogg", levelID);
                        snprintf(finalRelativePath, sizeof(finalRelativePath),
                                 "assets/MUSIC_CUSTOM/level_%02d_final.ogg", levelID);
                }
        }

        /* --- CACHE CHECK (keyed by resolved path) ------------------- */
        NativeAudio_LockOutput();
        if (s_customMusic.pcm != NULL &&
            s_customMusic.cachedPath[0] != '\0' &&
            strcmp(s_customMusic.cachedPath, relativePath) == 0)
        {
                s_customMusic.active = 1;
                s_customMusic.paused = 0;
                s_customMusic.maskMuted = 0;
                /* Retail reinicia la pista al terminar la máscara; el
                 * jugador no nota el reinicio porque el jingle tapa
                 * la transición. */
                s_customMusic.positionFp = 0;
                if (preservePosition)
                        s_customMusic.hubFallback = 0;
                NativeAudio_UnlockOutput();
                return 1;
        }
        /* silent cache miss */
        NativeAudio_UnlockOutput();

        if (!NativeCustomMusic_FileExists(relativePath))
        {
                printf("[CustomMusic] Level %d: sin %s\n",
                       levelID, relativePath);
                fflush(stdout);
                if (s_hubClockActive) NativeCustomMusic_StopTrackKeepHub();
                else                  NativeCustomMusic_Stop();
                return 0;
        }

        printf("[CustomMusic] Level %d: cargando %s\n", levelID, relativePath);
        fflush(stdout);

        if (!NativeCustomMusic_LoadOgg(relativePath, &newPcm, &newFrameCount,
                                       &newChannels, &newSampleRate))
        {
                fprintf(stderr,
                        "[CustomMusic] Level %d: fallo al cargar %s; uso CSEQ original.\n",
                        levelID, relativePath);
                if (s_hubClockActive) NativeCustomMusic_StopTrackKeepHub();
                else                  NativeCustomMusic_Stop();
                return 0;
        }

        if (NativeCustomMusic_FileExists(finalRelativePath))
        {
                printf("[CustomMusic] Level %d: cargando Final Lap %s\n",
                       levelID, finalRelativePath);
                fflush(stdout);

                if (!NativeCustomMusic_LoadOgg(finalRelativePath, &newFinalPcm,
                                               &newFinalFrameCount,
                                               &finalChannels, &finalSampleRate))
                {
                        printf("[CustomMusic] Final Lap invalido; uso tema normal.\n");
                        fflush(stdout);
                        newFinalPcm = NULL;
                        newFinalFrameCount = 0;
                }
                else if ((finalChannels != newChannels) ||
                         (finalSampleRate != newSampleRate))
                {
                        printf("[CustomMusic] Final Lap debe tener mismos canales y sample rate; uso tema normal.\n");
                        fflush(stdout);
                        free(newFinalPcm);
                        newFinalPcm = NULL;
                        newFinalFrameCount = 0;
                }
        }
        else
        {
                printf("[CustomMusic] Level %d: sin Final Lap custom.\n", levelID);
                fflush(stdout);
        }

        NativeAudio_LockOutput();
        if (preservePosition && s_hubClockActive && newFrameCount > 0)
        {
                u64 mappedFrame;
                startTimeline = s_hubClockFrames;
                mappedFrame = (startTimeline * (u64)newSampleRate) /
                              CUSTOM_MUSIC_OUTPUT_RATE;
                startPositionFp = (mappedFrame % (u64)newFrameCount) <<
                                  CUSTOM_MUSIC_FP_SHIFT;
        }
        NativeCustomMusic_StopNoLock(1);

        s_customMusic.pcm = newPcm;
        s_customMusic.frameCount = newFrameCount;
        s_customMusic.finalPcm = newFinalPcm;
        s_customMusic.finalFrameCount = newFinalFrameCount;
        s_customMusic.finalLapActive = 0;

        s_customMusic.channels = newChannels;
        s_customMusic.sampleRate = newSampleRate;
        s_customMusic.positionFp = startPositionFp;
        s_customMusic.timelineOutputFrames = startTimeline;
        s_customMusic.stepFp =
                (u32)(((u64)newSampleRate << CUSTOM_MUSIC_FP_SHIFT) /
                      CUSTOM_MUSIC_OUTPUT_RATE);

        if (s_customMusic.stepFp == 0)
                s_customMusic.stepFp = 1;

        s_customMusic.active = 1;
        s_customMusic.paused = 0;
        s_customMusic.maskMuted = 0;
        s_customMusic.hubFallback = 0;
        s_customMusic.volume = (sdata->vol_Music * 70) / 255;
        s_customMusic.levelID = levelID;

        NativeAudio_UnlockOutput();

        printf("[CustomMusic] Level %d: OK - %d Hz, %d canal(es), %d frames.\n",
               levelID, newSampleRate, newChannels, newFrameCount);
        fflush(stdout);

        NativeAudio_LockOutput();
        strncpy(s_customMusic.cachedPath, relativePath,
                sizeof(s_customMusic.cachedPath) - 1);
        s_customMusic.cachedPath[sizeof(s_customMusic.cachedPath) - 1] = '\0';
        NativeAudio_UnlockOutput();

        return 1;
}

int NativeCustomMusic_TryStartLevel(int levelID)
{
        return NativeCustomMusic_TryStartLevelEx(levelID, 0);
}

int NativeCustomMusic_TrySwapHub(int levelID)
{
        char relativePath[128];
        snprintf(relativePath, sizeof(relativePath),
                 "assets/MUSIC_CUSTOM/level_%02d.ogg", levelID);
        if (!NativeCustomMusic_FileExists(relativePath))
        {
                NativeAudio_LockOutput();
                if (s_customMusic.active) s_customMusic.hubFallback = 1;
                NativeAudio_UnlockOutput();
                return 0;
        }
        return NativeCustomMusic_TryStartLevelEx(levelID, 1);
}

int NativeCustomMusic_ShouldMuteLevelCseq(void)
{
        int mute;
        NativeAudio_LockOutput();
        mute = s_customMusic.active && !s_customMusic.hubFallback;
        NativeAudio_UnlockOutput();
        return mute;
}

int NativeCustomMusic_IsActive(void)
{
        int active;
        NativeAudio_LockOutput();
        active = s_customMusic.active;
        NativeAudio_UnlockOutput();
        return active;
}

void NativeCustomMusic_Stop(void)
{
        NativeAudio_LockOutput();
        NativeCustomMusic_StopNoLock(0);
        s_hubClockActive = 0;
        s_hubClockFrames = 0;
        s_hubClockPaused = 0;
        NativeAudio_UnlockOutput();
}

void NativeCustomMusic_SetPaused(int paused)
{
        NativeAudio_LockOutput();
        s_hubClockPaused = paused != 0;
        if (s_customMusic.active)
                s_customMusic.paused = paused != 0;
        NativeAudio_UnlockOutput();
}

void NativeCustomMusic_SetMaskMuted(int muted)
{
        NativeAudio_LockOutput();
        if (s_customMusic.active) s_customMusic.maskMuted = muted != 0;
        NativeAudio_UnlockOutput();
}

void NativeCustomMusic_SetVolume(int volume)
{
        int scaled;
        if (volume < 0) volume = 0;
        else if (volume > 255) volume = 255;
        scaled = (volume * 70) / 255;

        NativeAudio_LockOutput();
        if (s_customMusic.active) s_customMusic.volume = scaled;
        NativeAudio_UnlockOutput();
}

void NativeCustomMusic_Restart(void)
{
        NativeAudio_LockOutput();
        if (s_customMusic.active)
        {
                s_customMusic.positionFp = 0;
                s_customMusic.timelineOutputFrames = 0;
                if (s_hubClockActive) s_hubClockFrames = 0;
                s_customMusic.paused = 0;
                s_customMusic.maskMuted = 0;
                s_customMusic.finalLapActive = 0;
                s_customMusic.finalLapRequested = 0;
        }
        NativeAudio_UnlockOutput();
}

void NativeCustomMusic_EndRace(void)
{
        NativeAudio_LockOutput();
        if (s_customMusic.active)
        {
                if (s_customMusic.finalLapActive && s_customMusic.frameCount > 0 &&
                    s_customMusic.finalFrameCount > 0)
                {
                        u64 finalFrame = s_customMusic.positionFp >> CUSTOM_MUSIC_FP_SHIFT;
                        u64 normalFrame =
                                ((finalFrame % (u64)s_customMusic.finalFrameCount) *
                                 (u64)s_customMusic.frameCount) /
                                (u64)s_customMusic.finalFrameCount;
                        s_customMusic.positionFp =
                                (normalFrame << CUSTOM_MUSIC_FP_SHIFT) |
                                (s_customMusic.positionFp & (CUSTOM_MUSIC_FP_ONE - 1));
                }
                s_customMusic.finalLapActive = 0;
                s_customMusic.finalLapRequested = 0;
                s_customMusic.raceEndSeen = 1;
                s_customMusic.paused = 1;
        }
        NativeAudio_UnlockOutput();
}

void NativeCustomMusic_EnableFinalLap(void)
{
        int changed = 0;
        int hasFinal = 0;
        int firstRequest = 0;

        NativeAudio_LockOutput();

        if (s_customMusic.active && sdata->audioState != AUDIO_RACE_END)
        {
                if (!s_customMusic.finalLapRequested)
                {
                        s_customMusic.finalLapRequested = 1;
                        firstRequest = 1;
                }
                if (!s_customMusic.finalLapActive &&
                    (s_customMusic.finalPcm != NULL) &&
                    (s_customMusic.finalFrameCount > 0) &&
                    (s_customMusic.frameCount > 0))
                {
                        u64 normalFrame = s_customMusic.positionFp >> CUSTOM_MUSIC_FP_SHIFT;
                        u64 finalFrame;
                        normalFrame %= (u64)s_customMusic.frameCount;
                        finalFrame = (normalFrame * (u64)s_customMusic.finalFrameCount) /
                                     (u64)s_customMusic.frameCount;
                        s_customMusic.positionFp = finalFrame << CUSTOM_MUSIC_FP_SHIFT;
                        s_customMusic.finalLapActive = 1;
                        hasFinal = 1;
                        changed = 1;
                }
                else if (s_customMusic.finalLapActive)
                {
                        hasFinal = 1;
                }
        }

        NativeAudio_UnlockOutput();

        if (changed)
                printf("[CustomMusic] FINAL LAP -> usando _final.ogg\n");
        else if (!hasFinal && firstRequest)
                printf("[CustomMusic] FINAL LAP -> sin _final.ogg; OGG normal continua\n");

        fflush(stdout);
}

static s16 *NativeCustomMusic_GetCurrentPcm(void)
{
        if (s_customMusic.finalLapActive &&
            (s_customMusic.finalPcm != NULL) &&
            (s_customMusic.finalFrameCount > 0))
                return s_customMusic.finalPcm;
        return s_customMusic.pcm;
}

static int NativeCustomMusic_GetCurrentFrameCount(void)
{
        if (s_customMusic.finalLapActive &&
            (s_customMusic.finalPcm != NULL) &&
            (s_customMusic.finalFrameCount > 0))
                return s_customMusic.finalFrameCount;
        return s_customMusic.frameCount;
}

static int NativeCustomMusic_ReadSample(int channel)
{
        s16 *pcm;
        int frameCount;
        u64 frame0;
        u64 frame1;
        u32 frac;
        int sample0;
        int sample1;

        if (!s_customMusic.active || s_customMusic.paused)
                return 0;

        pcm = NativeCustomMusic_GetCurrentPcm();
        frameCount = NativeCustomMusic_GetCurrentFrameCount();

        if ((pcm == NULL) || (frameCount <= 0))
                return 0;

        frame0 = s_customMusic.positionFp >> CUSTOM_MUSIC_FP_SHIFT;

        if (frame0 >= (u64)frameCount)
        {
                frame0 %= (u64)frameCount;
                s_customMusic.positionFp = frame0 << CUSTOM_MUSIC_FP_SHIFT;
        }

        frame1 = frame0 + 1;
        if (frame1 >= (u64)frameCount)
                frame1 = 0;

        if (s_customMusic.channels == 1)
        {
                sample0 = pcm[frame0];
                sample1 = pcm[frame1];
        }
        else
        {
                sample0 = pcm[frame0 * 2 + channel];
                sample1 = pcm[frame1 * 2 + channel];
        }

        frac = (u32)(s_customMusic.positionFp & (CUSTOM_MUSIC_FP_ONE - 1));
        return sample0 + (int)(((s64)(sample1 - sample0) * frac) >> CUSTOM_MUSIC_FP_SHIFT);
}

void NativeCustomMusic_MixFrameNoLock(int *mixLeft, int *mixRight,
                                      s16 masterLeft, s16 masterRight)
{
        int left;
        int right;
        int frameCount;
        int maskPlaying = 0;
        int i;
        s64 scaledLeft;
        s64 scaledRight;

        if (s_hubClockActive && !s_hubClockPaused) s_hubClockFrames++;

        if (!s_customMusic.active || s_customMusic.paused)
                return;

        frameCount = NativeCustomMusic_GetCurrentFrameCount();
        if (frameCount <= 0)
                return;

        left = NativeCustomMusic_ReadSample(0);
        right = NativeCustomMusic_ReadSample(s_customMusic.channels == 1 ? 0 : 1);

        if (sdata->audioState != AUDIO_RACE_END)
                s_customMusic.raceEndSeen = 0;
        else if (sdata->XA_State != XA_IDLE && !s_customMusic.raceEndSeen)
        {
                if (s_customMusic.finalLapActive && s_customMusic.frameCount > 0 &&
                    s_customMusic.finalFrameCount > 0)
                {
                        u64 finalFrame = s_customMusic.positionFp >> CUSTOM_MUSIC_FP_SHIFT;
                        u64 normalFrame =
                                ((finalFrame % (u64)s_customMusic.finalFrameCount) *
                                 (u64)s_customMusic.frameCount) /
                                (u64)s_customMusic.finalFrameCount;
                        s_customMusic.positionFp =
                                (normalFrame << CUSTOM_MUSIC_FP_SHIFT) |
                                (s_customMusic.positionFp & (CUSTOM_MUSIC_FP_ONE - 1));
                }
                s_customMusic.finalLapActive = 0;
                s_customMusic.finalLapRequested = 0;
                s_customMusic.raceEndSeen = 1;
                left = NativeCustomMusic_ReadSample(0);
                right = NativeCustomMusic_ReadSample(s_customMusic.channels == 1 ? 0 : 1);
        }

        /* Detect retail mask CSEQ (songID 1 or 2) and mute ourselves. */
        if (sdata->ptrCseqHeader != NULL)
        {
                for (i = 0; i < 2; i++)
                {
                        struct Song *song = &sdata->songPool[i];
                        if ((song->flags & 1) && (song->id == 1 || song->id == 2))
                        {
                                maskPlaying = 1;
                                break;
                        }
                }
        }
        if (!maskPlaying) s_customMusic.maskMuted = 0;
        if (maskPlaying || s_customMusic.maskMuted || s_customMusic.hubFallback ||
            (sdata->audioState == AUDIO_RACE_INTRO) ||
            (sdata->audioState == AUDIO_RACE_END) ||
            (sdata->audioState == AUDIO_STOP_ALL) ||
            (sdata->audioState == AUDIO_TRAFFIC))
                left = right = 0;

        scaledLeft = (s64)left * s_customMusic.volume * masterLeft;
        scaledRight = (s64)right * s_customMusic.volume * masterRight;
        scaledLeft /= (255 * 0x3fff);
        scaledRight /= (255 * 0x3fff);

        *mixLeft += (int)scaledLeft;
        *mixRight += (int)scaledRight;

        s_customMusic.positionFp += s_customMusic.stepFp;
        s_customMusic.timelineOutputFrames++;

        while ((s_customMusic.positionFp >> CUSTOM_MUSIC_FP_SHIFT) >= (u64)frameCount)
                s_customMusic.positionFp -= ((u64)frameCount << CUSTOM_MUSIC_FP_SHIFT);
}