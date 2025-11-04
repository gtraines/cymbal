# Project Summary: Cymbal Airborne Gimbal Control System

## Overview

Complete dual gimbal control system for fixed-wing drones, controlled via Raspberry Pi 3B+.

## System Components

### 1. Camera Gimbal (Storm32bgc)
- **Type:** 3-axis brushless gimbal
- **Controller:** Storm32bgc
- **Communication:** UART serial (115200 baud)
- **Connection:** GPIO 14/15 (TX/RX)
- **Capabilities:**
  - 3-axis control (pitch, roll, yaw)
  - Angle and speed commands
  - Status monitoring

### 2. Spotlight Gimbal
- **Type:** 2-axis servo gimbal
- **Servos:** 2x 360-degree continuous rotation
- **Communication:** PWM via GPIO
- **Connection:** GPIO 17 (pitch), GPIO 27 (yaw)
- **IMU:** MPU6050 for stabilization
- **Capabilities:**
  - 2-axis control (pitch, yaw)
  - Position and speed control
  - IMU-based stabilization
  - Orientation sensing

### 3. MPU6050 IMU
- **Type:** 6-axis accelerometer + gyroscope
- **Communication:** I2C (400kHz)
- **Address:** 0x68 (default)
- **Features:**
  - Acceleration measurement (±2g)
  - Gyroscope measurement (±250°/s)
  - Temperature sensor
  - Calibration support

## Software Architecture

```
cymbal/
├── camera_gimbal/           # Storm32bgc controller
│   └── storm32_controller.py
├── spotlight_gimbal/        # Servo controller
│   └── servo_controller.py
├── sensors/                 # IMU interface
│   └── mpu6050.py
├── utils/                   # Configuration
│   └── config.py
└── main.py                  # Main application
```

## Key Features

1. **Unified Control Interface**
   - Single application controls both gimbals
   - Synchronized or independent control
   - Configuration-based setup

2. **Stabilization**
   - IMU-based stabilization for spotlight
   - Maintains orientation despite drone movement
   - Adjustable update rate

3. **Flexible Configuration**
   - JSON-based configuration
   - Runtime configuration changes
   - Default fallbacks

4. **Robust Design**
   - Context manager support
   - Signal handling
   - Comprehensive logging
   - Error handling

5. **Easy Integration**
   - Python package structure
   - pip installable
   - Example scripts provided
   - Well-documented API

## Implementation Details

### Hardware Requirements
- Raspberry Pi 3B+ (or compatible)
- Storm32bgc brushless gimbal controller
- 2x 360-degree continuous rotation servos
- MPU6050 6-axis IMU
- Appropriate power supplies (5V for servos, 12V for camera gimbal)

### Software Requirements
- Python 3.7+
- pyserial (serial communication)
- smbus2 (I2C communication)
- pigpio (GPIO/PWM control)

### Communication Protocols
- **UART:** 115200 baud, 8N1 for Storm32bgc
- **I2C:** 400kHz for MPU6050
- **PWM:** 1000-2000µs pulses for servos

## Documentation

### Available Documentation
1. **README.md** - Main project documentation
2. **docs/API.md** - Complete API reference
3. **docs/INSTALLATION.md** - Installation guide
4. **docs/HARDWARE.md** - Wiring and hardware setup
5. **CHANGELOG.md** - Version history

### Example Scripts
1. **camera_gimbal_example.py** - Storm32 control
2. **spotlight_gimbal_example.py** - Servo control
3. **dual_gimbal_example.py** - Synchronized control

## Usage Examples

### Basic Camera Control
```python
from cymbal import Storm32Controller

with Storm32Controller() as camera:
    camera.set_angle(pitch=30, roll=0, yaw=45)
```

### Basic Spotlight Control
```python
from cymbal import SpotlightController

with SpotlightController() as spotlight:
    spotlight.set_position(pitch=30, yaw=45)
    spotlight.stabilize()
```

### Synchronized Control
```python
from cymbal.utils.config import SystemConfig
from cymbal.main import GimbalController

config = SystemConfig.load('config.json')
controller = GimbalController(config)
controller.initialize()
controller.sync_gimbals(pitch=30, yaw=45)
controller.shutdown()
```

## Testing

Basic test suite included:
- Import tests
- Module availability tests
- Run with: `python3 -m unittest tests/test_imports.py`

## Deployment

### Installation
```bash
git clone https://github.com/gtraines/cymbal.git
cd cymbal
pip3 install -r requirements.txt
```

### As System Service
```bash
sudo cp cymbal.service /etc/systemd/system/
sudo systemctl enable cymbal
sudo systemctl start cymbal
```

## Performance Characteristics

- **Serial Commands:** ~10-50ms latency
- **I2C Reads:** ~1-5ms latency
- **PWM Updates:** <1ms latency
- **Stabilization Rate:** 10-50Hz recommended
- **CPU Usage:** Low (<5% on RPi 3B+)

## Limitations & Future Work

### Current Limitations
- Storm32 MAVLink protocol simplified
- Basic proportional stabilization (no PID)
- No multi-threading support
- Limited error recovery

### Planned Enhancements
- Full MAVLink protocol
- PID controller for stabilization
- Thread-safe operations
- Network control interface
- Computer vision integration
- Target tracking
- Data logging
- Telemetry

## License

See LICENSE file for details.

## Support

For issues and questions:
- GitHub Issues: https://github.com/gtraines/cymbal/issues
- Documentation: See docs/ directory
- Examples: See examples/ directory

## References

- [Storm32bgc Firmware](https://github.com/gtraines/storm32bgc)
- [MPU6050 Datasheet](https://invensense.tdk.com/products/motion-tracking/6-axis/mpu-6050/)
- [Raspberry Pi Documentation](https://www.raspberrypi.org/documentation/)
- [pigpio Library](http://abyz.me.uk/rpi/pigpio/)

---

**Project Status:** Initial release (v0.1.0)
**Date:** November 4, 2025
**Author:** gtraines
