# Changelog

All notable changes to the Cymbal Airborne Gimbal Control System will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2025-11-04

### Changed

#### Cython Implementation
- **Complete rewrite to Cython** - All Python modules converted to Cython (.pyx files)
  - `storm32_controller.pyx` - Camera gimbal controller
  - `servo_controller.pyx` - Spotlight gimbal controller
  - `mpu6050.pyx` - IMU sensor interface
  - `config.pyx` - Configuration management
  - `main.pyx` - Main control application

#### Performance Improvements
- Compiled C extensions for significantly faster execution
- Optimized math operations and tight loops
- Reduced Python overhead in critical paths
- Near-native C speed for hardware interfacing

#### Build System
- Updated `setup.py` with Cython build configuration
- Added `build_cython.sh` build script for easy compilation
- Configured compiler directives for optimal performance
- Added Cython to requirements.txt

#### Documentation
- Added `docs/CYTHON.md` - Comprehensive Cython implementation guide
- Updated README.md with Cython build instructions
- Added build troubleshooting section
- Updated installation guide for Cython dependencies

#### Development
- Updated `.gitignore` for Cython build artifacts (.c, .cpp, .html files)
- Maintained 100% API compatibility with Python version
- All imports and usage remain unchanged

### Technical Details

**Compiler Directives:**
- `language_level: 3` - Python 3 semantics
- `embedsignature: True` - Function signature embedding
- `boundscheck: False` - Array bounds checking disabled for speed
- `wraparound: False` - Negative indexing disabled for speed
- `cdivision: True` - C division semantics for speed

**Build Requirements:**
- Cython >= 0.29.0
- build-essential (gcc, make)
- python3-dev

## [0.1.0] - 2025-11-04

### Added

#### Core Components
- Initial implementation of Storm32bgc camera gimbal controller
  - Serial/UART communication interface
  - 3-axis control (pitch, roll, yaw)
  - Angle and speed control methods
  - Status monitoring
  - Context manager support

- Spotlight gimbal controller with servo control
  - 2-axis control via PWM (pitch, yaw)
  - GPIO pin configuration
  - Position and speed control
  - MPU6050 IMU integration for stabilization
  - Context manager support

- MPU6050 IMU sensor interface
  - I2C communication
  - 6-axis data (accelerometer + gyroscope)
  - Temperature reading
  - Sensor calibration
  - Orientation calculation

#### System Integration
- Main gimbal control application
  - Dual gimbal coordination
  - Synchronized control
  - Stabilization loop
  - Signal handling for graceful shutdown
  - Status monitoring

- Configuration management system
  - JSON-based configuration
  - Dataclass-based configuration objects
  - Load/save functionality
  - Default configurations

#### Documentation
- Comprehensive README with:
  - System overview
  - Hardware requirements
  - Installation instructions
  - Usage examples
  - API reference
  - Troubleshooting guide

- Installation guide (docs/INSTALLATION.md)
  - Step-by-step setup instructions
  - Hardware interface configuration
  - Testing procedures
  - Systemd service setup

- Hardware wiring documentation (docs/HARDWARE.md)
  - GPIO pinout reference
  - Connection tables
  - Wiring diagrams
  - Power considerations
  - Safety notes

- API documentation (docs/API.md)
  - Complete API reference
  - Code examples
  - Error handling guidelines
  - Performance considerations

#### Examples
- Camera gimbal example script
  - Basic Storm32 control demonstration
  - Position control examples
  - Status monitoring

- Spotlight gimbal example script
  - Servo control demonstration
  - IMU orientation reading
  - Stabilization demonstration

- Dual gimbal example script
  - Synchronized control
  - System status monitoring
  - Complete workflow demonstration

#### Package Management
- setup.py for pip installation
- requirements.txt with dependencies
  - pyserial for UART communication
  - smbus2 for I2C communication
  - pigpio for GPIO/PWM control

- .gitignore configured for Python projects
- Systemd service file template
- Example configuration file (config.json)

### Technical Details

#### Supported Hardware
- Raspberry Pi 3B+ (primary target)
- Storm32bgc brushless gimbal controller
- 360-degree continuous rotation servos (2x)
- MPU6050 6-axis IMU sensor

#### Communication Protocols
- UART/Serial (115200 baud) for Storm32bgc
- I2C (400kHz) for MPU6050
- PWM (1000-2000µs) for servo control

#### Software Features
- Python 3.7+ compatibility
- Object-oriented architecture
- Context manager support
- Logging integration
- Configuration management
- Signal handling

### Known Limitations
- Storm32 MAVLink protocol is simplified (placeholder implementation)
- Stabilization uses basic proportional control (no full PID)
- No multi-threading support
- Requires pigpiod daemon for GPIO control

### Dependencies
- Python 3.7+
- pyserial >= 3.5
- smbus2 >= 0.4.2
- pigpio >= 1.78

### Platform Support
- Linux (Raspberry Pi OS)
- Requires GPIO, I2C, and UART interfaces

## [Unreleased]

### Planned Features
- Full MAVLink protocol implementation for Storm32
- PID controller for stabilization
- Thread-safe operations
- Data logging and telemetry
- Remote control interface (network, RC receiver)
- Computer vision integration for target tracking
- Web interface for configuration and monitoring
- Support for additional IMU sensors
- Support for additional servo types
- Automated testing suite

### Future Improvements
- Improved error handling and recovery
- Performance optimizations
- Extended documentation
- Video tutorials
- Real-world usage examples
- Calibration utilities
- Diagnostic tools

---

## Version History

- **0.1.0** (2025-11-04) - Initial release with core functionality
