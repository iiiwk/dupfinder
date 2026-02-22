#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

BUILD_TYPE="Release"
INSTALL_DIR="$SCRIPT_DIR/install"

if echo "$1" | grep -qi "^debug$"; then
    BUILD_TYPE="Debug"
    INSTALL_DIR="$SCRIPT_DIR/install_debug"
fi

echo "[0/5] Checking dependencies ..."
if ! command -v cmake &>/dev/null; then
    echo "ERROR: cmake not found. Install with: brew install cmake"
    exit 1
fi

if [ "$(uname)" = "Darwin" ]; then
    if ! brew list libomp &>/dev/null; then
        echo "Installing libomp via Homebrew (required for OpenMP on macOS) ..."
        brew install libomp
    fi
    if ! brew list python-tk@3.13 &>/dev/null 2>&1; then
        echo "Installing python-tk via Homebrew (required for GUI) ..."
        brew install python-tk@3.13
    fi
fi

echo "[1/5] Configuring CMake ($BUILD_TYPE) ..."
cmake -B build -DCMAKE_BUILD_TYPE="$BUILD_TYPE" -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR"

echo "[2/5] Building ..."
cmake --build build --config "$BUILD_TYPE" -j "$(sysctl -n hw.logicalcpu 2>/dev/null || nproc 2>/dev/null || echo 4)"

echo "[3/5] Installing to $INSTALL_DIR ..."
cmake --install build --config "$BUILD_TYPE"

echo "[4/5] Setting up Python virtual environment ..."
PYTHON3="$(command -v python3.13 2>/dev/null || command -v python3 2>/dev/null)"
VENV_DIR="$INSTALL_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON3" -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

echo "[5/5] Installing Python dependencies ..."
pip install -r "$INSTALL_DIR/requirements.txt" || echo "WARNING: pip install failed, please run manually"

echo ""
echo "========================================"
echo "  $BUILD_TYPE build complete!"
echo "  Install directory: $INSTALL_DIR"
echo ""
echo "  To run:"
echo "    source \"$VENV_DIR/bin/activate\""
echo "    python3 \"$INSTALL_DIR/dupfinder_ui.py\""
echo "========================================"
