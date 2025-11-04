#!/bin/bash
# Build script for Cython extensions

set -e

echo "Building Cython extensions for Airborne Gimbal Control System..."

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
