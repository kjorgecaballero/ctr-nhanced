#!/usr/bin/env python3
import os, re

path = 'game/DecalFont.c'
if not os.path.isfile(path):
    print('ERROR: run from nhanced repo root')
    exit(1)

with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

if '#include <widescreen.h>' not in c:
    c = c.replace('#include <common.h>', '#include <common.h>\n#include <widescreen.h>', 1)

# 1. Insertar startX al inicio de la función (antes del if de justificación)
old_start = 'struct GameTracker *gGT = sdata->gGT;\n\n\t// text is justified left by default'
new_start = 'struct GameTracker *gGT = sdata->gGT;\n\tint startX = posX;\n\n\t// text is justified left by default'
if old_start in c:
    c = c.replace(old_start, new_start, 1)
    print('[OK] startX insertado')
else:
    print('[FAIL] No se encontró el inicio de la función')

# 2. Escalar alignX
old_align = 'int alignX = DecalFont_GetLineWidthStrlen(str, len, fontType);'
new_align = 'int alignX = DecalFont_GetLineWidthStrlen(str, len, fontType);\n\t\tif (Widescreen_HudActive()) alignX = Widescreen_HudW(alignX);'
if old_align in c:
    c = c.replace(old_align, new_align, 1)
    print('[OK] alignX escalado')

# 3. Escalar drawX (el avance de cada letra)
# El texto exacto tiene tabs y saltos de línea. Usamos regex flexible.
pattern = re.compile(
    r'(DecalHUD_DrawPolyGT4\s*\(iconPtrArray\[iconID\],\s*)(posX \+ pixWidthExtra)',
    re.MULTILINE
)

def repl(m):
    return m.group(1) + 'int drawX = Widescreen_HudActive() ? startX + Widescreen_HudW(posX - startX) : posX;\n\t\t\t\t\t' + m.group(1).split('(')[0] + '(' + m.group(1).split('(')[1] + 'drawX + pixWidthExtra'

# El reemplazo directo es más simple:
old_draw = 'DecalHUD_DrawPolyGT4(iconPtrArray[iconID],'
if old_draw in c:
    c = c.replace(old_draw, 'int drawX = Widescreen_HudActive() ? startX + Widescreen_HudW(posX - startX) : posX;\n\t\t\t\t\t' + old_draw, 1)
    
    # Ahora reemplazar 'posX + pixWidthExtra' con 'drawX + pixWidthExtra' SOLO en la llamada
    # Buscamos el bloque después de DecalHUD_DrawPolyGT4
    idx = c.find(old_draw)
    if idx != -1:
        sub = c[idx:idx+500]
        sub_new = sub.replace('posX + pixWidthExtra', 'drawX + pixWidthExtra', 1)
        c = c[:idx] + sub_new + c[idx+500:]
        print('[OK] drawX aplicado')

with open(path, 'w', encoding='utf-8', newline='\n') as f:
    f.write(c)

print('Guardado game/DecalFont.c')