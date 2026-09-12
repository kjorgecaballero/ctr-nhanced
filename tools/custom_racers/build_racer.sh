#!/bin/bash
set -e

if [ $# -lt 3 ]; then
    echo "Usage: $0 <source_mesh.json> <internal_name> <folder_name>"
    exit 1
fi

SOURCE_MESH="$1"
INTERNAL_NAME="$2"
FOLDER_NAME="$3"

WORKSPACE="/d/Users/Kevin/Downloads/ZIGGYEXAMPLE/rusty_export"
NHANCED_RACERS="/c/Users/Kevin/Desktop/Kevin/CTR/native_fork/nhanced/assets/mods/racers"
DEST="$NHANCED_RACERS/$FOLDER_NAME"

cd "$WORKSPACE"

echo "==============================================="
echo "Building: $FOLDER_NAME (internal: $INTERNAL_NAME)"
echo "==============================================="

mkdir -p "$DEST"

for SLOT in 0 1 2 3; do
    echo "[$((SLOT + 1))/6] Building model_p${SLOT}.ctr..."
    python build_character.py "$SOURCE_MESH" "$INTERNAL_NAME" \
        "model_p${SLOT}.ctr" --player_slot "$SLOT"
    cp "model_p${SLOT}.ctr" "$DEST/model_p${SLOT}.ctr"
done

echo "[5/6] Resetting texture_uploads.json to slot 0 base coordinates..."
python build_character.py "$SOURCE_MESH" "$INTERNAL_NAME" \
    "model_p0.ctr" --player_slot 0 > /dev/null

echo "[6/6] Building textures.vrm from base coordinates..."
python make_racer_vrm.py texture_uploads.json textures.vrm
cp textures.vrm "$DEST/textures.vrm"

echo "Done."
ls -la "$DEST/"
echo ""
