#ifndef NATIVE_DEBUG_H
#define NATIVE_DEBUG_H

#include <stdlib.h>

static inline int NativeDbg_Enabled(int *cache, const char *envName)
{
    if (*cache < 0) {
        *cache = (getenv(envName) != NULL) ? 1 : 0;
    }
    return *cache;
}

#endif /* NATIVE_DEBUG_H */
