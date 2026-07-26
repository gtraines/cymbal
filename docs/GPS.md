# GPS Integration

This document covers USB GPS receiver setup, terrain elevation database
preparation, and AGL altitude computation for the Cymbal gimbal control system.

## Overview

A USB GPS receiver (NMEA-0183 output) provides:

1. **Position** (latitude, longitude) — used for reverse geocoding and POI tracking.
2. **Altitude MSL** — combined with terrain elevation to compute AGL height.
3. **Ground speed and track** — available to the OSD and (future) lead-angle compensation.

## Supported Hardware

Any USB GPS module that outputs standard NMEA-0183 sentences at ≥1 Hz is supported.
Tested and recommended:

- **u-blox 7/8/M8** series (e.g. NEO-7M, NEO-8M, NEO-M8N)
- **GlobalTop PA6H** (MediaTek MT3339)
- Generic USB GPS dongles based on SiRF Star III / IV

Default baud rate: **9600** (NMEA default for most modules).  Some u-blox units can
be configured to 115200 for faster fix updates.

## Hardware Connection

Plug the USB GPS receiver into any USB port on the Raspberry Pi.  It will appear as:

```
/dev/ttyUSB0   (first USB serial device)
/dev/ttyUSB1   (if a second device is present)
```

Confirm the device path after plugging in:

```bash
dmesg | tail -20          # look for "ttyUSB0 attached"
ls -l /dev/ttyUSB*
```

Add your user to the `dialout` group if you see permission errors:

```bash
sudo usermod -a -G dialout $USER
# Log out and back in for the change to take effect
```

## Configuration

GPS settings live under the `gps` key in `/etc/cymbal/config.json`:

```json
"gps": {
  "port":             "/dev/ttyUSB0",
  "baudrate":         9600,
  "update_rate_hz":   5,
  "terrain_db_path":  "/opt/cymbal/srtm",
  "use_terrain_db":   true,
  "min_fix_quality":  1
}
```

| Key | Type | Default | Description |
|---|---|---|---|
| `port` | string | `/dev/ttyUSB0` | Serial device path |
| `baudrate` | int | `9600` | GPS module baud rate |
| `update_rate_hz` | int | `5` | How often `gps.update()` is called per second |
| `terrain_db_path` | string | `/opt/cymbal/srtm` | Directory containing SRTM `.hgt` tile files |
| `use_terrain_db` | bool | `true` | Enable terrain-elevation-based AGL computation |
| `min_fix_quality` | int | `1` | Minimum GPS fix quality to accept (1=GPS, 2=DGPS) |

## NMEA Sentences Parsed

| Sentence | Fields extracted |
|---|---|
| **GGA** | Latitude, longitude, altitude MSL, fix quality, satellite count, HDOP |
| **VTG** | Ground speed (km/h → m/s), true track (degrees) |
| **RMC** | Ground speed (knots → m/s), true course — fallback when VTG absent |

## Altitude Above Ground Level (AGL)

### How it works

```
altitude_AGL = gps_altitude_MSL − terrain_elevation(lat, lon)
```

The terrain elevation is looked up from pre-downloaded **SRTM** (Shuttle Radar
Topography Mission) tiles stored locally on the Pi SD card.

| Dataset | Resolution | Source |
|---|---|---|
| SRTM3 | ~90 m | NASA / USGS |
| SRTM1 | ~30 m (US coverage) | NASA / USGS |

For the primary operating area (North Mesa, Arizona) SRTM3 tile `N33W112.hgt`
covers the entire area in a single ~50 MB file.

### Pre-downloading SRTM tiles (one-time setup)

Run this on a machine with internet access, then copy the cache to the Pi:

```bash
# Install srtm.py on your workstation
pip3 install srtm.py

# Pre-fetch tile(s) for North Mesa, AZ (covers lat 33-34, lon -112 to -111)
python3 - <<'EOF'
import srtm
d = srtm.get_data(local_cache_dir='/tmp/srtm_cache')
# Request a point in each 1°×1° tile you need
for lat in [33, 34]:
    for lon in [-112, -111]:
        elev = d.get_elevation(lat + 0.5, lon + 0.5)
        print(f"Lat {lat+0.5}, Lon {lon+0.5} => {elev} m")
print("Tiles cached in /tmp/srtm_cache/")
EOF

# Copy the cache to the Pi
scp -r /tmp/srtm_cache/ pi@raspberrypi:/opt/cymbal/srtm/
```

Create the directory on the Pi first:

```bash
sudo mkdir -p /opt/cymbal/srtm
sudo chown pi:pi /opt/cymbal/srtm
```

### Verifying terrain lookup

```python
from cymbal.geo.terrain_elevation import TerrainElevationDB
db = TerrainElevationDB()
db.initialize('/opt/cymbal/srtm')
print(db.get_elevation(33.4152, -111.8315))   # North Mesa, AZ → ~360 m MSL
db.close()
```

### Fallback: GPS altitude only

Set `"use_terrain_db": false` to use GPS MSL altitude directly as AGL.  This is
useful during initial testing or if terrain tiles are not yet loaded.  When disabled,
`gps.altitude_agl` will be `NaN`; the OSD will display `--` for AGL.

## Troubleshooting

### No fix / `has_fix` always False

```bash
# Confirm GPS data is flowing
cat /dev/ttyUSB0     # raw NMEA sentences should scroll by
# or
minicom -b 9600 -D /dev/ttyUSB0
```

Give the receiver 30–60 seconds outdoors to acquire satellites on first use or
after being off for several hours (cold start).

### Wrong device path

```bash
# List all serial devices
ls -l /dev/ttyUSB* /dev/ttyACM*
dmesg | grep -i "tty" | tail -20
```

Update `gps.port` in `/etc/cymbal/config.json` to match.

### AGL reads as NaN

- Verify `terrain_db_path` points to a directory containing `*.hgt` files.
- Run the terrain verification snippet above.
- Check `/var/log/cymbal.log` for `TerrainElevationDB` error messages.

### GPS module is 115200 baud

If your module was previously configured for a higher baud rate:

```json
"gps": {
  "port":     "/dev/ttyUSB0",
  "baudrate": 115200
}
```
