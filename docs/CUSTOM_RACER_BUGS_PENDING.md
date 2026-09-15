# Pending bugs in the custom racer system

> Companion document. Every time a specific bug of the custom racer system is
> discovered and not yet fixed, it gets added here with its symptom, cause,
> and designed fix. When it's fixed, it moves to the corresponding commit
> and gets deleted from here.
>
> **Current state (HEAD `41597d689` in origin):**
>
> Still pending:
>   - BUG-ICON-02 (known limitation, design-level)
>
> Closed this session:
>   - BUG-PODIUM-01 (`41597d689`)
>   - BUG-VOICE-01 (`a38521281`)
>
> Closed in earlier sessions (kept for reference until next cleanup):
>   - BUG-GHOST-01 (`550c6972e`)
>   - BUG-GHOST-02 (`5b66782a9`)
>   - BUG-GHOST-03 (`8f4accdbc`)
>   - BUG-ICON-01 (`f7d208475` + `8a42427fa`)
>   - BUG-MENU-01 (not reproducible on HEAD, closed Phase 2.7)
>   - BUG-MENU-02 (`2e29a5eab`)
>   - BUG-MENU-03 (`5e0f71ff7`)
>   - BUG-MENU-04 (`1942c97cc`)
>   - BUG-MENU-05 (`1ce02010e`)
>   - BUG-MENU-06 (`c1cbd8f7b`)
>   - BUG-TNT-01 (`479024c23`)
>   - BUG-ARCADE-01 (`417b3e8b2`, OOM safety net `94633f4ae`)

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

## BUG-ICON-02: custom↔original (or custom↔custom from different pages) share the same VRAM icon slot — known limitation

**Status:** **pending — design-level, not fixed**
**Detected:** BUG-ICON-01 investigation (same session)

**Symptoms (all the same root cause):**

1. **2P+ VS, custom vs matching original.** P1 = Big Norm (customID 17,
   `iconID 33`, MPK 1), P2 = Cortex (original, `iconID 33`, MPK 1). Both
   ask for VRAM slot 1; whoever was uploaded last wins. The other renders
   the wrong icon on track and in the HUD.

2. **Ghost list, custom vs matching original.** Coco ghost (original,
   `iconID 35`) + Nash ghost (customID 19, page 1 slot 3 -> `iconID 35`).
   Both want VRAM slot 35, only one displays correctly.

3. **Any screen with more than one driver** where a custom and its
   matching original (or a custom on a different page whose slot maps
   to the same original) appear together.

**Confirmed cause:** customs use `iconID = 32 + slot`, exactly the same
0..12 range the originals occupy. VRAM has one rect per original slot
and no free rect reserved for customs. Two distinct characters sharing a
single VRAM rect cannot both be displayed at once. Same root cause as
BUG-ICON-01, but here it is user-visible because both characters are on
screen simultaneously.

**Why it's not fixed as part of BUG-ICON-01:** the on-demand
`EnsureIconForChar` mechanism re-checks the slot per call, but if two
call sites in the same frame disagree on which character should occupy
that slot, the last write wins. Any real fix requires customs to have
distinct icon IDs, which is a structural change:

- Assign customs `iconID = 48 + slot` (or similar) instead of `32 + slot`.
- Reserve / add VRAM rects for those new slots in `gGT->ptrIcons[]`.
- Update `build_icons.py` to emit page VRMs at those rects.
- Update `NativeCustomRacer_ApplyPageIcons` / `EnsureIconForChar` rect
  tables accordingly.
- Verify that nothing else in the engine assumes `ptrIcons` is only 0..47.

This is a Phase 3-scale change (menu/VRAM layout), not a bug fix.

**Workarounds for the user:**

- In 2P+ VS, don't put a custom and its MPK-matching original in the
  same race.
- In the ghost list, at most one of the colliding ghosts will show its
  correct icon at a time.

**Verification (negative):** reproduce with P1 = Big Norm, P2 = Cortex
in 2P VS, or with two saved ghosts (Coco + Nash) in the ghost list.

**Related:** BUG-ICON-01 (the fix that made this visible),
BUG-GHOST-03 (identification of custom ghosts — fixed; distinct from
this rendering limitation).

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
