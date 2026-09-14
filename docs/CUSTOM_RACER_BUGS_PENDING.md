# Pending bugs in the custom racer system

> Companion document. Every time a specific bug of the custom racer system is
> discovered and not yet fixed, it gets added here with its symptom, cause,
> and designed fix. When it's fixed, it moves to the corresponding commit
> and gets deleted from here.

---

## BUG-MENU-03: original racer invisible in 2P when it shares GET_MPK_ID with a custom

**Status:** fixed in `VehBirth_NonGhost` (original branch) — pending commit
**Detected:** Phase 2.1

**Symptom:** in 2P VS, if one player picks an original and the other picks a
custom whose slot collides via GET_MPK_ID (e.g. Cortex id=1 ↔ Big Norm
customID=17), the original becomes invisible on track. The custom renders
fine.

**Confirmed cause (via CR-DIAG logs):** the §8.1 branch for IDs 0..15
searched for the model ONLY in `sdata->PLYROBJECTLIST`. In 2P VS,
`PLYROBJECTLIST` points to the 4-AI pack built by `LOAD_Robots2P`, which
deliberately excludes both human drivers. Result: neither "cortex" nor
"crash" are in the list, `m == NULL`, and `INSTANCE_Birth3D(NULL, ...)`
renders nothing.

**Applied fix:** in `game/Vehicle/VehBirth.c`, original branch, after the
name-search over PLYROBJECTLIST fails, read
`data.driverModelExtras[index].model` BY INDEX (not by GET_MPK_ID). The
original always has its slot intact in `driverModelExtras[index]`, and a
custom can never hijack it because the custom lives in a different index.

**Bonus from the same fix:** the symptom "Tiny showed Crash's model when
P2 picked Rusty" had the same root cause — Tiny fell through to the Crash
fallback.

**Verification:** 2P VS Cortex + Big Norm, Crash + Cortex, Tiny + Rusty
(custom with internal name "tiny"), 1P arcade original and custom, 3P, 4P,
battle. All visible, no regressions.

**Related:** BUG-MENU-01, BUG-MENU-02 (menu, different root cause).

---

## BUG-MENU-04: crash on exiting a 4P race with a custom (OOB write to driverModelExtras[3])

**Status:** fixed (BSS side table + guard in VehBirth) — pending commit
**Detected:** Phase 2.5, verified after the BUG-MENU-03 fix

**Symptom:** in 4P (arcade or battle), exiting the race via
`Change Character`, `Change Level`, or `Quit` crashes the app if at least
one player uses a custom. 3P does not reproduce it.

**Confirmed cause (from layout analysis):**

- `DriverModelExtraSlot driverModelExtras[LOAD_DRIVER_MODEL_EXTRA_COUNT]`
  with `LOAD_DRIVER_MODEL_EXTRA_COUNT = 3`.
- The 3P/4P branch of `LOAD_DriverMPK` iterated up to `playerCount` (4),
  writing to `driverModelExtras[3]` = `podiumModel_firstPlace`.
- Each iteration overwrote the first podium model pointer with the
  `.fileBase` of a custom (raw malloc) or the `.model` of an original
  (already `+4`), corrupting the podium model table. On race exit the
  engine reused those pointers and crashed.

**Applied fix:**

- `platform/native_custom_racer.{h,c}`: new BSS side table
  `s_playerModelPtr[NATIVE_PLAYER_MODEL_SLOTS]` with two accessors
  `NativeCustomRacer_SetPlayerModelPtr` / `_GetPlayerModelPtr`.
- `game/LOAD/LOAD_Assets.c`, 3P/4P branch: first loop capped at
  `LOAD_DRIVER_MODEL_EXTRA_COUNT` (3), and a second loop for `i >= 3`
  that loads P4's custom and stores the buffer (with
  `+LOAD_MODEL_FILE_HEADER_BYTES` already applied) in the side table.
  Zero writes outside `driverModelExtras`.
- `game/Vehicle/VehBirth.c`: both branches (custom and original) guard
  against `index >= LOAD_DRIVER_MODEL_EXTRA_COUNT` to avoid OOB reads.

**Verification:** 4P arcade with custom in P1..P4, 4P battle with custom,
exits via `Change Character` / `Change Level` / `Quit`. No crash.
1P/2P/3P no regressions.

**Related:** BUG-MENU-03 (same load flow, different bug).

---

## BUG-TNT-01: TNT on a custom's head is invisible

**Status:** pending (not fixed)
**Detected:** Phase 2.1 (after `ef0d8b18d`)

**Symptom:** when a player using a custom (ID 16+) touches a TNT crate:

- The TNT **does work**: countdown, explosion, fuse sounds, "ohno"
  voiceline (though that sounds wrong due to BUG-VOICE-01), and damage to
  the driver are correct.
- **But the TNT model is invisible.** The red crate with the fuse is not
  drawn over the custom driver's head.

Originals (0..15) render it perfectly.

**Suspected cause:** `game/231/RB_TNT.c:264`:

````c
distHead = array[data.characterIDs[mw->driverTarget->driverID]];
array[] is a 16-entry table with per-character data. With
characterIDs[...] = 16+ it indexes OOB.

Designed fix: wrap the index with GET_MPK_ID:

c
distHead = array[GET_MPK_ID(data.characterIDs[mw->driverTarget->driverID])];
Verification: TNT on Rusty → crate visible. TNT on Crash/Cortex →
no change.

Related: §8.4 of the main context (same pattern array[characterIDs[...]]).

BUG-VOICE-01: voicelines don't play with a custom
Status: pending (§8.2 of the main context)

Symptom: no voiceline (crash, landing, item, jump) plays when the
driver is a custom. No crash.

Cause: 16-voice pool indexed by characterID.

Fix: wrap with GET_MPK_ID in ~16 call sites (list in context §8.2).

BUG-GHOST-01: ghost invisible in Time Trial
Status: pending (§8.3 of the main context)

Symptom: the ghost replays but its model is not drawn.

Cause: VehBirth_GetModelByName(name) with name="rusty" but the
.ctr internally names itself "tiny".

Fix: for IDs 16+, use data.driverModelExtras[1].model or the BSS
side table.

BUG-MENU-01: 3D menu models always show Crash
Status: pending (pre-existing, NOT §8.1)
Detected: Phase 2.1, confirmed via stash test

Symptom: in 2P VS with both characters original (e.g. P1=Crash,
P2=Cortex), both selection windows render Crash's 3D model regardless of
who the players pick.

Suspected cause: MM_Characters_GetModelByName(GET_METADATA(id)->name_Debug)
inside MM_Characters_DrawWindows searches level1->ptrModelsPtrArray,
but fails to find the models (or always returns the same one).

Designed fix: pending. Likely map currentCharacterID[p] to
driverModelExtras[p].model (or equivalent) in the menu.

Related: BUG-MENU-02.

BUG-MENU-02: custom 3D model invisible in the selection window
Status: pending (pre-existing, NOT §8.1)
Detected: Phase 2.1

Symptom: when a player picks a custom in the character-select menu,
their 3D window shows an empty model (invisible). Cursor, page, icon, and
physics work fine.

Suspected cause: same root cause as BUG-MENU-01.

Designed fix: for IDs 16+, use data.driverModelExtras[p].model
directly.

Related: BUG-MENU-01.

Template for new bugs
text
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
text

Cambios respecto a la versión mezclada:

- **Todo en inglés**, incluido lo que antes estaba en español (bug TNT, voice, ghost, MENU-01/02).
- **BUG-MENU-03** y **BUG-MENU-04** marcados como **fixed**, con la causa confirmada y el fix aplicado descritos.
- **BUG-TNT-01, BUG-VOICE-01, BUG-GHOST-01, BUG-MENU-01, BUG-MENU-02** marcados como **pending**, con su síntoma/causa/fix tal como estaban.
- **Plantilla** traducida.

Para aplicarlo:

```bash
cd ~/Desktop/Kevin/CTR/native_fork/nhanced
nano docs/CUSTOM_RACER_BUGS_PENDING.md
# o pega el contenido con tu editor preferido
sed -i 's/\r$//' docs/CUSTOM_RACER_BUGS_PENDING.md
wc -l docs/CUSTOM_RACER_BUGS_PENDING.md
````
