#!/bin/bash
# Build script for Cython extensions

set -e

echo "Building Cython extensions for Cymbal Airborne Gimbal Control System..."

# Check for a C compiler
if ! command -v gcc &>/dev/null && ! command -v cc &>/dev/null; then
    echo "Error: no C compiler found (gcc or cc required)." >&2
    echo "  On Ubuntu/Debian: sudo apt install build-essential" >&2
    echo "  On RHEL/Fedora:   sudo dnf install gcc" >&2
    echo "  On macOS:         xcode-select --install" >&2
    exit 1
fi
CC_BIN=$(command -v gcc || command -v cc)
echo "C compiler: $CC_BIN ($(${CC_BIN} --version 2>&1 | head -1))"

# Install build dependencies
echo "Installing build dependencies..."
pip install -q Cython setuptools wheel

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf build/ dist/ *.egg-info
find . -name "*.so" -delete
find . -name "*.c" -delete
find . -name "*.cpp" -delete

# Build Cython extensions
echo "Building Cython extensions..."
python setup.py build_ext --inplace

echo "Build complete! Cython extensions have been compiled."
echo ""
echo "To install the package, run:"
echo "  pip install -e ."
