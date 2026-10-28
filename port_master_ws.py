#!/usr/bin/env python3
"""
Port true widescreen (HUD) from ctr-native-master to nhanced.
Based on the Widescreen_Compress* approach.
"""
import os, sys, argparse, subprocess, re

def git(*args):
    return subprocess.run(['git'] + list(args), capture_output=True, text=True)

def load(path):
    with open(path, 'rb') as f:
        raw = f.read()
    eol = b'\r\n' if b'\r\n' in raw else b'\n'
    return raw.replace(b'\r\n', b'\n').decode('utf-8'), eol

def save(path, content, eol):
    with open(path, 'wb') as f:
        f.write(content.encode('utf-8').replace(b'\n', eol))

def repl_once(content, old, new, label, results):
    if new.strip() and new.strip() in content:
        results.append((label, 'skip', 'already applied'))
        return content
    if old not in content:
        results.append((label, 'fail', f'anchor not found'))
        return content
    if content.count(old) != 1:
        results.append((label, 'fail', f'{content.count(old)} matches'))
        return content
    results.append((label, 'ok', 'replaced'))
    return content.replace(old, new, 1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    if not os.path.isfile('game/DecalHUD.c'):
        print('ERROR: run from nhanced repo root')
        sys.exit(1)

    results = []

    # 1. Create include/widescreen.h
    ws_h = '''#ifndef WIDESCREEN_H
#define WIDESCREEN_H

int Widescreen_GetFactor(void);
int Widescreen_XShift(int width);

void Widescreen_CompressFT4(POLY_FT4 *p);
void Widescreen_CompressGT4(POLY_GT4 *p);
void Widescreen_CompressGT4Scaled(POLY_GT4 *p, int unscaledWidth, int scale);
void Widescreen_CompressNative(PolyFT4 *p);

#endif
'''
    if os.path.isfile('include/widescreen.h'):
        results.append(('include/widescreen.h', 'skip', 'exists'))
    else:
        results.append(('include/widescreen.h', 'ok', 'created'))
        if args.apply:
            with open('include/widescreen.h', 'w', encoding='utf-8', newline='\n') as f:
                f.write(ws_h)

    # 2. Create game/widescreen.c
    ws_c = '''#include <common.h>
#include <platform/native_renderer.h>

int Widescreen_GetFactor(void)
{
        return NativeRenderer_GetWidescreen() ? 750 : 1000; // 16:9 vs 4:3
}

int Widescreen_XShift(int width)
{
        const int factor = Widescreen_GetFactor();
        if (factor == 1000) return 0;
        return (width * (1000 - factor)) / 2000;
}

void Widescreen_CompressFT4(POLY_FT4 *p)
{
        int len = Widescreen_XShift(p->x1 - p->x0);
        p->x0 += len; p->x2 += len; p->x1 -= len; p->x3 -= len;
}

void Widescreen_CompressGT4(POLY_GT4 *p)
{
        int len = Widescreen_XShift(p->x1 - p->x0);
        p->x0 += len; p->x2 += len; p->x1 -= len; p->x3 -= len;
}

void Widescreen_CompressGT4Scaled(POLY_GT4 *p, int unscaledWidth, int scale)
{
        const int factor = Widescreen_GetFactor();
        if (scale <= 0 || scale >= FP(1.0) || factor == 1000) {
                Widescreen_CompressGT4(p); return;
        }
        const s64 divisor = (s64)FP(1.0) * 1000;
        const int width = ((s64)unscaledWidth * scale * factor + divisor / 2) / divisor;
        const int left = p->x0 + (p->x1 - p->x0 - width) / 2;
        p->x0 = p->x2 = left;
        p->x1 = p->x3 = left + width;
}

void Widescreen_CompressNative(PolyFT4 *p)
{
        int w = p->v[1].pos.x - p->v[0].pos.x;
        int len = Widescreen_XShift(w);
        p->v[0].pos.x += len; p->v[2].pos.x += len;
        p->v[1].pos.x -= len; p->v[3].pos.x -= len;
}
'''
    if os.path.isfile('game/widescreen.c'):
        results.append(('game/widescreen.c', 'skip', 'exists'))
    else:
        results.append(('game/widescreen.c', 'ok', 'created'))
        if args.apply:
            with open('game/widescreen.c', 'w', encoding='utf-8', newline='\n') as f:
                f.write(ws_c)

    # 3. Add to game/game_unity.h
    p_unity = 'game/game_unity.h'
    if os.path.isfile(p_unity):
        c, eol = load(p_unity)
        orig = c
        c = repl_once(c, '#include "native_graphics.c"', 
                      '#include "native_graphics.c"\n#include "widescreen.c"', 
                      'game_unity.h: add widescreen.c', results)
        if args.apply and c != orig:
            save(p_unity, c, eol)

    # 4. Modify game/DecalHUD.c
    p_decal = 'game/DecalHUD.c'
    c, eol = load(p_decal)
    orig = c
    # Add include
    if '#include <widescreen.h>' not in c:
        c = repl_once(c, '#include <common.h>', '#include <common.h>\n#include <widescreen.h>', 'DecalHUD.c: include', results)
    
    # Inject DecalHUD_DrawWeapon rot == 0...
    # The exact block from master:
    c = repl_once(c, 
        '''        if (rot == 0)
        {
          Widescreen_CompressFT4(p);
        }
        else if (rot == 1)
        {
          len = Widescreen_XShift(p->x2 - p->x0);
          p->x0 += len;
          p->x1 += len;
          p->x2 -= len;
          p->x3 -= len;
        }''', 
        '''        if (rot == 0)
        {
          Widescreen_CompressFT4(p);
        }
        else if (rot == 1)
        {
          len = Widescreen_XShift(p->x2 - p->x0);
          p->x0 += len;
          p->x1 += len;
          p->x2 -= len;
          p->x3 -= len;
        }''', 'DecalHUD.c: rot block', results)

    # Wait, if it's already there, my script skips. Since nhanced doesn't have it, we have to inject.
    # Let's just do a simple replacement for the specific exact lines from master.

    # Let's inject directly before p->tag = *ot | 0x09000000; for the first function
    c = repl_once(c, 
        'Widescreen_CompressFT4(p);\n        p->tag = *ot | 0x09000000;', 
        'Widescreen_CompressFT4(p);\n        p->tag = *ot | 0x09000000;', 
        'DecalHUD.c: FT4 call 1', results)

    # Actually, let's just find the missing parts and insert them.
    # Let's just do a generic search/replace based on what master had.
    
    if 'Widescreen_CompressFT4(p);' not in c:
        # Try to find the block where it sets x0..x3 and then tag
        pattern = re.compile(r'(CtrGpu_WritePackedXY\(&p->x3,.*?\);\s*)(p->tag = \*ot \| 0x09000000;)', re.MULTILINE)
        c = pattern.sub(r'\1Widescreen_CompressFT4(p);\n        \2', c)
        results.append(('DecalHUD.c: FT4 call 1', 'ok', 'injected via regex'))

    # Let's do the GT4Scaled
    if 'Widescreen_CompressGT4Scaled' not in c:
        pattern = re.compile(r'(CtrGpu_WritePackedXY\(&p->x3, xy3\);\s*)(CtrGpu_WriteColorCode)', re.MULTILINE)
        c = pattern.sub(r'\1Widescreen_CompressGT4Scaled(p, (uv1 & 0xff) - (uv0 & 0xff), scale);\n        \2', c)
        results.append(('DecalHUD.c: GT4Scaled', 'ok', 'injected via regex'))

    if args.apply and c != orig:
        save(p_decal, c, eol)

    # 5. Modify game/UI/UI_Icon.c
    p_icon = 'game/UI/UI_Icon.c'
    c, eol = load(p_icon)
    orig = c
    if '#include <widescreen.h>' not in c:
        c = repl_once(c, '#include <common.h>', '#include <common.h>\n#include <widescreen.h>', 'UI_Icon.c: include', results)

    if 'Widescreen_CompressGT4' not in c:
        pattern = re.compile(r'(\s*Widescreen_CompressGT4\(p\);)?\s*(CtrGpu_WriteColorCode|setPolyGT4\(p\);)', re.MULTILINE)
        # Just insert before setPolyGT4
        c = repl_once(c, 'setPolyGT4(p);', 'Widescreen_CompressGT4(p);\n                setPolyGT4(p);', 'UI_Icon.c: CompressGT4', results)

    if 'Widescreen_CompressNative' not in c:
        c = repl_once(c, 'p->polyClut.self = icon->texLayout.clut;', 'Widescreen_CompressNative(p);\n        p->polyClut.self = icon->texLayout.clut;', 'UI_Icon.c: CompressNative', results)

    if args.apply and c != orig:
        save(p_icon, c, eol)

    # Report
    print(f"=== {'APPLY' if args.apply else 'CHECK'} ===")
    for desc, st, det in results:
        print(f"[{st:4}] {desc}  ({det})")

if __name__ == '__main__':
    main()