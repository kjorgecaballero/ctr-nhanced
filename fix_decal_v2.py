#!/usr/bin/env python3
import os, subprocess

print("=== Revirtiendo DecalHUD.c ===")
subprocess.run('git checkout -- game/DecalHUD.c', shell=True)

path = 'game/DecalHUD.c'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Include
if '#include <widescreen.h>' not in content:
    content = content.replace('#include <common.h>',
                              '#include <common.h>\n#include <widescreen.h>', 1)
    print('[OK] include')

# 1. Posición de la función DecalHUD_DrawPolyGT4
func_idx = content.find('void DecalHUD_DrawPolyGT4')
if func_idx == -1:
    print('[FAIL] no se encontró DecalHUD_DrawPolyGT4')
    exit(1)
print(f'[OK] DecalHUD_DrawPolyGT4 en offset {func_idx}')

# 2. Buscar setIconUV SOLO después de func_idx
search_start = func_idx
idx = content.find('setIconUV(p, icon);', search_start)
if idx == -1:
    print('[FAIL] setIconUV no encontrado en DecalHUD_DrawPolyGT4')
    print('Pegame: sed -n "/void DecalHUD_DrawPolyGT4/,/^}/p" game/DecalHUD.c')
    exit(1)
print(f'[OK] setIconUV en offset {idx}')

# 3. Fin de la línea
eol = content.find('\n', idx)
if eol == -1:
    print('[FAIL] sin newline')
    exit(1)

# 4. Indent de la línea
line_start = content.rfind('\n', 0, idx) + 1
indent = content[line_start:idx]

# 5. Inyectar
injection = (
    '\n' + indent + '// [WIDESCREEN] Compress glyph width so the 16:9 viewport' +
    '\n' + indent + '// stretches it back to its original size (matches master).' +
    '\n' + indent + 'if (scale > 0)' +
    '\n' + indent + '{' +
    '\n' + indent + '\tWidescreen_CompressGT4Scaled(p, (s32)width, scale);' +
    '\n' + indent + '}'
)

content = content[:eol+1] + injection + content[eol+1:]

with open(path, 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)
print('[OK] inyectado')

# 6. Verificar braces
opens = content.count('{')
closes = content.count('}')
print(f'Braces: {opens} opens, {closes} closes')
if opens != closes:
    print('[WARN] braces desbalanceados — puede que el build falle')

# 7. Verificación
with open(path, 'r') as f:
    check = f.read()
m = check.find('void DecalHUD_DrawPolyGT4')
end = check.find('primMem->cursor = p + 1;', m)
print()
print("=== SECCIÓN MODIFICADA ===")
print(check[m:end+30])