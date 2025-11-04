# Cymbal: Cython gimbal controller
Code for control of a camera gimbal on a fixed-wing drone and overlay information about the location that the camera is looking at.

Control software for dual gimbals (camera and spotlight) mounted on a fixed-wing drone, controlled from a Raspberry Pi 3B+.

**⚡ Now with Cython for improved performance!**

## Overview

This system controls two independent gimbals:

1. **Camera Gimbal**: Uses the Storm32bgc brushless gimbal controller ([storm32bgc](https://github.com/gtraines/storm32bgc))
   - 3-axis control (pitch, roll, yaw)
   - Communicates via UART serial connection
   - High-precision brushless motor control

2. **Spotlight Gimbal**: Uses 2x 360-degree continuous rotation servos with MPU6050 IMU
   - 2-axis control (pitch, yaw)
   - PWM servo control via GPIO pins
   - IMU-based stabilization for maintaining orientation

Both gimbals are mounted on the bottom of the fixed-wing drone and controlled simultaneously from a Raspberry Pi 3B+.

### Cython Implementation

This project is implemented in **Cython** for optimal performance. All core modules are compiled to native C extensions, providing significant speed improvements while maintaining Python compatibility.

For details on building and using the Cython implementation, see [docs/CYTHON.md](docs/CYTHON.md).

## Hardware Requirements

### Raspberry Pi 3B+
- GPIO pins for servo control
- UART for Storm32bgc communication
- I2C for MPU6050 sensor

### Camera Gimbal
- Storm32bgc brushless gimbal controller
- Connected to RPi UART (GPIO 14/15, /dev/ttyAMA0)
- Configured for 115200 baud rate

### Spotlight Gimbal
- 2x 360-degree continuous rotation servos
- MPU6050 6-axis IMU (accelerometer + gyroscope)
- Connected to:
  - GPIO 17 (pitch servo)
  - GPIO 27 (yaw servo)
  - I2C bus 1 (MPU6050)

## Installation

### 1. System Dependencies

On Raspberry Pi, install required system packages:

```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-dev build-essential i2c-tools pigpio
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```

**Note**: `build-essential` and `python3-dev` are required for building Cython extensions.

### 2. Enable I2C and UART

Enable I2C and UART interfaces:

```bash
sudo raspi-config
# Navigate to: Interfacing Options -> I2C -> Enable
# Navigate to: Interfacing Options -> Serial -> Enable (hardware) / Disable (login shell)
```

Or edit `/boot/config.txt`:

```
dtparam=i2c_arm=on
enable_uart=1
```

Reboot after changes:

```bash
sudo reboot
```

### 3. Python Package Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/gtraines/cymbal.git
cd cymbal

# Install dependencies (includes Cython)
pip3 install -r requirements.txt

# Build Cython extensions
./build_cython.sh

# Install the package
pip3 install -e .
```

### 4. Verify Hardware Connections

Check I2C devices (should show MPU6050 at 0x68):

```bash
sudo i2cdetect -y 1
```

Check serial port:

```bash
ls -l /dev/ttyAMA0
```

## Configuration

The system uses a JSON configuration file. Copy the example configuration:

```bash
cp config.json /etc/cymbal/config.json
```

Edit `/etc/cymbal/config.json` to match your hardware setup:

```json
{
  "camera_gimbal": {
    "serial_port": "/dev/ttyAMA0",
    "baudrate": 115200,
    "timeout": 1.0
  },
  "spotlight_gimbal": {
    "pitch_pin": 17,
    "yaw_pin": 27,
    "i2c_address": 104,
    "i2c_bus": 1,
    "use_stabilization": true
  },
  "log_level": "INFO"
}
```

## Usage

### As a Python Package

```python
from cymbal import Storm32Controller, SpotlightController

# Camera gimbal control
with Storm32Controller() as camera:
    camera.set_angle(pitch=30, roll=0, yaw=45)

# Spotlight gimbal control
with SpotlightController() as spotlight:
    spotlight.set_position(pitch=30, yaw=45)
```

### Main Application

Run the main control application:

```bash
python3 -m cymbal.main
```

Or as a standalone script:

```bash
python3 cymbal/main.py
```

### Example Scripts

The `examples/` directory contains demonstration scripts:

```bash
# Camera gimbal example
python3 examples/camera_gimbal_example.py

# Spotlight gimbal example
python3 examples/spotlight_gimbal_example.py

# Synchronized dual gimbal control
python3 examples/dual_gimbal_example.py
```

## API Reference

### Storm32Controller (Camera Gimbal)

```python
from cymbal.camera_gimbal import Storm32Controller

controller = Storm32Controller(port="/dev/ttyAMA0", baudrate=115200)
controller.connect()

# Set gimbal angles (degrees)
controller.set_angle(pitch=30, roll=0, yaw=45)

# Set rotation speeds (degrees/second)
controller.set_speed(pitch_speed=10, roll_speed=0, yaw_speed=20)

# Center gimbal
controller.center()

# Get status
status = controller.get_status()

controller.disconnect()
```

### SpotlightController (Spotlight Gimbal)

```python
from cymbal.spotlight_gimbal import SpotlightController

controller = SpotlightController(pitch_pin=17, yaw_pin=27)
controller.initialize()

# Set gimbal position (degrees)
controller.set_position(pitch=30, yaw=45)

# Set rotation speeds (-100 to +100)
controller.set_speed(pitch_speed=50, yaw_speed=-30)

# Stop movement
controller.stop()

# Center gimbal
controller.center()

# Get orientation from IMU
pitch, roll = controller.get_orientation()

# Run stabilization
controller.stabilize()

controller.close()
```

### GimbalController (Main System)

```python
from cymbal.utils.config import SystemConfig
from cymbal.main import GimbalController

config = SystemConfig.load('config.json')
controller = GimbalController(config)
controller.initialize()

# Synchronized control
controller.sync_gimbals(pitch=30, yaw=45)

# Individual control
controller.set_camera_position(pitch=30, roll=0, yaw=45)
controller.set_spotlight_position(pitch=30, yaw=45)

# Get system status
status = controller.get_status()

controller.shutdown()
```

## Architecture

```
cymbal/
├── camera_gimbal/
│   └── storm32_controller.py    # Storm32bgc control
├── spotlight_gimbal/
│   └── servo_controller.py      # Servo control with MPU6050
├── sensors/
│   └── mpu6050.py              # MPU6050 IMU interface
├── utils/
│   └── config.py               # Configuration management
└── main.py                     # Main control application
```

## Wiring Diagram

### Camera Gimbal (Storm32bgc)
```
RPi 3B+          Storm32bgc
GPIO 14 (TX) --> RX
GPIO 15 (RX) <-- TX
GND          --- GND
```

### Spotlight Gimbal
```
RPi 3B+          Servos/IMU
GPIO 17      --> Pitch Servo (PWM)
GPIO 27      --> Yaw Servo (PWM)
GPIO 2 (SDA) <-> MPU6050 SDA
GPIO 3 (SCL) <-> MPU6050 SCL
5V           --> VCC (Servos & MPU6050)
GND          --- GND
```

## Troubleshooting

### Camera Gimbal Not Responding
- Check UART connection and baudrate
- Verify Storm32bgc is powered and configured
- Check serial port permissions: `sudo usermod -a -G dialout $USER`

### Spotlight Servos Not Moving
- Ensure pigpiod daemon is running: `sudo systemctl status pigpiod`
- Check GPIO pin connections
- Verify servo power supply (typically 5V, adequate current)

### MPU6050 Not Detected
- Check I2C connection: `sudo i2cdetect -y 1`
- Verify I2C is enabled in raspi-config
- Check I2C address (default: 0x68, alternative: 0x69)

### Permission Errors
```bash
# Add user to required groups
sudo usermod -a -G dialout,gpio,i2c $USER
# Logout and login again
```

## Development

### Running Tests

```bash
python3 -m pytest tests/
```

### Code Style

The project follows PEP 8 style guidelines.

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

See LICENSE file for details.

## References

- [Storm32bgc Firmware](https://github.com/gtraines/storm32bgc)
- [MPU6050 Datasheet](https://invensense.tdk.com/products/motion-tracking/6-axis/mpu-6050/)
- [Raspberry Pi GPIO Documentation](https://www.raspberrypi.org/documentation/hardware/raspberrypi/)
- [pigpio Library](http://abyz.me.uk/rpi/pigpio/)

## Support

For issues and questions, please open an issue on GitHub.

