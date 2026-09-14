#!/usr/bin/env bash
# run_recon.sh — Run blocks 1..14 and save each one to its own .txt file.
# Usage:   bash run_recon.sh
#          REPO=/other/path bash run_recon.sh
# Output:  /c/Users/Kevin/Desktop/Kevin/grep_CL_BASH/output/BLOCK_<n>_<name>.txt

set -u

REPO="${REPO:-$HOME/Desktop/Kevin/CTR/native_fork/nhanced}"
OUT="/c/Users/Kevin/Desktop/Kevin/grep_CL_BASH/output"

mkdir -p "$OUT" || { echo "ERROR: cannot create $OUT"; exit 1; }
cd "$REPO"      || { echo "ERROR: $REPO does not exist"; exit 1; }

echo "REPO = $REPO"
echo "OUT  = $OUT"
echo

run_block () {
  local n="$1"; shift
  local name="$1"; shift
  local outfile="$OUT/BLOCK_${n}_${name}.txt"
  printf '>>> Block %-2s -> %s\n' "$n" "$outfile"
  {
    echo "===== BLOCK $n - $name ====="
    echo "cwd : $(pwd)"
    echo "date: $(date)"
    echo
    "$@"
  } > "$outfile" 2>&1
}

# ---------------------------------------------------------------- BLOCK 1
b1 () {
  pwd; echo
  git remote -v; echo
  git branch --show-current; echo
  git branch -a; echo
  git log --oneline -10; echo
  git status --short
}

# ---------------------------------------------------------------- BLOCK 2
b2 () {
  find . -type f \( -iname "*.ctr" -o -iname "*.vrm" \) -exec ls -la {} \;
  echo "--- assets/mods ---"
  find assets/mods -type f 2>/dev/null | sort
  echo "--- tools/custom_racers ---"
  find tools/custom_racers -type f 2>/dev/null | sort
}

# ---------------------------------------------------------------- BLOCK 3
b3 () {
  echo "--- include/platform/native_custom_racer.h ---"
  cat include/platform/native_custom_racer.h 2>/dev/null
  echo
  echo "--- wc -l platform/native_custom_racer.c ---"
  wc -l platform/native_custom_racer.c 2>/dev/null
  echo "--- first 200 lines of platform/native_custom_racer.c ---"
  sed -n '1,200p' platform/native_custom_racer.c 2>/dev/null
}

# ---------------------------------------------------------------- BLOCK 4
b4 () {
  grep -RIn --include="*.c" "NativeCustomRacer_" game include platform \
    | grep -v "native_custom_racer"
}

# ---------------------------------------------------------------- BLOCK 5
b5 () {
  echo "--- data.MetaDataCharacters[ ---"
  grep -RIn --include="*.c" --include="*.h" "data\.MetaDataCharacters\[" game platform \
    | grep -v "zGlobal_DATA.c"
  echo
  echo "--- MetaDataCharacters[ (without data.) ---"
  grep -RIn --include="*.c" --include="*.h" "MetaDataCharacters\[" game platform include \
    | grep -v "zGlobal_DATA.c"
  echo
  echo "--- GET_METADATA / BSS tables present? ---"
  grep -RIn "GET_METADATA\|s_customMeta\|s_customIcons\|s_customMenuID\|CUSTOM_RACER_ID_BASE\|EXT_ID_BASE" platform include game
}

# ---------------------------------------------------------------- BLOCK 6
b6 () {
  echo "--- Vehicle enum ---"
  sed -n '25,70p' include/namespace_Vehicle.h 2>/dev/null
  echo
  echo "--- engineID values ---"
  grep -RIn "BALANCED\|SPEED\|ACCEL\|TURN" include/namespace_*.h | head -20
  echo
  echo "--- characterIDs[] usages ---"
  grep -RIn --include="*.c" --include="*.h" "characterIDs\[" game include | head -30
}

# ---------------------------------------------------------------- BLOCK 7
b7 () {
  echo "--- MetaDataCHAR ---"
  grep -n "struct MetaDataCHAR" -A 15 include/regionsEXE.h
  echo
  echo "--- Icon / TextureLayout ---"
  sed -n '105,175p' include/namespace_Decal.h 2>/dev/null
  echo
  echo "--- IconGroup ---"
  grep -n "struct IconGroup" -A 20 include/namespace_Decal.h 2>/dev/null
  echo
  echo "--- CharacterSelectMeta ---"
  grep -n "struct CharacterSelectMeta" -A 12 include/ovr_230.h 2>/dev/null
}

# ---------------------------------------------------------------- BLOCK 8
b8 () {
  echo "--- DecalGlobal.c ---"
  cat game/DecalGlobal.c 2>/dev/null
  echo
  echo "--- ptrIcons / iconGroup usages ---"
  grep -RIn --include="*.c" "ptrIcons\[\|iconGroup\[" game | head -40
  echo
  echo "--- ICONGROUP_GETICONS ---"
  grep -RIn "ICONGROUP_GETICONS" game include
}

# ---------------------------------------------------------------- BLOCK 9
b9 () {
  echo "--- MainMain.c ~671 ---"
  sed -n '655,690p' game/MAIN/MainMain.c
  echo
  echo "--- LOAD_Assets.c 90..240 ---"
  sed -n '90,240p' game/LOAD/LOAD_Assets.c
  echo
  echo "--- LOAD_TenStages.c 600..660 ---"
  sed -n '600,660p' game/LOAD/LOAD_TenStages.c
  echo
  echo "--- MM_Characters.c 480..540 ---"
  sed -n '480,540p' game/230/MM_Characters.c
}

# ---------------------------------------------------------------- BLOCK 10
b10 () {
  echo "--- zGlobal_DATA.c 5220..5280 ---"
  sed -n '5220,5280p' game/zGlobal_DATA.c
  echo
  echo "--- D230.c 470..560 ---"
  sed -n '470,560p' game/230/D230.c
  echo
  echo "--- CharacterSelectMeta arrays ---"
  grep -RIn "characterSelectMeta1P2P\|characterSelectMeta3P\|characterSelectMeta4P\|characterSelectMeta1P2PLimited\|characterSelectMetaByLayout" game
  echo
  echo "--- MM_CHARACTER_SELECT_* constants ---"
  grep -RIn "MM_CHARACTER_SELECT_ICON_COUNT\|MM_CHARACTER_SELECT_MAX_PLAYERS\|MM_CHARACTER_SELECT_EXPANSION_ICON_FIRST" game
  echo
  echo "--- characterMenuID ---"
  grep -RIn "characterMenuID" game include
}

# ---------------------------------------------------------------- BLOCK 11
b11 () {
  find assets/mods -type f \( -name "*.json" -o -name "*.ini" -o -name "*.txt" -o -name "*.cfg" \) \
    -exec echo "--- {} ---" \; -exec cat {} \;
}

# ---------------------------------------------------------------- BLOCK 12
b12 () {
  for f in tools/custom_racers/*; do
    [ -f "$f" ] && echo "===== $f =====" && head -40 "$f"
  done
}

# ---------------------------------------------------------------- BLOCK 13
b13 () {
  grep -n "POST_BUILD\|copy\|ctr_native" CMakeLists.txt | head -30
  echo
  ls -la build-msvc-x86/ 2>/dev/null | head
  ls -la ctr_native.exe 2>/dev/null
}

# ---------------------------------------------------------------- BLOCK 14
b14 () {
  grep -n "s_coco\|s_tiny\|s_cortex\|s_crash\|s_ngin\|s_dingo\|s_polar\|s_pura\|s_pinstripe\|s_papu\|s_roo\|s_joe\|s_ntropy\|s_pen\|s_fake\|s_oxide" game/zGlobal_RDATA.c
}

# ---------------------------------------------------------------- RUN
run_block 1  repo_state            b1
run_block 2  assets                b2
run_block 3  api_runtime           b3
run_block 4  native_call_sites     b4
run_block 5  metadata_call_sites   b5
run_block 6  vehicle_enums         b6
run_block 7  structs               b7
run_block 8  icons                 b8
run_block 9  engine_hooks          b9
run_block 10 menu_layouts          b10
run_block 11 roster_mods           b11
run_block 12 custom_racer_tools    b12
run_block 13 cmake_build           b13
run_block 14 debug_names           b14

echo
echo "Done. Files written to:"
echo "  $OUT"
ls -la "$OUT"/BLOCK_*.txt
