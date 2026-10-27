# Audio Restore Procedure — XNF + S\*.XA

How to restore retail audio if the custom voice pipeline corrupts `assets/XA/`.

## When to use this

Symptoms of broken audio:

- Boss cutscenes skip at frame 2 with no voice
- Any retail voice (Crash, Cortex, commentator) is silent
- Retail podium music is silent
- `[XA-LOOKUP] FAIL` lines in logs
- `CDSYS_XAPlay` returns 0 silently

Common causes:

- Pipeline with `VOICE_BANK_BASE=18` (overwrites retail S18-S20)
- XNF with `numTracks > 414` but no matching S\*.XA files
- `assets/XA/ENG/MUSIC/` is empty
- `.bak` overwritten with an already-processed XNF

## Backup

**Location:** `C:\Users\Kevin\Desktop\CTR_audio_retail_clean_backup_20261026\`

**Contents:** `XA/` with retail XNF (414 tracks) + `ENG/GAME/` (S00-S20) + `ENG/EXTRA/` (S00-S05) + `MUSIC/` (S00-S01).

**Size:** ~55-60 MB.

## Restore from backup

```bash
cd /c/Users/Kevin/Desktop/Kevin/CTR/native_fork/nhanced
rm -rf assets/XA
cp -r /c/Users/Kevin/Desktop/CTR_audio_retail_clean_backup_20261026/XA assets/XA
```

Verify:

```bash
xxd -l 20 assets/XA/ENG.XNF             # offset 0x10 must be 9e 01 (414)
ls assets/XA/ENG/GAME/*.XA | wc -l      # 21
ls assets/XA/ENG/EXTRA/*.XA | wc -l     # 6
ls assets/XA/MUSIC/*.XA | wc -l         # 2
```

## Regenerate custom XA (only if you have WAVs)

If you have WAVs in `<slug>/voices/` and/or `<slug>/music/podium.wav`:

```bash
python tools/custom_racers/build_voice_pipeline.py -v
```

Verify that it wrote to S21+ (not S18-S20):

```bash
ls assets/XA/ENG/GAME/S2*.XA   # S21+
ls assets/XA/MUSIC/S2*.XA      # S21+
xxd -l 20 assets/XA/ENG.XNF    # offset 0x10 > 0x019e
```

If there are no custom WAVs in the roster:

```bash
python tools/custom_racers/build_voice_pipeline.py -v
# → "No tracks to add." XNF stays at 414 (identical to backup)
```

## Critical rules

1. **NEVER touch `assets/XA/ENG.XNF.bak`** — it is the pristine base of the pipeline. If it is corrupted, the guard fails with "not pristine".
2. **If the guard fails, do NOT run the `rm` it suggests.** The message says:
   ```
   Restore with:
     rm assets/XA/ENG.XNF assets/XA/ENG.XNF.bak
     python extract_xnf.py
   ```
   **That `rm` deletes the retail `.bak`.** Instead:
   ```bash
   cp /c/Users/Kevin/Desktop/CTR_audio_retail_clean_backup_20261026/XA/ENG.XNF.bak assets/XA/ENG.XNF.bak
   cp /c/Users/Kevin/Desktop/CTR_audio_retail_clean_backup_20261026/XA/ENG.XNF assets/XA/ENG.XNF
   ```
3. **Custom banks always go to S21+** (`VOICE_BANK_BASE=21`, `MUSIC_BANK_BASE=21`). Retail occupies S00-S20. No overlap.

## Retail XNF layout (414 tracks)

```
MUSIC retail:   xaID 0..12   (13 tracks)  → MUSIC/S00.XA..S12.XA
EXTRA retail:   xaID 0..86   (87 tracks)  → EXTRA/S00.XA..S05.XA
GAME retail:    xaID 0..313  (314 tracks) → GAME/S00.XA..S20.XA
```

Custom (after `build_voice_pipeline.py`):

```
MUSIC custom:   xaID 13..      → MUSIC/S21.XA+
GAME custom:    xaID 314..     → GAME/S21.XA+
```

## Related commits

- `f2be8a48f` — pipeline: `_roster_filter` 0-23, `BANK_BASE=21`
