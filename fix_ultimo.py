#!/usr/bin/env python3
import os, re

def main():
    # ---------------------------------------------------------
    # 1. DECALFONT.C (Arreglar el Timer y el 1/3 como Reload)
    # ---------------------------------------------------------
    p_font = 'game/DecalFont.c'
    with open(p_font, 'r', encoding='utf-8') as f: c = f.read()
    
    if '#include <widescreen.h>' not in c:
        c = c.replace('#include <common.h>', '#include <common.h>\n#include <widescreen.h>', 1)

    # Escalar el ancho de la letra en GetLineWidthStrlen
    old_width = 'font_charPixWidth = data.font_charPixWidth[fontType];\n\tfont_buttonPixWidth = data.font_buttonPixWidth[fontType];\n\tfont_puncPixWidth = data.font_puncPixWidth[fontType];'
    new_width = old_width + '\n\tif (Widescreen_HudActive()) {\n\t\tfont_charPixWidth = (s16)(font_charPixWidth * Widescreen_GetFactor() / 1000);\n\t\tfont_buttonPixWidth = (s16)(font_buttonPixWidth * Widescreen_GetFactor() / 1000);\n\t\tfont_puncPixWidth = (s16)(font_puncPixWidth * Widescreen_GetFactor() / 1000);\n\t}'
    
    if old_width in c:
        c = c.replace(old_width, new_width, 1)
    else:
        # Fallback por si los tabs varían
        c = re.sub(r'(font_charPixWidth\s*=\s*data\.font_charPixWidth\[fontType\];[\s\S]*?font_puncPixWidth\s*=\s*data\.font_puncPixWidth\[fontType\];)', r'\1\n\tif (Widescreen_HudActive()) {\n\t\tfont_charPixWidth = (s16)(font_charPixWidth * Widescreen_GetFactor() / 1000);\n\t\tfont_buttonPixWidth = (s16)(font_buttonPixWidth * Widescreen_GetFactor() / 1000);\n\t\tfont_puncPixWidth = (s16)(font_puncPixWidth * Widescreen_GetFactor() / 1000);\n\t}', c)

    # Escalar charWidth e iconScale en DrawLineStrlen
    old_char = 's16 charWidth = data.font_charPixWidth[fontType];'
    new_char = old_char + '\n\t\tif (Widescreen_HudActive()) charWidth = (s16)(charWidth * Widescreen_GetFactor() / 1000);'
    c = c.replace(old_char, new_char, 1)

    old_icon = 's16 iconScale = FP(1.0);'
    new_icon = old_icon + '\n\t\tif (Widescreen_HudActive()) iconScale = (s16)(iconScale * Widescreen_GetFactor() / 1000);'
    c = c.replace(old_icon, new_icon, 1)

    with open(p_font, 'w', encoding='utf-8', newline='\n') as f: f.write(c)
    print('[OK] DecalFont.c: Texto y espaciado escalados como Reload')

    # ---------------------------------------------------------
    # 2. UI_ICON.C (Arreglar los Íconos de Rank y el Ancla del Sol)
    # ---------------------------------------------------------
    p_icon = 'game/UI/UI_Icon.c'
    with open(p_icon, 'r', encoding='utf-8') as f: c = f.read()
    
    if '#include <widescreen.h>' not in c:
        c = c.replace('#include <common.h>', '#include <common.h>\n#include <widescreen.h>', 1)

    # A. Íconos de Rank (UI_DrawDriverIcon)
    # Buscamos la función y le inyectamos la compresión justo antes de AddPrimitive
    if 'void UI_DrawDriverIcon' in c and 'Widescreen_CompressNative(p);' not in c:
        c = c.replace('AddPrimitive(p, ot);', 'if (Widescreen_HudActive()) Widescreen_CompressNative(p);\n        AddPrimitive(p, ot);', 1)
        print('[OK] UI_Icon.c: Íconos de Rank comprimidos')

    # B. El Sol (UI_WeaponBG_DrawShine)
    # Cambiamos el ancla de "rightX" al centro real del Sol (posX + widthOffset)
    if 'Widescreen_ScaleAbout(posX + widthOffset' not in c:
        c = c.replace('Widescreen_ScaleAbout(rightX, posX)', 'Widescreen_ScaleAbout(posX + widthOffset, posX)')
        c = c.replace('Widescreen_ScaleAbout(rightX, altX)', 'Widescreen_ScaleAbout(posX + widthOffset, altX)')
        c = c.replace('Widescreen_ScaleAbout(rightX, rightX)', 'Widescreen_ScaleAbout(posX + widthOffset, rightX)')
        c = c.replace('Widescreen_ScaleAbout(rightX, leftX)', 'Widescreen_ScaleAbout(posX + widthOffset, leftX)')
        print('[OK] UI_Icon.c: Sol anclado al centro correcto')

    with open(p_icon, 'w', encoding='utf-8', newline='\n') as f: f.write(c)

if __name__ == '__main__':
    main()