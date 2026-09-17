# Pending bugs in the custom racer system

> Companion document. Every time a specific bug of the custom racer
> system is discovered and not yet fixed, it gets added here with its
> symptom, cause, and designed fix. When it's fixed, it moves to the
> corresponding commit and gets deleted from here.
>
> **Current state (HEAD `7f9f420b4`, branch `nhanced`, origin at
> `ccfce3a2f`):** los 10 commits de modularización del addon
> (`3867b75ec..7f9f420b4`) son locales, aún no pusheados. La sesión
> de modularización no cerró ningún bug nuevo — fue refactor puro sin
> cambios funcionales.
>
> **Session after the modularization (this session):** doc-sync only,
> no commit. Verified BUG-ALPHA-01 (model textures) is already fixed
> (stale doc). Dismissed BUG-SLOT14-MYSTERY (works). BUG-ICON-07 may
> be a dirty-roster artifact. New open bug: add_25 blend mode dead
> in the model primitive writer (attempted fix failed, reverted).
>
> Still pending:
>
> - BUG-ICON-07 — Fantasma Sentinel icon: a subset of black
>   outline pixels vanish to transparent in
>   char-select, and in the arcade rank HUD at even
>   ranks (2, 4). Deferred, low priority. Possibly
>   caused by a dirty roster — did not reproduce
>   with a clean one.
> - BUG-ADD25-01 — add_25 blend mode is dead in the model
>   primitive writer. Attempted fix broke solid
>   textures, reverted. Root-cause hypothesis:
>   semi-trans double-pass in DrawSplit may not
>   filter STP=0 in pass 2. Needs native_renderer.c
>   read. See the "BUG-ADD25-01" entry below.
>
> Closed / reclassified in this session (doc-sync only, no commit):
>
> - BUG-ALPHA-01 (model textures) — actually fixed since
>   `69421d60f` + `82f66d1dd`. Verified in-game.
>   The pending entry cited `build_character.py`
>   line 183, which no longer exists (replaced by
>   the 3-bucket routing). Entry kept below as
>   historical reference.
> - BUG-SLOT14-MYSTERY — dismissed (works).
>
> Closed in the per-material blend modes session:
>
> - per-material blend modes via tpage ABR bits (half / add /
>   subtract / add_25). Encoded in the layout's
>   tpage bits 5-6. Blender addon exposes a dropdown
>   per material (`mat["blend_mode"]` is the source
>   of truth; the `EnumProperty nfr_racer_blend_mode`
>   mirrors it via an update callback). No runtime
>   change — GET_TPAGE_BLEND was already wired.
>   (`82f66d1dd`)
>   NOTE: the "verified in-game that all four modes
>   render correctly" claim was likely verified with
>   materials that had no semi texels, where the
>   visual difference between ABE=0 and ABE=1 is
>   invisible. add_25 was dead at the model writer
>   level the whole time — see BUG-ADD25-01.
> - BUG-AIRBORNE-CRASH — airborne anim remap via GET_MPK_ID
>   (`81a580ef6`)
> - BUG-ALPHA-01 (Sentinel icons) — semitransparent custom icons.
>   Three coordinated changes: two-palette quantizer
>   in build_icons.py, STP decode in
>   native_custom_racer.c, BM_SRC_ALPHA +
>   psxKeepTextureAlpha in native_gpu.c /
>   native_renderer.c. (`243c44d24`)
>
> Closed in the session before the blend modes session:
>
> - BUG-DS-01 — addon now writes double_sided in export_mesh_json
>   (`bf7f7aecd`)
> - BUG-ICON-05 — synthetic rects for grid slots 13/14 (`d2550fa2c`)
> - brace fix in ApplyPageMeta (`bb2236574`)
> - add_racer.py idempotence: skip icon copy if src == dst (`e9121be72`)
> - chore: untrack VRAM.TGA (`24a32dd96`) + ignore VRAM.TGA dumps
>   (`b6d0ec42b`)
>
> Closed recently (post-Fase 4, prior session):
>
> - BUG-ICON-06 — ApplyPageMeta no longer corrupts original iconID
>   (`40805acd3`, cleanup `588b254dc` + `0cbbf6e9f`)
> - BUG-ICON-03 — RefreshPage no longer bulk-uploads page_N.vrm for
>   N > 0 (`da3ac2942`)
> - Blender addon v1.7.0 (`1ab66ff1b` + `2236b1897`)
>
> Closed in Fase 4:
>
> - wheels=yes|no per custom (`343879295`)
> - mask=good|bad per custom (`3fdceaa41`)
> - high-score name color uses roster color (`4346f58f7`)
> - per-material double-sided (`25cf0b176`)
> - Blender addon for custom racer export, commit 1 (`0af0ebed0`)
>
> Closed in Fase 3:
>
> - LNG display names from roster.txt (`65164580a`)
> - Sentinel CLUT real (BUG-ICON-02) (`d7b198610`)
> - roster capacity 48 → 128 (`162f02aca`)
> - per-custom minimap colors from roster.txt (`0dd8177b5`)
>
> Closed in Fase 2:
>
> - BUG-ARCADE-ICON-01 (`6c945886a`)
> - BUG-HISCORE-01 (`5d973c6fe`)
> - BUG-VOICE-02 (`5d973c6fe`)
> - BUG-MAP-01 (`01605273d`)
> - BUG-PODIUM-01 (`41597d689`)
> - BUG-VOICE-01 (`a38521281`)
>
> Closed in Fase 1 / earlier:
>
> - BUG-GRID-01 — grid slot ↔ enum Characters mismatch
>   (`s_gridToCharID[16]` in `native_custom_racer.c`,
>   used by `GET_MPK_ID`. Already present in
>   HEAD `2236b1897`; introduced in Fase 1, most
>   likely `5a1cce91e GET_METADATA + BSS tables`.)
> - BUG-GHOST-01 (`550c6972e`)
> - BUG-GHOST-02 (`5b66782a9`)
> - BUG-GHOST-03 (`8f4accdbc`)
> - BUG-ICON-01 (`f7d208475` + `8a42427fa`)
> - BUG-MENU-01 (not reproducible on HEAD)
> - BUG-MENU-02 (`2e29a5eab`)
> - BUG-MENU-03 (`5e0f71ff7`)
> - BUG-MENU-04 (`1942c97cc`)
> - BUG-MENU-05 (`1ce02010e`)
> - BUG-MENU-06 (`c1cbd8f7b`)
> - BUG-TNT-01 (`479024c23`)
> - BUG-ARCADE-01 (`417b3e8b2`, OOM safety net `94633f4ae`)

---

## BUG-ADD25-01: add_25 blend mode dead in the model primitive writer

**Status:** open. Attempted fix failed, reverted. No commit.
**Detected:** session after the addon modularization, while
investigating BUG-ALPHA-01 (model textures).

**Symptom:** with `blend_mode='add_25'` (ABR=3) on a material that
has semi texels (alpha between 0.1 and 0.9), the material renders
identical to an opaque material instead of adding 25% of its color
to the background. The other three modes (half, add, subtract) work.

**Confirmed cause:** `game/RenderBucket/RenderBucket_QueueExecute.c`,
`RenderBucket_DrawInstPrim_NormalAtOTEntry`:

    u32 texWord1 = RenderBucket_ReadTextureWord(tex, RENDER_BUCKET_TEX_WORD1_OFFSET);
    codeWord = ((texWord1 & 0x00600000) == 0x00600000) ? 0x34000000 : 0x36000000;

`texWord1` carries the tpage word at offset 4 of the TextureLayout.
Bits 21-22 of texWord1 map to bits 5-6 of tpage = the ABR field.
When ABR=3 (add_25), the ternary picks `0x34` = POLY_GT3 with
ABE=0. With ABE=0 the engine ignores the ABR bits entirely, so
add_25 is dead. The other three modes (half=00, add=01, subtract=10)
fall through to `0x36` = ABE=1, and work.

Same pattern in `RenderBucket_DrawSplitPrimitiveNormalAtOTEntry`.

**Attempted fix (FAILED):** force `codeWord = 0x36000000` always on
textured model primitives (ABE=1 unconditionally, let the ABR bits
choose the blend). Reverted because it broke solid textures: every
solid material started rendering semi-transparent.

**Root cause of the failure (hypothesis, unverified):** the
double-pass path in `platform/native_gpu.c::DrawSplit`:

    if (split->psxTexturedSemiTrans) {
        NativeRenderer_SetBlendMode(BM_NONE);
        NativeRenderer_SetPSXTextureSemiTransPass(1);
        NativeRenderer_DrawTriangles(...);
        NativeRenderer_SetBlendMode(split->blendMode);
        NativeRenderer_SetPSXTextureSemiTransPass(2);
        NativeRenderer_DrawTriangles(...);
    }

Pass 2 is supposed to draw only texels whose STP=1 (from the
palette). If the shader ignores the pass argument and redraws every
texel with blend, solids become semi. Need to read
`platform/native_renderer.c` (`NativeRenderer_SetPSXTextureSemiTransPass`
and the 32-bit RGBA fragment shader) to confirm whether pass 2
actually filters STP=0.

**Next step:** read `platform/native_renderer.c` around the
semi-trans pass plumbing. If the shader doesn't filter STP=0 in pass
2, the real fix belongs in the shader, not in the codeWord ternary.
That would also explain why the codeWord-only change broke solids.

**Related:** per-material blend modes (`82f66d1dd`) exposed the ABR.

---

## BUG-ALPHA-01 (model textures): PS1 semitransparency not routed through STP bit

**Status:** fixed. Actually fixed since `69421d60f` (STP per palette
entry) + `82f66d1dd` (ABR in tpage). The pending entry cited
`build_character.py` line 183, which no longer exists. The block
below is kept for historical reference.
**Detected:** two sessions before the modularization, with
`SEMITRANTES.png` (uniform `alpha=0.376`).

**Symptom:** a racer texture with alpha in the `(0, 0.5)` range renders
as **opaque black** in-game, not semi-transparent. Specifically,
`SEMITRANTES.png` on a model → black.

**Confirmed cause (as written when the bug was filed):**

`tools/custom_racers/build_character.py`, `prepare_textures`, line 183:

    rgb555.append(0 if a < .5 else c if c else 0x8000)

- `a < 0.5` → `0x0000`, which on PS1 is **opaque black** in the CLUT.
- `SEMITRANTES.png` is uniformly `alpha = 0.376`, so every pixel
  becomes `0x0000`.

**Actual fix (already committed):** `69421d60f` replaced the single-
threshold routing with three buckets:

    if a < SEMI_LO (0.1):       transparent (palette index 0)
    elif a < SEMI_HI (0.9):     semi, STP bit set (0x8000 | c)
    else:                       opaque (no STP bit)

Opaque and semi get disjoint palette slots. The runtime honors the
STP bit because `RenderBucket_DrawInstPrim_NormalAtOTEntry` emits
`codeWord = 0x36000000` (ABE=1) for `blend_mode='half'` (ABR=0),
which is the default. Combined with `82f66d1dd` (ABR in tpage), the
per-material blend modes ride the same path.

**Verification (this session):** re-exported a racer with
`SEMITRANTES.png` and the default `blend_mode='half'`. In-game the
model renders semi-transparent, not opaque black. The pending entry
was stale.

**Related:** Sentinel icon half of BUG-ALPHA-01, closed in
`243c44d24`. See "BUG-ALPHA-01 (Sentinel icons)" below for the
mechanism that already works for icons.

---

## BUG-ALPHA-01 (Sentinel icons): custom icons rendered with black background

**Status:** fixed in `243c44d24`.
**Detected:** two sessions before the modularization, after the
Sentinel CLUT landed.

**Symptom:** custom icons with transparent PNG backgrounds rendered
with a **completely black** rectangular background instead of
transparency. The character silhouette and its black outline showed
correctly, but the "frame background" (semi-transparent region in the
source PNG) rendered as either black or fully opaque.

Two sub-symptoms emerged through the debugging session:

1. Initially (pre-fix): the entire icon background was solid black
   because `AddSplit` forced `blendMode = BM_NONE`, ignoring the
   RGBA8 texture's alpha. Any alpha-0 pixel rendered as opaque black.
2. After switching to `BM_SRC_ALPHA`: the semi-transparent region
   started blending, but the icon's black outline became
   semi-transparent too, because the original `pack_icon` mixed
   opaque and semi pixels in a single 15-color palette and marked the
   whole bucket semi.

**Confirmed cause:**

Three independent bugs, all in the icon pipeline:

1. `platform/native_gpu.c::AddSplit`, Sentinel branch:
   `blendMode = BM_NONE` ignored the RGBA8 texture's alpha.
   Fix: `BM_SRC_ALPHA` + `psxKeepTextureAlpha = true` so the fragment
   shader preserves the sampled alpha.

2. `platform/native_renderer.c::NativeRenderer_SetBlendMode` had no
   case for source-alpha blending. Fix: new `BM_SRC_ALPHA` blend mode
   using `glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA,
GL_ZERO, GL_ONE)`. The alpha factors preserve the framebuffer
   mask/STP bit.

3. `tools/custom_racers/build_icons.py::pack_icon` quantized all
   visible pixels into a single 15-color palette. When the icon had
   both opaque black pixels (the outline) and semi gray pixels (the
   frame background), the median-cut quantizer merged them, and the
   majority-semi vote marked the merged bucket STP=1. Fix: quantize
   opaque and semi pixels into **two separate palettes** with budget
   split by pixel-count ratio.

4. `platform/native_custom_racer.c::RegisterCustomIconTexture` decoded
   the CLUT STP bit into the RGBA8 texture alpha:
   `d[3] = (c & 0x8000) ? 128 : 255`. Without this, all non-index-0
   texels were alpha=255 regardless of STP.

**Applied fix:** the three coordinated changes above, committed as
`243c44d24`.

**Verification:** in-game char-select, custom icons show:

- Black outline opaque
- Semi frame background at 50% over the panel behind
- Fully transparent background showing the panel
- No regression on originals (still VRAM path with `BM_NONE` and
  `psxDrawMaskSet`)

**Related:** model textures half closed in `69421d60f`; see
"BUG-ALPHA-01 (model textures)" above.

---

## BUG-AIRBORNE-CRASH: custom racer crashes on jump (grid slot 14)

**Status:** fixed in `81a580ef6`.
**Detected:** in the per-material blend modes session, symptom
observed with ernest at grid slot 14 after re-exporting the racer
from the Blender addon.

**Symptom:** custom racer at grid slot 14 (ernest, after moving from
slot 11 to slot 14) crashed with a silent segfault on the first jump
in any race. Originals unaffected. Customs at grid slots 0, 1, 2, 3
did not crash.

**Confirmed cause:**

`game/Vehicle/VehFrame.c::VehFrameProc_Driving`, airborne branch:

    characterID = data.characterIDs[d->driverID];
    if (characterID == PENTA_PENGUIN)  { characterID = COCO_BANDICOOT; }
    if (characterID == FAKE_CRASH)     { characterID = CRASH_BANDICOOT; }

    matrixArray = GET_MPK_ID(characterID) + VEH_FRAME_AIRBORNE_MATRIX_BASE;

The two `if` statements compared the **raw** `characterID` against the
enum `Characters`. For custom racers (id ≥ 16), the raw ID never
equals either enum, so neither remap fired.

A custom sitting in grid slot 14 inherits enum `FAKE_CRASH` via
`s_gridToCharID[14]`. Without the remap, it falls through to
`matrixArray = GET_MPK_ID(30) + BASE = FAKE_CRASH + BASE = 14 + BASE`.
The airborne matrix block indexed by `FAKE_CRASH` is malformed in
retail — the retail engine always remaps Fake Crash to Crash for this
path, so those matrices were never meant to be read. Reading them
segfaults.

Confirmed by the isolation test: forced `double_sided = False` on
`build_character.py` and re-exported ernest. The crash persisted,
ruling out DS as the cause. rusty (slot 0, enum CRASH) never
crashed.

**Applied fix:**

    characterID = data.characterIDs[d->driverID];
    {
        u8 mpkID = GET_MPK_ID(characterID);
        if (mpkID == PENTA_PENGUIN) { characterID = COCO_BANDICOOT; }
        if (mpkID == FAKE_CRASH)    { characterID = CRASH_BANDICOOT; }
    }
    matrixArray = GET_MPK_ID(characterID) + VEH_FRAME_AIRBORNE_MATRIX_BASE;
    if (GET_MPK_ID(characterID) == NITROS_OXIDE)
    {
        matrixArray = VEH_FRAME_OXIDE_MATRIX_ARRAY;
    }

Originals (id < 16) unchanged: `GET_MPK_ID(id) == id`.

**Verification:**

- ernest on grid slot 14 no longer crashes on jump (10+ jumps, both
  in-race and char-select preview).
- rusty on slot 0 unchanged.
- big_norm on slot 1 unchanged.
- Custom on slot 13 (Penta) would also remap to Coco.
- Custom on slot 15 (Oxide) would also use `VEH_FRAME_OXIDE_MATRIX_ARRAY`.

**Related:** same "grid slot vs enum" trap as BUG-GRID-01 and
BUG-PODIUM-01, but a different code path (VehFrame airborne matrices).

---

## BUG-ICON-07: Fantasma Sentinel icon shows corrupt pixels; black outline partially vanishes

**Status:** open, deferred. Low priority (cosmetic, intermittent).
Possibly caused by a dirty roster (duplicate slots) — did not
reproduce with a clean roster (unconfirmed, reported this session).
**Detected:** in the per-material blend modes session, after the
blend-modes feature landed. Reported by the user as "un bug rarísimo,
muy sutil".

**Symptom:**

The custom icon "Fantasma" (page 1, slot 2, customID 18, ACCEL)
shows corrupt pixels in two situations:

1. **Character-select screen.** VRAM-like corruption on the icon
   sprite. Specifically, **some of the icon's black outline pixels
   render correctly as black, while others of the same black outline
   render as transparent** (fully see-through, exposing whatever is
   behind). Not all black pixels are affected, and not always the
   same ones — the subset that vanishes appears to change between
   draws.

2. **In-game (arcade).** The icon renders clean when the player is
   in rank **1 or 3** (odd), and shows the same class of corruption
   when in rank **2 or 4** (even). Position-dependent, reproducible.

The corruption is subtle — a handful of texels, not a broken
texture. Originals unaffected.

**What has been ruled out:**

- **Sentinel CLUT registration:** `s_customIconTex[2] = 8`,
  `attempted = 1`, no `[Sentinel] ABORT` in the logs. GL texture is
  registered correctly on the first call and reused.
- **`RegisterCustomIconTexture` parse:** `page_1.vrm` contains the
  block for slot 2 (pixels at 267,216 / CLUT at 16,253). Registration
  succeeds.
- **`AddSplit` Sentinel branch:** 400/400 draws of Fantasma come
  through with **identical state** (`w=44 h=26 fmt=3 blend=5 keepA=1
semi=0 stp=0 mask=0 drawPrim=0`). No state leak, no cross-draw
  contamination.
- **Roster duplication:** a clean roster (single `1 2 fantasma` at
  slot 2) does not change the symptom.
- **`page_1.vrm` regeneration:** file grows to 5 icons (3264 B) with
  the Fantasma block present. No change.

**Leading hypotheses (unverified):**

1. **Alpha routing on the black outline.** `build_icons.py::pack_icon`
   classifies texels as:
   - `a < 0.1` → transparent (palette index 0)
   - `0.1 <= a < 0.9` → semi (STP=1, 50% blend)
   - `a >= 0.9` → opaque (STP=0)
     If the source PNG's black outline has anti-aliased edges where
     some pixels sit at `a` just below 0.1, they get routed to the
     transparent bucket and disappear. Neighbours above the threshold
     stay black. This would explain the "some black pixels vanish,
     others stay black" pattern, and could vary per-pixel because the
     threshold cut is right at the edge of the AA gradient.
2. **NPOT sampling.** The Sentinel GL texture is 44x26 (not a power
   of two). With `GL_NEAREST` this should be fine, but a half-texel
   offset in the shader or an unclamped UV at the edges could bleed
   on certain draw positions.
3. **UV subpixel offset.** The HUD rank row animation (bounce/slide
   when overtaking) may emit the icon quad at fractional coordinates
   on ranks 2 and 4 only, tripping NPOT sampling on the edge
   texels.

**Dirty-roster hypothesis (added this session):** the original report
may have been caused by a roster with duplicate slots. `build_icons.py`
uses `dict[slot] = folder` with last-entry-wins, so a duplicate slot
silently overwrites. The user reported that with a clean roster the
symptom did not reproduce. Not confirmed — needs a controlled retest
if it comes back.

**Next steps when resumed:**

- Screenshot the corruption at rank 2 or 4 (edge vs centre, which
  pixels of the outline vanish, 1 px vs block).
- Dump `page_1.vrm` and inspect the Fantasma palette: how many
  outline pixels land in the transparent bucket vs the opaque
  bucket, versus the source PNG. Compare with a custom that does
  not exhibit the bug (Nash, Big Norm).
- Pause test: while at rank 2, pause the game. Do the vanishing
  pixels change over time (dynamic sampling) or stay fixed
  (texture data)?
- Test with another custom in the same rank slots: if generic →
  HUD issue; if Fantasma-only → PNG / palette issue.
- Force a clean roster (no duplicate slots) and retest.

**Related:** BUG-ALPHA-01 (Sentinel icons) — the two-palette
quantizer introduced in `243c44d24` is the same code path that
hypothesis (1) would tune.

---

## BUG-SLOT14-MYSTERY: ernest at grid slot 14 shows Penta Penguin icon/voice

**Status:** dismissed. The user reports that grid slot 14 works
correctly in-game (icon, voice, kart color). The original observation
was likely a side effect of a dirty roster. The block below is kept
for historical reference.
**Detected:** in the per-material blend modes session, after moving
ernest from slot 11 to slot 14 for the airborne crash test.

**Symptom (as originally reported):** with ernest at grid slot 14,
the in-game char-select cell shows the Penta Penguin icon, and the
voicelines / kart color used in races are also Penta's. Fake Crash's
icon is still visible in his own cell on page 2 (grid slot 14 of
page 0, reserved for originals).

According to `s_gridToCharID[14]`, slot 14 should map to
`FAKE_CRASH` (enum 14), not `PENTA_PENGUIN` (enum 13). So either:

- The roster has ernest at a different slot than reported (e.g. 13
  instead of 14).
- There's an off-by-one in the icon rect table for slots 13/14.
- The page-2 rendering is aliasing something.
- The user's memory of which icon/voice is displayed is off.

**Resolution (this session):** the user confirmed the symptom does
not reproduce on a clean roster. Grid slot 14 works correctly. No
action needed.

**Related:** BUG-GRID-01, BUG-AIRBORNE-CRASH.

---

## BUG-GRID-01: grid slot ↔ enum Characters mismatch (Papu sounds like Joe)

**Status:** fixed in Fase 1 (pre-`2236b1897`). Historical reference.
**Detected:** Fase 1 (before the session that produced this document).

**Symptom (historical):** ernest assigned to **grid slot 11** (which
draws Papu's cell) played **Komodo Joe's** voicelines on the podium,
engine start, and item pickups. Same for any custom in grids 8..14,
each inheriting the wrong voice / dance / kart color / TNT height /
BI\_\*PACK of their grid slot.

Note: ernest has since been moved from grid slot 11 to grid slot 14
for the airborne crash test. The fix (below) applies regardless of
which grid slot the custom is on.

**Confirmed cause:**
`D230.c`, `characterSelectMeta1P2P[15]` maps **grid slot → enum
Characters** with a permutation starting at index 8:

    grid:  0  1  2  3  4  5  6  7  8   9  10 11 12 13 14 15
    enum:  0  1  2  3  4  5  6  7  12  8  10 9  11 13 14 15

`enum Characters` (namespace_Vehicle.h):

    8  = PINSTRIPE
    9  = PAPU_PAPU
    10 = RIPPER_ROO
    11 = KOMODO_JOE
    12 = N_TROPY
    13 = PENTA_PENGUIN
    14 = FAKE_CRASH
    15 = NITROS_OXIDE

The original `GET_MPK_ID(id)` returned `((id) - 16) % 16`, i.e. the
**grid slot**, not the enum characterID. All the consumers —
`data.voiceData[]`, `STATIC_*DANCE` block, `BI_*PACK` ranges,
`s_tntThrowHeadY[]`, `data.ptrColor[]` — are enum-indexed. So a custom
in grid 11 got `data.voiceData[11]` (Joe).

**Applied fix:** Introduce `s_gridToCharID[16]` in
`native_custom_racer.c`:

    const u8 s_gridToCharID[16] = {
        0, 1, 2, 3, 4, 5, 6, 7,
        12, 8, 10, 9, 11, 13, 14, 15,
    };

Expose via `extern` in `native_custom_racer.h` and change `GET_MPK_ID`:

    #define GET_MPK_ID(id) \
        (((id) >= NATIVE_CUSTOM_ID_BASE) \
            ? s_gridToCharID[((id) - NATIVE_CUSTOM_ID_BASE) % NATIVE_PAGE_SIZE] \
            : (id))

Originals (id < 16) unaffected. Customs in any grid now inherit the
voice / dance / kart / TNT height / BI\_\*PACK of their grid slot:
rusty -> Crash, big_norm -> Cortex, fantasma -> Tiny, nash -> Coco,
ernest -> (whichever enum its grid slot maps to).

**Verification:** already covered by every voiceline/dance/kart test
in Fase 2 onward.

**Related:** BUG-AIRBORNE-CRASH (`81a580ef6`) — same "grid slot vs
enum" trap, but in `VehFrame.c` airborne matrices.

**Cleanup:** `docs/BUG-GRID-01-wip.patch` is no longer needed.

---

## BUG-ICON-06: ApplyPageMeta corrupts original iconID for customs on slots >= 8

**Status:** fixed in `40805acd3`; cleanup in `588b254dc` and `0cbbf6e9f`.
Historical reference.
**Detected:** previous session, reported by the user as "Pinstripe
appears twice on page 1 when a custom is placed on slot 11".

**Symptom:** with the roster having a custom on grid slot 11 (ernest
on Papu's cell at the time), Pinstripe appeared twice in the
character-select grid: once in his own cell (grid 9), once in Komodo
Joe's cell (grid 12). No crash. Reproducible by simply opening page 1.

**Confirmed cause:** `platform/native_custom_racer.c`,
`ApplyPageMeta`:

    for (int i = 0; i < s_pageEntryCount; i++) {
        PageEntry *e = &s_pageEntries[i];
        if (e->page != page) continue;
        if (e->slot < 0 || e->slot >= 15) continue;
        struct MetaDataCHAR *md = &data.MetaDataCharacters[e->slot];
        md->iconID = NATIVE_ICON_BASE + e->slot;
    }

Two independent bugs:

1. `data.MetaDataCharacters[]` is indexed by `enum Characters`, not by
   grid slot. `e->slot` is a GRID slot. For 0..7 they coincide, but
   grid 8 = N.Tropy (enum 12), grid 9 = Pinstripe (enum 8), etc.

2. The original iconIDs are NOT `32 + enum`. The real mapping for
   indices >= 8 (from a runtime dump):
   enum 8 (Pinstripe) -> iconID 43
   enum 9 (Papu) -> iconID 41
   enum 10 (Roo) -> iconID 40
   enum 11 (Joe) -> iconID 42
   enum 12 (Tropy) -> iconID 44
   So `NATIVE_ICON_BASE + 11 = 43` set Joe's iconID from 42 to 43,
   which is Pinstripe's icon.

**Applied fix:** `ApplyPageMeta` no longer writes to
`data.MetaDataCharacters[]`. Customs are drawn via Sentinel CLUT
(`s_customIcon[]`), which is independent of the meta array.

Cleanup: dead `md` variable removed (`588b254dc`), dead `page`
parameter silenced with `(void)page;` and a rationale comment added
(`0cbbf6e9f`). Brace imbalance left by `0cbbf6e9f` was fixed in
`bb2236574`.

**Verification:** with a custom at grid slot 11, page 1 shows the
custom in Papu's cell, Joe in his own cell (grid 12) with Joe's icon,
and Pinstripe only in his own cell (grid 9). Page 0 unaffected.

**Related:** BUG-GRID-01 (same "grid slot vs enum" trap, but different
code path and different symptom).

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
```
