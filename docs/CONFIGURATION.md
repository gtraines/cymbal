# Configuration Guide

The system uses a JSON configuration file located at `/etc/cymbal/config.json` or in the project root as `config.json`.

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
  
- **timeout** (float): Serial read timeout in seconds
  - Default: `1.0`

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

- **pitch_pin** / **yaw_pin** (integer): BCM GPIO pins for servos
- **i2c_address** (integer): MPU6050 address — `104` (0x68) or `105` (0x69)
- **i2c_bus** (integer): I2C bus number — `1` on Raspberry Pi 3B+
- **use_stabilization** (boolean): Enable IMU-based stabilization

### GPS Section

```json
"gps": {
  "port": "/dev/ttyUSB0",
  "baudrate": 9600,
  "update_rate_hz": 5,
  "terrain_db_path": "/opt/cymbal/srtm",
  "use_terrain_db": true,
  "min_fix_quality": 1
}
```

- **port**: USB serial device for GPS receiver
- **baudrate**: GPS module baud rate (default `9600`)
- **update_rate_hz**: GPS polling rate in the main loop
- **terrain_db_path**: Directory containing pre-downloaded SRTM `.hgt` tile files
- **use_terrain_db**: Set `false` to bypass terrain lookup and leave AGL as NaN
- **min_fix_quality**: Minimum acceptable fix — `1` = GPS, `2` = DGPS

See [GPS.md](GPS.md) for terrain tile download instructions.

### Geo (Address Lookup) Section

```json
"geo": {
  "address_db_path": "/opt/cymbal/addresses.db",
  "search_radius_deg": 0.01,
  "enabled": true
}
```

- **address_db_path**: Path to the SQLite address database built by `tools/load_openaddresses.py`
- **search_radius_deg**: Bounding box radius for nearest-address search (~1.1 km at Mesa, AZ)
- **enabled**: Set `false` to disable reverse geocoding

### OSD Section

```json
"osd": {
  "enabled": true,
  "font_scale": 0.6,
  "font_thickness": 1,
  "text_color": [255, 255, 255],
  "background_color": [0, 0, 0],
  "background_alpha": 0.5,
  "show_sbus_channels": false
}
```

See [OSD.md](OSD.md) for detailed display configuration.

### S-BUS Section

```json
"sbus": {
  "gpio_pin": 4,
  "socket_path": "/run/cymbal/sbus.sock",
  "failsafe_action": "center",
  "frame_timeout_ms": 100,
  "enabled": true
}
```

- **gpio_pin**: BCM GPIO pin receiving the S-BUS signal (default `4`)
- **socket_path**: Unix domain socket for the sbus-decoder ↔ cymbal IPC
- **failsafe_action**: Action on frame loss — `"center"` centers all gimbals
- **enabled**: Set `false` to disable S-BUS input

See [SBUS.md](SBUS.md) for wiring and service setup.

### Channel Map Section

```json
"channel_map": {
  "camera_pitch": 6,
  "camera_yaw": 7,
  "spotlight_pitch": 8,
  "spotlight_yaw": 9,
  "mode_select": 5,
  "poi_lock": 10,
  "camera_pitch_range": [-90.0, 30.0],
  "camera_yaw_range": [-90.0, 90.0],
  "spotlight_pitch_range": [-90.0, 30.0],
  "spotlight_yaw_range": [-180.0, 180.0]
}
```

- **camera_pitch / camera_yaw / spotlight_pitch / spotlight_yaw**: S-BUS channel numbers (1-indexed) mapped to gimbal axes
- **mode_select**: Channel number for the 3-position mode switch (MANUAL / STABILIZE / TRACK)
- **poi_lock**: Channel number for the momentary POI-lock switch
- **\*_range**: `[min_angle, max_angle]` — output angle range in degrees for each axis

### System Section

```json
"log_level": "INFO"
```

Valid values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

## Complete Example Configuration

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
  "gps": {
    "port": "/dev/ttyUSB0",
    "baudrate": 9600,
    "update_rate_hz": 5,
    "terrain_db_path": "/opt/cymbal/srtm",
    "use_terrain_db": true,
    "min_fix_quality": 1
  },
  "geo": {
    "address_db_path": "/opt/cymbal/addresses.db",
    "search_radius_deg": 0.01,
    "enabled": true
  },
  "osd": {
    "enabled": true,
    "font_scale": 0.6,
    "font_thickness": 1,
    "text_color": [255, 255, 255],
    "background_color": [0, 0, 0],
    "background_alpha": 0.5,
    "show_sbus_channels": false
  },
  "sbus": {
    "gpio_pin": 4,
    "socket_path": "/run/cymbal/sbus.sock",
    "failsafe_action": "center",
    "frame_timeout_ms": 100,
    "enabled": true
  },
  "channel_map": {
    "camera_pitch": 6,
    "camera_yaw": 7,
    "spotlight_pitch": 8,
    "spotlight_yaw": 9,
    "mode_select": 5,
    "poi_lock": 10,
    "camera_pitch_range": [-90.0, 30.0],
    "camera_yaw_range": [-90.0, 90.0],
    "spotlight_pitch_range": [-90.0, 30.0],
    "spotlight_yaw_range": [-180.0, 180.0]
  },
  "log_level": "INFO"
}
```

## Troubleshooting

### Serial Port Issues
- Check permissions: `ls -l /dev/ttyAMA0 /dev/ttyUSB0`
- Add user to dialout group: `sudo usermod -a -G dialout $USER`

### I2C Address Issues
- Scan I2C bus: `sudo i2cdetect -y 1`

### GPIO Pin Issues
- Verify pigpiod is running: `sudo systemctl status pigpiod`

### Configuration File Issues
- Validate JSON syntax: `python3 -m json.tool /etc/cymbal/config.json`

