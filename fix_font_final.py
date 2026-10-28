#!/usr/bin/env python3
"""Fix text stretching in DecalFont.c (nhanced specific)."""
import os, sys, argparse, re

def load(p):
    with open(p, 'rb') as f: raw = f.read()
    eol = b'\r\n' if b'\r\n' in raw else b'\n'
    return raw.replace(b'\r\n', b'\n').decode('utf-8'), eol

def save(p, c, e):
    with open(p, 'wb') as f: f.write(c.encode('utf-8').replace(b'\n', e))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    path = 'game/DecalFont.c'
    if not os.path.isfile(path):
        print('ERROR: run from nhanced repo root'); sys.exit(1)

    c, e = load(path)

    # Anchor: el bloque exacto de la llamada a DecalHUD_DrawPolyGT4
    old = '''				if (iconID < gGT->iconGroup[iconGroupID]->numIcons)
				{
					struct Icon **iconPtrArray = ICONGROUP_GETICONS(gGT->iconGroup[iconGroupID]);

					DecalHUD_DrawPolyGT4(iconPtrArray[iconID],

					                     posX + pixWidthExtra, posY + pixHeightExtra,

					                     &gGT->backBuffer->primMem, gGT->pushBuffer_UI.ptrOT,

					                     ptrColor[0], ptrColor[1], ptrColor[2], ptrColor[3],

					                     0, iconScale);
				}'''

    new = '''				if (iconID < gGT->iconGroup[iconGroupID]->numIcons)
				{
					struct Icon **iconPtrArray = ICONGROUP_GETICONS(gGT->iconGroup[iconGroupID]);

					// [WIDESCREEN] Capture the POLY_GT4 before the call so we
					// can compress it after, mirroring ctr-native-master's
					// per-glyph compression (letters stay original size but
					// appear separated instead of stretched).
					POLY_GT4 *p = (POLY_GT4 *)gGT->backBuffer->primMem.cursor;

					DecalHUD_DrawPolyGT4(iconPtrArray[iconID],

					                     posX + pixWidthExtra, posY + pixHeightExtra,

					                     &gGT->backBuffer->primMem, gGT->pushBuffer_UI.ptrOT,

					                     ptrColor[0], ptrColor[1], ptrColor[2], ptrColor[3],

					                     0, iconScale);

					// Only compress if DecalHUD_DrawPolyGT4 didn't already do it.
					// If the width still equals charWidth, it wasn't compressed.
					if (Widescreen_GetFactor() != 1000 && (p->x1 - p->x0) >= charWidth)
					{
						Widescreen_CompressGT4(p);
					}
				}'''

    if 'Widescreen_CompressGT4(p);' in c:
        print('[skip] DecalFont.c already patched')
        return

    if old not in c:
        print('[fail] Anchor not found. Trying regex fallback...')
        # Regex fallback: capture the entire if-block
        pattern = re.compile(
            r'(\t+if \(iconID < gGT->iconGroup\[iconGroupID\]->numIcons\)\s*\{\s*'
            r'struct Icon \*\*iconPtrArray = ICONGROUP_GETICONS\(gGT->iconGroup\[iconGroupID\]\);\s*'
            r'DecalHUD_DrawPolyGT4\(iconPtrArray\[iconID\],[\s\S]*?0, iconScale\);\s*\})',
            re.MULTILINE
        )
        m = pattern.search(c)
        if not m:
            print('[fail] Regex also failed. Pegame el output de:')
            print('  sed -n "145,165p" game/DecalFont.c')
            return

        # Build replacement from the matched block
        block = m.group(1)
        # Get the indent
        indent = re.match(r'(\t+)', block).group(1)
        sub_indent = indent + '\t'

        # Split at "DecalHUD_DrawPolyGT4"
        parts = block.split('DecalHUD_DrawPolyGT4', 1)
        before_call = parts[0]  # "if (...) { struct Icon **iconPtrArray = ...; "
        call_and_after = 'DecalHUD_DrawPolyGT4' + parts[1]

        new_block = (before_call +
            sub_indent + 'POLY_GT4 *p = (POLY_GT4 *)gGT->backBuffer->primMem.cursor;\n\n' +
            sub_indent + call_and_after[:-1] +  # remove closing brace
            '\n\n' + sub_indent + 'if (Widescreen_GetFactor() != 1000 && (p->x1 - p->x0) >= charWidth)\n' +
            sub_indent + '{\n' +
            sub_indent + '\tWidescreen_CompressGT4(p);\n' +
            sub_indent + '}\n' +
            indent + '}')

        c = c[:m.start(1)] + new_block + c[m.end(1):]
        print('[ok] Patched via regex fallback')
    else:
        c = c.replace(old, new, 1)
        print('[ok] Patched exact anchor')

    if args.apply:
        save(path, c, e)
        print('Saved game/DecalFont.c')
    else:
        print('(dry-run, use --apply to save)')

if __name__ == '__main__':
    main()