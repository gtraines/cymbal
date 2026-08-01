# Installation Guide

This guide provides detailed installation instructions for setting up the Cymbal Airborne Gimbal Control System on a Raspberry Pi 3B+.

## Prerequisites

- Raspberry Pi 3B+ with Raspberry Pi OS (formerly Raspbian) installed
- Internet connection for downloading packages
- Physical access to the Raspberry Pi for hardware connections

## Step-by-Step Installation

### 1. Update System

```bash
sudo apt-get update
sudo apt-get upgrade -y
```

### 2. Install System Dependencies

```bash
# Install Python development tools
sudo apt-get install -y python3-pip python3-dev python3-setuptools

# Install I2C tools for MPU6050
sudo apt-get install -y i2c-tools libi2c-dev

# Install pigpio for GPIO/PWM and S-BUS bit-bang serial
sudo apt-get install -y pigpio python3-pigpio

# Install build tools for Cython extensions
sudo apt-get install -y build-essential

# Enable and start pigpio daemon
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```

### 3. Enable Hardware Interfaces

#### Using raspi-config (Recommended)

```bash
sudo raspi-config
```

Navigate through the menus:
1. **Interfacing Options** → **I2C** → **Enable**
2. **Interfacing Options** → **Serial Port**
   - "Would you like a login shell accessible over serial?" → **No**
   - "Would you like the serial port hardware enabled?" → **Yes**

#### Manual Configuration

Edit `/boot/config.txt`:

```bash
sudo nano /boot/config.txt
```

Add or uncomment these lines:

```
dtparam=i2c_arm=on
enable_uart=1
```

Edit `/boot/cmdline.txt` and remove any references to `console=serial0,115200` or similar.

### 4. Reboot

```bash
sudo reboot
```

### 5. Verify Hardware Interfaces

After reboot, verify I2C is working:

```bash
# Should show devices on the I2C bus
sudo i2cdetect -y 1
```

Verify UART is available:

```bash
ls -l /dev/ttyAMA0
# or
ls -l /dev/serial0
```

### 6. Install Python Package

Clone and install the cymbal package:

```bash
cd ~
git clone https://github.com/gtraines/cymbal.git
cd cymbal

# Install in development mode
pip3 install -e .

# Or install normally
pip3 install .
```

### 7. Set Permissions

Add your user to required groups:

```bash
sudo usermod -a -G dialout,gpio,i2c $USER
```

Log out and log back in for group changes to take effect.

### 8. Configuration

Create configuration directory and data directories:

```bash
sudo mkdir -p /etc/cymbal /opt/cymbal/srtm
sudo cp config.json /etc/cymbal/config.json
sudo chown -R pi:pi /etc/cymbal /opt/cymbal
```

Edit configuration as needed:

```bash
nano /etc/cymbal/config.json
```

See [docs/CONFIGURATION.md](CONFIGURATION.md) for a full reference.

### 8a. Build the Address Database (optional, for reverse geocoding)

```bash
# Download OpenAddresses data for your area from https://batch.openaddresses.io
# Then build the local SQLite database:
python3 tools/load_openaddresses.py \
    --input /path/to/openaddresses-us-az.csv \
    --output /opt/cymbal/addresses.db \
    --bbox 33.3,33.55,-111.95,-111.60
```

See [docs/OSD.md](OSD.md) for details.

### 8b. Download SRTM Terrain Tiles (optional, for AGL altitude)

Pre-download tiles on a machine with internet access, then copy to the Pi.
See [docs/GPS.md](GPS.md) for instructions.

### 9. Install Systemd Services

Cymbal runs as four coordinated systemd services.  See [docs/SERVICES.md](SERVICES.md)
for the full service graph, IPC paths, and resource isolation details.

#### Sidecar mode (recommended — GPS and OSD run in separate processes)

```bash
sudo cp sbus-decoder.service    /etc/systemd/system/
sudo cp cymbal-telemetry.service /etc/systemd/system/
sudo cp cymbal-video.service     /etc/systemd/system/
sudo cp cymbal.service           /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sbus-decoder cymbal-telemetry cymbal-video cymbal
```

Also ensure `config.json` has:

```json
"telemetry": {
  "mode": "sidecar",
  "socket_path": "/run/cymbal/telemetry.sock",
  "frame_timeout_ms": 500
}
```

#### In-process mode (simpler — GPS runs inside the control loop, may block at 5 Hz)

```bash
sudo cp sbus-decoder.service /etc/systemd/system/
sudo cp cymbal.service       /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sbus-decoder cymbal
```

Set `"telemetry": {"mode": "in_process"}` in `config.json` (this is the default).

Test basic imports:

```bash
python3 -c "from cymbal import Storm32Controller, SpotlightController; print('Import successful!')"
```

Run example scripts (with hardware connected):

```bash
python3 examples/camera_gimbal_example.py
python3 examples/spotlight_gimbal_example.py
```

## Hardware Connections

### Storm32bgc Camera Gimbal

Connect to Raspberry Pi UART:
- **TX** (GPIO 14) → Storm32bgc RX
- **RX** (GPIO 15) → Storm32bgc TX
- **GND** → Storm32bgc GND

### Spotlight Gimbal Servos

Connect servos to GPIO pins:
- **GPIO 17** → Pitch Servo Signal (Orange/Yellow wire)
- **GPIO 27** → Yaw Servo Signal (Orange/Yellow wire)
- **5V** → Servo Power (Red wire) - Use external power supply for multiple servos
- **GND** → Servo Ground (Brown/Black wire)

**Note:** For multiple servos, use an external 5V power supply with adequate current capacity. Connect RPi GND to power supply GND for common ground.

### MPU6050 IMU

Connect to I2C bus:
- **GPIO 2 (SDA)** → MPU6050 SDA
- **GPIO 3 (SCL)** → MPU6050 SCL
- **3.3V or 5V** → MPU6050 VCC (check module specifications)
- **GND** → MPU6050 GND

## Troubleshooting Installation

### I2C Not Working

```bash
# Check I2C is enabled
sudo raspi-config

# Load I2C kernel module manually
sudo modprobe i2c-dev

# Check for I2C devices
sudo i2cdetect -y 1
```

### UART Not Working

```bash
# Check UART is enabled
ls -l /dev/ttyAMA0 /dev/serial0

# Disable Bluetooth to free up UART (if needed)
sudo systemctl disable hciuart
```

### pigpio Daemon Issues

```bash
# Check daemon status
sudo systemctl status pigpiod

# Restart daemon
sudo systemctl restart pigpiod

# Check if daemon is listening
sudo netstat -tlnp | grep pigpio
```

### Permission Errors

```bash
# Verify group membership
groups

# Should include: dialout, gpio, i2c

# If not, add user to groups and reboot
sudo usermod -a -G dialout,gpio,i2c $USER
sudo reboot
```

### Python Package Import Errors

```bash
# Reinstall dependencies
pip3 install --upgrade -r requirements.txt

# Check Python path
python3 -c "import sys; print('\n'.join(sys.path))"

# Install package in development mode
pip3 install -e .
```

## Optional: Install as System Service

Create a systemd service file:

```bash
sudo nano /etc/systemd/system/cymbal.service
```

Add:

```ini
[Unit]
Description=Cymbal Airborne Gimbal Control System
After=network.target pigpiod.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/cymbal
ExecStart=/usr/bin/python3 -m cymbal.main
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable cymbal
sudo systemctl start cymbal
sudo systemctl status cymbal
```

## Next Steps

After successful installation:
1. Test individual gimbal controllers with example scripts
2. Calibrate the MPU6050 sensor
3. Adjust configuration for your specific hardware
4. Test synchronized gimbal control
5. Integrate with your drone control system

For detailed usage instructions, see the main README.md file.
