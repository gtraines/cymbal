# Configuration Guide

The system uses a JSON configuration file located at `/etc/airborne_gimbal/config.json` or in the project root as `config.json`.

## Configuration Parameters

### Camera Gimbal Section

```json
"camera_gimbal": {
  "serial_port": "/dev/ttyAMA0",
  "baudrate": 115200,
  "timeout": 1.0
}
```

- **serial_port** (string): Serial port device path for Storm32bgc connection
  - Default: `/dev/ttyAMA0` (primary UART on Raspberry Pi)
  - Alternative: `/dev/serial0` (symlink to primary UART)
  
- **baudrate** (integer): Communication speed for serial connection
  - Default: `115200` (Storm32bgc default)
  - Valid values: 9600, 19200, 38400, 57600, 115200
  
- **timeout** (float): Serial read timeout in seconds
  - Default: `1.0`
  - Range: 0.1 to 10.0

### Spotlight Gimbal Section

```json
"spotlight_gimbal": {
  "pitch_pin": 17,
  "yaw_pin": 27,
  "i2c_address": 104,
  "i2c_bus": 1,
  "use_stabilization": true
}
```

- **pitch_pin** (integer): GPIO pin number for pitch servo (BCM numbering)
  - Default: `17` (physical pin 11)
  - Valid range: Any valid GPIO pin
  
- **yaw_pin** (integer): GPIO pin number for yaw servo (BCM numbering)
  - Default: `27` (physical pin 13)
  - Valid range: Any valid GPIO pin
  
- **i2c_address** (integer): I2C address for MPU6050 sensor
  - Default: `104` (0x68 in hexadecimal)
  - Alternative: `105` (0x69 in hexadecimal, when AD0 pin is high)
  - **Note:** JSON doesn't support hexadecimal literals, so decimal values are used
  - The MPU6050 only supports two addresses: 104 or 105 (0x68 or 0x69)
  
- **i2c_bus** (integer): I2C bus number
  - Default: `1` (Raspberry Pi 3B+ I2C bus)
  - Raspberry Pi 3B+ has I2C bus 1 on GPIO 2/3
  
- **use_stabilization** (boolean): Enable IMU-based stabilization
  - Default: `true`
  - Set to `false` to disable stabilization

### System Section

```json
"log_level": "INFO"
```

- **log_level** (string): Logging verbosity level
  - Valid values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
  - Default: `INFO`
  - Use `DEBUG` for troubleshooting
  - Use `WARNING` or higher for production

## Example Configuration

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

## I2C Address Reference

The MPU6050 I2C address is determined by the AD0 pin:

| AD0 Pin State | Hexadecimal | Decimal | Use in config.json |
|---------------|-------------|---------|-------------------|
| LOW (GND)     | 0x68        | 104     | `"i2c_address": 104` |
| HIGH (VCC)    | 0x69        | 105     | `"i2c_address": 105` |

To verify your MPU6050 address:
```bash
sudo i2cdetect -y 1
```

## GPIO Pin Reference (BCM Numbering)

Common GPIO pins for servo control:

| BCM Number | Physical Pin | Common Use |
|------------|--------------|------------|
| 17         | 11           | Pitch servo (default) |
| 27         | 13           | Yaw servo (default) |
| 22         | 15           | Alternative |
| 23         | 16           | Alternative |
| 24         | 18           | Alternative |

**Important:** Use BCM numbering in the configuration, not physical pin numbers.

## Loading Configuration

### From Default Location
```python
from airborne_gimbal.utils.config import SystemConfig

config = SystemConfig.load('/etc/airborne_gimbal/config.json')
```

### From Custom Location
```python
config = SystemConfig.load('/path/to/your/config.json')
```

### Using Defaults
```python
# If file doesn't exist, defaults are used
config = SystemConfig.load('nonexistent.json')
```

## Saving Configuration

```python
from airborne_gimbal.utils.config import SystemConfig, CameraGimbalConfig, SpotlightGimbalConfig

# Create configuration
camera = CameraGimbalConfig(serial_port="/dev/ttyAMA0", baudrate=115200)
spotlight = SpotlightGimbalConfig(pitch_pin=17, yaw_pin=27, i2c_address=104)
config = SystemConfig(camera_gimbal=camera, spotlight_gimbal=spotlight)

# Save to file
config.save('config.json')
```

## Troubleshooting

### Serial Port Issues
- Check permissions: `ls -l /dev/ttyAMA0`
- Add user to dialout group: `sudo usermod -a -G dialout $USER`
- Verify UART is enabled in `/boot/config.txt`: `enable_uart=1`

### I2C Address Issues
- Scan I2C bus: `sudo i2cdetect -y 1`
- Check MPU6050 AD0 pin connection
- Verify I2C is enabled: `dtparam=i2c_arm=on` in `/boot/config.txt`

### GPIO Pin Issues
- Verify pigpiod is running: `sudo systemctl status pigpiod`
- Check pin availability: `gpio readall` (requires wiringpi)
- Ensure pins aren't used by other services

### Configuration File Issues
- Validate JSON syntax: `python3 -m json.tool config.json`
- Check file permissions: `ls -l config.json`
- Verify file location is correct
