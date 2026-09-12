#!/bin/bash
# build_racer.sh <source_mesh.json> <internal_name> <folder_name>
#
# Examples:
#   ./build_racer.sh source_mesh_rusty.json tiny rusty
#   ./build_racer.sh source_mesh_bignorm.json cortex big_norm

set -e

if [ $# -lt 3 ]; then
    echo "Usage: $0 <source_mesh.json> <internal_name> <folder_name>"
    echo "Example: $0 source_mesh_rusty.json tiny rusty"
    exit 1
fi

SOURCE_MESH="$1"
INTERNAL_NAME="$2"
FOLDER_NAME="$3"

WORKSPACE="/d/Users/Kevin/Downloads/ZIGGYEXAMPLE/rusty_export"
NHANCED_RACERS="/c/Users/Kevin/Desktop/Kevin/CTR/native_fork/nhanced/assets/mods/racers"

cd "$WORKSPACE"

echo "==============================================="
echo "Building: $FOLDER_NAME (internal: $INTERNAL_NAME)"
echo "Source:   $SOURCE_MESH"
echo "==============================================="

# Step 1 - Build the .ctr
echo "[1/4] Building model.ctr..."
python build_character.py "$SOURCE_MESH" "$INTERNAL_NAME" "model.ctr"

# Step 2 - Build the VRM
echo "[2/4] Building textures.vrm..."
python make_racer_vrm.py texture_uploads.json textures.vrm

# Step 3 - Copy to nhanced assets
echo "[3/4] Copying to nhanced..."
mkdir -p "$NHANCED_RACERS/$FOLDER_NAME"
cp model.ctr "$NHANCED_RACERS/$FOLDER_NAME/model.ctr"
cp textures.vrm "$NHANCED_RACERS/$FOLDER_NAME/textures.vrm"

# Step 4 - Show result
echo "[4/4] Done."
ls -la "$NHANCED_RACERS/$FOLDER_NAME/"
echo ""