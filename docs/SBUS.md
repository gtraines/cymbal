# S-BUS RC Signal Decoder

This document covers wiring, configuration, and operation of the S-BUS receiver
integration for the Cymbal gimbal control system.

## What is S-BUS?

S-BUS is a serial RC-receiver protocol developed by Futaba and widely supported by
FrSky, Graupner, and other manufacturers.  A single wire carries up to **16 proportional
channels** (11-bit resolution) and **2 digital channels** in a continuous 25-byte stream
at ~70 Hz.

| Parameter | Value |
|---|---|
| Baud rate | 100,000 bps |
| Frame format | 8 data bits, Even parity, 2 stop bits (8E2) |
| Frame length | 25 bytes |
| Frame period | ~14 ms (standard) / ~7 ms (fast mode) |
| Signal level | **Inverted** UART (idle = low voltage) |
| Channel value range | 0 – 2047 (11-bit), center ≈ 992 (Futaba) |

## Hardware Wiring

### Signal Inversion

S-BUS uses an **inverted UART** signal.  Cymbal handles this **in software** using
`pigpio.bb_serial_invert()`, so **no hardware inverter component is required**.

> If your RC receiver has a non-inverted "S-BUS out" pin labelled differently (e.g.
> "F.PORT" or "CRSF") you must use the standard S-BUS output pin only.

### GPIO Connection

Connect the S-BUS signal wire from your RC receiver directly to **GPIO 4 (Pin 7)**:

```
RC Receiver                 Raspberry Pi 3B+
──────────────────          ─────────────────────────
S-BUS OUT  ──────────────── GPIO 4 (Pin 7)
GND        ──────────────── GND    (Pin 6 or any GND)
+5V        ──────────────── (use external 5 V supply; do NOT power receiver from Pi)
```

> **Power note:** Do not power your RC receiver from the Pi 5 V pin — the Pi's fused
> 5 V rail is limited to ~1.5 A shared with all other peripherals.  Use the flight
> battery BEC or a dedicated 5 V regulator.

### GPIO Pin Summary

| BCM GPIO | Physical Pin | Role |
|---|---|---|
| GPIO 4 | Pin 7 | S-BUS signal input (default) |

To use a different GPIO pin change `sbus.gpio_pin` in `/etc/cymbal/config.json`.
Avoid pins already assigned: GPIO 2, 3 (I2C), 14, 15 (UART Storm32), 17, 27 (servos).

## Service Setup

The S-BUS decoder runs as a separate systemd service that must be started before
`cymbal.service`.

### Install the service

```bash
sudo cp sbus-decoder.service /etc/systemd/system/
sudo cp cymbal.service       /etc/systemd/system/   # updated version with dependency
sudo systemctl daemon-reload
sudo systemctl enable sbus-decoder
sudo systemctl enable cymbal
```

### Start / stop

```bash
sudo systemctl start  sbus-decoder
sudo systemctl status sbus-decoder
sudo systemctl stop   sbus-decoder
```

### View logs

```bash
journalctl -u sbus-decoder -f
journalctl -u cymbal -f
```

## Runtime Socket

The decoder publishes decoded channel data over a **Unix domain datagram socket**:

```
/run/cymbal/sbus.sock
```

The socket directory `/run/cymbal/` is created automatically by systemd
(`RuntimeDirectory=cymbal` in the service file).

### Payload format (48 bytes, big-endian)

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 4 | `4s` | Magic bytes `b'SBUS'` |
| 4 | 32 | `16H` | Channel values 1–16 (uint16, 0–2047 each) |
| 36 | 1 | `B` | Digital channel 17 (0 or 1) |
| 37 | 1 | `B` | Digital channel 18 (0 or 1) |
| 38 | 1 | `B` | `frame_lost` flag (0 or 1) |
| 39 | 1 | `B` | `failsafe_active` flag (0 or 1) |
| 40 | 8 | `d` | Monotonic timestamp (float, seconds) |

## Configuration Reference

All S-BUS settings live under the `sbus` key in `/etc/cymbal/config.json`:

```json
"sbus": {
  "gpio_pin":         4,
  "socket_path":      "/run/cymbal/sbus.sock",
  "failsafe_action":  "center",
  "frame_timeout_ms": 100,
  "enabled":          true
}
```

| Key | Type | Default | Description |
|---|---|---|---|
| `gpio_pin` | int | `4` | BCM GPIO pin connected to S-BUS signal |
| `socket_path` | string | `/run/cymbal/sbus.sock` | Unix socket path for IPC |
| `failsafe_action` | string | `"center"` | Action on failsafe: `"center"` only option currently |
| `frame_timeout_ms` | int | `100` | (reserved) Max ms between valid frames before warning |
| `enabled` | bool | `true` | Set `false` to disable S-BUS integration entirely |

## Channel Mapping Configuration

RC channels are mapped to gimbal functions under the `channel_map` key:

```json
"channel_map": {
  "camera_pitch":           6,
  "camera_yaw":             7,
  "spotlight_pitch":        8,
  "spotlight_yaw":          9,
  "mode_select":            5,
  "poi_lock":               10,
  "camera_pitch_range":     [-90.0, 30.0],
  "camera_yaw_range":       [-90.0, 90.0],
  "spotlight_pitch_range":  [-90.0, 30.0],
  "spotlight_yaw_range":    [-180.0, 180.0]
}
```

### Operating modes (channel 5 by default)

| Switch position | Raw value | Mode |
|---|---|---|
| Low | < 600 | **MANUAL** — channels directly set gimbal angles |
| Mid | 600 – 1400 | **STABILIZE** — IMU stabilizes; S-BUS provides trim |
| High | > 1400 | **TRACK** — GPS + POI geometry drives gimbals |

### POI lock (channel 10 by default)

A **rising edge** on the POI-lock channel (threshold 1400) captures the current GPS
position as the point-of-interest.  In TRACK mode the gimbals will then point at
that ground position continuously.

## Failsafe Behavior

When the S-BUS `failsafe_active` or `frame_lost` flags are set (e.g. RC link loss):

1. Both gimbals are immediately centered.
2. A `WARNING` message is logged to `/var/log/cymbal.log` and the systemd journal.
3. Control resumes automatically when valid frames return.

## Troubleshooting

### No frames received

```bash
# Verify pigpiod is running
sudo systemctl status pigpiod

# Confirm GPIO 4 is not already in use
gpio readall | grep "GPIO  4"

# Check the decoder service is running
sudo systemctl status sbus-decoder
journalctl -u sbus-decoder --no-pager -n 50
```

### All channels stuck at center (992)

- Check that the receiver is bound to your transmitter and powered.
- Verify the S-BUS wire is connected to GPIO 4 (not a servo rail).
- Confirm the receiver S-BUS output is the **inverted** type (standard S-BUS,
  not an uninverted variant).

### `bb_serial_read_open` error in logs

The GPIO pin may already be in use.  Check `/etc/cymbal/config.json` and ensure
`sbus.gpio_pin` does not conflict with other GPIO assignments.
