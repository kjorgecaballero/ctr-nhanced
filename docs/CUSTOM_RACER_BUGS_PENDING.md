# Custom Racer System — Pending Bugs

> Living document. Every time a specific bug of the custom racer system is
> discovered and not yet fixed, it goes here with symptom, cause, and
> designed fix. When fixed, it moves to the corresponding commit and is
> removed from here.

---

## BUG-TNT-01: TNT on custom racer head is invisible

**Status:** pending (not fixed)
**Detected:** Fase 2.1 (post `ef0d8b18d`)

**Symptom:** when a player using a custom racer (ID 16+) touches a TNT crate:

- The TNT **works correctly**: countdown, explosion, fuse sound effects,
  "ohno" voiceline (though that one plays wrong due to §8.2 of the main
  context), and driver damage all behave as expected.
- **But the TNT model is invisible.** The red crate with the fuse above the
  custom driver's head is not rendered.

With original characters (0..15) it renders fine.

**Suspected cause:** `game/231/RB_TNT.c:264`:

```c
distHead = array[data.characterIDs[mw->driverTarget->driverID]];
array[] is very likely a 16-entry table with per-character data (head
placement offset for the TNT, or index to the TNT head model/instance).
With characterIDs[...] = 16+ it indexes out of bounds:

If array[] stores model pointers → NULL → invisible instance.

If it stores numeric offsets → garbage → weird or off-screen position.

Since "it works and explodes" still holds, the TNT thread logic is not
broken — only the visual model.

Designed fix: wrap the index with GET_MPK_ID:

c
distHead = array[GET_MPK_ID(data.characterIDs[mw->driverTarget->driverID])];
Add #include <platform/native_custom_racer.h> if not already present in
RB_TNT.c.

Verification: when touching TNT with Rusty, the crate is visible on the
custom driver's head. When touching TNT with Crash/Cortex, nothing changes.

Related: same pattern as §8.4 of the main context
(array[characterIDs[...]] with a 16-entry array).

BUG-VOICE-01: Voicelines do not play with custom racers
Status: pending (already documented in §8.2 of the main context)
Symptom: no voiceline (crash, landing, item, jump) plays when the
driver is a custom racer. No crash.
Cause: 16-entry voice pool indexed by characterID.
Fix: wrap with GET_MPK_ID in ~16 call sites (full list in §8.2 of
the main context).

BUG-GHOST-01: Ghost is invisible in Time Trial
Status: pending (already documented in §8.3 of the main context)
Symptom: the ghost replays (behaviour) but its model is not rendered.
Cause: VehBirth_GetModelByName(name) with name="rusty" but the .ctr
internal name is "tiny".
Fix: for IDs 16+ use data.driverModelExtras[1].model.

Template for new bugs
text
## BUG-<SYSTEM>-<NN>: <short title>

**Status:** pending | in progress | fixed in <commit>
**Detected:** <fase> (post <commit>)

**Symptom:**
<Exact description. Does it crash? Invisible? Plays wrong sound? When?>

**Suspected / confirmed cause:**
<File:line. What it does. Why it breaks with IDs 16+.>

**Designed fix:**
<Conceptual diff. Wrap with GET_MPK_ID, change lookup, etc.>

**Verification:**
<How to check it is fixed without breaking originals.>

**Related:**
<§X.Y of the main context, or similar bug.>
```

DOC_EOF

sed -i 's/\r$//' docs/CUSTOM_RACER_BUGS_PENDING.md
wc -l docs/CUSTOM_RACER_BUGS_PENDING.md
file docs/CUSTOM_RACER_BUGS_PENDING.md

git add docs/CUSTOM_RACER_BUGS_PENDING.md
git commit -m "docs: pending custom racer bugs (invisible TNT, voicelines, ghost)"
git log --oneline -3
