# On-Screen Display (OSD)

This document covers the OSD telemetry overlay — what it shows, how to configure it,
and how to connect a camera feed for live annotation.

## Overview

The OSD module annotates video frames with real-time flight telemetry using OpenCV
drawing primitives.  It operates on NumPy image arrays so it works with any camera
source that produces OpenCV-compatible frames (USB webcam, Raspberry Pi Camera Module
via `picamera2`, or pre-recorded test frames).

## What the OSD displays

Each rendered frame shows a **text overlay box** in the top-left corner and a
**compass widget** in the top-right corner.

### Text overlay box

| Row | Content | Example |
|---|---|---|
| 1 | UTC timestamp | `17:42:03 UTC` |
| 2 | Nearest street address | `1234 E Main St, Mesa, AZ 85201` |
| 3 | GPS position | `Lat: 33.41520  Lon: -111.83150` |
| 4 | Altitude AGL | `Alt AGL: 152.3 m` |
| 5 | Ground speed | `GndSpd: 28.4 m/s` |
| 6 | Fix quality / satellites | `Fix: GPS  Sats: 9` |
| 7–8 | SBUS channels (optional) | `SBUS[1-8]:  1500  1500  ...` |

When GPS has no fix, position and altitude rows show `--`.

### Compass widget

A small circle drawn in the **top-right corner** of the frame with two directional
arrows and a north reference:

```
        N
       ┆        ← thin tick marks at N/E/S/W
   W ──○── E    ← compass ring (dims when no GPS fix)
       ┆
        S

 ←white arrow→  aircraft travel direction (GPS ground track)
 ←yellow arrow→ camera aim direction in yaw (absolute geographic)

 Trk: 045.0°    (white text, below ring)
 Cam: +030.0°   (yellow text, offset from aircraft nose)
```

| Element | Colour | Meaning |
|---|---|---|
| White arrow | White | GPS ground track — where the aircraft is flying geographically |
| Yellow arrow | Yellow | Absolute camera yaw direction = ground track + camera yaw offset |
| Ring | Bright grey | Compass ring; dims to dark grey when GPS fix is unavailable |
| `Trk:` label | White | Ground track in degrees from north, clockwise (0–360) |
| `Cam:` label | Yellow | Camera yaw relative to aircraft nose (+° = right, −° = left) |

The compass is **north-up** (standard aviation convention). Both arrows are suppressed
when the relevant value is unavailable (no GPS fix, or no gimbal command sent yet).

## Configuration

OSD settings live under the `osd` key in `/etc/cymbal/config.json`:

```json
"osd": {
  "enabled":           true,
  "font_scale":        0.6,
  "font_thickness":    1,
  "text_color":        [255, 255, 255],
  "background_color":  [0, 0, 0],
  "background_alpha":  0.5,
  "show_sbus_channels": false,
  "show_compass":      true,
  "compass_radius":    45
}
```

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Master enable; set `false` to disable all rendering |
| `font_scale` | float | `0.6` | OpenCV font scale factor |
| `font_thickness` | int | `1` | Text stroke thickness in pixels |
| `text_color` | [R,G,B] | `[255,255,255]` | Text colour (white) |
| `background_color` | [R,G,B] | `[0,0,0]` | Background box colour (black) |
| `background_alpha` | float | `0.5` | Background opacity 0.0 (transparent) to 1.0 (solid) |
| `show_sbus_channels` | bool | `false` | Show raw SBUS channel values for debugging |
| `show_compass` | bool | `true` | Show the compass widget in the top-right corner |
| `compass_radius` | int | `45` | Radius of the compass ring in pixels (default fits 640×480) |

> **Note:** OpenCV uses BGR channel ordering internally.  The config accepts RGB
> for readability; the module converts to BGR automatically when drawing.

## Connecting a camera

### USB webcam

```python
import cv2
from cymbal.osd.overlay_controller import OSDOverlay

cap = cv2.VideoCapture(0)   # /dev/video0
osd = OSDOverlay(config.osd)
osd.initialize()

while True:
    ret, frame = cap.read()
    if not ret:
        break
    osd.update_telemetry(lat, lon, alt_agl, groundspeed, address,
                         fix_quality, satellites, sbus_channels)
    osd.render_frame(frame)     # annotates frame in-place
    cv2.imshow('Cymbal OSD', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
```

### Raspberry Pi Camera Module (picamera2)

```python
from picamera2 import Picamera2
import cv2, numpy as np

picam2 = Picamera2()
picam2.configure(picam2.create_preview_configuration(
    main={"format": "BGR888", "size": (640, 480)}))
picam2.start()

while True:
    frame = picam2.capture_array()
    osd.render_frame(frame)
    # transmit or display frame as needed
```

### Headless / no display

`render_frame()` only writes to the numpy array; it does **not** call `cv2.imshow()`.
You can annotate frames and then:

- Write to a video file: `cv2.VideoWriter`
- Stream over RTSP/RTP with `cv2.VideoWriter` + FFMPEG
- Transmit raw frames over a network socket

## Dependency

OpenCV is installed via `requirements.txt` as `opencv-python-headless`, which
provides all drawing and codec functions without requiring a desktop GUI stack.
This makes it safe to install on a headless Raspberry Pi OS Lite image.

```bash
pip3 install opencv-python-headless
```

Verify:

```bash
python3 -c "import cv2; print(cv2.__version__)"
```

## Address Database for OSD

The address shown on the OSD comes from the offline reverse geocoding database.
See [GPS.md](GPS.md) for terrain elevation setup and the project root
`tools/load_openaddresses.py` for building the address database.

```bash
# Build address database for North Mesa, AZ from OpenAddresses CSV
python3 tools/load_openaddresses.py \
    --input /path/to/openaddresses-us-az-maricopa.csv \
    --output /opt/cymbal/addresses.db \
    --bbox 33.3,33.55,-111.95,-111.60
```

Configure the path in `/etc/cymbal/config.json`:

```json
"geo": {
  "address_db_path":   "/opt/cymbal/addresses.db",
  "search_radius_deg": 0.01,
  "enabled":           true
}
```

## Troubleshooting

### `OSDOverlay initialized` not appearing in logs

Check that `osd.enabled` is `true` in config and that `opencv-python-headless`
is installed:

```bash
pip3 show opencv-python-headless
```

### Address always shows "Unknown address"

- Verify the database file exists: `ls -lh /opt/cymbal/addresses.db`
- Confirm the GPS has a valid fix and the drone is over the loaded area.
- Increase `geo.search_radius_deg` slightly (e.g. `0.02`) if the database
  has sparse coverage.

### OSD text is too small / large

Adjust `osd.font_scale` in config.  A value of `0.5` is readable at 480p;
use `0.8`–`1.0` for 1080p output.
