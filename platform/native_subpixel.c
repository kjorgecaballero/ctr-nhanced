// The counting of the subpixel coverage. Why it exists and what exactly it
// counts is in include/ctr_subpixel.h.

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <ctr_subpixel.h>
#include <macros.h>
#include <platform.h>
#include <platform/native_log.h>

int g_cfg_subpixelReport = 0;
int g_cfg_subpixel = 0;
int g_subpixelForwarded = 0; // 1 si el draw actual tiene Forward

// THE REGIONS. Three are enough: the two draw arenas (gGT->db[0/1].primMem)
// and the scratchpad, in which the track renderer keeps its scratch vertices.
// A fourth would only exist if someone created primitives elsewhere - then
// NativeSubpixel_Lookup finds nothing there and the whole pixel applies, which
// is correct and becomes visible in the counting.
#define NATIVE_SUBPIXEL_REGIONS 8

struct NativeSubpixelRegion
{
	const u8 *base;
	u32 bytes;
	u32 slots;

	// One slot per four-byte word of the region: the XY word, as the
	// store helper wrote it, and the fractional part for it.
	// frac == 0 means "nothing there" - a fractional part of exactly (0,0)
	// changes nothing anyway, so it needs no validity bit of its own.
	u32 *word;
	u8 *frac;

	// WHY A SLOT IS EMPTY. Only for the counting: when a vertex
	// reads a slot without a fractional part, the mark says whether there never
	// was a GTE store, whether it was unusable (clipped, set from
	// outside), whether the fractional part was already passed on and consumed
	// in the process, or whether it was usable but exactly zero.
	u8 *mark;

	// 1 for the draw arenas, 0 for the scratchpad. A fractional part that
	// lies in an arena is one that a vertex COULD read.
	int arena;
};

#define NATIVE_SUBPIXEL_MARK_NONE     0
#define NATIVE_SUBPIXEL_MARK_UNUSABLE 1
#define NATIVE_SUBPIXEL_MARK_OK       2
#define NATIVE_SUBPIXEL_MARK_CONSUMED 3
#define NATIVE_SUBPIXEL_MARK_COPIED   4
#define NATIVE_SUBPIXEL_MARK_HAND     5
#define NATIVE_SUBPIXEL_MARK_FORWARDED 6  // fraction there, already passed on at least once
#define NATIVE_SUBPIXEL_MARKS         7

// Primitive types like NATIVE_GPU_SIZE_* in native_gpu.c; 8 is enough, -1 becomes 8.
#define NATIVE_SUBPIXEL_KINDS 9

internal struct NativeSubpixelRegion s_regions[NATIVE_SUBPIXEL_REGIONS];
internal int s_regionCount = 0;

// From how many frames one report line is made. 0 means: only the
// sum at the end. The same meaning as for --gte-report.
internal int s_subpixelReportEvery = 0;
internal int s_subpixelArmed = 0;

// THE SHADOW STACK. Three slots, just like SXY0/SXY1/SXY2, and it moves
// along with them. A slot holds the sixteen fractional bits that
// GTE_RotTransPers throws away with `>> 16` - separately for X and Y, because they come from
// two sums.
//
// valid is 0 as soon as someone has written the matching register from outside
// (MTC2). Then some number stands there, but NO known
// fractional part, and a counter that does not keep these apart would
// report coverage that does not exist.
internal u16 s_fracX[3];
internal u16 s_fracY[3];
internal u8 s_fracValid[3];
internal u8 s_fracClamped[3];

struct NativeSubpixelCensus
{
	s64 projections;      // vertices that RTPS/RTPT projected
	s64 projClamped;      // of those, clipped by Lm_G1/Lm_G2 - fraction worthless
	s64 projFracX;        // of those, with a non-zero fractional part in X
	s64 projFracY;        // likewise Y
	s64 projFrac4X;       // of those, with the UPPER FOUR bits non-zero in X
	s64 projFrac4Y;       // likewise Y
	s64 stores;           // coordinates that go out through CTR_GteStoreSXY*
	s64 storesStale;      // of those, without a known fractional part (set from outside)
	s64 storesClamped;    // of those, from a clipped projection
	s64 storesFrac4;      // of those, with a non-zero quarter fraction in X OR Y
	s64 storesOffMirror;  // usable, but outside every mirrored region
	s64 vertices[NATIVE_SUBPIXEL_VTX_KINDS];
	s64 verticesCarried;  // vertices that REALLY got the fractional part
	s64 lookupOffMirror;  // vertex from a primitive outside every region
	s64 lookupEmpty;      // slot there, but never written (or already consumed)
	s64 lookupStale;      // fractional part there, but the primitive holds a different word
	s64 forwardNoSrc;     // passing on: nothing lay at the source
	s64 forwardBadWord;   // passing on: source word no longer matched
	s64 arenaWritten;     // fractional parts that landed in an ARENA
	// Empty slots on reading, by reason and origin [world=0, ui=1].
	s64 emptyNone[2];     // never a GTE store at this place
	s64 emptyUnusable[2]; // GTE store, but clipped or set from outside
	s64 emptyConsumed[2]; // already passed on and consumed in the process
	s64 emptyOkZero[2];   // usable, but fraction exactly (0,0)
	s64 carriedBy[2];     // carried, by origin
	s64 emptyCopied[2];   // scratch vertex was a copy (DrawLevelOvr1P_CopyProjectedScreenDepth)
	s64 emptyHand[2];     // scratch vertex by hand from the IR vector (Ovr226_800aaad0_PrepareClipRecordDepthScratch)
	s64 forwardSrcMark[NATIVE_SUBPIXEL_MARKS];  // passing on without a source, by source reason
	s64 forwardReread;    // passing on from a source that had already been read once
	s64 emptyNoneKind[2][NATIVE_SUBPIXEL_KINDS]; // "never GTE" by primitive type
};

internal struct NativeSubpixelCensus s_window;
internal struct NativeSubpixelCensus s_total;
internal int s_windowFrames = 0;
internal int s_totalFrames = 0;

#define NATIVE_SUBPIXEL_ACTIVE() (g_cfg_subpixel || g_cfg_subpixelReport)

void NativeSubpixel_PushFrac(s64 sxFull, s64 syFull, int sxClamped, int syClamped)
{
	if (!NATIVE_SUBPIXEL_ACTIVE())
	{
		return;
	}

	const u16 fx = (u16)((u64)sxFull & 0xffffu);
	const u16 fy = (u16)((u64)syFull & 0xffffu);
	const int clamped = (sxClamped || syClamped) ? 1 : 0;

	s_fracX[0] = s_fracX[1];
	s_fracX[1] = s_fracX[2];
	s_fracX[2] = fx;
	s_fracY[0] = s_fracY[1];
	s_fracY[1] = s_fracY[2];
	s_fracY[2] = fy;
	s_fracValid[0] = s_fracValid[1];
	s_fracValid[1] = s_fracValid[2];
	s_fracValid[2] = 1;
	s_fracClamped[0] = s_fracClamped[1];
	s_fracClamped[1] = s_fracClamped[2];
	s_fracClamped[2] = (u8)clamped;

	if (!g_cfg_subpixelReport)
	{
		return;
	}

	s_window.projections++;
	s_total.projections++;

	if (clamped)
	{
		s_window.projClamped++;
		s_total.projClamped++;
	}

	if (fx != 0)
	{
		s_window.projFracX++;
		s_total.projFracX++;
	}
	if (fy != 0)
	{
		s_window.projFracY++;
		s_total.projFracY++;
	}

	// The upper four bits are what a target with factor four to eight
	// could show at all: a sixteenth of a PSX pixel. Everything below that is
	// invisible even at --internal-res 8.
	if ((fx & 0xf000u) != 0)
	{
		s_window.projFrac4X++;
		s_total.projFrac4X++;
	}
	if ((fy & 0xf000u) != 0)
	{
		s_window.projFrac4Y++;
		s_total.projFrac4Y++;
	}
}

void NativeSubpixel_InvalidateReg(int reg)
{
	if (!NATIVE_SUBPIXEL_ACTIVE())
	{
		return;
	}

	if ((reg >= 12) && (reg <= 14))
	{
		s_fracValid[reg - 12] = 0;
	}
}

void NativeSubpixel_PushExternal(void)
{
	if (!NATIVE_SUBPIXEL_ACTIVE())
	{
		return;
	}

	s_fracValid[0] = s_fracValid[1];
	s_fracValid[1] = s_fracValid[2];
	s_fracValid[2] = 0;
	s_fracClamped[0] = s_fracClamped[1];
	s_fracClamped[1] = s_fracClamped[2];
	s_fracClamped[2] = 0;
}

// --- The mirror ---------------------------------------------------------------

void NativeSubpixel_RegisterRegion(const void *base, u32 bytes, const char *what)
{
	int i;
	struct NativeSubpixelRegion *r = NULL;

	// If the switch is off, nothing at all is allocated. That is not only
	// economical: it also keeps the off state from allocating half a megabyte of
	// host memory, so the only unconditional remnant of this feature is the one
	// addition in the shader - and that adds an exact zero.
	if (!g_cfg_subpixel)
	{
		return;
	}

	if ((base == NULL) || (bytes < 4))
	{
		return;
	}

	// The same base once more: the entry is replaced. The arenas are
	// reallocated on every track change, and an old entry would then point
	// to freed memory.
	for (i = 0; i < s_regionCount; i++)
	{
		if (s_regions[i].base == (const u8 *)base)
		{
			r = &s_regions[i];
			free(r->word);
			free(r->frac);
			free(r->mark);
			break;
		}
	}

	if (r == NULL)
	{
		if (s_regionCount >= NATIVE_SUBPIXEL_REGIONS)
		{
			Platform_Log("[CTR Sub] no room to mirror %s - %d regions is the limit, this one keeps whole pixels\n", what ? what : "?",
			             NATIVE_SUBPIXEL_REGIONS);
			return;
		}

		r = &s_regions[s_regionCount++];
	}

	r->base = (const u8 *)base;
	r->bytes = bytes;
	r->slots = bytes >> 2;
	r->word = (u32 *)calloc(r->slots, sizeof(u32));
	r->frac = (u8 *)calloc(r->slots, sizeof(u8));
	r->mark = (u8 *)calloc(r->slots, sizeof(u8));
	r->arena = (bytes > 4096u) ? 1 : 0;

	if ((r->word == NULL) || (r->frac == NULL) || (r->mark == NULL))
	{
		// No room: the region stays unmirrored instead of half. A half
		// allocated mirror would be the one kind of bug that is forbidden here.
		free(r->word);
		free(r->frac);
		free(r->mark);
		r->word = NULL;
		r->frac = NULL;
		r->mark = NULL;
		r->slots = 0;
		Platform_Log("[CTR Sub] out of memory mirroring %s (%u bytes) - it keeps whole pixels\n", what ? what : "?", bytes);
		return;
	}

	Platform_Log("[CTR Sub] mirroring %s: %u bytes, %u slots\n", what ? what : "?", bytes, r->slots);
}

internal struct NativeSubpixelRegion *NativeSubpixel_RegionOf(const void *addr)
{
	const u8 *p = (const u8 *)addr;
	int i;

	for (i = 0; i < s_regionCount; i++)
	{
		struct NativeSubpixelRegion *r = &s_regions[i];

		if ((r->word != NULL) && (p >= r->base) && (p < (r->base + r->bytes)))
		{
			return r;
		}
	}

	return NULL;
}

void NativeSubpixel_ClearRegion(const void *base)
{
	struct NativeSubpixelRegion *r;

	if (!NATIVE_SUBPIXEL_ACTIVE())
	{
		return;
	}

	r = NativeSubpixel_RegionOf(base);

	if (r == NULL)
	{
		return;
	}

	// Only the fractional parts. The word array may stay, because without a
	// fractional part it is never read - and one memset fewer per frame.
	memset(r->frac, 0, r->slots);
	memset(r->mark, 0, r->slots);
}

// The slot of a four-byte word. NULL if the address lies in no
// registered region or is misaligned.
internal int NativeSubpixel_SlotOf(const void *addr, struct NativeSubpixelRegion **out)
{
	struct NativeSubpixelRegion *r = NativeSubpixel_RegionOf(addr);
	u32 off;

	if (r == NULL)
	{
		return -1;
	}

	off = (u32)((const u8 *)addr - r->base);

	if ((off & 3u) != 0)
	{
		return -1;
	}

	*out = r;
	return (int)(off >> 2);
}

void NativeSubpixel_NoteStore(void *dst, u32 word, int slot)
{
	struct NativeSubpixelRegion *r;
	int at;
	int usable;

	if (!NATIVE_SUBPIXEL_ACTIVE())
	{
		return;
	}

	if ((slot < 0) || (slot > 2))
	{
		return;
	}

	// The fractional part is only usable if it comes from a projection
	// (not written into the register from outside) and the projection did not
	// clip. With a clip even the integer part is already wrong.
	usable = (s_fracValid[slot] != 0) && (s_fracClamped[slot] == 0);

	if (g_cfg_subpixelReport)
	{
		s_window.stores++;
		s_total.stores++;

		if (s_fracValid[slot] == 0)
		{
			s_window.storesStale++;
			s_total.storesStale++;
		}
		else if (s_fracClamped[slot] != 0)
		{
			s_window.storesClamped++;
			s_total.storesClamped++;
		}
		else if (((s_fracX[slot] & 0xf000u) != 0) || ((s_fracY[slot] & 0xf000u) != 0))
		{
			s_window.storesFrac4++;
			s_total.storesFrac4++;
		}
	}

	if (!g_cfg_subpixel)
	{
		return;
	}

	at = NativeSubpixel_SlotOf(dst, &r);

	if (at < 0)
	{
		if (g_cfg_subpixelReport && usable)
		{
			s_window.storesOffMirror++;
			s_total.storesOffMirror++;
		}
		return;
	}

	if (!usable)
	{
		r->frac[at] = 0;
		r->mark[at] = NATIVE_SUBPIXEL_MARK_UNUSABLE;
		return;
	}

	r->word[at] = word;
	r->frac[at] = (u8)(((s_fracX[slot] >> 12) & 0xfu) | (((s_fracY[slot] >> 12) & 0xfu) << 4));
	r->mark[at] = NATIVE_SUBPIXEL_MARK_OK;

	if (g_cfg_subpixelReport && r->arena && (r->frac[at] != 0))
	{
		s_window.arenaWritten++;
		s_total.arenaWritten++;
	}
}

void NativeSubpixel_Forward(void *dst, const void *src)
{
	struct NativeSubpixelRegion *rs;
	struct NativeSubpixelRegion *rd;
	int from;
	int to;
	u8 frac;

	if (!g_cfg_subpixel)
	{
		return;
	}

	g_subpixelForwarded = 1;
  
	from = NativeSubpixel_SlotOf(src, &rs);

	if (from < 0)
	{
		return;
	}

	frac = rs->frac[from];

	if (frac == 0)
	{
		if (g_cfg_subpixelReport)
		{
			const int m = (rs->mark[from] < NATIVE_SUBPIXEL_MARKS) ? rs->mark[from] : 0;

			s_window.forwardNoSrc++;
			s_total.forwardNoSrc++;
			s_window.forwardSrcMark[m]++;
			s_total.forwardSrcMark[m]++;
		}

		// Nothing to pass on - but the reason travels along, so that the
		// empty slot is not counted as "never GTE" on reading.
		to = NativeSubpixel_SlotOf(dst, &rd);

		if (to >= 0)
		{
			rd->frac[to] = 0;
			rd->mark[to] = rs->mark[from];
		}
		return;
	}

	// The source stays - four quads share one corner, and
	// each gets it. The protection against a foreign fraction no longer sits
	// here, but with the writers (NativeSubpixel_Invalidate*) and in the
	// per-frame clearing; see include/ctr_subpixel.h.
	if (g_cfg_subpixelReport && (rs->mark[from] == NATIVE_SUBPIXEL_MARK_FORWARDED))
	{
		s_window.forwardReread++;
		s_total.forwardReread++;
	}

	// It only counts if the source still holds THE word it
	// belongs to. The caller has just read it itself and passed it on -
	// if something else stands there, someone has written in between.
	if (rs->word[from] != CTR_ReadU32LE(src))
	{
		if (g_cfg_subpixelReport)
		{
			s_window.forwardBadWord++;
			s_total.forwardBadWord++;
		}
		return;
	}

	to = NativeSubpixel_SlotOf(dst, &rd);

	if (to < 0)
	{
		return;
	}

	rs->mark[from] = NATIVE_SUBPIXEL_MARK_FORWARDED;
	rd->word[to] = CTR_ReadU32LE(dst);
	rd->frac[to] = frac;
	rd->mark[to] = NATIVE_SUBPIXEL_MARK_OK;

	if (g_cfg_subpixelReport && rd->arena)
	{
		s_window.arenaWritten++;
		s_total.arenaWritten++;
	}
}

void NativeSubpixel_CopyEntry(const void *dst, const void *src)
{
	struct NativeSubpixelRegion *rd;
	struct NativeSubpixelRegion *rs;
	int to;
	int from;

	if (!g_cfg_subpixel)
	{
		return;
	}

	to = NativeSubpixel_SlotOf(dst, &rd);

	if (to < 0)
	{
		return;
	}

	from = NativeSubpixel_SlotOf(src, &rs);

	// The entry moves along - under the same condition under which
	// passing on takes it: a fraction lies at the source, and the word
	// there is still the one it belongs to. The caller has just copied posScreen
	// word for word, so the target word is the same.
	if ((from >= 0) && (rs->frac[from] != 0) && (rs->word[from] == CTR_ReadU32LE(src)))
	{
		rd->word[to] = rs->word[from];
		rd->frac[to] = rs->frac[from];
		rd->mark[to] = NATIVE_SUBPIXEL_MARK_OK;
		return;
	}

	// Otherwise: whatever lay at the target belonged to another vertex. Clear it, and
	// tell the counting that there was a copy here - and of which kind the
	// source was, if it was already empty itself.
	rd->frac[to] = 0;
	rd->mark[to] = ((from >= 0) && (rs->frac[from] == 0) && (rs->mark[from] != NATIVE_SUBPIXEL_MARK_OK)) ? rs->mark[from]
	                                                                                                           : NATIVE_SUBPIXEL_MARK_COPIED;
}

void NativeSubpixel_InvalidateHand(const void *dst)
{
	struct NativeSubpixelRegion *rd;
	int to;

	if (!g_cfg_subpixel)
	{
		return;
	}

	to = NativeSubpixel_SlotOf(dst, &rd);

	if (to < 0)
	{
		return;
	}

	// Written by hand: whatever lay here belonged to another vertex.
	rd->frac[to] = 0;
	rd->mark[to] = NATIVE_SUBPIXEL_MARK_HAND;
}

int NativeSubpixel_Lookup(const void *xy, int *fx, int *fy, int ui, int kind)
{
	struct NativeSubpixelRegion *r;
	int at;
	u8 frac;
	const int who = ui ? 1 : 0;
	const int k = ((kind >= 0) && (kind < (NATIVE_SUBPIXEL_KINDS - 1))) ? kind : (NATIVE_SUBPIXEL_KINDS - 1);

	if (!g_cfg_subpixel)
	{
		return 0;
	}

	at = NativeSubpixel_SlotOf(xy, &r);

	if (at < 0)
	{
		if (g_cfg_subpixelReport)
		{
			s_window.lookupOffMirror++;
			s_total.lookupOffMirror++;
		}
		return 0;
	}

	frac = r->frac[at];

	if (frac == 0)
	{
		if (g_cfg_subpixelReport)
		{
			s64 *w;
			s64 *t;

			s_window.lookupEmpty++;
			s_total.lookupEmpty++;

			switch (r->mark[at])
			{
			case NATIVE_SUBPIXEL_MARK_UNUSABLE:
				w = &s_window.emptyUnusable[who];
				t = &s_total.emptyUnusable[who];
				break;
			case NATIVE_SUBPIXEL_MARK_CONSUMED:
				w = &s_window.emptyConsumed[who];
				t = &s_total.emptyConsumed[who];
				break;
			case NATIVE_SUBPIXEL_MARK_OK:
			case NATIVE_SUBPIXEL_MARK_FORWARDED:
				w = &s_window.emptyOkZero[who];
				t = &s_total.emptyOkZero[who];
				break;
			case NATIVE_SUBPIXEL_MARK_COPIED:
				w = &s_window.emptyCopied[who];
				t = &s_total.emptyCopied[who];
				break;
			case NATIVE_SUBPIXEL_MARK_HAND:
				w = &s_window.emptyHand[who];
				t = &s_total.emptyHand[who];
				break;
			default:
				w = &s_window.emptyNone[who];
				t = &s_total.emptyNone[who];
				s_window.emptyNoneKind[who][k]++;
				s_total.emptyNoneKind[who][k]++;
				break;
			}

			(*w)++;
			(*t)++;
		}

		/* Fix gaps: un vértice con fracción 0.0 es válido si el GTE lo registró.
		   Devolvemos 1 con fx=0, fy=0 para que el polígono se mueva (por 0) 
		   en lugar de ignorar la fracción por completo. */
		if (r->mark[at] == NATIVE_SUBPIXEL_MARK_OK || r->mark[at] == NATIVE_SUBPIXEL_MARK_FORWARDED)
		{
			*fx = 0;
			*fy = 0;
			return 1;
		}
		return 0;
	}

	// THE CHECK THAT KILLS THE DANGEROUS CASE. The fractional part
	// only applies to the word it was stored with. If the primitive
	// now holds something else, one of the 305 writers has written into it
	// by hand - then the whole pixel applies.
	if (r->word[at] != CTR_ReadU32LE(xy))
	{
		if (g_cfg_subpixelReport)
		{
			s_window.lookupStale++;
			s_total.lookupStale++;
		}
		return 0;
	}

	if (g_cfg_subpixelReport)
	{
		s_window.carriedBy[who]++;
		s_total.carriedBy[who]++;
	}

	*fx = (int)(frac & 0xfu);
	*fy = (int)((frac >> 4) & 0xfu);
	return 1;
}

void NativeSubpixel_NoteVertexCarried(int count)
{
	if (!g_cfg_subpixelReport)
	{
		return;
	}

	s_window.verticesCarried += count;
	s_total.verticesCarried += count;
}

void NativeSubpixel_NoteVertices(int kind, int count)
{
	if (!g_cfg_subpixelReport)
	{
		return;
	}

	if ((kind < 0) || (kind >= NATIVE_SUBPIXEL_VTX_KINDS))
	{
		return;
	}

	s_window.vertices[kind] += count;
	s_total.vertices[kind] += count;
}

internal void NativeSubpixel_Line(const char *what, const struct NativeSubpixelCensus *c, int frames)
{
	const s64 poly = c->vertices[NATIVE_SUBPIXEL_VTX_TRI] + c->vertices[NATIVE_SUBPIXEL_VTX_QUAD];
	const s64 all = poly + c->vertices[NATIVE_SUBPIXEL_VTX_RECT] + c->vertices[NATIVE_SUBPIXEL_VTX_LINE];
	const double sharePoly = (poly > 0) ? (100.0 * (double)c->stores / (double)poly) : 0.0;
	const double shareAll = (all > 0) ? (100.0 * (double)c->stores / (double)all) : 0.0;

	Platform_Log("[CTR Sub] %s %d frames - projections %lld (clamped %lld, frac4 x %lld y %lld), "
	             "stores %lld (stale %lld, clamped %lld, frac4 %lld)\n",
	             what, frames, c->projections, c->projClamped, c->projFrac4X, c->projFrac4Y, c->stores, c->storesStale, c->storesClamped,
	             c->storesFrac4);
	Platform_Log("[CTR Sub] %s vertices tri %lld quad %lld rect %lld line %lld - "
	             "stores/polygon-vertices %.1f %%, stores/all-vertices %.1f %%\n",
	             what, c->vertices[NATIVE_SUBPIXEL_VTX_TRI], c->vertices[NATIVE_SUBPIXEL_VTX_QUAD], c->vertices[NATIVE_SUBPIXEL_VTX_RECT],
	             c->vertices[NATIVE_SUBPIXEL_VTX_LINE], sharePoly, shareAll);
	Platform_Log("[CTR Sub] %s CARRIED %lld of %lld vertices (%.1f %%) - stores outside every mirror %lld\n", what, c->verticesCarried, all,
	             (all > 0) ? (100.0 * (double)c->verticesCarried / (double)all) : 0.0, c->storesOffMirror);
	Platform_Log("[CTR Sub] %s   lost: off-mirror %lld, empty %lld, stale %lld; forward no-src %lld, bad-word %lld\n", what,
	             c->lookupOffMirror, c->lookupEmpty, c->lookupStale, c->forwardNoSrc, c->forwardBadWord);
	Platform_Log("[CTR Sub] %s   arena: %lld fractions written, %lld read - %lld never read (primitive not drawn)\n", what,
	             c->arenaWritten, c->verticesCarried, c->arenaWritten - c->verticesCarried);
	Platform_Log("[CTR Sub] %s   empty by cause, WORLD: never-gte %lld, unusable %lld, consumed %lld, ok-zero %lld (carried %lld)\n", what,
	             c->emptyNone[0], c->emptyUnusable[0], c->emptyConsumed[0], c->emptyOkZero[0], c->carriedBy[0]);
	Platform_Log("[CTR Sub] %s   empty by cause, UI:    never-gte %lld, unusable %lld, consumed %lld, ok-zero %lld (carried %lld)\n", what,
	             c->emptyNone[1], c->emptyUnusable[1], c->emptyConsumed[1], c->emptyOkZero[1], c->carriedBy[1]);
	Platform_Log("[CTR Sub] %s   empty, track paths: copied world %lld ui %lld, hand world %lld ui %lld\n", what, c->emptyCopied[0],
	             c->emptyCopied[1], c->emptyHand[0], c->emptyHand[1]);
	Platform_Log("[CTR Sub] %s   forward no-src by source mark: none %lld unusable %lld ok-zero %lld consumed %lld copied %lld hand %lld; "
	             "re-reads %lld\n",
	             what, c->forwardSrcMark[0], c->forwardSrcMark[1], c->forwardSrcMark[2], c->forwardSrcMark[3], c->forwardSrcMark[4],
	             c->forwardSrcMark[5], c->forwardReread);
	Platform_Log("[CTR Sub] %s   never-gte WORLD by type (F3 FT3 G3 GT3 F4 FT4 G4 GT4 ?): %lld %lld %lld %lld %lld %lld %lld %lld %lld\n", what,
	             c->emptyNoneKind[0][0], c->emptyNoneKind[0][1], c->emptyNoneKind[0][2], c->emptyNoneKind[0][3], c->emptyNoneKind[0][4],
	             c->emptyNoneKind[0][5], c->emptyNoneKind[0][6], c->emptyNoneKind[0][7], c->emptyNoneKind[0][8]);
}

internal void NativeSubpixel_Clear(struct NativeSubpixelCensus *c)
{
	int i;

	c->projections = 0;
	c->projClamped = 0;
	c->projFracX = 0;
	c->projFracY = 0;
	c->projFrac4X = 0;
	c->projFrac4Y = 0;
	c->stores = 0;
	c->storesStale = 0;
	c->storesClamped = 0;
	c->storesFrac4 = 0;
	c->storesOffMirror = 0;
	c->verticesCarried = 0;
	c->lookupOffMirror = 0;
	c->lookupEmpty = 0;
	c->lookupStale = 0;
	c->forwardNoSrc = 0;
	c->forwardBadWord = 0;
	c->arenaWritten = 0;
	c->forwardReread = 0;

	for (i = 0; i < 2; i++)
	{
		c->emptyNone[i] = 0;
		c->emptyUnusable[i] = 0;
		c->emptyConsumed[i] = 0;
		c->emptyOkZero[i] = 0;
		c->carriedBy[i] = 0;
		c->emptyCopied[i] = 0;
		c->emptyHand[i] = 0;
	}

	for (i = 0; i < NATIVE_SUBPIXEL_MARKS; i++)
	{
		c->forwardSrcMark[i] = 0;
	}

	for (i = 0; i < NATIVE_SUBPIXEL_KINDS; i++)
	{
		c->emptyNoneKind[0][i] = 0;
		c->emptyNoneKind[1][i] = 0;
	}

	for (i = 0; i < NATIVE_SUBPIXEL_VTX_KINDS; i++)
	{
		c->vertices[i] = 0;
	}
}

void NativeSubpixel_Frame(void)
{
	if (!g_cfg_subpixelReport)
	{
		return;
	}

	// As for --gte-report: register once, and here rather than when
	// reading the switch, because Platform_AtExitReport runs in Platform_Shutdown before
	// the log is closed.
	if (!s_subpixelArmed)
	{
		s_subpixelArmed = 1;
		        atexit(NativeSubpixel_Report);
	}

	s_windowFrames++;
	s_totalFrames++;

	if ((s_subpixelReportEvery <= 0) || (s_windowFrames < s_subpixelReportEvery))
	{
		return;
	}

	NativeSubpixel_Line("over", &s_window, s_windowFrames);
	NativeSubpixel_Clear(&s_window);
	s_windowFrames = 0;
}

void NativeSubpixel_Report(void)
{
	if (!g_cfg_subpixelReport)
	{
		return;
	}

	if (s_windowFrames > 0)
	{
		NativeSubpixel_Line("closing", &s_window, s_windowFrames);
	}

	NativeSubpixel_Line("TOTAL", &s_total, s_totalFrames);
	Platform_Log("[CTR Sub] stores are coordinates leaving the GTE, vertices are what the drawer submits - "
	             "their ratio is a BOUND, not an identity: a stored coordinate can still be culled, "
	             "a vertex can be submitted more than once\n");
	Platform_LogFlush();
}

void NativeSubpixel_Arm(int everyFrames)
{
	g_cfg_subpixelReport = 1;
	s_subpixelReportEvery = everyFrames;

	NativeSubpixel_Clear(&s_window);
	NativeSubpixel_Clear(&s_total);
	s_windowFrames = 0;
	s_totalFrames = 0;

	if (everyFrames > 0)
	{
		printf("[CTR Sub] subpixel coverage census on, one line every %d frames (--subpixel-report)\n", everyFrames);
	}
	else
	{
		printf("[CTR Sub] subpixel coverage census on, total at exit (--subpixel-report)\n");
	}
}
