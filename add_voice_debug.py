#!/usr/bin/env python3
from pathlib import Path
import sys

# Patch 1: log al entrar a la branch custom en HOWL_Voiceline.c
p = Path("game/HOWL/HOWL_Voiceline.c")
raw = p.read_bytes(); had = b"\r\n" in raw
t = raw.decode("utf-8").replace("\r\n", "\n")

OLD1 = '''	if (characterID >= NATIVE_CUSTOM_ID_BASE)
	{
		if (characterID >= NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT)
			return;'''
NEW1 = '''	if (characterID >= NATIVE_CUSTOM_ID_BASE)
	{
		fprintf(stderr, "[CustomRacer] custom branch: charID=%u voiceID=%u\\n", characterID, voiceID);
		if (characterID >= NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT)
			return;'''

if NEW1 in t:
    print("[skip] HOWL already patched")
elif OLD1 in t:
    t = t.replace(OLD1, NEW1, 1)
    if had: t = t.replace("\n", "\r\n")
    p.write_bytes(t.encode("utf-8"))
    print("[ok] HOWL debug log added")
else:
    print("[FAIL] HOWL anchor"); sys.exit(1)

# Patch 2: log en ProbeVoiceSet + PlayVoice
p = Path("platform/native_custom_racer.c")
raw = p.read_bytes(); had = b"\r\n" in raw
t = raw.decode("utf-8").replace("\r\n", "\n")

OLD2 = '''    for (int v = 0; v < NATIVE_VOICE_MAX_VARIANTS; v++)
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
}'''
NEW2 = '''    for (int v = 0; v < NATIVE_VOICE_MAX_VARIANTS; v++)
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
    Log("[CustomRacer] ProbeVoiceSet: charIdx=%d setIdx=%d -> %d variants\\n",
        charIdx, setIdx, vs->numVariants);
}'''

if NEW2 in t:
    print("[skip] ProbeVoiceSet already patched")
elif OLD2 in t:
    t = t.replace(OLD2, NEW2, 1)
    if had: t = t.replace("\n", "\r\n")
    p.write_bytes(t.encode("utf-8"))
    print("[ok] ProbeVoiceSet debug log added")
else:
    print("[FAIL] ProbeVoiceSet anchor"); sys.exit(1)

# Patch 3: log al entrar a PlayVoice + si PlayXAFile falla
p = Path("platform/native_custom_racer.c")
raw = p.read_bytes(); had = b"\r\n" in raw
t = raw.decode("utf-8").replace("\r\n", "\n")

OLD3 = '''    if (NativeAudio_PlayXAFile(audioPath, 0, vol, vol) == 0)
        return 0;'''
NEW3 = '''    if (NativeAudio_PlayXAFile(audioPath, 0, vol, vol) == 0)
    {
        Log("[CustomRacer] PlayXAFile FAILED: %s\\n", audioPath);
        return 0;
    }'''

if NEW3 in t:
    print("[skip] PlayXAFile fail log already present")
elif OLD3 in t:
    t = t.replace(OLD3, NEW3, 1)
    if had: t = t.replace("\n", "\r\n")
    p.write_bytes(t.encode("utf-8"))
    print("[ok] PlayXAFile fail log added")
else:
    print("[FAIL] PlayXAFile anchor"); sys.exit(1)

print("\nDone. Rebuild and test.")