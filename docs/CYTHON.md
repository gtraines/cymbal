# Cython Implementation Guide

This project has been rewritten in Cython for improved performance and efficiency. Cython is a superset of Python that compiles to C, providing significant speed improvements while maintaining Python's ease of use.

**All core classes use `cdef class` (extension types) for maximum performance!**

## Overview

All core modules have been converted to Cython (`.pyx` files) with proper Cython syntax:

- `cymbal/camera_gimbal/storm32_controller.pyx` - Storm32bgc camera gimbal controller (`cdef class`)
- `cymbal/spotlight_gimbal/servo_controller.pyx` - Spotlight servo controller (`cdef class`)
- `cymbal/sensors/mpu6050.pyx` - MPU6050 IMU interface (`cdef class`)
- `cymbal/utils/config.pyx` - Configuration management (dataclasses)
- `cymbal/main.pyx` - Main control application (`cdef class`)

## Cython Features Used

### Extension Types (`cdef class`)

All main controller classes are implemented as Cython extension types for optimal performance:

```cython
cdef class Storm32Controller:
    cdef public str port
    cdef public int baudrate
    cdef public double timeout
    cdef object serial_conn
    cdef bint _is_connected
```

### Typed Methods

Methods use `cpdef` for public APIs (callable from Python and Cython) and `cdef` for internal methods:

```cython
cpdef bint connect(self):  # Public method
    """Connect to device"""
    ...

cdef bytes _build_command(self, double angle):  # Private method
    """Build internal command"""
    ...
```

### C Type Declarations

Variables use C types for maximum performance:
- `int` - C integer
- `double` - C double precision float
- `bint` - C boolean
- `cdef` - C-level variable

## Benefits of Cython

1. **Performance**: Compiled C extensions run significantly faster than pure Python
2. **Type Safety**: Type declarations catch errors at compile time
3. **C Integration**: Direct access to C libraries and APIs
4. **Python Compatibility**: Can still be imported and used like regular Python modules
5. **Extension Types**: `cdef class` provides C-level object attributes for speed

## Building from Source

### Prerequisites

Install required build tools:

```bash
# Debian/Ubuntu/Raspberry Pi OS
sudo apt-get install -y build-essential python3-dev

# Install Python dependencies
pip3 install Cython setuptools wheel
```

### Quick Build

Use the provided build script:

```bash
./build_cython.sh
```

This script will:
1. Install Cython and build dependencies
2. Clean previous builds
3. Compile all Cython extensions
4. Create `.so` shared library files

### Manual Build

If you prefer to build manually:

```bash
# Build extensions in-place
python3 setup.py build_ext --inplace

# Or build and install
pip3 install -e .
```

### Build Options

For optimized production builds:

```bash
# Build with optimizations
CFLAGS="-O3 -march=native" python3 setup.py build_ext --inplace

# Build with debugging symbols
CFLAGS="-g" python3 setup.py build_ext --inplace
```

## Installation

### Install from Source

After building the Cython extensions:

```bash
pip3 install -e .
```

### Install from Wheel

To create and install a distributable wheel:

```bash
python3 setup.py bdist_wheel
pip3 install dist/cymbal-*.whl
```

## Usage

The Cython-compiled modules work exactly like the original Python modules:

```python
from cymbal import Storm32Controller, SpotlightController, MPU6050

# Use exactly as before
with Storm32Controller() as camera:
    camera.set_angle(30, 0, 45)

with SpotlightController() as spotlight:
    spotlight.set_position(30, 45)
```

## Compilation Directives

The setup.py includes these Cython compiler directives for optimal performance:

- `language_level: 3` - Use Python 3 semantics
- `embedsignature: True` - Embed function signatures for help()
- `boundscheck: False` - Disable array bounds checking for speed
- `wraparound: False` - Disable negative indexing for speed
- `cdivision: True` - Use C division semantics for speed

## Development

### Modifying Cython Code

1. Edit the `.pyx` files (not `.py` files)
2. Rebuild the extensions:
   ```bash
   python3 setup.py build_ext --inplace
   ```
3. Test your changes

### Debugging

To generate annotated HTML showing Python/C interaction:

```bash
cython -a cymbal/camera_gimbal/storm32_controller.pyx
# Open storm32_controller.html in a browser
```

Yellow highlights indicate Python API calls (slower), white is pure C (faster).

## Performance Considerations

### Speed Improvements

Typical performance improvements with Cython:

- **Tight loops**: 10-100x faster
- **Math operations**: 5-50x faster
- **C library calls**: Near-native C speed
- **Overall application**: 2-10x faster depending on workload

### Optimization Tips

For maximum performance in `.pyx` files:

1. **Add type declarations**:
   ```cython
   cdef int x = 0
   cdef double y = 1.5
   ```

2. **Use C types for loops**:
   ```cython
   cdef int i
   for i in range(1000):
       # fast C loop
   ```

3. **Disable checks in hot code**:
   ```cython
   @cython.boundscheck(False)
   @cython.wraparound(False)
   def fast_function():
       pass
   ```

## Troubleshooting

### Build Errors

**"fatal error: Python.h: No such file or directory"**
```bash
sudo apt-get install python3-dev
```

**"Cython not found"**
```bash
pip3 install Cython
```

**"gcc: command not found"**
```bash
sudo apt-get install build-essential
```

### Runtime Errors

**"ImportError: cannot import name 'Storm32Controller'"**
- The Cython extensions may not be built. Run `./build_cython.sh`
- Check for `.so` files in the module directories

**"ImportError: *.so: cannot open shared object file"**
- Rebuild with: `python3 setup.py build_ext --inplace`
- Check library dependencies with: `ldd cymbal/camera_gimbal/storm32_controller.*.so`

## Distribution

### Source Distribution

Create a source distribution with Cython sources:

```bash
python3 setup.py sdist
```

Users can build from source without needing the original `.pyx` files.

### Binary Distribution

Create platform-specific wheels:

```bash
python3 setup.py bdist_wheel
```

**Note**: Wheels are platform-specific. Build on the target platform (e.g., Raspberry Pi OS on RPi 3B+).

## Compatibility

- **Python**: 3.7+
- **Cython**: 0.29.0+
- **Architecture**: All platforms (x86_64, ARM, ARM64)
- **OS**: Linux (Raspberry Pi OS, Ubuntu, Debian)

## Advanced Features

### Profiling

Profile Cython code to find bottlenecks:

```bash
# Build with profiling enabled
python3 setup.py build_ext --inplace --profile

# Run with cProfile
python3 -m cProfile -o profile.stats your_script.py

# Analyze results
python3 -m pstats profile.stats
```

### Type Annotations

Cython respects Python type hints for optimization:

```python
def calculate(x: float, y: float) -> float:
    return x + y  # Cython will optimize this
```

### C Library Integration

Cython can directly interface with C libraries:

```cython
# Example: calling C math functions
from libc.math cimport sin, cos, sqrt

cdef double fast_distance(double x, double y):
    return sqrt(x*x + y*y)
```

## Migration Notes

### Differences from Python Version

1. **Import paths unchanged** - All imports work the same
2. **API compatibility** - All public APIs are identical
3. **Type safety** - Some internal type checking is stricter
4. **Performance** - Significantly faster execution

### Backward Compatibility

The Cython version maintains 100% API compatibility with the original Python version. All existing code will work without modifications.

## Support

For Cython-specific issues:
- Check the [Cython documentation](https://cython.readthedocs.io/)
- Review build logs for compilation errors
- Ensure all dependencies are installed

For package functionality issues:
- See main README.md
- Check docs/ directory
- Open an issue on GitHub

## References

- [Cython Documentation](https://cython.readthedocs.io/)
- [Cython Tutorial](https://cython.readthedocs.io/en/latest/src/tutorial/cython_tutorial.html)
- [Performance Tips](https://cython.readthedocs.io/en/latest/src/userguide/numpy_tutorial.html)
