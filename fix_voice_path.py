#!/usr/bin/env python3
from pathlib import Path
import sys

p = Path("platform/native_custom_racer.c")
raw = p.read_bytes()
had_crlf = b"\r\n" in raw
text = raw.decode("utf-8").replace("\r\n", "\n")

OLD = '''    int vol = sdata->vol_Voice << CDSYS_XA_VOLUME_SHIFT;
    if (NativeAudio_PlayXAFile(vs->paths[variant], 0, vol, vol) == 0)
        return 0;'''

NEW = '''    int vol = sdata->vol_Voice << CDSYS_XA_VOLUME_SHIFT;
    /* NativeAudio_PlayXAFile resolves paths via NativeAssets_ResolvePath,
     * which prepends the assets root; ProbeVoiceSet's fopen runs from CWD.
     * Strip "assets/" to bridge the two conventions. */
    const char *audioPath = vs->paths[variant];
    if (strncmp(audioPath, "assets/", 7) == 0)
        audioPath += 7;
    if (NativeAudio_PlayXAFile(audioPath, 0, vol, vol) == 0)
        return 0;'''

if NEW in text:
    print("[skip] already applied"); sys.exit(0)
if OLD not in text:
    print("[FAIL] anchor not found"); sys.exit(1)
text = text.replace(OLD, NEW, 1)
if had_crlf:
    text = text.replace("\n", "\r\n")
p.write_bytes(text.encode("utf-8"))
print("[ok] path fix applied")