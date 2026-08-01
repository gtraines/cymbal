# Cymbal Service Architecture

This document describes the four systemd services that make up the Cymbal
airborne gimbal control system, their dependencies, IPC paths, startup
sequence, resource policies, and troubleshooting guide.

---

## Service graph

```
pigpiod.service        (system daemon, required by sbus-decoder + cymbal)
     │
     ├─► sbus-decoder.service   ── binds /run/cymbal/sbus.sock
     │         │                    publishes S-BUS frames → cymbal
     │
     ├─► cymbal-telemetry.service ── binds /run/cymbal/telemetry.sock
     │         │                      publishes TelemetrySnapshots → cymbal + cymbal-video
     │
     ├─► cymbal-video.service   ── reads telemetry socket
     │                              renders OSD / camera output
     │
     └─► cymbal.service         ── reads sbus + telemetry sockets
                                   commands gimbals via serial / GPIO
```

### Dependency types

| Dependency | Type | Meaning |
|---|---|---|
| `sbus-decoder → pigpiod` | `Requires=` | Hard: SBUS cannot run without pigpiod |
| `cymbal → pigpiod` | `Requires=` | Hard: GPIO servo control requires pigpiod |
| `cymbal → sbus-decoder` | `Requires=` | Hard: S-BUS input is mandatory for safe operation |
| `cymbal → cymbal-telemetry` | `Wants=` | Soft: control starts without the sidecar; degrades to NaN telemetry |
| `cymbal → cymbal-video` | `Wants=` | Soft: control starts without video; OSD is a display concern only |
| `cymbal-video → cymbal-telemetry` | `Wants=` | Soft: video renders blank OSD if telemetry sidecar is absent |

---

## IPC paths

All sockets live under `/run/cymbal/` (created by systemd `RuntimeDirectory=cymbal`).
The directory is owned by the `pi` user and group (`0755`).

| Socket | Publisher | Reader(s) | Protocol |
|---|---|---|---|
| `/run/cymbal/sbus.sock` | sbus-decoder | cymbal | Unix DGRAM, 48-byte `SBUS` struct |
| `/run/cymbal/sbus.sock.reader` | cymbal | sbus-decoder sends to this | Unix DGRAM |
| `/run/cymbal/telemetry.sock` | cymbal-telemetry | cymbal, cymbal-video | Unix DGRAM, 190-byte `TELE` struct |
| `/run/cymbal/telemetry.sock.reader` | cymbal / cymbal-video | telemetry sends to this | Unix DGRAM |

See `cymbal/controller/ipc_schemas.py` for the exact struct layouts and magic bytes.

**Note:** The `.reader` path is created by the consuming process when it calls
`socket.bind()`.  Publishers use `socket.sendto(payload, reader_path)` with a
`FileNotFoundError` guard so they don't fail if the reader has not yet started.

---

## Resource isolation

| Service | `Nice` | `CPUAffinity` | `MemoryMax` | Purpose |
|---|---|---|---|---|
| pigpiod | (system-managed) | — | — | GPIO daemon |
| sbus-decoder | `-5` | `0` | `64M` | Bit-bang serial → socket bridge |
| cymbal | `-10` | `0 1` | `256M` | Control loop: SBUS, gimbals, failsafe |
| cymbal-telemetry | `0` | `2 3` | `512M` | GPS + terrain + address publisher |
| cymbal-video | `+5` | `2 3` | `512M` | OSD rendering + camera capture |

**Priority ladder:** cymbal (-10) > sbus-decoder (-5) > telemetry (0) > video (+5)

**Core isolation rationale (RPi 3B+, 4× ARM Cortex-A53):**
- Cores 0–1: time-sensitive work (SBUS decoding, gimbal command dispatch).
  SBUS frames arrive every 14 ms; a missed frame triggers failsafe.
- Cores 2–3: bursty background work (GPS serial + SQLite + OpenCV).
  These workloads have no hard deadline and benefit from being kept off the
  control cores to avoid L1/L2 cache eviction.

---

## Startup sequence

### Standard (sidecar mode)

```
1. pigpiod           starts automatically at boot
2. sbus-decoder      starts; binds /run/cymbal/sbus.sock; waits for S-BUS frames
3. cymbal-telemetry  starts; opens GPS serial; binds /run/cymbal/telemetry.sock
4. cymbal-video      starts; connects to telemetry socket; opens camera (optional)
5. cymbal            starts; connects to sbus.sock + telemetry.sock; initializes gimbals
```

### In-process mode (no sidecars)

Set `"telemetry": {"mode": "in_process"}` in config.json.  Only `sbus-decoder` and
`cymbal` need to be running; the control loop does GPS + SQLite inline (blocking).

```
1. pigpiod      starts at boot
2. sbus-decoder starts
3. cymbal       starts (GPS/terrain/address run inside the control loop)
```

---

## Installation

### Install all services

```bash
sudo cp sbus-decoder.service      /etc/systemd/system/
sudo cp cymbal.service             /etc/systemd/system/
sudo cp cymbal-telemetry.service   /etc/systemd/system/
sudo cp cymbal-video.service       /etc/systemd/system/
sudo systemctl daemon-reload
```

### Enable at boot (recommended: sidecar mode)

```bash
sudo systemctl enable sbus-decoder cymbal-telemetry cymbal-video cymbal
```

### Enable at boot (in-process mode)

```bash
sudo systemctl enable sbus-decoder cymbal
# cymbal-telemetry and cymbal-video are not needed
```

### Start immediately

```bash
sudo systemctl start sbus-decoder
sudo systemctl start cymbal-telemetry
sudo systemctl start cymbal-video
sudo systemctl start cymbal
```

---

## Log viewing

```bash
# All cymbal services together
journalctl -u sbus-decoder -u cymbal-telemetry -u cymbal-video -u cymbal -f

# Individual service
journalctl -u cymbal -f
journalctl -u cymbal-telemetry --no-pager -n 50
journalctl -u cymbal-video --no-pager -n 50
journalctl -u sbus-decoder --no-pager -n 50

# Persistent log file (written by all services)
tail -f /var/log/cymbal.log
```

---

## Status and health checks

```bash
systemctl status sbus-decoder cymbal-telemetry cymbal-video cymbal

# Verify sockets are present once services are running
ls -l /run/cymbal/
# Expected: sbus.sock, sbus.sock.reader, telemetry.sock, telemetry.sock.reader

# Check process priorities
ps -eo pid,ni,comm | grep -E 'cymbal|sbus'
```

---

## Shutdown and restart

```bash
# Graceful shutdown (gimbals center before stopping)
sudo systemctl stop cymbal

# Restart the telemetry sidecar without stopping control
sudo systemctl restart cymbal-telemetry

# Restart video without stopping control
sudo systemctl restart cymbal-video

# Full restart in correct order
sudo systemctl restart sbus-decoder cymbal-telemetry cymbal-video cymbal
```

---

## Troubleshooting

### Control starts but telemetry shows "No fix"

1. Check telemetry sidecar is running: `systemctl status cymbal-telemetry`
2. Verify socket exists: `ls -l /run/cymbal/telemetry.sock`
3. Check telemetry logs: `journalctl -u cymbal-telemetry -n 50`
4. Verify GPS device: `ls -l /dev/ttyUSB0` and `cat /dev/ttyUSB0`
5. If `cymbal-telemetry` is not running, the control process falls back
   to in-process GPS — or check `telemetry.mode` in `config.json`.

### Video shows blank screen / no OSD

1. Check `cymbal-video` is running: `systemctl status cymbal-video`
2. Verify OpenCV is installed: `python3 -c "import cv2; print(cv2.__version__)"`
3. Verify camera device: `ls -l /dev/video0`
4. Check video mode in config: `"video": {"mode": "display"}` requires a desktop.
   Use `"headless"` for Raspberry Pi OS Lite.

### S-BUS failsafe activating unexpectedly

1. Check `sbus-decoder` is running and receiving frames: `journalctl -u sbus-decoder -f`
2. Verify RC receiver is bound and powered.
3. Check socket: `ls -l /run/cymbal/sbus.sock`
4. Reduce `sbus.frame_timeout_ms` in config if the receiver sends fast-mode frames.

### Service hits `MemoryMax` and is OOM-killed

Check `journalctl -u <service>` for `OOM` messages.  Common causes:
- `cymbal-telemetry`: SRTM tile cache growing unbounded. Set `"use_terrain_db": false`
  in config to disable terrain DB and reduce memory usage to ~128M.
- `cymbal-video`: High-resolution frames or `capture=True` test mode enabled.
  Lower `video.width` / `video.height` in config.

---

## Related documentation

- [SBUS.md](SBUS.md) — S-BUS wiring, GPIO pin assignment, and failsafe
- [CONFIGURATION.md](CONFIGURATION.md) — complete config.json reference
- [OSD.md](OSD.md) — OSD layout, compass widget, address database
- [GPS.md](GPS.md) — GPS sensor, terrain tiles, AGL altitude
- [ADR-001-native-video-pipeline.md](ADR-001-native-video-pipeline.md) — evaluation of native vs Python/OpenCV video backend
