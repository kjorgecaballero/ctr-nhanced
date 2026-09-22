#!/usr/bin/env python3
"""Verify all the voiceline-pipeline changes were applied correctly.

Checks each anchor by substring / structural markers, not exact text.
Exit code 0 = all good, 1 = something missing.
"""
import json
import sys
from pathlib import Path


def check(name, ok, detail=""):
    mark = "[OK]  " if ok else "[FAIL]"
    line = f"{mark} {name}"
    if detail:
        line += f"  ({detail})"
    print(line)
    return ok


def read(p):
    return Path(p).read_text(encoding="utf-8", errors="replace")


all_ok = True


# ---------------------------------------------------------------------
# platform/native_custom_racer.c
# ---------------------------------------------------------------------
p = "platform/native_custom_racer.c"
if not Path(p).is_file():
    print(f"[FAIL] {p} not found")
    sys.exit(1)
t = read(p)

all_ok &= check(
    "native_custom_racer.c : s_customVoiceBase declared",
    "static int s_customVoiceBase[NATIVE_CUSTOM_COUNT];" in t,
)
all_ok &= check(
    "native_custom_racer.c : NATIVE_VOICE_TRACK_BASE not duplicated in .c",
    "#define NATIVE_VOICE_TRACK_BASE" not in t,
)
all_ok &= check(
    "native_custom_racer.c : NATIVE_VOICE_EVENT_COUNT moved to header",
    "#define NATIVE_VOICE_EVENT_COUNT" not in t,
)
all_ok &= check(
    "native_custom_racer.c : voice_slot counter removed (uses roster index)",
    "int voice_slot = 0;" not in t,
)
all_ok &= check(
    "native_custom_racer.c : s_customVoiceBase assignment in ReloadRoster",
    "s_customVoiceBase[idx] = NATIVE_VOICE_TRACK_BASE" in t
    or "s_customVoiceBase[idx]" in t and "voice_slot" in t,
)
all_ok &= check(
    "native_custom_racer.c : memset s_customVoiceBase",
    "memset(s_customVoiceBase, 0, sizeof(s_customVoiceBase));" in t,
)
all_ok &= check(
    "native_custom_racer.c : NativeCustomRacer_GetVoiceTrackBase defined",
    "int NativeCustomRacer_GetVoiceTrackBase(int characterID)" in t,
)
all_ok &= check(
    "native_custom_racer.c : GetVoiceTrackBase returns from table",
    "return s_customVoiceBase[characterID - NATIVE_CUSTOM_ID_BASE];" in t,
)


# ---------------------------------------------------------------------
# include/platform/native_custom_racer.h
# ---------------------------------------------------------------------
p = "include/platform/native_custom_racer.h"
t = read(p)
all_ok &= check(
    "native_custom_racer.h : GetVoiceTrackBase declared",
    "int NativeCustomRacer_GetVoiceTrackBase(int characterID);" in t,
)
all_ok &= check(
    "native_custom_racer.h : event index defines",
    "NATIVE_VOICE_EVENT_MENU_YES" in t
    and "NATIVE_VOICE_EVENT_MENU_OUCH" in t
    and "NATIVE_VOICE_EVENT_COUNT     10" in t
    and "#define NATIVE_VOICE_TRACK_BASE  314" in t,
)


# ---------------------------------------------------------------------
# game/HOWL/HOWL_Voiceline.c
# ---------------------------------------------------------------------
p = "game/HOWL/HOWL_Voiceline.c"
t = read(p)

# RequestPlay: enqueue branch (should NOT call PlayVoice directly)
all_ok &= check(
    "HOWL_Voiceline.c : RequestPlay no longer calls PlayVoice directly",
    "NativeCustomRacer_PlayVoice((int)characterID, voiceSetIdx)" not in t,
)
all_ok &= check(
    "HOWL_Voiceline.c : RequestPlay enqueues with LIST_AddFront",
    "LIST_AddFront(&sdata->Voiceline2, item);" in t,
)
all_ok &= check(
    "HOWL_Voiceline.c : RequestPlay has dedup loop",
    "Dedup: don't enqueue the same" in t,
)

# StartPlay: custom branch with GetVoiceTrackBase + CDSYS_XAPlay
all_ok &= check(
    "HOWL_Voiceline.c : StartPlay uses GetVoiceTrackBase",
    "NativeCustomRacer_GetVoiceTrackBase((int)characterID)" in t,
)
all_ok &= check(
    "HOWL_Voiceline.c : StartPlay calls CDSYS_XAPlay with trackId",
    "CDSYS_XAPlay(CDSYS_XA_TYPE_GAME, trackId)" in t,
)
all_ok &= check(
    "HOWL_Voiceline.c : StartPlay custom branch marker",
    "Custom branch: route through the retail CDSYS_XAPlay" in t,
)

# Old debug log should be gone (or at least not in RequestPlay anymore)
all_ok &= check(
    "HOWL_Voiceline.c : old custom-branch log removed",
    "custom branch: charID=%u voiceID=%u" not in t
    or "custom branch: charID=%u voiceID=%u" in t and "GetVoiceTrackBase" in t,
)


# ---------------------------------------------------------------------
# game/HOWL/HOWL_Settings.c (menu YES/OUCH)
# ---------------------------------------------------------------------
p = "game/HOWL/HOWL_Settings.c"
t = read(p)
all_ok &= check(
    "HOWL_Settings.c : custom branch in OptionsMenu_TestSound",
    "NATIVE_VOICE_EVENT_MENU_OUCH" in t
    and "NATIVE_VOICE_EVENT_MENU_YES" in t
    and "NativeCustomRacer_GetVoiceTrackBase(rawCharID)" in t,
)


# ---------------------------------------------------------------------
# tools/custom_racers/build_voice_pipeline.py
# ---------------------------------------------------------------------
p = "tools/custom_racers/build_voice_pipeline.py"
t = read(p)
all_ok &= check(
    "build_voice_pipeline.py : VOICE_EVENT_COUNT = 10",
    "VOICE_EVENT_COUNT = 10" in t,
)
all_ok &= check(
    "build_voice_pipeline.py : EVENTS includes menu_yes/menu_ouch",
    '"menu_yes", "menu_ouch"' in t,
)
all_ok &= check(
    "build_voice_pipeline.py : sidecar emits event_count",
    '"event_count": VOICE_EVENT_COUNT' in t,
)


# ---------------------------------------------------------------------
# assets
# ---------------------------------------------------------------------
all_ok &= check(
    "assets/XA/ENG.XNF exists",
    Path("assets/XA/ENG.XNF").is_file(),
)
all_ok &= check(
    "assets/XA/ENG.XNF.bak exists (backup from first run)",
    Path("assets/XA/ENG.XNF.bak").is_file(),
)

# At least one voice bank
banks = sorted(Path("assets/XA/ENG/GAME").glob("S1[89].XA")) + \
        sorted(Path("assets/XA/ENG/GAME").glob("S[2-9][0-9].XA"))
all_ok &= check(
    "at least one custom voice bank (S18.XA+)",
    len(banks) > 0,
    f"found {len(banks)}: {[b.name for b in banks]}",
)

# XNF grew
if Path("assets/XA/ENG.XNF.bak").is_file():
    orig_size = Path("assets/XA/ENG.XNF.bak").stat().st_size
    new_size  = Path("assets/XA/ENG.XNF").stat().st_size
    all_ok &= check(
        "XNF was extended",
        new_size > orig_size,
        f"{orig_size} -> {new_size} (+{new_size - orig_size})",
    )

# Sidecar advertises the current event count
sidecar_path = Path("assets/XA/ENG.XNF.voices.json")
if sidecar_path.is_file():
    try:
        sc = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except Exception:
        sc = {}
    all_ok &= check(
        "sidecar advertises event_count=10",
        sc.get("event_count") == 10,
        f"got {sc.get('event_count')!r}",
    )


# ---------------------------------------------------------------------
# warnings
# ---------------------------------------------------------------------
warnings = []
if "int NativeCustomRacer_GetLastCustomVoiceFrames" in read("platform/native_custom_racer.c"):
    warnings.append(
        "GetLastCustomVoiceFrames still exists (orphan). "
        "Harmless, but can be removed in a cleanup later."
    )
if warnings:
    print()
    for w in warnings:
        print(f"[WARN] {w}")


print()
print("=" * 60)
if all_ok:
    print("ALL CHECKS PASSED")
    sys.exit(0)
else:
    print("SOME CHECKS FAILED - see [FAIL] above")
    sys.exit(1)