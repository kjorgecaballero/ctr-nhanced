#!/usr/bin/env python3
"""
1. Fix SetPsyXUiSafeArea macro (no .tag.code).
2. Inject debug prints.
3. Build.
4. Launch game (user closes it manually).
5. Restore source.
6. Print diagnostic log.
"""
import os, sys, subprocess, re

def run(cmd):
    print(f"$ {cmd}")
    return subprocess.run(cmd, shell=True)

def patch_libgpu(path):
    """Fix SetPsyXUiSafeArea. Returns original content for restore."""
    with open(path, 'r', encoding='utf-8') as f:
        original = f.read()

    # Locate the current macro (from fix_ui_safe.py)
    pattern = re.compile(
        r'#define\s+SetPsyXUiSafeArea\(p, enable\)[\s\S]*?\}\s*\n',
        re.MULTILINE
    )
    replacement = '''#define SetPsyXUiSafeArea(p, enable)             \\
        do {                                     \\
                DR_PSYX_UI_SAFE* _sfSafe = (DR_PSYX_UI_SAFE*)(p); \\
                P_TAG* _sfTag = (P_TAG*)(p);     \\
                _sfSafe->code = ((enable) ? 1 : 0); \\
                _sfTag->code = (_sfTag->code & ~0x0F) | 0x03; \\
                _sfTag->len = 1;                 \\
                (p) += sizeof(DR_PSYX_UI_SAFE);  \\
        } while (0)
'''
    new_content, count = pattern.subn(replacement, original)
    if count == 0:
        print("ERROR: SetPsyXUiSafeArea macro not found in libgpu.h")
        sys.exit(1)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f"[fixed] {path}")
    return original

def patch_gpu_debug(path):
    """Inject debug prints in native_gpu.c."""
    with open(path, 'r', encoding='utf-8') as f:
        original = f.read()

    # Debug in case 0x03
    old_case = re.compile(
        r'(case 0x03:\s*\{[\s\S]*?s_gpu\.widescreenUiSafeArea\s*=\s*\(uiSafe->code\s*&\s*1\)\s*!=\s*0;\s*)return 1;',
        re.MULTILINE
    )
    def repl_case(m):
        return m.group(1) + 'fprintf(stderr, "[UI_SAFE] flag=%d\\n", s_gpu.widescreenUiSafeArea);\n                return 1;'
    new_content, count = old_case.subn(repl_case, original)
    if count == 0:
        print("ERROR: case 0x03 block not found in native_gpu.c")
        sys.exit(1)

    # Debug in Apply function
    apply_pattern = re.compile(
        r'(internal void NativeGpu_ApplyWidescreenUiSafeArea\(GrVertex \*vertex, int count\)\s*\{\s*)if \(!s_gpu\.widescreenUiSafeArea',
        re.MULTILINE
    )
    new_content2, count2 = apply_pattern.subn(
        r'\1if (!s_gpu.widescreenUiSafeArea || !NativeRenderer_GetWidescreen() || count <= 0) { fprintf(stderr, "[UI_SAFE_APPLY] skip flag=%d ws=%d\\n", s_gpu.widescreenUiSafeArea, NativeRenderer_GetWidescreen()); return; }\n        { static int _s_dbg_ok=0; if (_s_dbg_ok++ < 20) fprintf(stderr, "[UI_SAFE_APPLY] OK count=%d\\n", count); }\n        if (0 && !s_gpu.widescreenUiSafeArea',
        new_content
    )
    if count2 == 0:
        print("WARNING: could not inject apply debug (continuing without)")
        new_content2 = new_content
    else:
        new_content2 = new_content2

    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content2)
    print(f"[debug injected] {path}")
    return original

def main():
    if not os.path.isfile('platform/native_gpu.c'):
        print('ERROR: run from nhanced repo root')
        sys.exit(1)

    libgpu_orig = patch_libgpu('include/psx/libgpu.h')
    gpu_orig = patch_gpu_debug('platform/native_gpu.c')

    print("\n=== Building ===")
    run("rm -f build-msvc-x86/*.obj")
    build = run("cmake --build build-msvc-x86 --config Release")
    if build.returncode != 0:
        print("Build FAILED. Restoring...")
        with open('include/psx/libgpu.h', 'w', encoding='utf-8') as f: f.write(libgpu_orig)
        with open('platform/native_gpu.c', 'w', encoding='utf-8') as f: f.write(gpu_orig)
        sys.exit(1)

    print("\n=== Launching Game ===")
    print("Entrá a 1P Crash Cove (16:9), mirá el HUD, CERRÁ el juego.")
    run("./ctr_native.exe 2> ui_safe_test.log")

    print("\n=== Restoring Source ===")
    with open('include/psx/libgpu.h', 'w', encoding='utf-8') as f: f.write(libgpu_orig)
    with open('platform/native_gpu.c', 'w', encoding='utf-8') as f: f.write(gpu_orig)

    print("\n=== Diagnostic Log ===")
    run("grep -E \"UI_SAFE|UI_SAFE_APPLY\" ui_safe_test.log | head -40")
    print("\nDone.")

if __name__ == '__main__':
    main()