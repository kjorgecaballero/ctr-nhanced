#!/usr/bin/env python3
import os, re

path = 'game/RenderLevel/RenderLists.c'
if not os.path.isfile(path):
    print('ERROR: run from nhanced repo root')
    exit(1)

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add include
if '#include <platform/native_renderer.h>' not in content:
    content = content.replace('#include <common.h>', '#include <common.h>\n#include <platform/native_renderer.h>', 1)
    print('[OK] include agregado')

# Inject bypass in RenderLists_IsVisible
# We need to find the function body
func_match = re.search(r'static int RenderLists_IsVisible\([^)]*\)\s*\{', content)
if not func_match:
    print('[FAIL] no se encontró RenderLists_IsVisible')
    exit(1)

if 'NativeRenderer_GetWidescreen()' in content[func_match.start():func_match.end()+300]:
    print('[SKIP] ya está parcheado')
    exit(0)

insert_pos = func_match.end()
injection = '''
        // [WIDESCREEN] Bypass BSP culling. Let the near clipper handle it.
        if (NativeRenderer_GetWidescreen())
        {
                return 1;
        }
'''
content = content[:insert_pos] + injection + content[insert_pos:]

with open(path, 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)
print('[OK] RenderLists_IsVisible parcheado')

# Verify
with open(path, 'r') as f:
    check = f.read()
print(f'Braces: {check.count("{")} opens, {check.count("}")} closes')