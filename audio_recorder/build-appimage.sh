#!/bin/bash
# Build script for creating the AppImage using python-appimage
# Requires: uv, python-appimage

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Building Audio Recorder AppImage ==="

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf AppDir build dist *.AppImage 2>/dev/null || true

# Create a temporary directory for packaging the app module
echo "Preparing application package..."
mkdir -p appimage-build/opt/audio_recorder
cp -r audio_recorder appimage-build/opt/audio_recorder/

# Copy a simple icon (use python-appimage's default icon as placeholder)
PYTHON_APPIMAGE_ICON="$(uv run python -c "import python_appimage; from pathlib import Path; print(Path(python_appimage.__file__).parent / 'data' / 'python.png')")"
cp "$PYTHON_APPIMAGE_ICON" appimage-build/audio-recorder.png

# Create AppImage
echo "Creating AppImage..."
uv run python -m python_appimage build app \
    --linux-tag manylinux2014_x86_64 \
    --python-version 3.12 \
    --name audio-recorder \
    appimage-build

# Clean up temp files
rm -rf appimage-build/opt

echo "=== Build complete ==="
ls -la *.AppImage 2>/dev/null || echo "No AppImage found - check for errors above"
