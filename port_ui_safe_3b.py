#!/usr/bin/env python3
"""
Port UI Safe Area emission (Commit 3b).
Run from nhanced repo root:
    python port_ui_safe_3b.py --check
    python port_ui_safe_3b.py --apply
Rollback:
    git checkout -- platform/native_gpu.c include/platform/native_gpu.h game/UI/UI_RenderFrame.c game/MAIN/MainFrame_RenderFrame.c
"""
import os, sys, argparse, subprocess

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

def repl_once(content, old, new, label):
    if new.strip() and new.strip() in content:
        return content, 'skip', 'already applied'
    if old not in content:
        return content, 'fail', f'anchor not found: {label}'
    if content.count(old) != 1:
        return content, 'fail', f'{content.count(old)} matches for {label}'
    return content.replace(old, new, 1), 'ok', 'replaced'

def insert_after_line(content, needle, new_lines, label):
    if new_lines.strip() and new_lines.strip() in content:
        return content, 'skip', 'already applied'
    pos = 0
    while pos < len(content):
        end = content.find('\n', pos)
        if end < 0: end = len(content)
        if needle in content[pos:end]:
            return content[:end+1] + new_lines + content[end+1:], 'ok', 'inserted'
        pos = end + 1
    return content, 'fail', f'anchor not found: {needle}'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()

    if not os.path.isfile('platform/native_gpu.c'):
        print('ERROR: run from nhanced repo root')
        sys.exit(1)

    results = []

    # ========== File 1: native_gpu.c ==========
    f1 = 'platform/native_gpu.c'
    c1, eol1 = load(f1)
    orig1 = c1
    r1 = []

    # Add reset function right after the apply function
    c1, s, d = insert_after_line(c1,
        'void MakeLineArray(GrVertex *vertex, VERTTYPE *p0, VERTTYPE *p1)',
        '''void NativeGpu_ResetWidescreenUiSafeArea(void)
{
        s_gpu.widescreenUiSafeArea = 0;
}

''', 'native_gpu.c: + reset function')
    # insert_after_line inserts after the line containing MakeLineArray, which is `void MakeLineArray(...) {`
    # Actually we want to insert BEFORE MakeLineArray. Let's use repl_once instead.
    r1.append(('reset function (via insert)', s, d))
    # Undo if it went to the wrong place: fallback to repl_once
    # Let's just redo it cleanly.

    # Reload and use repl_once
    c1, eol1 = load(f1)
    orig1 = c1
    r1 = []

    c1, s, d = repl_once(c1,
        'void MakeLineArray(GrVertex *vertex, VERTTYPE *p0, VERTTYPE *p1)\n{',
        '''void NativeGpu_ResetWidescreenUiSafeArea(void)
{
        s_gpu.widescreenUiSafeArea = 0;
}

void MakeLineArray(GrVertex *vertex, VERTTYPE *p0, VERTTYPE *p1)
{''', 'native_gpu.c: + reset function')
    r1.append(('reset function', s, d))

    f1h = 'include/platform/native_gpu.h'
    if os.path.isfile(f1h):
        c1h, eol1h = load(f1h)
        orig1h = c1h
        c1h, s, d = repl_once(c1h,
            'void NativeGpu_RegisterCustomTexture',
            'void NativeGpu_ResetWidescreenUiSafeArea(void);\nvoid NativeGpu_RegisterCustomTexture',
            'native_gpu.h: + reset prototype')
        r1.append(('reset prototype', s, d))
    else:
        c1h, eol1h, orig1h = None, None, None
        r1.append(('reset prototype', 'skip', 'native_gpu.h not found'))

    # ========== File 2: UI_RenderFrame.c ==========
    f2 = 'game/UI/UI_RenderFrame.c'
    c2, eol2 = load(f2)
    orig2 = c2
    r2 = []

    # Add macro after includes
    c2, s, d = insert_after_line(c2,
        '#include <platform/native_renderer.h>',
        '''
#define EMIT_UI_SAFE_AREA(enable) do { \\
    u32 *primptr = gGT->backBuffer->primMem.cursor; \\
    SetPsyXUiSafeArea(primptr, enable); \\
    AddPrim(&gGT->pushBuffer_UI.ptrOT[0], (P_TAG*)((u8*)primptr - sizeof(DR_PSYX_UI_SAFE))); \\
    gGT->backBuffer->primMem.cursor = primptr; \\
} while (0)
''', 'UI_RenderFrame.c: + macro')
    r2.append(('EMIT_UI_SAFE_AREA macro', s, d))

    # Racing
    c2, s, d = repl_once(c2,
        'void UI_RenderFrame_Racing()\n{',
        'void UI_RenderFrame_Racing()\n{\n        /* UI safe area marker (widescreen) */\n        EMIT_UI_SAFE_AREA(1);',
        'Racing')
    r2.append(('Racing ON', s, d))

    # CrystChall
    c2, s, d = repl_once(c2,
        'void UI_RenderFrame_CrystChall(void)\n{',
        'void UI_RenderFrame_CrystChall(void)\n{\n        /* UI safe area marker (widescreen) */\n        EMIT_UI_SAFE_AREA(1);',
        'CrystChall')
    r2.append(('CrystChall ON', s, d))

    # AdvHub
    c2, s, d = repl_once(c2,
        'void UI_RenderFrame_AdvHub(void)\n{',
        'void UI_RenderFrame_AdvHub(void)\n{\n        /* UI safe area marker (widescreen) */\n        EMIT_UI_SAFE_AREA(1);',
        'AdvHub')
    r2.append(('AdvHub ON', s, d))

    # ========== File 3: MainFrame_RenderFrame.c ==========
    f3 = 'game/MAIN/MainFrame_RenderFrame.c'
    c3, eol3 = load(f3)
    orig3 = c3
    r3 = []

    # Reset before RenderAllLevelGeometry
    c3, s, d = repl_once(c3,
        'RenderAllLevelGeometry(gGT, lev, ptr_mesh_info);',
        'NativeGpu_ResetWidescreenUiSafeArea();\n                                RenderAllLevelGeometry(gGT, lev, ptr_mesh_info);',
        'reset before 3D')
    r3.append(('reset before 3D', s, d))

    # ========== Report ==========
    mode = 'CHECK' if args.check else ('APPLY' if args.apply else 'DRY-RUN')
    print(f'=== mode: {mode} ===')
    for title, items in [(f1, r1), (f1h if c1h is not None else '(skip)', r1), (f2, r2), (f3, r3)]:
        if title == '(skip)': continue
        print(f'--- {title} ---')
        for desc, st, det in items:
            print(f'[{st:4}] {desc}  ({det})')
    
    fails = [x for x in (r1 + r2 + r3) if x[1] == 'fail']
    if fails:
        print(f'!!! {len(fails)} failure(s). Not applying.')
        sys.exit(1)

    if mode == 'APPLY':
        changed = []
        if c1 != orig1: save(f1, c1, eol1); changed.append(f1)
        if c1h is not None and c1h != orig1h: save(f1h, c1h, eol1h); changed.append(f1h)
        if c2 != orig2: save(f2, c2, eol2); changed.append(f2)
        if c3 != orig3: save(f3, c3, eol3); changed.append(f3)
        for f in changed:
            print('Applied:', f)
        if changed:
            print(git('diff', '--stat').stdout)
        else:
            print('Nothing to change.')

if __name__ == '__main__':
    main()