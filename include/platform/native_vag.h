#ifndef NATIVE_VAG_H
#define NATIVE_VAG_H

#include <common.h>

/* Voices 24+ are outside the range HOWL_Channel.c iterates
 * (NUM_SFX_CHANNELS = 24). Custom VAG features use those voices
 * without any reservation hack. Each feature picks its own; dance
 * SFX uses 24 (NATIVE_DANCE_SFX_SPU_VOICE in native_custom_racer.h). */

/* Load a VAG file into SPU RAM at a fixed address.
 * Skips the 48-byte VAG header; writes only the raw ADPCM to SPU.
 * Returns the SPU address on success, 0 on failure.
 * If out_size is non-NULL, receives the ADPCM byte size. */
u32 NativeVag_Load(const char *path, u32 spu_addr, u32 *out_size);

/* Trigger a VAG on a specific SPU voice (0..23).
 * spu_addr: value returned by NativeVag_Load.
 * volume_l, volume_r: 0..0x3FFF (0x3FFF = max).
 * pitch: 0x1000 = 1.0x. */
void NativeVag_Play(u32 spu_addr, int voice,
                    int volume_l, int volume_r, int pitch);

/* Stop a voice. */
void NativeVag_Stop(int voice);

/* Loads a 16-byte ADPCM silence block into a reserved SPU address
 * (once) and points the voice's addr at it, with pitch 0x1000 and
 * zero volume. After this, if another audio path (CSEQ/OtherFX)
 * key-ons the voice without setting the addr, it plays silence. */
void NativeVag_PointVoiceAtSilence(int voice);
/* Debug helper: loads assets/vag_test.vag on first call
 * (cached), then plays it on voice 23 at 50% volume.
 * Wired to a hotkey behind CTR_DEBUG_VAG_TEST. */
void NativeVag_TestPlay(void);

#endif