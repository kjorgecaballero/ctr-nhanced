#!/usr/bin/env python3
import os, re

def patch(path, old, new, label):
    if not os.path.isfile(path):
        print(f'[SKIP] {path} not found'); return
    with open(path, 'r', encoding='utf-8') as f: c = f.read()
    if new in c: print(f'[SKIP] {label}'); return
    if old not in c: print(f'[FAIL] {label}: anchor not found'); return
    c = c.replace(old, new, 1)
    with open(path, 'w', encoding='utf-8', newline='\n') as f: f.write(c)
    print(f'[OK] {label}')

# 1. Widescreen_GetFactor - ¿se llama? ¿qué retorna?
patch('game/widescreen.c',
'''int Widescreen_GetFactor(void)
{
        return NativeRenderer_GetWidescreen() ? 750 : 1000; // 16:9 vs 4:3
}''',
'''int Widescreen_GetFactor(void)
{
        static int s_dbg = 0;
        int v = NativeRenderer_GetWidescreen() ? 750 : 1000;
        if (s_dbg++ < 20) fprintf(stderr, "[DBG_FACTOR] v=%d ws=%d\\n", v, NativeRenderer_GetWidescreen());
        return v;
}''', 'Widescreen_GetFactor')

# 2. NativeRenderer_GetWidescreen - ¿retorna 0 o 1?
patch('platform/native_renderer.c',
'''int NativeRenderer_GetWidescreen(void)
{
    return s_widescreen;
}''',
'''int NativeRenderer_GetWidescreen(void)
{
    static int s_dbg2 = 0;
    if (s_dbg2++ < 10) fprintf(stderr, "[DBG_GETWS] s_widescreen=%d\\n", s_widescreen);
    return s_widescreen;
}''', 'NativeRenderer_GetWidescreen')

# 3. DecalHUD_DrawPolyGT4 - ¿se llama? ¿qué ancho tiene?
path = 'game/DecalHUD.c'
with open(path, 'r') as f: c = f.read()
if 'DBG_GT4' not in c:
    m = re.search(r'(void DecalHUD_DrawPolyGT4\s*\([^)]*\)\s*\{[\s\S]*?)(primMem->cursor = p \+ 1;)', c)
    if m:
        new = m.group(1) + '''{
                static int s_dbg3 = 0;
                if (s_dbg3++ < 20) fprintf(stderr, "[DBG_GT4] width=%d ws=%d\\n", (int)(p->x1 - p->x0), NativeRenderer_GetWidescreen());
        }
        ''' + m.group(2)
        c = c.replace(m.group(0), new, 1)
        with open(path, 'w', newline='\n') as f: f.write(c)
        print('[OK] DecalHUD_DrawPolyGT4')
    else:
        print('[FAIL] DecalHUD_DrawPolyGT4: match failed')
else:
    print('[SKIP] DecalHUD_DrawPolyGT4')