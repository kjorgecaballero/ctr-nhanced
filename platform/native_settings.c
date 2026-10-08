#include <common.h>
#include "native_settings.h"
#include <stdio.h>
#include <string.h>

#define NATIVE_SETTINGS_FILE "ctr_native.cfg"

extern int  gNativeDitheringEnabled;
extern int  g_cfg_bilinearFiltering;
extern void NativeRenderer_SetInternalScale(int scale);
extern int  NativeRenderer_GetInternalScale(void);

static int s_loaded     = 0;
static int s_dithering  = 1;
static int s_resolution = 2;
static int s_bilinear   = 0;

int NativeSettings_GetDithering(void) { return s_dithering; }
int NativeSettings_GetResolution(void) { return s_resolution; }
int NativeSettings_GetBilinear(void)   { return s_bilinear; }

void NativeSettings_Save(void)
{
    if (!s_loaded) return;
    FILE *f = fopen(NATIVE_SETTINGS_FILE, "wb");
    if (f == NULL) return;
    fprintf(f, "version=1\n");
    fprintf(f, "dithering=%d\n",  s_dithering);
    fprintf(f, "resolution=%d\n", s_resolution);
    fprintf(f, "bilinear=%d\n",   s_bilinear);
    fclose(f);
}

static void NativeSettings_Apply(void)
{
    gNativeDitheringEnabled = s_dithering;
    g_cfg_bilinearFiltering = s_bilinear;
    NativeRenderer_SetInternalScale(s_resolution);
}

void NativeSettings_Load(void)
{
    if (s_loaded) return;
    s_loaded = 1;

    FILE *f = fopen(NATIVE_SETTINGS_FILE, "rb");
    if (f == NULL)
    {
        NativeSettings_Apply();
        NativeSettings_Save();
        return;
    }

    char line[128];
    while (fgets(line, sizeof(line), f) != NULL)
    {
        char key[64];
        int value;
        if (sscanf(line, "%63[^=]=%d", key, &value) != 2) continue;
        if      (strcmp(key, "dithering")  == 0) s_dithering  = (value != 0);
        else if (strcmp(key, "resolution") == 0) s_resolution = value;
        else if (strcmp(key, "bilinear")   == 0) s_bilinear   = (value != 0);
    }
    fclose(f);

    if (s_resolution < 1) s_resolution = 1;
    if (s_resolution > 8) s_resolution = 8;

    NativeSettings_Apply();
}

void NativeSettings_SetDithering(int enabled)
{
    enabled = (enabled != 0);
    if (s_dithering == enabled) return;
    s_dithering = enabled;
    gNativeDitheringEnabled = enabled;
    NativeSettings_Save();
}

void NativeSettings_SetResolution(int scale)
{
    if (scale < 1) scale = 1;
    if (scale > 8) scale = 8;
    if (s_resolution == scale) return;
    s_resolution = scale;
    NativeRenderer_SetInternalScale(scale);
    NativeSettings_Save();
}

void NativeSettings_SetBilinear(int enabled)
{
    enabled = (enabled != 0);
    if (s_bilinear == enabled) return;
    s_bilinear = enabled;
    g_cfg_bilinearFiltering = enabled;
    NativeSettings_Save();
}