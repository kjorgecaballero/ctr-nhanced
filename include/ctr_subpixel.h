// SUBPIXEL: THE FRACTIONAL DIGITS OF THE PROJECTION, ALL THE WAY TO THE VERTEX.
//
// The problem. The geometry sits on whole PSX screen coordinates
// before the render target sees it - two thirds of all vertical
// colour steps sit at 4:3 on the 4-pixel grid of the 2048-wide target. The GTE
// would have more: GTE_RotTransPers computes the screen position as 16.16 and
// throws away exactly sixteen fractional bits with `>> 16`
// (platform/native_gte_core.c, GTE_RotTransPers).
//
// MAC0 DOES NOT CARRY THIS VALUE. After RTPS it holds the fog interpolation
// DQB + DQA*h (platform/native_gte_core.c, GTE_operator), written in the same operator
// before a caller can see it. The exact screen value
// exists only inside GTE_RotTransPers, between the sum and the
// shift. That is why it is tapped there - in both GTE paths, otherwise
// --gte-alt measures something else - and put into a shadow stack that moves
// along with SXY0/1/2.
//
// WHY A MIRROR AND NOT THE PRIMITIVE ITSELF. Between the GTE and
// MakeVertexTriangle lies the primitive. Its s16 coordinate field would have room
// - the values are clamped to +-1024, 12.4 fits in -, but it has 305
// writers: 178 direct assignments in 11 files and 127 via
// CtrGpu_WritePackedXY in 23 files. The bulk of them are hand-set
// whole pixels (UI_Icon 48, UI_Meter 24, MainFrame_RenderFrame 24, FLARE 16,
// ...). Both kinds land in the same field, and the vertex builder has nothing
// by which it could tell them apart. A mirror next to the arena leaves
// all 305 writers alone.
//
// This is NOT an address-keyed scatter store with collisions (an earlier
// approach of that kind reached 43.6 % coverage). This one is addressed directly:
// one slot per four-byte word of a registered region, collision-free,
// complete on its paths.
//
// THE DANGEROUS CASE, AND HOW IT IS KILLED. A mirror that
// stays while the primitive changes colours a foreign
// vertex. Three precautions, none of them is enough alone:
//
//   1. Every slot also holds the XY word, as the store helper
//      wrote it. The fractional part is only read if the primitive
//      NOW still holds exactly this word. Whoever wrote into it by hand afterwards
//      gets the whole pixel - without having to know anything about it.
//   2. A fractional part of zero counts as "nothing there". A slot that was never
//      written can therefore not falsify anything.
//   3. The mirror of the arena is cleared when the draw buffer is reset
//      (MainFrame_ResetDB). Without that a still element
//      that lands frame after frame at the same place with the same coordinates
//      could inherit the fractional part of the previous frame.
//
// THE SCRATCH MEMORY AS A SOURCE. The track renderer does not store into the
// arena but into scratch vertices in the scratchpad, and only later packs them
// into the primitive. The scratchpad is therefore registered as a second region, and
// DrawLevelOvr1P_WriteProjected*/WriteClipRecord* pass the fractional part on
// explicitly (NativeSubpixel_Forward).
//
// A scratch vertex is read SEVERAL times - four neighbouring quads share
// one corner. When passing it on consumed the source slot, only the first
// quad got the fraction: 14.8 % of all drawn vertices. The consumption
// protected against exactly one thing: that a
// fraction keeps acting after the slot was written by someone other than the GTE.
// 37 files share the scratchpad; posScreen, however,
// is written by only three paths - the GTE store (sets the fraction), the copy
// (DrawLevelOvr1P_CopyProjectedScreenDepth) and the hand path from the
// IR vector (Ovr226_800aaad0_PrepareClipRecordDepthScratch). So the
// protection moves there: both clear the slot (NativeSubpixel_Invalidate), the
// scratch mirror is cleared per frame like the arena, and the word check
// on passing on stays. The source may then be read as often as
// it is needed.
//
// What can still go wrong after that: a foreign writer that puts THE SAME
// four-byte value at the same place the GTE left there, and
// which the track renderer then reads as posScreen without projecting it
// anew. Both would lie in the same pixel; the error would be smaller than a
// sixteenth of a pixel. The word check counts the cases in which the value
// was NOT the same (bad-word in the report) - that is the upper bound for the
// frequency of such overlaps at all.
//
// SWITCH: --subpixel, default off. If it is off, nothing is mirrored, the
// vertices get a fraction of zero, and the shader adds a zero.
// --subpixel-report [every N frames] counts independently of that how much coverage
// is reached.

#ifndef CTR_SUBPIXEL_H
#define CTR_SUBPIXEL_H

#include <macros.h>

// Default 0. Set from main.c.
extern int g_cfg_subpixel;
extern int g_cfg_subpixelReport;

// How many fractional bits are carried at all. Four, because GrVertex.x/y
// are clamped to +-1024 and an s16 would then still have four bits left -
// a target at NATIVE_RES_SCALE_MAX 8 can only show three, though.
#define NATIVE_SUBPIXEL_BITS  4
#define NATIVE_SUBPIXEL_STEPS (1 << NATIVE_SUBPIXEL_BITS)

// The kinds of vertex, counted separately. Triangle and quad are the
// only ones that can ever come from the GTE; rectangle and line are
// two-dimensional by construction and are here only for size comparison.
enum
{
	NATIVE_SUBPIXEL_VTX_TRI = 0,
	NATIVE_SUBPIXEL_VTX_QUAD,
	NATIVE_SUBPIXEL_VTX_RECT,
	NATIVE_SUBPIXEL_VTX_LINE,
	NATIVE_SUBPIXEL_VTX_KINDS
};

// --- The shadow stack in the GTE ---------------------------------------------

// From GTE_RotTransPers and GteAlt_RotTransPers, with the sums BEFORE the
// shift. clamped says whether Lm_G1/Lm_G2 clipped - then the
// fractional part is meaningless, because the integer part is already wrong.
void NativeSubpixel_PushFrac(s64 sxFull, s64 syFull, int sxClamped, int syClamped);

// From MTC2/MTC2_S. Whoever writes an SXY register from outside invalidates the
// shadow stack at this place.
void NativeSubpixel_InvalidateReg(int reg);
void NativeSubpixel_PushExternal(void);

// --- The mirror ---------------------------------------------------------

// Register a region whose four-byte words are to be mirrored. From
// MainDB_PrimMem (the two draw arenas) and Platform_InitScratchpad.
// Registering the same base more than once replaces the entry.
void NativeSubpixel_RegisterRegion(const void *base, u32 bytes, const char *what);

// Clear all slots of a region. From MainFrame_ResetDB for the arena of the
// back buffer.
void NativeSubpixel_ClearRegion(const void *base);

// From CTR_GteStoreSXY*: this XY word just went to this place, and the
// fractional part for it is at slot slot (0/1/2 for SXY0/SXY1/SXY2) of the
// shadow stack.
void NativeSubpixel_NoteStore(void *dst, u32 word, int slot);

// From DrawLevelOvr1P: the fractional part that lies at src belongs (also) to
// dst. The source stays readable.
void NativeSubpixel_Forward(void *dst, const void *src);

// From DrawLevelOvr1P_CopyProjectedScreenDepth: posScreen was copied from src to
// dst - the mirror entry moves along if at src there is one that belongs to the
// word standing there. Otherwise dst is cleared, so that no foreign
// fraction keeps acting. The 14 callers are the subdivision frames: corners
// are copied, only the midpoints are projected anew; without carrying it along
// the corners of every subdivision lost their fraction (7.8 % of all vertices).
void NativeSubpixel_CopyEntry(const void *dst, const void *src);

// From Ovr226_800aaad0_PrepareClipRecordDepthScratch: posScreen was written by hand
// from the IR vector. There is no fraction for that; the slot is
// cleared.
void NativeSubpixel_InvalidateHand(const void *dst);

// From the vertex builders. Returns 1 and sets fx/fy to 0..15 if at xy there is a
// fractional part that belongs to the value STANDING there.
// ui: the primitive lies in the UI ordering table (s_gpu.uiViewActive). Only
// for counting - the answer does not depend on it.
// kind: the primitive type from native_gpu.c (NATIVE_GPU_SIZE_*), counting only.
int NativeSubpixel_Lookup(const void *xy, int *fx, int *fy, int ui, int kind);

// --- The counting -----------------------------------------------------------

void NativeSubpixel_NoteVertices(int kind, int count);
void NativeSubpixel_NoteVertexCarried(int count);
void NativeSubpixel_Frame(void);
void NativeSubpixel_Report(void);
void NativeSubpixel_Arm(int everyFrames);

#endif
