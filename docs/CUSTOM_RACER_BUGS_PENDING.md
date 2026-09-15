# Pending bugs in the custom racer system

> Companion document. Every time a specific bug of the custom racer system is
> discovered and not yet fixed, it gets added here with its symptom, cause,
> and designed fix. When it's fixed, it moves to the corresponding commit
> and gets deleted from here.
>
> **Current state (HEAD `65164580a`, branch `nhanced`, origin synced):**
>
> Still pending:
>   (none)
>
> Closed in Fase 3:
>   - `65164580a` LNG display names from roster.txt
>   - `d7b198610` Sentinel CLUT real (BUG-ICON-02)
>   - `162f02aca` expand roster capacity from 48 to 128
>
> Closed in Fase 2:
>   - BUG-ARCADE-ICON-01 (`6c945886a`)
>   - BUG-HISCORE-01 (`5d973c6fe`)
>   - BUG-VOICE-02 (`5d973c6fe`)
>   - BUG-MAP-01 (`01605273d`)
>   - BUG-PODIUM-01 (`41597d689`)
>   - BUG-VOICE-01 (`a38521281`)
>
> Closed in earlier sessions (kept for reference until next cleanup):
>   - BUG-GHOST-01 (`550c6972e`)
>   - BUG-GHOST-02 (`5b66782a9`)
>   - BUG-GHOST-03 (`8f4accdbc`)
>   - BUG-ICON-01 (`f7d208475` + `8a42427fa`)

---

## BUG-PODIUM-01: custom shows the wrong dance model and Tawna on the podium

**Status:** fixed in `41597d689`
**Detected:** this session, confirmed by static analysis of the
`STATIC_*DANCE` enum block.

**Symptom:** when a custom racer (ID 16+) finishes 1st, 2nd or 3rd, the
podium scene shows the wrong dance model and the wrong Tawna variant.
Concretely: rusty (customID 16) displays `STATIC_GARAGETOP` (a garage
building), big_norm (17) shows Tawna1, fantasma (18) shows Tawna2, nash
(19) shows Tawna3, ernest (20) shows Tawna4. Custom IDs 21+ would land on
`STATIC_C` / `STATIC_T` / `STATIC_R` (HUD letters) and eventually
`STATIC_CRASHINTRO`. No crash.

**Confirmed cause:** `game/Podium.c`, `Podium_InitModels`:

    u8 characterID = data.characterIDs[driver->driverID];
    podiumModelIndexArr[rank] = characterID + STATIC_CRASHDANCE;

`STATIC_CRASHDANCE = 0x7E` and the dance block spans 0x7E..0x8D (16
entries, one per original). A customID of 16 already lands on 0x8E
(`STATIC_GARAGETOP`), and higher customIDs walk through Tawna1..Tawna4,
the HUD letters C/T/R, and eventually `STATIC_CRASHINTRO`. The
`modelPtr[]` array is 227 entries (0xE3), so the index is in-bounds and
nothing crashes — the podium just shows garbage.

Secondary: the `switch (characterID)` that selects the Tawna variant
(Crash/Coco -> Tawna2, Polar/Pura -> Tawna3, Cortex/N.Gin -> Tawna4,
default -> Tawna1) never matches a customID, so customs always fall
through to Tawna1.

**Applied fix:** compute `mpkID = GET_MPK_ID(characterID)` once and use
it for both the dance index and the Tawna switch:

    u8 characterID = data.characterIDs[driver->driverID];
    u8 mpkID       = GET_MPK_ID(characterID);

    podiumModelIndexArr[rank] = mpkID + STATIC_CRASHDANCE;
    ...
    switch (mpkID) { ... }

Customs inherit the dance model and Tawna variant of their slot-mate:
rusty -> Crash + Tawna2, nash -> Coco + Tawna2, ernest -> N.Gin + Tawna4.
Originals unchanged (`mpkID == characterID`).

**Verification:** 1P arcade with rusty finishing top-3 shows the Crash
dance animation and Tawna2. Originals (Crash, Coco, N.Gin, Polar)
unchanged. No crash on any custom.

**Related:** same pattern as `RB_TNT.c`, `HOWL_Music.c`, and BUG-VOICE-01.
Per-custom dance animations remain Phase 6 (FUTURE): the
`add_racer.py` / `export_character.py` pipeline does not export a dance
animation yet, so inheritance is the only coherent option.

---

## BUG-VOICE-01: voicelines don't play with a custom

**Status:** fixed in `a38521281`
**Detected:** Phase 2.1

**Symptom:** no voiceline (crash, landing, item, jump) plays when the
driver is a custom. No crash. Silent drop.

**Confirmed cause:** `game/HOWL/HOWL_Voiceline.c`,
`Voiceline_RequestPlay` opens with two explicit guards:

    if (voiceID >= 0x18)      return;
    if (characterID >= 0x10)  return;
    if (characterID2 >= 0x11) return;

`characterID = 16+` fails the second guard and the request is dropped.
The function does not wrap with `GET_MPK_ID` itself.

**Applied fix:** wrap the second (and, where applicable, third) argument
with `GET_MPK_ID` at each call site. 20 sites across 13 files:

    231/RB_Crate.c:479
    231/RB_MaskShieldCloud.c:572
    231/RB_Spider.c:297
    BOTS.c:2859
    COLL.c:2634
    UI/UI_Meter.c:110
    Vehicle/VehFire.c:55
    Vehicle/VehPhysCrash.c:195,219,302
    Vehicle/VehPhysProc.c:2372
    Vehicle/VehPickupItem.c:619,701,841,952,1022
    PickupBots.c:93                (both args wrapped)
    PlayLevel.c:411
    Vehicle/VehPickState.c:69,191

**Not touched:** the guard inside `Voiceline_RequestPlay` stays as-is.
Wrapping inside the function would let the raw 16+ ID reach
`timeSet1[]` / `timeSet2[]`, the `OtherFX_Play(characterID + 0x1c/0x2c)`
tables, and `data.voiceData[characterID].voiceSet[]` — all 16-entry
arrays. `BOTS.c:1035` passes constants (`0xf, 0x10`), both in range.

**Verification:** 1P arcade rusty (Crash voice), 1P arcade ernest (N.Gin
voice), Crash/Tiny originals unchanged, 2P VS rusty+Crash no crash,
Time Trial rusty pass voiceline, battle ernest vs bot with PickupBots
and VehPickState paths exercised.

**Related:** §8.2 of the main context.

---

## BUG-HISCORE-01: high-score entry name colors are wrong for a custom

**Status:** fixed in `5d973c6fe`
**Detected:** this session (Phase 2 closeout sweep, section 8.4)

**Symptom:** when a custom racer (ID 16+) places in the top-5 of a high
score table (relic race end, time trial end, main menu high scores), its
name is drawn in the wrong color. rusty (customID 16) showed BLACK
instead of CRASH_BLUE. customIDs 30+ read past `data.ptrColor[]` entirely.

**Confirmed cause:** five sites do `characterID + N` where the result is
used as an index into `data.ptrColor[]` (`enum DecalFontStyle`, 16 driver
colors at indices 5..20, `NUM_COLORS` = 35):

    game/223.c:271,280              RR_HIGH_SCORE_DRIVER_COLOR_OFFSET (= 5)
    game/224.c:339                  TT_HIGH_SCORE_DRIVER_COLOR_OFFSET (= 5)
    game/230/MM_HighScore.c:160,194 MM_HIGHSCORE_DRIVER_COLOR_OFFSET (= 5)

`HighScoreEntry.characterID` stores the raw ID (`MainGameEnd.c:121,141`
write `data.characterIDs[...]` unchanged), so customs reach these sites
intact.

**Applied fix:** wrap with `GET_MPK_ID` at all five. Customs inherit the
color of their slot-mate (rusty -> CRASH_BLUE, nash -> COCO_MAGENTA,
ernest -> N_GIN_PURPLE). Originals unchanged (mpkID == characterID).

**Verification:** 1P arcade rusty beats a fresh relic race record -> name
in CRASH_BLUE. Time Trial nash -> name in COCO_MAGENTA. Crash / Cortex
unchanged. No crash.

**Related:** same family as BUG-MAP-01, BUG-PODIUM-01, BUG-VOICE-01.

---

## BUG-VOICE-02: options menu voice slider plays the wrong SFX for a custom

**Status:** fixed in `5d973c6fe`
**Detected:** this session (section 8.4 sweep, found while auditing
characterID reads outside GET_MPK_ID).

**Symptom:** in the Options menu, moving the Voice slider with a custom
racer as P1 plays the wrong voice SFX (or a non-existent one). No crash.

**Confirmed cause:** `game/HOWL/HOWL_Settings.c`,
`OptionsMenu_TestSound`:

    int driverID = sdata->gGT->cameraDC[0].driverToFollow->driverID;
    int characterID = data.characterIDs[driverID];       // raw 16+
    ...
    sampleVoiceID = characterID + 0x1c;  // (or +0x2c)
    OtherFX_Play(sampleVoiceID, 0);

Custom IDs produce SFX IDs 44+ (or 60+), outside the valid range. This
path is NOT `Voiceline_RequestPlay`, so the BUG-VOICE-01 call-site wrap
missed it.

**Applied fix:** wrap the source:
`characterID = GET_MPK_ID(data.characterIDs[driverID])`.

**Verification:** 1P arcade rusty -> Options -> Voice slider cycles ->
plays Crash's voice. Crash / Tiny originals unchanged.

**Related:** BUG-VOICE-01 (same family, different path).

---

## BUG-ARCADE-ICON-01: custom icon missing in arcade end-of-race standings

**Status:** fixed in `6c945886a`
**Detected:** this session, reported by the user while validating
BUG-HISCORE-01.

**Symptom:** in 1P arcade, the end-of-race standings (8 icons showing
the finishing order) does not draw the icon for a custom racer. The
other icons draw normally. No crash.

**Confirmed cause:** `game/222.c`, `AA_EndEvent_DrawMenu`, the loop that
draws all 8 icons:

    #define gameCharacterMetadata  (data.MetaDataCharacters)   // line 73
    ...
    characterID = characterIDs[driversInRaceOrder[i]->driverID];  // raw 16+
    iconID = characterMetadata[characterID].iconID;               // OOB read

`data.MetaDataCharacters` has 16 entries (0..15). Custom IDs (16+) read
past the array into the adjacent `data.characterIDs[]` field. The
resulting `iconID` is garbage, `gGT->ptrIcons[garbage]` is typically
NULL, and `UI_DrawDriverIcon` silently draws nothing.

Secondary: this is the only standings path that does NOT call
`NativeCustomRacer_EnsureIconForChar` before drawing. Even after the OOB
fix, VRAM may hold the original's icon (which the custom inherits via
`GET_METADATA(...)->iconID` = `32 + slot`) instead of the custom's own
`page_N.vrm` upload.

**Applied fix:** two changes at the loop:

    iconID = GET_METADATA(characterID)->iconID;
    ...
    NativeCustomRacer_EnsureIconForChar(characterID);
    UI_DrawDriverIcon(gGT->ptrIcons[iconID], ...);

Originals unchanged (mpkID == characterID; `EnsureIconForChar` is a no-op
when the slot already holds the right content).

**Verification:** 1P arcade rusty finishes any race -> rusty's icon
appears in the standings. Same with nash.

**Related:** same VRAM approach as UI_Map / UI_Rank / UI_CupStandings
(BUG-ICON-01).

---

## BUG-ICON-02: custom↔original share the same VRAM icon slot

**Status:** fixed in `d7b198610`.

**Original symptoms:**
1. 2P+ VS, custom vs matching original → whoever was uploaded last won.
2. Ghost list, custom vs matching original → only one displayed correctly.
3. Any screen with more than one driver where both occupied the same
   iconID slot (32+slot).

**Cause:** customs used `iconID = 32 + slot`, exactly the same 0..12
range the originals occupy. VRAM has one rect per original slot; two
distinct characters sharing a single VRAM rect cannot both be displayed
at once. No universal free block of sufficient size existed in any of
the four VRAM dumps (charsel / title / race / 4P).

**Fix (Sentinel CLUT):** customs no longer use VRAM. Each custom icon is
decoded once from its `page_N.vrm` into a dedicated RGBA8 OpenGL texture,
and a fabricated `struct Icon` carries the Sentinel bit
(`clut = 0x8000 | idx`) so `AddSplit` in `platform/native_gpu.c` routes
sampling to that GL texture instead of VRAM.

Mechanism:
- `platform/native_gpu.c`: `s_gpu.currentClut` set per-primitive before
  each `AddSplit`. `AddSplit` checks bit 15; on hit, forces
  `TF_32_BIT_RGBA`, picks `textureId` from `s_gpu.customTextures[]`,
  sets `blendMode = BM_NONE`, and reads texel size from
  `s_gpu.customTextureSizes`. New API `NativeGpu_RegisterCustomTexture`.
- `platform/native_custom_racer.c`: decode 4bpp+CLUT from `page_N.vrm`
  into RGBA8, upload with `glGenTextures`/`glTexImage2D`, register with
  native_gpu. `NativeCustomRacer_GetIconPtr` returns the fabricated Icon
  for customs or the real VRAM icon for originals.
- 13 call sites swapped to `NativeCustomRacer_GetIconPtr` across:
  standings, HUD, battle setup + battle standings, char select,
  high scores, ghost list, cup standings, rank.

**Side fixes in the same commit:**
- 4P VS custom icons rendered semi-transparent because `blendMode` was
  inherited from the caller (TRANS_50_DECAL). Sentinel branch now forces
  BM_NONE.
- `RefreshCard_GhostReadHeaderInfo` used `fopen("bu00:BASCUS-94426G...")`,
  which does not resolve on Windows. Custom ghosts in the list showed
  the filename-truncated character ID (nash 19 & 0xF = 3 = Coco). Now
  uses `NativeMemcard_ReadSaveData` with the same path resolution as
  MEMCARD_Load/MEMCARD_Save.

**Verified in-game:**
- 1P arcade rusty — standings + HUD.
- 2P VS rusty vs Crash — both icons correct.
- 4P VS with 4 customs — all 4 correct, no semi-transparency.
- Battle setup + battle standings with Coco + nash — correct.
- Ghost list with Coco + nash — correct.
- High scores with customs — correct.
- Originals unchanged.

**Related:** BUG-ICON-01 (on-demand VRAM, still active for originals and
as a fallback when the custom texture fails), BUG-GHOST-03.

---

## Template for new bugs

```text
## BUG-<SYSTEM>-<NN>: <Short title>

**Status:** pending | in progress | fixed in <commit>
**Detected:** <phase> (after <commit>)

**Symptom:**
<Exact description. Does it crash? Is it invisible? Sounds wrong? When?>

**Suspected / confirmed cause:**
<File:line. What it does. Why it fails with IDs 16+.>

**Designed fix:**
<Conceptual diff. Wrap with GET_MPK_ID, change lookup, etc.>

**Verification:**
<How to confirm it's fixed without breaking originals.>

**Related:**
<§X.Y of the main context, or similar bug.>
