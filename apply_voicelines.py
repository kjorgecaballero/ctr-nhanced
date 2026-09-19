#!/usr/bin/env python3
"""Apply custom voicelines (v1) to the CTR Native tree. Idempotent."""
import sys
from pathlib import Path

ROOT = Path(".").resolve()

def read_preserve(path):
    raw = path.read_bytes()
    had_crlf = b"\r\n" in raw
    return raw.decode("utf-8").replace("\r\n", "\n"), had_crlf

def write_preserve(path, text, had_crlf):
    if had_crlf:
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))

def patch(path, old, new, label):
    p = ROOT / path
    text, had_crlf = read_preserve(p)
    if new in text and old not in text:
        print(f"  [skip] {path}: already applied"); return
    if old not in text:
        print(f"  [FAIL] {path}: anchor not found ({label})"); sys.exit(1)
    if text.count(old) > 1:
        print(f"  [FAIL] {path}: anchor x{text.count(old)} ({label})"); sys.exit(1)
    write_preserve(p, text.replace(old, new, 1), had_crlf)
    print(f"  [ok]   {path}: {label}")

# 1) native_custom_racer.h
patch(
    "include/platform/native_custom_racer.h",
    'int NativeCustomRacer_HasWheels(int characterID);\n\n#ifdef __cplusplus\n}\n#endif',
    '''int NativeCustomRacer_HasWheels(int characterID);

/* === Custom voicelines (v1) ============================================
 * Customs deliver XA files under
 *   assets/mods/racers/<slug>/voices/<set>_<var>.xa
 * <set> = 0..10 (data.voiceID[voiceID], same index as retail)
 * <var> = 0..7 (variants; RNG picks one per call).
 * Returns 1 if a custom voice was played. */
int NativeCustomRacer_PlayVoice(int characterID, int voiceSetIndex);

/* Wrapper for Voiceline_RequestPlay call sites. Originals map to their
 * grid enum (retail path); customs (>= NATIVE_CUSTOM_ID_BASE) pass
 * through raw so the custom voice table is used. */
static inline int GET_VOICE_CHAR_ID(int id)
{
    if (id >= NATIVE_CUSTOM_ID_BASE)
        return id;
    return GET_MPK_ID(id);
}

#ifdef __cplusplus
}
#endif''',
    "add voice decls + GET_VOICE_CHAR_ID")

# 2) native_custom_racer.c — include
patch(
    "platform/native_custom_racer.c",
    "#include <platform/native_glad.h>\n#include <ovr_230.h>",
    "#include <platform/native_glad.h>\n#include <platform/native_audio.h>\n#include <ovr_230.h>",
    "add native_audio.h include")

# 2b) table
patch(
    "platform/native_custom_racer.c",
    "static int s_nextModelTexIdx = NATIVE_MODEL_TEX_BASE;\nstatic s16 s_sentinelTexMap[NATIVE_CUSTOM_COUNT][NATIVE_MODEL_TEX_MAX];",
    '''static int s_nextModelTexIdx = NATIVE_MODEL_TEX_BASE;
static s16 s_sentinelTexMap[NATIVE_CUSTOM_COUNT][NATIVE_MODEL_TEX_MAX];

/* Custom voicelines table (see NativeCustomRacer_PlayVoice). */
#define NATIVE_VOICE_SET_COUNT    11
#define NATIVE_VOICE_MAX_VARIANTS 8
#define NATIVE_VOICE_PATH_LEN     128

typedef struct
{
    u8 attempted;
    u8 numVariants;
    char paths[NATIVE_VOICE_MAX_VARIANTS][NATIVE_VOICE_PATH_LEN];
} NativeVoiceSet;

static NativeVoiceSet s_customVoices[NATIVE_CUSTOM_COUNT][NATIVE_VOICE_SET_COUNT];''',
    "add s_customVoices table")

# 2c) memset in ReloadRoster
patch(
    "platform/native_custom_racer.c",
    "    memset(s_sentinelTexMap, 0xFF, sizeof(s_sentinelTexMap));       /* -1 = unset */\n    s_nextModelTexIdx = NATIVE_MODEL_TEX_BASE;",
    "    memset(s_sentinelTexMap, 0xFF, sizeof(s_sentinelTexMap));       /* -1 = unset */\n    memset(s_customVoices, 0, sizeof(s_customVoices));\n    s_nextModelTexIdx = NATIVE_MODEL_TEX_BASE;",
    "memset s_customVoices in ReloadRoster")

# 2d) ProbeVoiceSet + PlayVoice, before LoadModel
patch(
    "platform/native_custom_racer.c",
    "void *NativeCustomRacer_LoadModel(int playerIndex, int characterID)\n{",
    '''/* === Custom voicelines ================================================
 * s_customVoices[charIdx][setIdx] caches probed paths under
 * assets/mods/racers/<slug>/voices/<setIdx>_<var>.xa. Lazy probe: the
 * first PlayVoice for a (custom, set) pair walks variants 0..N-1 with
 * fopen, stops at the first miss. ReloadRoster wipes the table. */
static void ProbeVoiceSet(int charIdx, int setIdx)
{
    NativeVoiceSet *vs = &s_customVoices[charIdx][setIdx];
    if (vs->attempted)
        return;
    vs->attempted = 1;

    const char *folder = NativeCustomRacer_GetFolder(NATIVE_CUSTOM_ID_BASE + charIdx);
    if (folder == NULL)
        return;

    for (int v = 0; v < NATIVE_VOICE_MAX_VARIANTS; v++)
    {
        char path[256];
        snprintf(path, sizeof(path),
                 "assets/mods/racers/%s/voices/%d_%d.xa", folder, setIdx, v);
        FILE *f = fopen(path, "rb");
        if (f == NULL)
            break;
        fclose(f);
        strncpy(vs->paths[v], path, NATIVE_VOICE_PATH_LEN - 1);
        vs->paths[v][NATIVE_VOICE_PATH_LEN - 1] = 0;
        vs->numVariants = (u8)(v + 1);
    }
}

int NativeCustomRacer_PlayVoice(int characterID, int voiceSetIndex)
{
    if (characterID < NATIVE_CUSTOM_ID_BASE)
        return 0;
    if (characterID >= NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT)
        return 0;
    if (voiceSetIndex < 0 || voiceSetIndex >= NATIVE_VOICE_SET_COUNT)
        return 0;

    int charIdx = characterID - NATIVE_CUSTOM_ID_BASE;
    ProbeVoiceSet(charIdx, voiceSetIndex);

    NativeVoiceSet *vs = &s_customVoices[charIdx][voiceSetIndex];
    if (vs->numVariants == 0)
        return 0;

    /* Same RNG as Voiceline_RequestPlay_NextAudioRNG. */
    sdata->audioRNG = ((sdata->audioRNG >> 3) + sdata->audioRNG * 0x20000000) * 5 + 1;
    u32 rng = sdata->audioRNG;
    int variant = (int)(rng % vs->numVariants);

    int vol = sdata->vol_Voice << CDSYS_XA_VOLUME_SHIFT;
    if (NativeAudio_PlayXAFile(vs->paths[variant], 0, vol, vol) == 0)
        return 0;

    Log("[CustomRacer] voiceline: charID=%d set=%d var=%d file=%s\\n",
        characterID, voiceSetIndex, variant, vs->paths[variant]);
    return 1;
}

void *NativeCustomRacer_LoadModel(int playerIndex, int characterID)
{''',
    "add ProbeVoiceSet + PlayVoice")

# 3) HOWL_Voiceline.c
patch(
    "game/HOWL/HOWL_Voiceline.c",
    "#include <common.h>\n\n// does not really touch voiceline",
    "#include <common.h>\n#include <platform/native_custom_racer.h>\n\n// does not really touch voiceline",
    "add native_custom_racer.h include")

patch(
    "game/HOWL/HOWL_Voiceline.c",
    "\tif (voiceID >= 0x18)\n\t{\n\t\treturn;\n\t}\n\n\tif (characterID >= 0x10)\n\t{\n\t\treturn;\n\t}",
    '''\tif (voiceID >= 0x18)
\t{
\t\treturn;
\t}

\t/* === Custom voicelines (v1) ===
\t * Customs (characterID >= NATIVE_CUSTOM_ID_BASE) bypass the retail
\t * queueing path: voiceData[0x10] and timeSet1/2 are indexed by enum
\t * Characters (0..15) and would overrun with custom IDs. Play the
\t * custom XA immediately through NativeAudio. */
\tif (characterID >= NATIVE_CUSTOM_ID_BASE)
\t{
\t\tif (characterID >= NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT)
\t\t\treturn;
\t\tif ((sdata->gGT->gameMode1 & END_OF_RACE) != 0)
\t\t\treturn;
\t\tif (sdata->boolCanPlayVoicelines == 0)
\t\t\treturn;
\t\tif (sdata->voicelineCooldown != 0)
\t\t\treturn;

\t\t{
\t\t\tu8 voiceSetIdx = data.voiceID[voiceID];
\t\t\tif (NativeCustomRacer_PlayVoice((int)characterID, voiceSetIdx) != 0)
\t\t\t{
\t\t\t\tsdata->voicelineCooldown = 0x1e;
\t\t\t}
\t\t}
\t\treturn;
\t}

\tif (characterID >= 0x10)
\t{
\t\treturn;
\t}''',
    "add custom voiceline branch")

# 4) call sites
CALL_SITES = [
    "game/231/RB_Crate.c", "game/231/RB_MaskShieldCloud.c", "game/231/RB_Spider.c",
    "game/BOTS.c", "game/COLL.c", "game/PickupBots.c", "game/PlayLevel.c",
    "game/UI/UI_Meter.c", "game/Vehicle/VehFire.c", "game/Vehicle/VehPhysCrash.c",
    "game/Vehicle/VehPhysProc.c", "game/Vehicle/VehPickState.c",
    "game/Vehicle/VehPickupItem.c",
]
for f in CALL_SITES:
    p = ROOT / f
    text, had_crlf = read_preserve(p)
    lines = text.splitlines(keepends=True)
    changed = False
    for i, line in enumerate(lines):
        if "Voiceline_RequestPlay" in line and "GET_MPK_ID" in line:
            new = line.replace("GET_MPK_ID(", "GET_VOICE_CHAR_ID(")
            if new != line:
                lines[i] = new
                changed = True
    if changed:
        write_preserve(p, "".join(lines), had_crlf)
        print(f"  [ok]   {f}: call sites updated")
    else:
        print(f"  [skip] {f}: no change")

print("\nDone. Next: touch the 3 main files, build, test.")