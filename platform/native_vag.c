#include <common.h>
#include <platform/native_vag.h>
#include <platform/native_audio.h>
#include <psx/libspu.h>

#include <stdio.h>
#include <string.h>

#define VAG_HEADER_SIZE 48

/* Test address: 0x70000 = 448 KB. Assumed above retail usage.
 * Confirmed safely below NATIVE_AUDIO_SPU_MEMSIZE (512 KB). */
#define NATIVE_VAG_TEST_ADDR  0x70000u
#define NATIVE_VAG_TEST_VOICE 23

/* Scratch buffer: 256 KB max VAG (enough for short SFX + short loops). */
static u8 s_vagScratch[256 * 1024];

static u32 ReadLE32(const u8 *p)
{
    return (u32)p[0] | ((u32)p[1] << 8) | ((u32)p[2] << 16) | ((u32)p[3] << 24);
}

u32 NativeVag_Load(const char *path, u32 spu_addr, u32 *out_size)
{
    FILE *f = fopen(path, "rb");
    if (f == NULL) {
        fprintf(stderr, "[VAG] fopen failed: %s\n", path);
        return 0;
    }

    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);

    if (size < VAG_HEADER_SIZE || size > (long)sizeof(s_vagScratch)) {
        fprintf(stderr, "[VAG] bad size: %ld (max %d)\n",
                size, (int)sizeof(s_vagScratch));
        fclose(f);
        return 0;
    }

    size_t n = fread(s_vagScratch, 1, (size_t)size, f);
    fclose(f);
    if (n != (size_t)size) {
        fprintf(stderr, "[VAG] short read: %zu != %ld\n", n, size);
        return 0;
    }

    if (memcmp(s_vagScratch, "VAGp", 4) != 0) {
        fprintf(stderr, "[VAG] bad magic\n");
        return 0;
    }

    u32 dataSize = ReadLE32(s_vagScratch + 0x0C);
    if (dataSize == 0 || (VAG_HEADER_SIZE + dataSize) > (u32)size) {
        fprintf(stderr, "[VAG] invalid dataSize: %u (file %ld)\n",
                dataSize, size);
        return 0;
    }

    /* Set SPU transfer destination, then write ADPCM (skip VAG header). */
    NativeAudio_SpuSetTransferStartAddr(spu_addr);
    u32 written = NativeAudio_SpuWrite(s_vagScratch + VAG_HEADER_SIZE, dataSize);
    if (written != dataSize) {
        fprintf(stderr, "[VAG] short write: %u != %u\n", written, dataSize);
        return 0;
    }

    if (out_size != NULL) *out_size = dataSize;

    fprintf(stderr, "[VAG] loaded %s: %u bytes ADPCM -> SPU 0x%X\n",
            path, dataSize, spu_addr);
    return spu_addr;
}

void NativeVag_Play(u32 spu_addr, int voice, int volume_l, int volume_r, int pitch, int loop)
{
    if (voice < 0 || voice >= 32) return;
    if (spu_addr == 0) return;

    SpuVoiceAttr attr;
    memset(&attr, 0, sizeof(attr));
    attr.voice = (u32)(1u << voice);
    attr.mask  = SPU_VOICE_WDSA
               | SPU_VOICE_VOLL | SPU_VOICE_VOLR
               | SPU_VOICE_PITCH
               | SPU_VOICE_ADSR_AR | SPU_VOICE_ADSR_DR   
               | SPU_VOICE_ADSR_SR | SPU_VOICE_ADSR_SL   
               | SPU_VOICE_ADSR_RR
               | SPU_VOICE_ADSR_AMODE | SPU_VOICE_ADSR_SMODE
               | SPU_VOICE_ADSR_RMODE;

    attr.addr         = spu_addr;
    attr.volume.left  = (short)volume_l;
    attr.volume.right = (short)volume_r;
    attr.pitch        = (u16)pitch;

    /* Envelope: one-shot (attack/release) for loop==0, sustain-held
     * for loop==1. The VAG data must carry the loop-start / loop-end
     * block flags (vag_codec.py --loop) for the SPU to actually
     * wrap; the envelope only decides whether the voice keeps
     * producing sound after the wrap. */
    attr.ar = 0x00;   /* fastest attack */
    attr.dr = 0x0F;
    if (loop) {
        attr.sr = 0x00;
        attr.sl = 0x0F;   /* sustain at max level forever */
        attr.rr = 0x00;
        attr.r_mode = 0x01;
    } else {
        attr.sr = 0x7F;
        attr.sl = 0x02;
        attr.rr = 0x0F;
        attr.r_mode = 0x03;
    }
    attr.a_mode = 0x05;
    attr.s_mode = 0x01;

    /* Key off any previous state, set attr, then key on. */
    NativeAudio_SpuSetKey(0, 1u << voice);
    NativeAudio_SpuSetVoiceAttr(&attr);
    NativeAudio_SpuSetKey(1, 1u << voice);

#if defined(CTR_DEBUG_PODIUM_JUMP)
    if (voice == NATIVE_DANCE_SFX_SPU_VOICE)
        fprintf(stderr, "[VAG24] play addr=0x%X pitch=0x%X loop=%d\n",
                (unsigned)spu_addr, (unsigned)pitch, loop);    
#endif
}

void NativeVag_Stop(int voice)
{
    if (voice < 0 || voice >= 32) return;
    NativeAudio_SpuSetKey(0, 1u << voice);

#if defined(CTR_DEBUG_PODIUM_JUMP)
    if (voice == NATIVE_DANCE_SFX_SPU_VOICE)
        fprintf(stderr, "[VAG24] stop\n");
#endif
}

void NativeVag_TestPlay(void)
{
    static u32 s_loaded_addr = 0;

    if (s_loaded_addr == 0) {
        s_loaded_addr = NativeVag_Load("assets/vag_test.vag",
                                       NATIVE_VAG_TEST_ADDR, NULL);
        if (s_loaded_addr == 0) {
            fprintf(stderr, "[VAG-TEST] load failed\n");
            return;
        }
    }

    NativeVag_Play(s_loaded_addr, NATIVE_VAG_TEST_VOICE,
                   0x2000, 0x2000,   /* ~50% volume */
                   0x1000,           /* 1.0x pitch */
                   0);               /* one-shot */
    fprintf(stderr, "[VAG-TEST] played on voice %d\n", NATIVE_VAG_TEST_VOICE);
}