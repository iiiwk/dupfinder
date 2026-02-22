#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

ARCH="$(uname -m)"
RELEASE_NAME="dupfinder-macos-${ARCH}"
DIST_DIR="$SCRIPT_DIR/dist"
CMAKE_BUILD="$SCRIPT_DIR/cmake-build"

echo "============================================"
echo "  DupFinder Release Packager (macOS)"
echo "============================================"

# --- Step 1: Build C++ engine ---
echo ""
echo "[1/4] Building C++ engine ..."
cmake -B "$CMAKE_BUILD" -DCMAKE_BUILD_TYPE=Release
cmake --build "$CMAKE_BUILD" --config Release -j "$(sysctl -n hw.logicalcpu 2>/dev/null || echo 4)"

# --- Step 2: Ensure venv with dependencies ---
echo ""
echo "[2/4] Preparing Python environment ..."
PYTHON3="$(command -v python3.13 2>/dev/null || command -v python3 2>/dev/null)"
if [ ! -d venv ]; then
    "$PYTHON3" -m venv venv
fi
source venv/bin/activate
pip install -q pyinstaller -r requirements.txt

# --- Step 3: PyInstaller bundle ---
echo ""
echo "[3/4] Packaging with PyInstaller ..."
pyinstaller \
    --noconfirm \
    --clean \
    --name dupfinder \
    --windowed \
    --add-data "dupfinder_strings.json:." \
    --add-data "font:font" \
    --collect-all ttkthemes \
    --collect-all sv_ttk \
    --hidden-import send2trash \
    --hidden-import PIL \
    dupfinder_ui.py 2>&1 | tail -5

# --- Step 4: Assemble release ---
echo ""
echo "[4/4] Assembling release package ..."

# Copy C++ engine into the .app bundle
cp "$CMAKE_BUILD/dupfinder_engine" "$DIST_DIR/dupfinder.app/Contents/MacOS/dupfinder_engine"

# Clean up intermediate folder output, keep only .app
rm -rf "$DIST_DIR/dupfinder/" 2>/dev/null

# Create zip containing only the .app
cd "$DIST_DIR"
rm -f "${RELEASE_NAME}.zip"
zip -r -q "${RELEASE_NAME}.zip" "dupfinder.app"

# Clean up intermediate .app (zip is the final product)
rm -rf "$DIST_DIR/dupfinder.app"

echo ""
echo "============================================"
echo "  Release package created:"
echo "  $DIST_DIR/${RELEASE_NAME}.zip"
echo "============================================"
