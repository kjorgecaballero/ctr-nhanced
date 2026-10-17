#include <common.h>

enum LibraryOfModelsConstants
{
	LIBRARY_OF_MODELS_CLEAR_COUNT = 0xe2,
};

#if defined(_WIN32)
#include <windows.h>

/* Reject any pointer that isn't a mapped readable region. The 0x10000
 * threshold was too low: garbage pointers as high as 0x3801C slipped
 * through and crashed at m->id. VirtualQuery covers every case. */
static int LibraryOfModels_PtrIsReadable(const void *p, size_t size)
{
	MEMORY_BASIC_INFORMATION mbi;
	uintptr_t start, end, regionEnd;

	if (p == NULL || size == 0) return 0;
	if (VirtualQuery(p, &mbi, sizeof(mbi)) == 0) return 0;
	if (mbi.State != MEM_COMMIT) return 0;
	if (mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)) return 0;

	start = (uintptr_t)p;
	end = start + size;
	regionEnd = (uintptr_t)mbi.BaseAddress + mbi.RegionSize;
	if (end > regionEnd) return 0;

	return 1;
}
#else
static int LibraryOfModels_PtrIsReadable(const void *p, size_t size)
{
	(void)p; (void)size;
	return 1;
}
#endif

void LibraryOfModels_Store(struct GameTracker *gGT, u32 numModels, struct Model **ptrModelArray)
{
	if (ptrModelArray == NULL)
	{
		return;
	}

	while (numModels != 0)
	{
		struct Model *m = *ptrModelArray;

		/* Reject NULL, small-invalid, or unmapped pointers. A stale
		 * driverModelExtras[] entry on the second custom load has
		 * produced m = 0x38000 (above the old 0x10000 threshold),
		 * then crashed reading m->id. VirtualQuery catches every case. */
		if (!LibraryOfModels_PtrIsReadable(m, sizeof(struct Model)))
		{
			return;
		}

		if (m->id != -1)
		{
			gGT->modelPtr[m->id] = m;
		}
		numModels--;
		ptrModelArray++;
	}
}

void LibraryOfModels_Clear(struct GameTracker *gGT)
{
	for (s32 i = 0; i < LIBRARY_OF_MODELS_CLEAR_COUNT; i++)
	{
		gGT->modelPtr[i] = 0;
	}
}