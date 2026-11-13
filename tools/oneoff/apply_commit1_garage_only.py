#!/usr/bin/env python3
"""
Commit 1 -- Garage-only ID namespace (inert).

Applies 3 file edits atomically:
  include/platform/native_custom_racer.h
    - NATIVE_CUSTOM_COUNT 200 -> 240
    - garage-only block after NATIVE_CUSTOM_ID_BASE define
    - GET_METADATA replacement
  platform/native_custom_racer.c
    - side table + helpers after s_customMenuID definition
    - ApplyGarageOnlyMeta() hook after ReloadRoster memset
  platform/native_adventure_pack.c
    - ResetGarageOnly() at top of ResolvePack()

Usage:
  python tools/oneoff/apply_commit1_garage_only.py            # dry-run (default)
  python tools/oneoff/apply_commit1_garage_only.py --apply    # write

Safety:
  - every anchor must match EXACTLY once, otherwise nothing is written
  - idempotent: already-applied steps report "already applied, skip"
  - preserves CRLF/LF and trailing whitespace
"""
import os, re, sys, difflib

APPLY = "--apply" in sys.argv
HERE  = os.path.dirname(os.path.abspath(__file__))
ROOT  = os.path.abspath(os.path.join(HERE, "..", ".."))
if not os.path.isdir(os.path.join(ROOT, "platform")):
    sys.exit(f"ERROR: platform/ not found under {ROOT}")

print(f"repo root: {ROOT}")
print(f"mode:      {'APPLY' if APPLY else 'DRY-RUN'}")
print()

errors  = []
changes = []

def read(rel):
    with open(os.path.join(ROOT, rel), "r", newline="") as f:
        return f.read()

def write(rel, content):
    with open(os.path.join(ROOT, rel), "w", newline="") as f:
        f.write(content)

def must_unique(rel, src, needle, label):
    n = src.count(needle)
    if n != 1:
        errors.append(f"{rel} :: {label} :: expected 1 match, got {n}")
        return False
    return True

def detect_le(s):
    return "\r\n" if "\r\n" in s else "\n"

def adapt(block, le):
    return block.replace("\n", le) if le != "\n" else block

def diff(rel, old, new):
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=rel + "  (current)",
        tofile=rel + "  (patched)", n=3))

# =====================================================================
# 1. include/platform/native_custom_racer.h
# =====================================================================
H      = "include/platform/native_custom_racer.h"
h_src  = read(H)
h_out  = h_src
le_h   = detect_le(h_src)

# 1a. COUNT 200 -> 240
if re.search(r"#define NATIVE_CUSTOM_COUNT\s+240\b", h_out):
    print(f"[{H}] COUNT: already 240, skip")
else:
    m = re.search(r"#define NATIVE_CUSTOM_COUNT\s+200\b", h_out)
    if not m:
        errors.append(f"{H} :: COUNT: no '#define NATIVE_CUSTOM_COUNT ... 200'")
    else:
        s, e = m.span()
        h_out = h_out[:s] + "#define NATIVE_CUSTOM_COUNT   240" + h_out[e:]
        print(f"[{H}] COUNT: 200 -> 240")

# 1b. Garage-only block after ID_BASE define
if "NATIVE_GARAGE_ONLY_BASE" in h_out:
    print(f"[{H}] garage-only block: already present, skip")
else:
    anchor = "#define NATIVE_CUSTOM_ID_BASE 16"
    if must_unique(H, h_out, anchor, "ID_BASE anchor"):
        nl = h_out.find("\n", h_out.find(anchor))
        if nl < 0:
            errors.append(f"{H} :: no newline after ID_BASE anchor")
        else:
            GO = adapt(r"""
/* ---------------------------------------------------------------------
 * Garage-only: retail chars with a custom HD garage model, NOT in roster.
 * Live INSIDE the custom namespace (216..255) so every per-custom array
 * (s_customMeta, sentinel maps, s_customRot, garage anims, ...) works
 * unchanged.
 *
 *   s_customMeta[idx].name_Debug = folder slug  -> GetFolder(216+) returns
 *       "ntropy" -> LoadModel loads racers/ntropy/garage/model.ctr
 *   s_customMeta[idx].iconID    = -1            -> never in char-select
 *   GET_METADATA(216+)          -> data.MetaDataCharacters[retailID]
 *       (name, stats, engine, color, voice come from the retail char)
 *
 * Registered by NativeAdventurePack_ResolvePack from level.json.
 * Cleared on NativeAdventurePack_OnGarageReset.
 * --------------------------------------------------------------------- */
#define NATIVE_GARAGE_ONLY_BASE   (NATIVE_CUSTOM_ID_BASE + 200)  /* 216 */
#define NATIVE_GARAGE_ONLY_COUNT  40
#define IS_NATIVE_GARAGE_ONLY_ID(id)                                     \
    ((id) >= NATIVE_GARAGE_ONLY_BASE &&                                  \
     (id) <  (NATIVE_GARAGE_ONLY_BASE + NATIVE_GARAGE_ONLY_COUNT))

int  NativeCustomRacer_RegisterGarageOnly(const char *slug, int retailID);
void NativeCustomRacer_ResetGarageOnly(void);
int  NativeCustomRacer_GetGarageOnlyRetailID(int id);    /* no-op si no garage-only */
const char *NativeCustomRacer_GetGarageOnlySlug(int id); /* NULL si no garage-only */
""", le_h)
            h_out = h_out[:nl+1] + GO + h_out[nl+1:]
            print(f"[{H}] garage-only block: inserted")

# 1c. GET_METADATA replacement
tail = h_out.split("#define GET_METADATA", 1)
already_gm = len(tail) == 2 and "IS_NATIVE_GARAGE_ONLY_ID(id)" in tail[1][:300]
if already_gm:
    print(f"[{H}] GET_METADATA: already patched, skip")
else:
    start = h_out.find("#define GET_METADATA(id)")
    end_marker = ": &data.MetaDataCharacters[(id)])"
    if start < 0:
        errors.append(f"{H} :: GET_METADATA define not found")
    else:
        rel = h_out.find(end_marker, start)
        if rel < 0:
            errors.append(f"{H} :: GET_METADATA end marker not found")
        else:
            end = rel + len(end_marker)
            NEW_MACRO = adapt(
                "#define GET_METADATA(id)                                                         \\\n"
                "    (IS_NATIVE_GARAGE_ONLY_ID(id)                                                \\\n"
                "        ? &data.MetaDataCharacters[NativeCustomRacer_GetGarageOnlyRetailID(id)]  \\\n"
                "        : (((id) >= NATIVE_CUSTOM_ID_BASE &&                                     \\\n"
                "            (id) <  NATIVE_CUSTOM_ID_BASE + NATIVE_CUSTOM_COUNT)                 \\\n"
                "             ? &s_customMeta[(id) - NATIVE_CUSTOM_ID_BASE]                       \\\n"
                "             : &data.MetaDataCharacters[(id)]))",
                le_h)
            h_out = h_out[:start] + NEW_MACRO + h_out[end:]
            print(f"[{H}] GET_METADATA: replaced")

if h_out != h_src:
    changes.append((H, h_src, h_out))

# =====================================================================
# 2. platform/native_custom_racer.c
# =====================================================================
C     = "platform/native_custom_racer.c"
c_src = read(C)
c_out = c_src
le_c  = detect_le(c_src)

# 2a. Side table + helpers after s_customMenuID definition
if "s_garageOnly[NATIVE_GARAGE_ONLY_COUNT]" in c_out:
    print(f"[{C}] side table: already present, skip")
else:
    anchor = "s_customMenuID[NATIVE_CUSTOM_COUNT];"
    if must_unique(C, c_out, anchor, "s_customMenuID def"):
        nl = c_out.find("\n", c_out.find(anchor))
        if nl < 0:
            errors.append(f"{C} :: no newline after s_customMenuID")
        else:
            SIDE = adapt(r"""

/* --- Garage-only side table -----------------------------------------
 * Stored outside s_customMeta so it survives ReloadRoster's memset.
 * ApplyGarageOnlyMeta() re-populates the s_customMeta[] mirror after
 * every reset. Kept minimal on purpose: name_Debug = folder slug (for
 * GetFolder -> LoadModel), iconID = -1 (never in char-select).
 * All identity data comes from GET_METADATA -> data.MetaDataCharacters[retailID]. */
static struct {
    int  used;
    int  retailID;
    char slug[64];
} s_garageOnly[NATIVE_GARAGE_ONLY_COUNT];

static void ApplyGarageOnlyMeta(void)
{
    for (int i = 0; i < NATIVE_GARAGE_ONLY_COUNT; i++) {
        if (!s_garageOnly[i].used) continue;
        int idx = NATIVE_GARAGE_ONLY_BASE - NATIVE_CUSTOM_ID_BASE + i;  /* 200 + i */
        if (idx < 0 || idx >= NATIVE_CUSTOM_COUNT) continue;

        s_customMeta[idx].name_Debug = s_garageOnly[i].slug;
        s_customMeta[idx].iconID     = (s16)-1;
    }
}

int NativeCustomRacer_RegisterGarageOnly(const char *slug, int retailID)
{
    if (!slug || !slug[0] || retailID < 0 || retailID >= 0x10)
        return -1;

    for (int i = 0; i < NATIVE_GARAGE_ONLY_COUNT; i++) {
        if (s_garageOnly[i].used &&
            s_garageOnly[i].retailID == retailID &&
            strcmp(s_garageOnly[i].slug, slug) == 0)
            return NATIVE_GARAGE_ONLY_BASE + i;
    }

    for (int i = 0; i < NATIVE_GARAGE_ONLY_COUNT; i++) {
        if (!s_garageOnly[i].used) {
            s_garageOnly[i].used     = 1;
            s_garageOnly[i].retailID = retailID;
            strncpy(s_garageOnly[i].slug, slug, sizeof(s_garageOnly[i].slug) - 1);
            s_garageOnly[i].slug[sizeof(s_garageOnly[i].slug) - 1] = '\0';
            ApplyGarageOnlyMeta();
            fprintf(stderr,
                    "[GarageOnly] '%s' retail=%d -> id=%d\n",
                    slug, retailID, NATIVE_GARAGE_ONLY_BASE + i);
            return NATIVE_GARAGE_ONLY_BASE + i;
        }
    }
    fprintf(stderr, "[GarageOnly] FULL (%d): cannot register '%s'\n",
            NATIVE_GARAGE_ONLY_COUNT, slug);
    return -1;
}

void NativeCustomRacer_ResetGarageOnly(void)
{
    memset(s_garageOnly, 0, sizeof(s_garageOnly));
    for (int i = 0; i < NATIVE_GARAGE_ONLY_COUNT; i++) {
        int idx = NATIVE_GARAGE_ONLY_BASE - NATIVE_CUSTOM_ID_BASE + i;
        if (idx >= 0 && idx < NATIVE_CUSTOM_COUNT)
            memset(&s_customMeta[idx], 0, sizeof(s_customMeta[idx]));
    }
}

int NativeCustomRacer_GetGarageOnlyRetailID(int id)
{
    if (!IS_NATIVE_GARAGE_ONLY_ID(id)) return id;
    int i = id - NATIVE_GARAGE_ONLY_BASE;
    return s_garageOnly[i].used ? s_garageOnly[i].retailID : id;
}

const char *NativeCustomRacer_GetGarageOnlySlug(int id)
{
    if (!IS_NATIVE_GARAGE_ONLY_ID(id)) return NULL;
    int i = id - NATIVE_GARAGE_ONLY_BASE;
    return s_garageOnly[i].used ? s_garageOnly[i].slug : NULL;
}
""", le_c)
            c_out = c_out[:nl+1] + SIDE + c_out[nl+1:]
            print(f"[{C}] side table + helpers: inserted")

# 2b. ReloadRoster hook after memset(s_customMeta, ...)
if "ApplyGarageOnlyMeta();   /* re-populate garage-only entries after memset */" in c_out:
    print(f"[{C}] ReloadRoster hook: already present, skip")
else:
    anchor = "memset(s_customMeta, 0, sizeof(s_customMeta));"
    if must_unique(C, c_out, anchor, "ReloadRoster memset"):
        nl = c_out.find("\n", c_out.find(anchor))
        if nl < 0:
            errors.append(f"{C} :: no newline after ReloadRoster memset")
        else:
            HOOK = adapt("\n    ApplyGarageOnlyMeta();   /* re-populate garage-only entries after memset */", le_c)
            c_out = c_out[:nl] + HOOK + c_out[nl:]
            print(f"[{C}] ReloadRoster hook: inserted")

if c_out != c_src:
    changes.append((C, c_src, c_out))

# =====================================================================
# 3. platform/native_adventure_pack.c
# =====================================================================
P     = "platform/native_adventure_pack.c"
p_src = read(P)
p_out = p_src
le_p  = detect_le(p_src)

if "NativeCustomRacer_ResetGarageOnly();   /* wipe garage-only before re-resolving */" in p_out:
    print(f"[{P}] ResolvePack reset: already present, skip")
else:
    anchor = adapt("static void ResolvePack(void)\n{\n    s_packActive = 0;", le_p)
    if must_unique(P, p_out, anchor, "ResolvePack entry"):
        repl = adapt(
            "static void ResolvePack(void)\n"
            "{\n"
            "    NativeCustomRacer_ResetGarageOnly();   /* wipe garage-only before re-resolving */\n"
            "\n"
            "    s_packActive = 0;", le_p)
        p_out = p_out.replace(anchor, repl, 1)
        print(f"[{P}] ResolvePack reset: inserted")

if p_out != p_src:
    changes.append((P, p_src, p_out))

# =====================================================================
# Report / write
# =====================================================================
print()
if errors:
    print("ERRORS -- nothing will be written:")
    for e in errors:
        print("  " + e)
    sys.exit(1)

if not changes:
    print("All steps already applied. Nothing to do.")
    sys.exit(0)

for rel, old, new in changes:
    print(diff(rel, old, new))
    print()

if APPLY:
    for rel, old, new in changes:
        write(rel, new)
    print("WROTE:")
    for rel, _, _ in changes:
        print("  " + rel)
    print()
    print("Next:")
    print("  rm -f build-msvc-x86/**/*.obj")
    print("  cmake --build build-msvc-x86 --config Release 2>&1 | grep -E \"error|ctr_native.vcxproj ->\"")
    print()
    print("Expected at runtime: no [GarageOnly] logs, MEGUMI/yaya/etc. unchanged.")
else:
    print("DRY-RUN -- no files changed. Re-run with --apply to write.")