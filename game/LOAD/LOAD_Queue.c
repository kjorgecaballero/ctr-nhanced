#include <common.h>

#if defined(CTR_NATIVE) && defined(_MSC_VER)
#include <windows.h>
#include <dbghelp.h>
#pragma comment(lib, "dbghelp.lib")
static void LOADQ_Backtrace(void)
{
	void *frames[24];
	USHORT n = CaptureStackBackTrace(0, 24, frames, NULL);
	HANDLE proc = GetCurrentProcess();
	SymInitialize(proc, NULL, TRUE);
	for (USHORT i = 0; i < n; i++)
	{
		DWORD64 a = (DWORD64)frames[i];
		char b[sizeof(SYMBOL_INFO) + 256];
		SYMBOL_INFO *s = (SYMBOL_INFO *)b;
		s->SizeOfStruct = sizeof(SYMBOL_INFO);
		s->MaxNameLen = 255;
		DWORD64 d = 0;
		if (SymFromAddr(proc, a, &d, s))
			fprintf(stderr, "      [%02d] %s + 0x%llx\n", i, s->Name, (unsigned long long)d);
		else
			fprintf(stderr, "      [%02d] 0x%llx\n", i, (unsigned long long)a);
	}
}
#endif

void LOAD_AppendQueue(struct BigHeader *bigfile, int type, int fileIndex, void *destinationPtr, void (*callback)(struct LoadQueueSlot *))
{
#ifdef CTR_NATIVE
	if (bigfile == NULL)
		bigfile = sdata->ptrBigfile1;

	/* LOAD_TenStages may pass a bigfile that only has 608 entries
	 * while the file we want (BI_TIMETRIALPACK + mpkID, index ~763)
	 * lives in the main bigfile (thousands of entries). If the passed
	 * bigfile can't hold the index, swap to sdata->ptrBigfile1. */
	if (bigfile != NULL && (fileIndex < 0 || (u32)fileIndex >= (u32)bigfile->numEntry))
	{
		fprintf(stderr,
		        "[LOAD] AppendQueue: fileIndex=%d out of range for bigfile=%p (numEntry=%d), ptrBigfile1=%p (numEntry=%d)\n",
		        fileIndex, (void *)bigfile, (int)bigfile->numEntry,
		        (void *)sdata->ptrBigfile1,
		        sdata->ptrBigfile1 ? (int)sdata->ptrBigfile1->numEntry : -1);

		if (sdata->ptrBigfile1 != NULL &&
		    sdata->ptrBigfile1 != bigfile &&
		    fileIndex >= 0 &&
		    (u32)fileIndex < (u32)sdata->ptrBigfile1->numEntry)
		{
			fprintf(stderr, "[LOAD] AppendQueue: swapping to ptrBigfile1\n");
			bigfile = sdata->ptrBigfile1;
		}
		else
		{
			/* Bigfile truncated (custom repack, 608 entries) — the
			 * MPK packs at BI_TIMETRIALPACK+ do not exist in this
			 * build. Return success without queueing, so the load
			 * callback chain stays alive. The affected slot will
			 * use its default model. */
			fprintf(stderr, "[LOAD] AppendQueue: index %d missing from bigfile, skipping\n", fileIndex);
			fileIndex = 0;
		}
	}
#endif

	if (sdata->queueLength >= LOAD_QUEUE_SLOT_COUNT)
	{
		return;
	}

	struct LoadQueueSlot *lqs = &sdata->queueSlots[(s32)sdata->queueLength];
	lqs->ptrBigfileCdPos_UNUSED = bigfile;
	lqs->flags = 0;
	lqs->type_UNUSED = type;
	lqs->subfileIndex = fileIndex;
	lqs->ptrDestination = destinationPtr;
	lqs->size_UNUSED = 0;
	lqs->callbackFuncPtr = callback;

	sdata->queueLength++;
}

void LOAD_CDRequestCallback(struct LoadQueueSlot *lqs)
{
	if (lqs->callbackFuncPtr != NULL)
	{
		lqs->callbackFuncPtr(lqs);
	}

	sdata->queueReady = 1;
}

void LOAD_NextQueuedFile()
{
	struct LoadQueueSlot *curr = &data.currSlot;

	if ((sdata->queueReady != 0) && (sdata->XA_State == 0) && (sdata->queueLength != 0))
	{
		sdata->queueReady = 0;

		if (sdata->queueRetry != 0)
		{
			sdata->queueRetry = 0;
		}
		else
		{
			*curr = sdata->queueSlots[0];

			for (int i = LOAD_QUEUE_FIRST_PENDING_SLOT; i < sdata->queueLength; i++)
			{
				sdata->queueSlots[i - 1] = sdata->queueSlots[i];
			}
		}

		switch (curr->type_UNUSED)
		{
		case LT_RAW:
			curr->ptrDestination = LOAD_ReadFile_ex(curr->ptrBigfileCdPos_UNUSED, LT_SETADDR, curr->subfileIndex, curr->ptrDestination, &curr->size_UNUSED,
			                                        LOAD_CDRequestCallback);
			break;

		case LT_DRAM:
			curr->ptrDestination =
			    LOAD_DramFile(curr->ptrBigfileCdPos_UNUSED, curr->subfileIndex, curr->ptrDestination, &curr->size_UNUSED, (int)(s32)curr->callbackFuncPtr);
			break;

		case LT_VRAM:
			curr->ptrDestination =
			    LOAD_VramFile(curr->ptrBigfileCdPos_UNUSED, curr->subfileIndex, curr->ptrDestination, &curr->size_UNUSED, (int)(s32)curr->callbackFuncPtr);
			break;
		}

		sdata->queueLength--;
	}

	if (sdata->frameFinishedVRAM != 0)
	{
		if ((u32)(sdata->gGT->frameTimer_VsyncCallback - sdata->frameFinishedVRAM) >= LOAD_QUEUE_VRAM_CALLBACK_DELAY_FRAMES)
		{
			if (curr->callbackFuncPtr != NULL)
			{
				curr->callbackFuncPtr(curr);
			}

			sdata->frameFinishedVRAM = 0;

#if defined(CTR_NATIVE)
			if ((curr->flags & (LT_SETADDR | LT_MEMPACK)) != 0)
#else
			if ((curr->flags & LT_SETADDR) != 0)
#endif
			{
				MEMPACK_PopState();
			}

			sdata->queueReady = 1;
		}
	}
}